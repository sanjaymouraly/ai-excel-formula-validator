import json

import pytest

from app.benchmarks.library import BENCHMARKS
from app.core.models import EvaluationRequest

pytestmark = pytest.mark.integration


def test_mandatory_counterexample_discovery_replay_and_valid_alternative(evaluator):
    result = evaluator.evaluate(EvaluationRequest(cases=10))
    assert result["status"] == "Counterexample Found", result.get("error")
    assert result["cases"][0]["expected"] == result["cases"][0]["actual"] == 100
    assert result["cases"][1]["expected"] == 107
    assert result["cases"][1]["actual"] == 100
    assert result["counterexample"]["changes"]["B6"] == {"before": 0, "after": 7}
    assert result["counterexample"]["minimized"]
    assert evaluator.replay(result["id"])["reproduced"] is True
    # Different syntax, same correct business result on the meaningful generated suite.
    valid = evaluator.evaluate(EvaluationRequest(candidate="=SUM(B2:B100)+0", cases=10))
    assert valid["status"] == "Passed Tested Cases", valid.get("error")
    assert valid["passed"] == 10 and valid["failed"] == 0


@pytest.mark.parametrize("benchmark", BENCHMARKS, ids=lambda b: b.id)
def test_business_categories_reference_and_defective(evaluator, benchmark):
    bad = evaluator.evaluate(
        EvaluationRequest(
            benchmark=benchmark.id, candidate=benchmark.defective, cases=5, minimize=False
        )
    )
    assert bad["status"] == "Counterexample Found", json.dumps(bad, default=str)
    assert bad["cases"][0]["passed"] is True
    assert bad["failed"] >= 1
    assert bad["reference_failures"] == 0
    good = evaluator.evaluate(
        EvaluationRequest(
            benchmark=benchmark.id, candidate=benchmark.reference, cases=5, minimize=False
        )
    )
    assert good["status"] == "Passed Tested Cases", json.dumps(good, default=str)
    assert good["passed"] == 5


def test_reference_failure_separate_and_not_scored(evaluator):
    result = evaluator.evaluate(
        EvaluationRequest(
            benchmark="wrong_column", reference="=SUM(C2:C100)", candidate="=SUM(C2:C100)", cases=3
        )
    )
    assert result["status"] == "Reference Failure"
    assert result["reference_failures"] == 1
    assert result["passed"] == 1 and result["failed"] == 0


def test_lo_syntax_failure_is_real_execution(evaluator):
    result = evaluator.evaluate(EvaluationRequest(candidate="=SUM(,)", cases=2, minimize=False))
    # Some tokenizable invalid expressions are only rejected by the engine.
    assert result["status"] in {"Syntax Error", "Counterexample Found"}


def test_valid_lookup_error_is_not_misdiagnosed_as_syntax(evaluator):
    result = evaluator.evaluate(
        EvaluationRequest(
            benchmark="lookup", candidate="=VLOOKUP(999,A2:B100,2,FALSE)", cases=3, minimize=False
        )
    )
    assert result["status"] == "Counterexample Found"
    assert all(case["actual"] == "#N/A" for case in result["cases"])
