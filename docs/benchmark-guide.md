# Benchmark and regression guide

The source of truth is `app/benchmarks/library.py`. `benchmarks/catalog.json` is an export, not executable Python or an independent parser. Regenerate it and example evidence with `python scripts/make_examples.py`.

## Built-in categories

| IDs | Business-rule oracle / hidden issue |
|---|---|
| `sales_total`, `wrong_column`, `hardcoded` | Python sum; omitted final row, coincidentally equal columns, literal answer |
| `aggregation`, `weighted` | Python arithmetic/weighted mean; SUM versus AVERAGE and unequal weights |
| `regional` | Filtered Python sum; wrong region condition |
| `discount_tax` | Quantity × price, discount and tax with multi-sheet input |
| `profit` | Net margin and zero-revenue handling |
| `inventory` | Stock threshold count; inclusive/exclusive boundary |
| `payroll` | Row-three hours × fixed F2 rate; incorrectly copied relative reference |
| `delivery` | Supplier and delivery-day conditions, exact five-day boundary |
| `invoices` | Invoices less payments, including credits |
| `budget` | Actual minus budget; reversed sign |
| `lookup`, `index_match` | First exact match or missing; duplicates, absent and reordered keys |
| `dates` | Python date interval; January 31 included, February 1/year boundaries excluded |
| `negatives` | Net sum including credits, blanks and zero |
| `nested_if` | Inclusive numeric thresholds at 50 and 100 |
| `errors` | Preserve division-by-zero error, not silently replace with zero |

Each Benchmark contains identity, version, task text, difficulty, reference, deliberately defective formula, target and documented failure mechanism. The public representation includes schema, expected behavior and generation strategy. The common workbook has Data columns A–D, parameter F2 and result H2 (H3 for payroll); Rates!B2 holds tax.

Case 0 is deliberately misleading. Case 1 is a controlled adversarial input. Later cases are seeded random data or task-specific small boundary domains. Expansion tasks grow to up to 20 rows while references cover through row 100. More cases do not guarantee more unique inputs for fixed-domain tasks. These are correctness challenges, not a statistical estimate of all spreadsheet use.

## Ten hidden-bug scenarios

1. Omitted last SUM row initially zero: `sales_total`.
2. Wrong column initially equal: `wrong_column`.
3. Hardcoded original answer: `hardcoded`.
4. Incorrect copied absolute reference: `payroll` evaluates the copy-down formula at H3 with changing F3.
5. SUM and AVERAGE agree on initial all-zero sample: `aggregation`.
6. Approximate lookup versus exact first match under reordered/duplicate/missing keys: `lookup`, `index_match`.
7. Ignored refunds/blanks/new records: `negatives`, `sales_total`.
8. Bad month-end/year-boundary conditions: `dates`.
9. Wrong aggregation condition initially balanced: `regional`.
10. Small workbook passes but expanded rows fail: `sales_total`, `wrong_column` and bounded-range manual candidates.

## Add a reviewed independently certified task

1. Add a `Benchmark` entry with a new ID, clear schema/intention, valid reference and a genuinely misleading defective example.
2. Add generation/business logic to `generate()`. Derive the oracle from Python business operations, never from formula text or cached worksheet values. Do not use eval, execute imported Python or call the candidate as an oracle.
3. Ensure both formulas match the baseline, but a controlled mutation exposes the defect. Cover blanks, boundaries, signs, duplicates and expansion where relevant.
4. Add domain-specific tests as needed. The parametrized real-engine suite automatically challenges every built-in reference/defective pair, but review the oracle independently.
5. If correcting a formula, schema or data-generation contract, increment the task version and explain the correction in CHANGELOG.md. Preserve regression fixtures for the original bug.
6. Run unit/property tests, real LibreOffice integration tests, rebuild examples/catalog and check that the exported metadata matches the code.

Separate review matters: reference and oracle could share the same mistaken business interpretation. Neither this tool nor finite testing can certify an ambiguous natural-language task universally.

## Custom workbooks and reusable requests

Beginners can upload an XLSX and supply a reference without writing a generator. This is **relative differential validation**, not independent certification. Choose numeric input cells; output formula cells cannot be mutation inputs. Reference and candidate see the same numeric substitutions. Arbitrary uploaded Python oracles, dynamic arrays and macros are not accepted.

Batch imports are lists/CSV rows of REST `EvaluationRequest` fields. Use `examples/batch.json` or `examples/batch.csv`, modify formulas/seed/cases/project and import in Batch Evaluation. These are reusable evaluation specifications referencing built-ins, or a local upload ID; exported upload IDs are not portable without the original local source. To add a completely new independently certified generator, use the reviewed code extension above.

## Regression workflow

Save a project label, pin benchmark versions in your external release manifest, keep seed/budget, and rerun the same request list after changing model, prompt, formula or reference. History compares observed execution evidence; do not treat increased case budgets or repeated fixed-domain inputs as fair model sample sizes. First-failure signatures group duplicates without discarding original XLSX evidence. A built-in reference failure invalidates that run's overall accuracy and requires investigation before any model conclusion.
