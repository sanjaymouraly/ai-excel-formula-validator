import pytest

from app.core.analysis import analyze
from app.core.comparison import equal
from app.core.models import EvaluationRequest


@pytest.mark.parametrize(
    "formula",
    [
        "=SUM(B2:B100)",
        "=INDEX(B2:B9,MATCH(F2,A2:A9,0))",
        "='Other sheet'!$B$2+3",
        '=IF(B2>0,"yes","no")',
    ],
)
def test_tokenized_formulas(formula):
    assert not analyze(formula, ["Data", "Other sheet"])["errors"]


@pytest.mark.parametrize(
    "formula",
    [
        "SUM(A1:A2)",
        "=SUM(A1:A2",
        "=SUM([evil.xlsx]Data!A1)",
        "=cmd|' /C calc'!A0",
        "=Missing!A1",
        "=SUM(A:A)",
        "=XFE1",
        "=A0",
        "=",
    ],
)
def test_reject_invalid_or_unbounded(formula):
    assert analyze(formula, ["Data"])["errors"]


@pytest.mark.parametrize(
    "formula",
    [
        '=WEBSERVICE("https://example.com")',
        '=HYPERLINK("https://evil.com")',
        "=INDIRECT(A1)",
        "=RAND()",
        "=TODAY()",
        "=XLOOKUP(A1,B1:B5,C1:C5)",
    ],
)
def test_deny_unknown_network_and_volatile(formula):
    assert analyze(formula)["unsupported"]


def test_warnings_are_not_execution_errors():
    report = analyze("=100")
    assert report["warnings"] and not report["errors"]
    assert analyze("=SUM($B$2:B9)")["references"] == ["$B$2:B9"]


def test_type_aware_comparison():
    from datetime import datetime

    assert equal(0.1 + 0.2, 0.3)
    assert not equal(None, 0)
    assert not equal(False, 0)
    assert not equal("1", 1)
    assert equal("#DIV/0!", "#DIV/0!")
    assert not equal("#REF!", "#N/A")
    assert equal(datetime(2024, 1, 1), 45292)
    assert not equal(float("nan"), float("nan"))
    assert not equal(1.2, 1.3, atol=0, rtol=0)


def test_input_validation():
    for body in (
        {"candidate": "x"},
        {"cases": 1},
        {"cases": 10000},
        {"candidate": "=" + "A" * 2001},
    ):
        with pytest.raises(ValueError):
            EvaluationRequest(**body)
