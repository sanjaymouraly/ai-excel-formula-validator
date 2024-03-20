# REST API

Start `uvicorn app.api.main:app --host 127.0.0.1 --port 8000` from the repository root. Swagger: <http://localhost:8000/docs>. OpenAPI: <http://localhost:8000/openapi.json>. If configured, send `Authorization: Bearer <VERIFIER_API_TOKEN>` to every application endpoint. Examples below assume localhost and no configured token.

| Method | Path | Purpose |
|---|---|---|
| GET | `/health` | Engine version, isolation and trust-mode evidence |
| GET | `/benchmarks` | Complete versioned benchmark metadata |
| GET | `/benchmarks/{id}/sample` | Download sample XLSX input |
| POST | `/inspect` | Analyze `{ "formula": "=SUM(B2:B100)", "sheets": ["Data"] }` |
| POST | `/evaluate` | Synchronous evaluation request |
| POST | `/batch` | List of evaluation requests, at most 20 / 500 total cases |
| POST | `/batch/import` | Multipart `file` with JSON list or CSV rows, at most 1 MiB |
| POST | `/uploads` | Multipart `file`, macro-free XLSX up to 5 MiB |
| DELETE | `/uploads/{id}` | Delete original uploaded source |
| GET | `/runs` | Latest 1,000 run summaries, model/generation evidence |
| GET | `/runs/{id}` | Full persisted result and artifact names |
| GET | `/counterexamples` | Deduplicated first-failure signature groups |
| POST | `/runs/{id}/replay` | Recalculate the saved original failing pair |
| POST | `/runs/{id}/repair` | Substitute reference as candidate and rerun same budget/seed |
| GET | `/runs/{id}/report/{format}` | JSON, CSV or HTML report download |
| GET | `/runs/{id}/artifacts/{name}` | Download an exact listed artifact; arbitrary paths forbidden |
| DELETE | `/runs/{id}` | Delete result and saved run workbooks |
| GET | `/providers` | Profiles with environment-variable names, never key values |
| PUT | `/providers` | Validate and save ProviderProfile |
| POST | `/providers/test` | Opt-in model discovery / offline connection fixture |
| POST | `/generate` | Opt-in AI request, or explicitly labeled offline fixture |

## Evaluation

```json
{
  "benchmark": "sales_total",
  "candidate": "=SUM(B2:B5)",
  "reference": null,
  "cases": 10,
  "seed": 42,
  "atol": 1e-8,
  "rtol": 1e-7,
  "minimize": true,
  "project": "Quarterly formula regressions",
  "provider": "manual",
  "model": "manual"
}
```

`reference: null` selects the benchmark's versioned reference. Overrides for built-in tasks still must agree with that task's independent Python oracle. Cases must be 2–200; seed must be a nonnegative signed-32-bit integer. Candidate/reference formulas start with `=` and are at most 2,000 characters. Generation evidence, when provided, has `latency_seconds`, integer token-usage fields, and optional `estimated_cost_usd`.

Response includes `id`, `status`, `request`, `reference`, `benchmark_version`, `backend`, `inspection`, `passed`, `failed`, `reference_failures`, nullable `accuracy`, `latency_seconds`, per-case `expected`/`actual`/`oracle`/changes, first `counterexample`, `artifacts` and limitations. A reference failure can leave prior successfully scored case counts, but has no overall accuracy.

### Complete Python example

```python
import httpx

with httpx.Client(base_url="http://127.0.0.1:8000", timeout=240) as client:
    response = client.post(
        "/evaluate",
        json={
            "benchmark": "sales_total",
            "candidate": "=SUM(B2:B5)",
            "cases": 10,
            "seed": 42,
        },
    )
    response.raise_for_status()
    run = response.json()
    print(run["status"], run["counterexample"]["expected"], run["counterexample"]["actual"])
    replay = client.post(f"/runs/{run['id']}/replay")
    replay.raise_for_status()
    assert replay.json()["reproduced"]
    report = client.get(f"/runs/{run['id']}/report/html")
    report.raise_for_status()
    open("evaluation.html", "wb").write(report.content)
    for name in run["artifacts"]:
        evidence = client.get(f"/runs/{run['id']}/artifacts/{name}")
        evidence.raise_for_status()
        open(name, "wb").write(evidence.content)
```

## Uploaded custom workbook

Upload returns its opaque generated `id`, sheet names, bounded preview, numeric-cell choices and `execution_allowed`. No caller filename becomes a server path. Evaluate using:

```json
{
  "upload_id": "USE_THE_REAL_ID_FROM_UPLOAD",
  "sheet": "Data", "target": "H2",
  "mutation_cells": ["B2", "B3", "B6"],
  "candidate": "=SUM(B2:B5)",
  "reference": "=SUM(B2:B100)",
  "cases": 10, "seed": 42
}
```

The placeholder above is explanatory only; an actual generated ID is required. Mutation cells must be numeric inputs, not the target. The first mutation sets selected cells to zero, later mutations substitute seeded integers between -100 and 300. This flow does not insert rows or certify business semantics. Without strong isolation, evaluation is Inconclusive and execution is blocked.

## Provider profiles

```json
{
  "name": "my-compatible-provider",
  "kind": "compatible",
  "base_url": "https://your-confirmed-endpoint.example/v1",
  "key_env": "AI_API_KEY",
  "model": "YOUR_CONFIRMED_MODEL_IDENTIFIER",
  "max_tokens": 256,
  "temperature": 0,
  "timeout": 30,
  "request_limit": 20,
  "budget_usd": null,
  "input_per_million": null,
  "output_per_million": null,
  "default": true
}
```

Do not send `api_key` values in profile bodies. Set the named variable on the backend server; only the environment-variable name persists. Profiles are local trusted configuration. Remote HTTP without TLS, credential-bearing URLs, query parameters and fragments are rejected. Local Ollama HTTP is allowed.

`POST /generate` or `/providers/test`:

```json
{"provider":"my-compatible-provider","prompt":"Total revenue from B2:B100","opt_in":true}
```

Only the displayed prompt is transmitted, never an automatically attached workbook. Generation returns formula, selected model/provider, request latency, scalar token usage, estimated cost if priced, and reserved cost. A blank model triggers discovery; if unavailable, provide a confirmed identifier. Offline mode returns a clearly labeled deterministic sales reference fixture and makes no network call.

## Errors and limits

- 400: invalid/unsafe upload, unknown benchmark, provider error or bad imported specification.
- 401: API token missing/incorrect when configured.
- 404: unknown run, sample or artifact.
- 409: calculation worker busy; retry after the active run finishes.
- 422: Pydantic request validation failure.
- Engine/semantic statuses are generally HTTP 200 **result objects**, not HTTP failures. Inspect `status`.

The service uses one synchronous calculation worker. For large budgets, allow sufficient HTTP client timeout and engine wall-clock allowance. Safe generated IDs and exact artifact allowlists prevent caller-selected filesystem paths. Report CSV cells are escaped against spreadsheet formula injection; import CSV intentionally contains formulas and is a different trust boundary.
