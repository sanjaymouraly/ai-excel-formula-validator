"""Bounded CI readiness probe, not a substitute for process supervision."""

import time
from urllib.request import urlopen

for url in ["http://127.0.0.1:8000/health", "http://127.0.0.1:8501/_stcore/health"]:
    deadline = time.monotonic() + 45
    while True:
        try:
            with urlopen(url, timeout=2) as response:
                assert response.status == 200
            break
        except (OSError, AssertionError):
            if time.monotonic() > deadline:
                raise RuntimeError(f"Service did not become healthy: {url}") from None
            time.sleep(0.5)
    print(f"Ready: {url}")
