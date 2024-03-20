import shutil
import tempfile
from pathlib import Path

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st
from openpyxl import Workbook

from app.engines.libreoffice import EngineError, LibreOfficeEngine

pytestmark = pytest.mark.integration


@given(st.lists(st.one_of(st.integers(-10000, 10000), st.none()), min_size=2, max_size=20))
@settings(max_examples=8, deadline=None)
def test_real_sum_agrees_with_python_on_blanks_credits_and_zeros(values):
    with tempfile.TemporaryDirectory() as directory:
        path = Path(directory)
        wb = Workbook()
        wb.active.title = "Data"
        for i, value in enumerate(values, 2):
            wb.active[f"B{i}"] = value
        wb.active["H2"] = "=SUM(B2:B100)"
        wb.save(path / "sum.xlsx")
        actual = LibreOfficeEngine().calculate(path, ["sum.xlsx"], "Data", "H2")[0]
        assert actual == sum(v for v in values if v is not None)


def test_timeout_terminates_worker_group(tmp_path, monkeypatch):
    if not shutil.which("sleep"):
        pytest.skip("POSIX timeout test requires sleep")
    script = tmp_path / "slow-engine"
    script.write_text("#!/bin/sh\nsleep 10\n")
    script.chmod(0o700)
    engine = LibreOfficeEngine()
    engine.binary = str(script)
    engine.isolated = False
    monkeypatch.setattr("app.engines.libreoffice.ENGINE_TIMEOUT", 0.1)
    with pytest.raises(EngineError, match="timeout"):
        engine.calculate(tmp_path, [], "Data", "H2")
