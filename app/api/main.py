import csv
import io
import json
import os
import shutil
import threading
import uuid
from pathlib import Path

from fastapi import Depends, FastAPI, File, Header, HTTPException, UploadFile
from fastapi.responses import FileResponse, RedirectResponse, Response
from pydantic import BaseModel, Field

from app.benchmarks.library import BENCHMARKS, LIBRARY, generate
from app.core.analysis import analyze
from app.core.config import DATA, MAX_UPLOAD
from app.core.evaluation import Evaluator
from app.core.models import EvaluationRequest, ProviderProfile
from app.core.workbooks import validate_upload
from app.db.store import Store
from app.providers.client import ProviderClient, ProviderError, endpoint
from app.reports.export import export


def auth(authorization: str | None = Header(default=None)):
    token = os.getenv("VERIFIER_API_TOKEN")
    if token and authorization != f"Bearer {token}":
        raise HTTPException(401, "API token required")


app = FastAPI(title="AI Excel Formula Validator", version="0.1.1", dependencies=[Depends(auth)])
store = Store()
evaluator = Evaluator(store)
worker_lock = threading.Lock()


@app.exception_handler(ValueError)
async def invalid_request(_, exc):
    return Response(
        content=json.dumps({"detail": str(exc)}), status_code=400, media_type="application/json"
    )


@app.get("/", include_in_schema=False)
def root():
    return RedirectResponse("/docs")


@app.get("/health")
def health():
    return {"status": "ok", "engine": evaluator.engine.info()}


@app.get("/benchmarks")
def benchmarks():
    return [b.public() for b in BENCHMARKS]


@app.get("/benchmarks/{key}/sample")
def sample(key: str):
    if key not in LIBRARY:
        raise HTTPException(404, "Unknown benchmark")
    path = DATA / f"sample-{key}.xlsx"
    wb = generate(key, 42, 0).workbook()
    wb["Data"][LIBRARY[key].target] = LIBRARY[key].reference
    wb.save(path)
    return FileResponse(path, filename=f"{key}.xlsx")


@app.post("/inspect")
def inspect_formula(body: dict):
    return analyze(str(body.get("formula", "")), body.get("sheets", ["Data", "Rates"]))


def perform(body):
    if not worker_lock.acquire(blocking=False):
        raise HTTPException(409, "Calculation worker is busy; retry after the current run")
    try:
        return evaluator.evaluate(body)
    finally:
        worker_lock.release()


@app.post("/evaluate")
def evaluate(body: EvaluationRequest):
    return perform(body)


@app.post("/batch")
def batch(body: list[EvaluationRequest]):
    if not 1 <= len(body) <= 20 or sum(r.cases for r in body) > 500:
        raise HTTPException(400, "Batch limit: 20 formulas / 500 total cases")
    return [perform(r) for r in body]


@app.post("/batch/import")
async def import_batch(file: UploadFile = File(...)):
    data = await file.read(1024 * 1024 + 1)
    if len(data) > 1024 * 1024:
        raise ValueError("Import exceeds 1 MiB")
    try:
        rows = (
            json.loads(data)
            if file.filename.endswith(".json")
            else list(csv.DictReader(io.StringIO(data.decode())))
        )
        requests = [EvaluationRequest(**r) for r in rows]
    except (ValueError, TypeError) as exc:
        raise ValueError("Invalid batch JSON/CSV; use EvaluationRequest fields") from exc
    return batch(requests)


@app.post("/uploads")
async def upload(file: UploadFile = File(...)):
    if not file.filename or not file.filename.lower().endswith(".xlsx"):
        raise ValueError("Only macro-free .xlsx files are supported")
    content = await file.read(MAX_UPLOAD + 1)
    wb = validate_upload(content)
    key = uuid.uuid4().hex
    directory = DATA / "uploads"
    directory.mkdir(exist_ok=True)
    # Re-serialize a macro-free workbook. Never use the caller's filename as a path.
    wb.save(directory / f"{key}.xlsx")
    previews = {
        ws.title: [
            [str(c.value) if c.data_type == "f" else c.value for c in row]
            for row in ws.iter_rows(max_row=min(20, ws.max_row), max_col=min(12, ws.max_column))
        ]
        for ws in wb
    }
    numeric = {
        ws.title: [
            c.coordinate
            for row in ws
            for c in row
            if isinstance(c.value, (int, float)) and not isinstance(c.value, bool)
        ]
        for ws in wb
    }
    return {
        "id": key,
        "sheets": wb.sheetnames,
        "preview": previews,
        "numeric_cells": numeric,
        "execution_allowed": evaluator.engine.isolated,
    }


@app.delete("/uploads/{key}")
def delete_upload(key: str):
    if not key.isalnum() or len(key) != 32:
        raise ValueError("Invalid upload id")
    (DATA / "uploads" / f"{key}.xlsx").unlink(missing_ok=True)
    return {"deleted": True}


@app.get("/counterexamples")
def counterexamples():
    return store.counterexamples()


@app.get("/runs")
def runs():
    return store.history()


@app.get("/runs/{run_id}")
def run(run_id: str):
    result = store.get(run_id)
    if not result:
        raise HTTPException(404, "Run not found")
    return result


@app.post("/runs/{run_id}/replay")
def replay(run_id: str):
    with worker_lock:
        return evaluator.replay(run_id)


@app.post("/runs/{run_id}/repair")
def repair(run_id: str):
    old = run(run_id)
    req = EvaluationRequest(
        **{
            **old["request"],
            "candidate": old["reference"],
            "reference": old["reference"],
            "provider": "reference-repair",
            "model": "deterministic",
        }
    )
    repaired = perform(req)
    return {
        "original_id": run_id,
        "repair": repaired,
        "notice": "Reference substitution, not an independently generated AI repair",
    }


@app.get("/runs/{run_id}/report/{format}")
def report(run_id: str, format: str):
    content, media = export(run(run_id), format)
    return Response(
        content,
        media_type=media,
        headers={"Content-Disposition": f'attachment; filename="evaluation.{format}"'},
    )


@app.get("/runs/{run_id}/artifacts/{name}")
def artifact(run_id: str, name: str):
    result = run(run_id)
    if name not in result["artifacts"] or Path(name).name != name:
        raise HTTPException(404, "Artifact not found")
    return FileResponse(DATA / "runs" / run_id / name, filename=name)


@app.delete("/runs/{run_id}")
def remove(run_id: str):
    run(run_id)
    store.remove(run_id)
    shutil.rmtree(DATA / "runs" / run_id, ignore_errors=True)
    return {"deleted": True}


@app.get("/providers")
def providers():
    return store.profiles()


@app.put("/providers")
def save_provider(body: ProviderProfile):
    if body.kind != "offline":
        endpoint(body)
    store.save_profile(body.model_dump())
    return {"saved": body.name, "key_configured": bool(os.getenv(body.key_env))}


class Generation(BaseModel):
    provider: str
    prompt: str = Field(default="Sum revenue B2:B100", max_length=12000)
    opt_in: bool = False


def profile(name):
    p = store.profile(name)
    if not p:
        raise ProviderError("Provider profile not found")
    return ProviderProfile(**p)


@app.post("/providers/test")
def test_provider(body: Generation):
    p = profile(body.provider)
    return {
        "models": ProviderClient(store).models(p, body.opt_in),
        "notice": "Model discovery only; no formula request charged by this application",
    }


@app.post("/generate")
def generate_formula(body: Generation):
    return ProviderClient(store).generate(profile(body.provider), body.prompt, body.opt_in)
