# Contributing

1. Read README.md, SECURITY.md and docs/architecture.md.
2. Create a virtualenv and install `pip install -e '.[dev]'`; install LibreOffice Calc and bubblewrap on Linux.
3. Make a small focused change with a meaningful regression test. Never replace real calculation with hardcoded expected outputs or accept unsupported cases as successes.
4. Run:
   ```bash
   ruff check .
   ruff format --check .
   pytest -q -m 'not e2e'
   # Start API and dashboard, then:
   VERIFIER_E2E=1 pytest -q -m e2e
   ```
5. For benchmarks, independently review the business oracle, bump task versions when semantics change, and regenerate the catalog/examples with `python scripts/make_examples.py`.
6. For provider changes, use deterministic HTTPX transport tests. Live smoke tests are optional and must never expose credentials or fabricate model availability/costs.
7. Update documentation and changelog. Screenshots must come from the running application using Playwright, never UI artwork or stock images.
8. Keep `.env`, private workbooks, generated runtime databases, caches and provider responses outside Git. Checked-in examples must use synthetic non-sensitive data only.

Pull requests should state which commands actually ran, their outcomes, engine/runtime versions, and any untested platforms or external dependencies. Do not suppress meaningful warnings or weaken failing assertions to create a green check. Discuss reference/oracle corrections explicitly; formulas must be tested against unchanged business expectations where possible.

The project is MIT licensed. Contributions are accepted under the same license. Repository publication and remote pushes require the owner's authorization; no remote repository is created automatically.
