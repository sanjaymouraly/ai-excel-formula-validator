"""Configuration; credentials are environment-only and never serialized."""

import os
from pathlib import Path

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parents[2]
load_dotenv(ROOT / ".env", override=False)
DATA = Path(os.getenv("VERIFIER_DATA", str(ROOT / "data"))).resolve()
DATA.mkdir(parents=True, exist_ok=True)
MAX_UPLOAD = 5 * 1024 * 1024
MAX_CELLS = 20000
MAX_FORMULA = 2000
ENGINE_TIMEOUT = int(os.getenv("ENGINE_TIMEOUT", "90"))
