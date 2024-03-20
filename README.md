# AI-Generated Excel Formula Validator

Validates AI-generated Excel formulas by parsing, testing, and checking them against workbook data.

## Features

- Token-based formula inspection using openpyxl's tokenizer; bounded A1 references, missing-sheet checks, hardcoded-constant warnings and a calculation-function allowlist.
- 19 versioned business benchmarks, each with a deterministic generator, deliberately misleading sample, defective formula, description and independent Python reference oracle.
- Boundary, adversarial, expansion and seeded random cases. Budgets of 10, 50, 100 or 200 cases; configurable seed and numerical tolerances through REST.
- Type-aware scalar comparison: booleans are not numbers, blank is not zero, strings/errors compare exactly, dates/times normalize, floating-point tolerances are explicit.
- Counterexample XLSX downloads, reproducible replay, bounded greedy cell deletion for selected additive benchmarks, failure-signature grouping and deterministic reference-substitution repair followed by retesting.
- XLSX upload validation/preview; isolated execution on explicitly selected numeric input mutations. Custom references are clearly labeled as not independently certified.
- Batch JSON/CSV requests, saved project labels, SQLite history, and downloadable JSON, CSV and escaped self-contained HTML reports.

## Stack

Python, FastAPI, Uvicorn, Streamlit, openpyxl, Pydantic, SQLAlchemy, pandas, NumPy, Plotly

## Clone

```bash
git clone https://github.com/sanjaymouraly/ai-excel-formula-validator.git
cd ai-excel-formula-validator
```

## Setup

```bash
# The project ships a Docker Compose setup.
docker compose up --build
```

See `docs/` or the compose file for environment variables and ports.

## Run

```bash
docker compose up --build
```

## Tests

```bash
pytest -q
```

## Notes

- Sample data, when included, is synthetic.

## License

MIT © 2024 [Sanjay Mouraly](https://github.com/sanjaymouraly)
