# Troubleshooting

## Engine not installed / Inconclusive

`which libreoffice` (Linux) or `Get-Command soffice` (PowerShell) must succeed. Install LibreOffice Calc and add its `program` folder to PATH on Windows. Restart the API after changing PATH. openpyxl is not a fallback calculation engine.

## Upload preview works, but execution is blocked

Inspect `/health` → `engine.isolated`. Upload execution requires bubblewrap plus permitted unprivileged user namespaces. Docker/Ubuntu/AppArmor policies can deny them even when the binary exists. Preview remains available; built-in trusted generated inputs can still run. Do not disable the gate, run as root, use privileged Docker or globally weaken kernel security to accept hostile files. Use an appropriately administered Linux worker environment.

## Cannot reach API from the dashboard

Start both terminals. The dashboard server uses `VERIFIER_API_URL`; in Compose this must be `http://api:8000`, not browser localhost. With a bearer token, set exactly the same `VERIFIER_API_TOKEN` on API and dashboard. Start from the repository root or keep `.env` at that location. The UI loads the repository `.env` automatically without overriding exported variables.

## HTTP 409, slow calculation or timeout

One API calculation runs at a time. Finish or retry the active request. A ten-case run writes twenty input workbooks plus any minimization trials; budgets up to 200 can take longer on slow disks. Increase ENGINE_TIMEOUT deliberately, or use fewer cases. Timeout kills the worker process group on Linux and yields Inconclusive, not a pass. Do not launch multiple API workers; generation budget/admission controls are single-worker local controls.

## Reference Failure

Inspect `oracle`, `expected`, benchmark version and backend version. For built-in tasks, a custom reference must still agree with the independent business-rule oracle. Do not “fix” the failure by comparing the candidate against the same wrong reference. Review business rules, generator and Calc compatibility. Partial earlier case counts are visible; the run has no overall accuracy score.

## Unsupported formula / Syntax Error

Read `inspection.errors` and `inspection.unsupported`. Use bounded A1 ranges rather than full columns or named/structured references. Unsupported functions are deliberately rejected. Token inspection is not a complete grammar: a tokenizable formula can still produce a Calc error during execution. `#N/A` or `#VALUE!` is not by itself proof of malformed syntax; it can be a real data-dependent result.

## Provider connection or discovery fails

- Confirm Base URL includes the documented version prefix, but not `/chat/completions` or `/messages` itself.
- Put only the **key environment variable name** in the profile, not the key value.
- Restart backend after changing `.env`; a subscription or browser login is not API access.
- Discovery requires opt-in and endpoint support. Supply a model ID confirmed by your provider when it lacks discovery.
- Ollama localhost means the API server's machine/container. Docker cannot reach host Ollama through container localhost; configure an explicitly reachable trusted host endpoint and its firewall appropriately.
- HTTP 429/502/503 retries are bounded with exponential backoff. Raw provider bodies and authorization values are not included in errors.
- Lifetime generation limits include failed/reserved attempts. No automatic refund is applied. A budget without supplied prices is intentionally refused. Use a new explicitly named profile only when you intend a new separate budget; these controls are not a provider-wide billing ledger.

## Browser tests do not start

Run `python -m playwright install --with-deps chromium`. This downloads the browser and installs system libraries. The first attempt in the development environment failed because libatk was absent; installing dependencies fixed the actual browser launch. Start API and dashboard before `VERIFIER_E2E=1 pytest -m e2e`.

Native Windows: use PowerShell environment syntax. Browser UI tests are designed around current Streamlit accessible labels and may need updating for future major UI changes; do not weaken functional assertions to make them pass.

## SQLite schema error / backups

Stop services and copy the entire private data directory before any upgrade. Version 1 rejects unknown schema versions. No destructive auto-upgrade is attempted. Wait for a reviewed version-specific migration rather than deleting tables or editing the version row. Run deletion removes only the selected run and its evidence; upload-source deletion is separate. Historical replay remains possible from preserved failing pairs even if the original uploaded source was deleted, but rerunning the entire upload evaluation requires its source.

## Report shows unfamiliar run ID

Checked-in example reports contain actual IDs from the environment where examples were generated. They are evidence files, not database seeds. Run `python scripts/make_examples.py` to create new current IDs/artifacts locally. JSON/HTML may contain private business values; protect exports. CSV reports escape formula-injection characters, while batch CSV is an intentional formula-input specification.

## Known dependency warning

The installed Starlette version emits a TestClient deprecation warning recommending httpx2. Tests use the currently functioning HTTPX-compatible TestClient interface and were run with the warning visible; it is not suppressed or counted as a failure. Reassess/pin compatible versions before a future dependency upgrade.
