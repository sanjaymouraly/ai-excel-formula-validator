import io
import json

import pytest
from fastapi.testclient import TestClient
from openpyxl import Workbook
from typer.testing import CliRunner

from app.api.main import app
from app.cli.main import app as cli

client = TestClient(app)
pytestmark = pytest.mark.integration


def test_health_inspection_validation_and_not_found():
    assert client.get("/health").json()["engine"]["version"].startswith("LibreOffice")
    assert len(client.get("/benchmarks").json()) == 19
    assert client.post("/inspect", json={"formula": "=SUM(B2:B100)"}).json()["references"]
    assert client.post("/evaluate", json={"cases": 0}).status_code == 422
    assert client.get("/runs/does-not-exist").status_code == 404


def test_api_counterexample_exports_replay_repair_delete():
    result = client.post("/evaluate", json={"cases": 3, "minimize": False}).json()
    assert result["status"] == "Counterexample Found", result
    key = result["id"]
    assert client.get(f"/runs/{key}").json()["id"] == key
    assert client.post(f"/runs/{key}/replay").json()["reproduced"]
    for fmt in ("json", "csv", "html"):
        response = client.get(f"/runs/{key}/report/{fmt}")
        assert response.status_code == 200 and len(response.content) > 100
    for name in result["artifacts"]:
        assert client.get(f"/runs/{key}/artifacts/{name}").content.startswith(b"PK")
    repair = client.post(f"/runs/{key}/repair").json()
    assert repair["repair"]["status"] == "Passed Tested Cases"
    assert client.delete(f"/runs/{key}").json()["deleted"]
    assert client.get(f"/runs/{key}").status_code == 404


def test_workbook_upload_preview_execution_and_delete():
    wb = Workbook()
    wb.active.title = "Data"
    wb.active.append(["Item", "Revenue"])
    for i in range(5):
        wb.active.append([f"Item {i}", 0 if i == 4 else 25])
    stream = io.BytesIO()
    wb.save(stream)
    response = client.post("/uploads", files={"file": ("sample.xlsx", stream.getvalue())})
    assert response.status_code == 200, response.text
    upload = response.json()
    assert upload["sheets"] == ["Data"] and "B6" in upload["numeric_cells"]["Data"]
    body = {
        "upload_id": upload["id"],
        "sheet": "Data",
        "target": "H2",
        "mutation_cells": ["B6"],
        "candidate": "=SUM(B2:B5)",
        "reference": "=SUM(B2:B100)",
        "cases": 3,
        "minimize": False,
    }
    result = client.post("/evaluate", json=body).json()
    if upload["execution_allowed"]:
        assert result["status"] == "Counterexample Found", result
        assert all(not r["reference_validated"] for r in result["cases"])
    else:
        assert result["status"] == "Inconclusive"
    assert client.delete(f"/uploads/{upload['id']}").status_code == 200
    assert (
        client.post("/uploads", files={"file": ("bad.xlsm", stream.getvalue())}).status_code == 400
    )
    assert client.post("/uploads", files={"file": ("bad.xlsx", b"bad")}).status_code == 400


def test_provider_configuration_offline_and_batch_import():
    assert (
        client.put(
            "/providers", json={"name": "offline-test", "kind": "offline", "default": True}
        ).status_code
        == 200
    )
    assert any(p["name"] == "offline-test" for p in client.get("/providers").json())
    assert client.post("/providers/test", json={"provider": "offline-test"}).json()["models"] == [
        "offline-reference-demo"
    ]
    generated = client.post("/generate", json={"provider": "offline-test"}).json()
    assert generated["formula"] == "=SUM(B2:B100)"
    for filename, data in [
        ("tasks.json", json.dumps([{"candidate": "=SUM(B2:B100)", "cases": 2}])),
        ("tasks.csv", 'candidate,cases\n"=SUM(B2:B5)",2\n'),
    ]:
        response = client.post("/batch/import", files={"file": (filename, data)})
        assert response.status_code == 200, response.text
        assert response.json()[0]["status"] in {"Passed Tested Cases", "Counterexample Found"}


def test_cli_smoke_and_export(tmp_path):
    runner = CliRunner()
    assert runner.invoke(cli, ["benchmarks"]).exit_code == 0
    output = tmp_path / "report.json"
    result = runner.invoke(cli, ["evaluate", "--cases", "3", "--output", str(output)])
    assert result.exit_code == 0, result.output
    report = json.loads(output.read_text())
    assert report["status"] == "Counterexample Found"
    replay = runner.invoke(cli, ["replay", report["id"]])
    assert replay.exit_code == 0 and '"reproduced": true' in replay.output


def test_api_authentication(monkeypatch):
    monkeypatch.setenv("VERIFIER_API_TOKEN", "test-secret")
    assert client.get("/health").status_code == 401
    assert client.get("/health", headers={"Authorization": "Bearer test-secret"}).status_code == 200
