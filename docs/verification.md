# Executed verification record

Re-verified for this environment: **2026-10-19**. This record describes observed execution, not promises about untested platforms. No paid-provider result has been fabricated; the only live AI call used a **local Ollama model with no credentials or external service**.

## Environment inspected

- Workspace `/workspaces/codespaces-blank/14ai-excel-formula-verifier`; no unrelated user files modified.
- Ubuntu 24.04 (Linux 6.8, x86_64), unprivileged user, `sudo` available for installing system packages.
- Python 3.12 in a fresh `.venv` (project requires 3.11+).
- LibreOffice initially absent; installed LibreOffice Calc **24.2.7.2** (`libreoffice-calc`).
- `bubblewrap` present; its user/network namespace probe succeeded (`/health` → `engine.isolated = true`), and real calculations ran inside it.
- Ollama was already running with no models; pulled and used **`gemma:2b`** for the live-provider check.
- Docker CLI present but **not exercised** (the container is not a Docker host).

## Final commands and observed results

| Command / check | Actual result |
|---|---|
| `ruff check .` | **All checks passed** |
| `ruff format --check .` | **46 files already formatted** |
| `pytest -q -m 'not e2e' --junitxml=docs/evidence/pytest.xml` | **79 passed, 1 deselected, 1 warning in 134.96 s** (unit, deterministic property, real LibreOffice integration, API/CLI) |
| `VERIFIER_E2E=1 pytest -q -m e2e --junitxml=docs/evidence/browser-final.xml` | **1 passed, 79 deselected, 1 warning in 61.85 s** (real Chromium against the running API + dashboard) |
| `POST /evaluate` defective `=SUM(B2:B5)` | **Counterexample Found**, 2 passed / 8 failed; case 0 = 100/100, case 1 expected **107** vs actual **100**; `changes` = `B6 0→7`, `C6 0→7`; minimized pair produced |
| CLI `excel-verify evaluate --candidate '=SUM(B2:B100)+0' --cases 10` | **Passed Tested Cases**, 10 passed / 0 failed |
| `POST /runs/{id}/replay` and CLI `replay` | `{"expected":107,"actual":100,"reproduced":true}` from the saved XLSX pair |
| Report + artifact downloads | JSON/CSV/HTML reports **200**; `case_001_reference.xlsx` artifact **200**, `PK` ZIP header |
| `scripts/live_provider_smoke.py` (Ollama `gemma:2b`, opt-in) | Discovery returned `["gemma:2b"]`. Prompt 1 → `=SUMIF(Data!B2:B, ">0")` → **Syntax Error** (unbounded reference; correctly rejected). Prompt 2 → `=SUM(B2:B100)` → **Passed Tested Cases**, 10/10 |
| `python scripts/make_examples.py` | Defective **Counterexample Found** (2/8); valid **Passed Tested Cases** (10/0); example workbooks recalculated |
| Example XLSX caches inspected with `data_only=True` | case 0 pair **100/100**; case 1 **107/100**; minimized pair **77/70** |
| Browser workflow | Passed; **10 real screenshots** regenerated under `docs/images/` |

Machine-readable/log evidence: [full pytest output](evidence/pytest.txt), [JUnit cases](evidence/pytest.xml), [browser JUnit case](evidence/browser-final.xml), [live hosted provider results](evidence/live-hosted-provider.json), and the checked-in example [reports](../examples/reports/) and [workbooks](../examples/workbooks/). Direct tested dependency versions are in [`requirements-tested.txt`](../requirements-tested.txt).

## Mandatory acceptance evidence

`test_mandatory_counterexample_discovery_replay_and_valid_alternative` checks:

1. Defective `=SUM(B2:B5)` and reference `=SUM(B2:B100)` both yield 100 on the original workbook.
2. Controlled case 1 changes B6 from 0 to 7 (and mirrored C6), reference yields 107 and candidate 100.
3. Counterexample includes seed, changed cells, expected/actual, exact formulas, backend version/trust mode, first-failure signature and saved XLSX artifacts.
4. Replay executes the preserved pair again and reproduces the mismatch.
5. Bounded cell deletion produces a smaller still-failing pair (now 77 vs 70).
6. Syntactically different valid `=SUM(B2:B100)+0` passes all ten meaningful cases.

The parametrized real-calculation suite also challenges **all 19 categories** with both defective and valid formulas; every built-in defective matches its initial sample and fails a later case, and every reference agrees with its independent Python oracle. A separate test supplies a wrong reference and confirms Reference Failure rather than candidate success. Hypothesis executes real Calc SUM formulas with generated blanks, negatives and zeros.

## Live AI integration

The provider-neutral adapter was exercised end-to-end against two real providers, with evaluation of every returned formula through the real calculation engine:

**Local Ollama `gemma:2b`** (no credentials, no external service): model discovery, opt-in generation with the API's conservative controls, and evaluation. It produced an invalid formula (`Data!B2:B` is an unbounded reference) that the validator correctly classified as **Syntax Error** instead of silently evaluating it, plus a valid `=SUM(B2:B100)` that passed 10/10.

**Hosted OpenAI-compatible router** supplied by the project owner (`https://router.bynara.id/v1`, model `laguna-s-2.1`), authenticated with a server-side environment variable only (`BYNARA_API_KEY` in a gitignored `.env`; the key never enters the database, dashboard, logs, reports or screenshots). Discovery returned **44 models** including the requested `laguna-s-2.1`. A deliberately loose prompt exposed a real model habit — whole-column references (`=SUMIF(A:A,"East",B:B)`) — which the bounded-domain analysis rejects as **Syntax Error**. With the data region stated explicitly (rows 2–100, matching the benchmark task text) the model produced fully bounded formulas that passed **8/8 benchmark tasks at 10/10 cases each** (sales_total, regional, inventory, invoices, budget, dates, weighted, lookup), with recorded latency and token usage. Full evidence: [`docs/evidence/live-hosted-provider.json`](evidence/live-hosted-provider.json). The captured [`model-comparison.png`](images/model-comparison.png) shows this hosted model alongside the offline fixture.

This is genuine live evidence, not a mock. No OpenAI/Anthropic/OpenRouter vendor endpoint was contacted; those adapters remain covered by deterministic HTTPX mock transport tests.

## Browser acceptance coverage

The browser test navigates all ten sections and executes: defective-formula evaluation, expected-versus-actual inspection, saved replay, report download, valid-formula evaluation with all cases passing, provider profile save and connection test, offline-fixture comparison with the accuracy chart, real XLSX upload and API-backed preview, batch evaluation, benchmark/counterexample/history navigation and help. Ten screenshots under `docs/images/` are genuine captures from this run; the model-comparison chart now contains a **real `gemma:2b` column** alongside the offline fixture.

## Defects found and repaired during this verification

- **Missing CI workflow.** README/docs promised GitHub Actions, but `.github/workflows/` did not exist. Added `ci.yml` with lint, real-calculation integration, and live-browser jobs.
- **Playwright browser installed to root.** `sudo playwright install --with-deps` downloaded Chromium into root's cache, so the unprivileged test could not launch it. Installed the browser for the invoking user; OS libraries from `--with-deps` were kept.
- **Non-idempotent browser assertion.** Once history accumulated, `get_by_text("offline-demo")` matched many history cells and hit Playwright strict mode on Model Comparison. Scoped the assertion to the multiselect widget (a precision fix, not a weakened check).
- **Incomplete overview screenshot.** The dashboard screenshot was captured before Streamlit rendered the metric cards, saving empty skeletons. Added a wait for a real metric label so the image shows actual values.
- **Newer dependency majors.** The `>=,<` ranges resolved pandas 3.0.6, numpy 2.5.4, pydantic 2.14.1 and fastapi 0.146.0; the full suite passed unchanged, and `requirements-tested.txt` was refreshed to the versions actually executed.
- **Provider "easy connect" presets.** Added one-click protocol/Base URL/key-variable presets (OpenAI, Anthropic, OpenRouter, Ollama, custom, offline) requested for practical use, verified by the browser workflow that saves and tests a profile.

Previously repaired (retained as regression knowledge): missing `/bin` symlink in the minimal bubblewrap mount layout; a reference-failure test that assumed sales columns diverge; a malformed report CSV comprehension; Streamlit magic rendering of a multiline conditional; history not refreshed before model charts; provider usage containing nested detail dictionaries; single-quoted XML external-relationship attributes; and misdiagnosing a valid `#N/A` lookup result as a syntax error.

## What is not verified / not implemented

- No OpenAI/Anthropic/OpenRouter **vendor** endpoint was contacted by name; those adapters are protocol-tested with deterministic mocks. One hosted OpenAI-compatible third-party router was contacted live with owner-supplied credentials (see above).
- No Microsoft Excel desktop cross-engine comparison; LibreOffice Calc is the supported backend.
- No native Windows or Docker runtime execution in this environment; their files are prepared and labeled unverified.
- No public multi-tenant security certification, hostile-file parser isolation, universal formula-equivalence proof, dynamic arrays, PDF API, arbitrary imported Python oracles, distributed queue, or AI explanation-quality scoring.

**Readiness:** a single-user local application with a tested real-calculation core and offline acceptance workflows, suitable for source publication under the stated trust model. No remote repository was created or pushed; credentials and runtime data stay out of source control.
