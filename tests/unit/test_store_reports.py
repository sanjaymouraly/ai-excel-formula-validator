import json

from app.core.models import EvaluationRequest
from app.reports.export import export


def test_persistence_and_reports(store, evaluator):
    # Rejected before execution, but still persisted and reportable.
    result = evaluator.evaluate(EvaluationRequest(candidate="=WEBSERVICE(A1)", cases=2))
    assert result["status"] == "Unsupported Function"
    assert result["accuracy"] is None
    assert store.get(result["id"])["id"] == result["id"]
    assert store.history()[0]["status"] == "Unsupported Function"
    for fmt in ("json", "csv", "html"):
        data, media = export(result, fmt)
        assert data and media
    assert json.loads(export(result, "json")[0])["status"] == "Unsupported Function"
    html = export({**result, "reference": "<script>alert('x')</script>"}, "html")[0]
    assert b"<script>" not in html
    store.remove(result["id"])
    assert store.get(result["id"]) is None


def test_csv_formula_injection():
    from app.reports.export import safe_csv

    assert safe_csv("=cmd()") == "'=cmd()"
    assert safe_csv("@SUM(A1)").startswith("'")
    assert safe_csv("normal") == "normal"


def test_default_profile_unique(store):
    store.save_profile({"name": "a", "default": True})
    store.save_profile({"name": "b", "default": True})
    assert sum(p.get("default", False) for p in store.profiles()) == 1


def test_unknown_schema_refuses_startup(tmp_path):
    import pytest
    from sqlalchemy import update
    from sqlalchemy.orm import Session

    from app.db.store import Schema, Store

    path = tmp_path / "future.sqlite3"
    store = Store(path)
    with Session(store.engine) as session:
        session.execute(update(Schema).values(version=999))
        session.commit()
    with pytest.raises(RuntimeError, match="Unsupported database schema"):
        Store(path)
