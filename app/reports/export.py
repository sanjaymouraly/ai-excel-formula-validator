import csv
import html
import io
import json


def safe_csv(value):
    # Prevent Excel formula injection when users open the report CSV.
    text = str(value) if value is not None else ""
    return "'" + text if text.startswith(("=", "+", "-", "@", "\t", "\r")) else text


def export(result, format):
    if format == "json":
        return json.dumps(result, indent=2, default=str).encode(), "application/json"
    if format == "csv":
        stream = io.StringIO()
        writer = csv.writer(stream, lineterminator="\n")
        writer.writerow(
            [
                "run",
                "benchmark",
                "candidate",
                "reference",
                "case",
                "seed",
                "expected",
                "actual",
                "passed",
                "reference_validated",
                "mutation",
            ]
        )
        for row in result["cases"]:
            writer.writerow(
                [
                    safe_csv(v)
                    for v in [
                        result["id"],
                        result["request"]["benchmark"],
                        result["request"]["candidate"],
                        result["reference"],
                        row["index"],
                        row["seed"],
                        row["expected"],
                        row["actual"],
                        row["passed"],
                        row["reference_validated"],
                        row["mutation"],
                    ]
                ]
            )
        return stream.getvalue().encode(), "text/csv"
    if format != "html":
        raise ValueError("Supported formats: json, csv, html")
    esc = lambda v: html.escape(str(v))  # noqa: E731
    rows = "".join(
        f"<tr><td>{r['index']}</td><td>{esc(r['expected'])}</td><td>{esc(r['actual'])}</td><td>{'PASS' if r['passed'] else 'FAIL'}</td><td>{esc(r['mutation'])}</td></tr>"
        for r in result["cases"]
    )
    body = f"""<!doctype html><html lang="en"><meta charset="utf-8"><title>Formula validation report</title><style>body{{font:16px system-ui;max-width:1100px;margin:48px auto;color:#173348;padding:20px}}code,pre{{background:#eef4f8;padding:12px;display:block;white-space:pre-wrap}}table{{border-collapse:collapse;width:100%}}td,th{{padding:12px;border-bottom:1px solid #ddd;text-align:left}}h1{{color:#076c65}}</style><h1>Formula validation • {esc(result["status"])}</h1><p>Run {esc(result["id"])} · seed {result["request"]["seed"]} · benchmark v{esc(result["benchmark_version"])}</p><h2>Candidate</h2><code>{esc(result["request"]["candidate"])}</code><h2>Reference</h2><code>{esc(result["reference"])}</code><p>{result["passed"]} passed / {result["passed"] + result["failed"]} scored; {result["reference_failures"]} reference failures. Unsupported or inconclusive cases are not successes.</p><table><tr><th>Case</th><th>Expected</th><th>Actual</th><th>Result</th><th>Input change</th></tr>{rows}</table><h2>Counterexample</h2><pre>{esc(json.dumps(result["counterexample"], indent=2, default=str))}</pre><h2>Execution & limitations</h2><pre>{esc(json.dumps(result["backend"], indent=2))}</pre><p>{esc(" ".join(result["warnings"]))}</p><h2>Static warnings (not execution evidence)</h2><pre>{esc(json.dumps(result["inspection"], indent=2))}</pre></html>"""
    return body.encode(), "text/html"
