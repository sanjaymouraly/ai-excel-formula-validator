"""Rebuild all checked-in examples using the actual calculation backend."""

import json
import shutil
import tempfile
from pathlib import Path

from app.benchmarks.library import BENCHMARKS, generate
from app.core.config import DATA, ROOT
from app.core.evaluation import Evaluator
from app.core.models import EvaluationRequest
from app.reports.export import export


def main():
    (ROOT / "benchmarks" / "catalog.json").write_text(
        json.dumps([b.public() for b in BENCHMARKS], indent=2) + "\n"
    )
    evaluator = Evaluator()
    bad = evaluator.evaluate(EvaluationRequest(cases=10))
    good = evaluator.evaluate(EvaluationRequest(candidate="=SUM(B2:B100)+0", cases=10))
    assert bad["status"] == "Counterexample Found" and good["status"] == "Passed Tested Cases"
    assert evaluator.replay(bad["id"])["reproduced"]
    for name, result in (("counterexample", bad), ("valid-formula", good)):
        for fmt in ("json", "csv", "html"):
            (ROOT / "examples" / "reports" / f"{name}.{fmt}").write_bytes(export(result, fmt)[0])
    with tempfile.TemporaryDirectory() as directory:
        work = Path(directory)
        for name in bad["artifacts"]:
            shutil.copy(DATA / "runs" / bad["id"] / name, work / name)
        evaluator.engine.calculate(work, bad["artifacts"], "Data", "H2")
        for name in bad["artifacts"]:
            shutil.copy(work / "out" / name, ROOT / "examples" / "workbooks" / name)
    # Useful additional domain sample files; these are inputs, not claimed calculated caches.
    for key in ("dates", "lookup", "payroll", "discount_tax"):
        wb = generate(key, 42, 1).workbook()
        task = next(b for b in BENCHMARKS if b.id == key)
        wb["Data"][task.target] = task.reference
        wb.save(ROOT / "examples" / "workbooks" / f"{key}-input.xlsx")
    print(
        json.dumps(
            {
                "defective": {k: bad[k] for k in ("id", "status", "passed", "failed")},
                "valid": {k: good[k] for k in ("id", "status", "passed", "failed")},
            },
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
