"""Run against live API/dashboard: VERIFIER_E2E=1 pytest -m e2e.
Captures the actual interface; no screenshot data is fabricated.
"""

import os
from pathlib import Path

import httpx
import pytest
from playwright.sync_api import expect, sync_playwright

pytestmark = [
    pytest.mark.e2e,
    pytest.mark.skipif(
        os.getenv("VERIFIER_E2E") != "1", reason="Start API+dashboard and set VERIFIER_E2E=1"
    ),
]
ROOT = Path(__file__).resolve().parents[2]
IMAGES = ROOT / "docs" / "images"
BASE = os.getenv("VERIFIER_DASHBOARD_URL", "http://127.0.0.1:8501")
API = os.getenv("VERIFIER_API_URL", "http://127.0.0.1:8000")


def test_connected_dashboard_workflows():
    IMAGES.mkdir(exist_ok=True)
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True, args=["--no-sandbox"])
        page = browser.new_page(viewport={"width": 1440, "height": 1100}, device_scale_factor=1)
        page.set_default_timeout(30000)
        errors = []
        page.on("pageerror", lambda error: errors.append(str(error)))
        page.goto(BASE)
        page.get_by_text("Looks right. But does it calculate right?", exact=True).wait_for()
        # Wait for the metric cards to render real values rather than loading
        # skeletons, so the saved overview shows actual evidence.
        page.get_by_text("Benchmark scenarios", exact=True).wait_for()
        page.screenshot(path=str(IMAGES / "overview.png"))

        def navigate(label, heading=None):
            page.get_by_text(label, exact=True).first.click()
            page.get_by_role("heading", name=heading or label, exact=True).wait_for()
            expect(page.locator('[data-testid="stException"]')).to_have_count(0)

        navigate("Formula Playground")
        page.screenshot(path=str(IMAGES / "playground.png"))
        page.get_by_role("button", name="Validate formula", exact=True).click()
        page.get_by_text(
            "Counterexample Found — a plausible formula failed when the input changed.", exact=True
        ).wait_for(timeout=120000)
        page.get_by_role("heading", name="Validation results").scroll_into_view_if_needed()
        page.screenshot(path=str(IMAGES / "counterexample.png"))
        page.get_by_role("heading", name="Counterexample evidence").scroll_into_view_if_needed()
        page.screenshot(path=str(IMAGES / "expected-actual.png"))
        page.get_by_role("button", name="Replay saved counterexample", exact=True).click()
        page.get_by_text("Failure reproduced from saved XLSX inputs", exact=True).wait_for()
        page.screenshot(path=str(IMAGES / "replay.png"))
        expect(page.locator('[data-testid="stException"]')).to_have_count(0)
        with page.expect_download() as downloaded:
            page.get_by_role("button", name="Download JSON", exact=True).click()
        assert downloaded.value.suggested_filename.endswith(".json")
        page.get_by_text("Validated reference example", exact=True).click()
        page.get_by_role("button", name="Validate formula", exact=True).click()
        page.get_by_text(
            "✓ Passed Tested Cases — this is finite test evidence, not a proof of equivalence.",
            exact=True,
        ).wait_for(timeout=120000)
        page.get_by_role("heading", name="Validation results").scroll_into_view_if_needed()
        page.screenshot(path=str(IMAGES / "success.png"))

        navigate("AI Provider Settings")
        page.get_by_label("Profile name", exact=True).fill("offline-demo")
        default_checkbox = page.get_by_role("checkbox", name="Default provider", exact=True)
        if not default_checkbox.is_checked():
            page.get_by_text("Default provider", exact=True).click()
        expect(default_checkbox).to_be_checked()
        page.get_by_role("button", name="Save provider profile", exact=True).click()
        page.get_by_text("Profile saved. No secrets stored in profile.", exact=True).wait_for()
        page.get_by_role("button", name="Test connection / discover models").click()
        page.get_by_text("Connection test succeeded", exact=True).wait_for()
        page.get_by_role(
            "heading", name="AI Provider Settings", exact=True
        ).scroll_into_view_if_needed()
        page.screenshot(path=str(IMAGES / "provider-settings.png"))

        navigate("Model Comparison")
        # The saved default profile must be selected without a separate UI action.
        # Scope to the multiselect: accumulated history rows also contain the name.
        selector = page.locator('[data-testid="stMultiSelect"]')
        expect(selector.get_by_text("offline-demo", exact=True)).to_be_visible()
        expect(
            page.get_by_role("button", name="Generate and evaluate selected profiles", exact=True)
        ).to_be_enabled()
        page.get_by_role(
            "button", name="Generate and evaluate selected profiles", exact=True
        ).click()
        page.get_by_role("heading", name="Historical execution evidence").wait_for(timeout=120000)
        expect(page.locator('[data-testid="stPlotlyChart"]')).to_have_count(1, timeout=30000)
        page.locator('[data-testid="stPlotlyChart"]').scroll_into_view_if_needed()
        page.screenshot(path=str(IMAGES / "model-comparison.png"))

        navigate("Workbook Upload", "Workbook Upload & Preview")
        sample = httpx.get(API + "/benchmarks/sales_total/sample", timeout=20).content
        page.locator("input[type=file]").set_input_files(
            {
                "name": "sample.xlsx",
                "mimeType": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                "buffer": sample,
            }
        )
        page.get_by_role("button", name="Validate and preview upload").click()
        page.get_by_label("Worksheet", exact=True).wait_for()
        page.screenshot(path=str(IMAGES / "workbook-upload.png"))

        navigate("Benchmark Explorer")
        navigate("Batch Evaluation")
        page.get_by_role("button", name="Run batch", exact=True).click()
        page.get_by_text("=SUM(B2:B5) — Counterexample Found", exact=True).wait_for(timeout=120000)
        navigate("Counterexample Explorer")
        navigate("Execution History")
        page.screenshot(path=str(IMAGES / "history.png"))
        navigate("Help & Documentation")
        assert not errors, errors
        browser.close()
