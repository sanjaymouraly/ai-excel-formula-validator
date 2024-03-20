import os
import tempfile

# Keep tests out of the user's history, including imported API module globals.
TEST_DATA = tempfile.TemporaryDirectory(prefix="verifier-test-data-")
os.environ["VERIFIER_DATA"] = TEST_DATA.name

import pytest  # noqa: E402

from app.core.evaluation import Evaluator  # noqa: E402
from app.db.store import Store  # noqa: E402


@pytest.fixture
def store(tmp_path):
    return Store(tmp_path / "test.sqlite3")


@pytest.fixture
def evaluator(store):
    return Evaluator(store)
