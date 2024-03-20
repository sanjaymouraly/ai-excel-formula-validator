# Architecture and correctness contract

## Calculation pipeline

1. Pydantic bounds formulas, case counts, seeds and tolerances. The tokenizer and reference allowlist enforce a deliberately small scalar formula domain. Static findings are not execution failures.
2. The selected versioned benchmark creates a baseline, a controlled boundary case, then seeded random or additional adversarial cases. Some boundary-focused tasks intentionally repeat a small domain. Case `i` uses `seed + i * 100003`.
3. Independent Python code calculates expected business values from generated inputs, without interpreting the reference formula. Reference and candidate are written at the **same cell of separate, identical input workbooks**. They cannot influence each other's intermediate calculations.
4. A fresh headless LibreOffice profile recalculates the complete file pair. openpyxl reads results only from the newly produced output files, not from untrusted input caches. An engine process exit without all expected output files is an infrastructure failure.
5. Reference output must agree with the business oracle before that case is scored. If it fails, scoring stops with Reference Failure, not a candidate failure. Uploaded custom references have no independent oracle, are labeled accordingly and score relative agreement only.
6. Type-aware comparison checks exact text, booleans, error strings and blank identity, and finite numeric values under supplied absolute/relative tolerances. Dates/times normalize to serial values. Currency/percentage formatting does not create a separate arithmetic type.
7. The first failing input pair, original sample pair and optional reduced pair are saved. Original input artifacts are sufficient for replay without trusting random generator stability across future releases.
8. SQLite stores request/configuration, backend version/trust mode, benchmark version, case values/changes, first failure signature, statistics and optional generation evidence. JSON/CSV/HTML exports use the same stored payload.

## Main boundaries

| Module | Responsibility |
|---|---|
| `core/analysis.py` | Tokenized function and A1 reference checks; not a full Excel semantic parser |
| `benchmarks/library.py` | Versioned task, generator and independent Python business logic |
| `engines/libreoffice.py` | Real calculation and isolated subprocess lifecycle |
| `core/evaluation.py` | Identical-input pairs, oracle gate, comparison, artifacts, minimization, replay |
| `providers/client.py` | Opt-in HTTP adapters, discovery, retries, redacted errors and reservations |
| `db/store.py` | Explicit-version SQLite storage and failure grouping |
| `reports/export.py` | Deterministic JSON, safe report CSV and escaped standalone HTML |
| `api/main.py` | REST interface, bounded uploads, worker admission and provider profiles |
| `ui/dashboard.py` | Server-side API client and presentation, no calculation shortcuts |
| `cli/main.py` | Local service invocation for evaluation and replay |

## Isolation and concurrency

The Linux worker runs as the invoking unprivileged user with bubblewrap user/network/PID namespaces, no capabilities, read-only runtime mounts, private `/tmp` and a single writable work directory. Host homes, app data and provider keys are not mounted or inherited. `prlimit` bounds CPU time (60 seconds), address space (2 GiB), file size (50 MiB) and open files (256). The configurable wall-clock limit terminates the process group. Address-space and CPU limits are inherited per process, not a cgroup-wide aggregate. See SECURITY.md for the remaining threat model and Docker aggregate controls.

The API uses one worker and a nonblocking calculation lock; simultaneous evaluations return HTTP 409. Batch work is synchronous and bounded to 20 formulas / 500 total cases, not a distributed queue. Replay waits for the same lock. Separate CLI processes do not share admission control. Multiple API workers are not supported for budget accounting/admission consistency. SQLite uses transactions and a 30-second busy timeout.

When user namespaces or bubblewrap are absent, untrusted uploads cannot calculate. Restricted formulas over locally generated benchmark inputs can run in explicitly labeled trusted-input fallback mode. A plain subprocess is never called a security sandbox.

## Result semantics

- **Passed Tested Cases:** all scored generated inputs agreed. Not proof of equivalence.
- **Counterexample Found:** at least one reference-valid input returned a differing candidate value, including a legitimate spreadsheet error result. Error cells alone do not prove syntax errors.
- **Syntax Error:** static token/reference/domain validation rejected the candidate. Some valid-but-disallowed reference forms are also reported here; see the concrete inspection errors.
- **Unsupported Function:** a function is not in the supported allowlist or is volatile.
- **Reference Failure:** a built-in reference disagreed with its oracle, or reference analysis failed. Partial prior case counts remain visible, but overall accuracy is null.
- **Inconclusive:** missing engine, isolation unavailable for upload, timeout or other supported infrastructure failure. Never a successful evaluation.

Numerical case accuracy is `passed / (passed + failed)`. It is null for unsupported, reference-failure and inconclusive evaluations. The model chart excludes these evaluations. Grouped chart denominators are sums of scored cases for each task, provider and model. These are not statistically independent model predictions: one generated formula is challenged with many inputs. No explanation-quality or arbitrary blended score is produced.

## Minimization and repair

Selected additive benchmarks attempt two greedy chunks of numeric input-cell deletion. Each trial executes reference and candidate again and is accepted only if a non-error reference still differs. This can yield a smaller witness but is not exhaustive delta debugging or a globally minimal workbook. The minimized oracle is not independently recomputed; original independently checked evidence is retained.

Repair is transparent reference substitution followed by automatic retesting at the original seed/budget. It is not claimed as an independently AI-generated correction. Failure signatures group identical first-failure evidence without deleting original runs. They include task/reference/candidate, changed cells and expected/actual values.

## Schema upgrade strategy

Schema version 1 is created only when absent. Unknown version rows cause startup refusal; there is no destructive automatic migration. This is intentionally an explicit safe strategy for the initial release. Back up the entire private data directory while services are stopped. A future migration must provide a reviewed transactional upgrade script, a prior-version fixture and round-trip tests before changing the version. Do not delete tables to “fix” a version mismatch. Provider keys are never database columns; profiles store environment-variable names only.

## Extension points

Evaluator accepts injected store/engine objects; alternative engines must implement `info()` and `calculate(workdir, filenames, sheet, target, trusted)` with equivalent provenance and isolation guarantees. ProviderClient accepts an HTTPX transport for deterministic protocol tests. Add reviewed benchmark generators/oracles as described in benchmark-guide.md; never accept Python code from imported task specifications.
