"""Single-user Streamlit dashboard. All calculation/persistence goes through REST."""

import hmac
import json
import os
from pathlib import Path

import httpx
import pandas as pd
import plotly.express as px
import streamlit as st
from dotenv import load_dotenv

load_dotenv(Path(__file__).resolve().parents[2] / ".env", override=False)

API = os.getenv("VERIFIER_API_URL", "http://127.0.0.1:8000").rstrip("/")
TOKEN = os.getenv("VERIFIER_API_TOKEN", "")

st.set_page_config(page_title="FormulaLens • Excel Validator", page_icon="🔎", layout="wide")
st.markdown(
    """<style>
.stApp {background:#f6f8fb} [data-testid=stSidebar]{background:#102b3b}
[data-testid=stSidebar] *{color:#e5eff6} [data-testid=stSidebar] input{color:#142b3c}
h1,h2,h3{color:#15394b!important;letter-spacing:-.035em}
[data-testid=stMetric]{background:white;border:1px solid #e1e8ee;border-radius:12px;padding:18px}
.hero{background:linear-gradient(115deg,#143d50,#0b6e69);border-radius:18px;padding:30px 36px;color:white;margin:8px 0 24px}
.hero h1{color:white!important;font-size:2.35rem}.hero p{color:#d8ebe9;margin-bottom:0}
.eyebrow{font-size:12px;font-weight:700;letter-spacing:.17em;color:#86d9cb}
.stButton>button[kind=primary]{background:#087f75;border:0;border-radius:8px}
code{color:#096b63} [data-testid=stDataFrame]{background:white;border-radius:10px}
</style>""",
    unsafe_allow_html=True,
)


def api(method, path, **kwargs):
    try:
        response = httpx.request(
            method,
            API + path,
            headers={"Authorization": f"Bearer {TOKEN}"} if TOKEN else {},
            timeout=240,
            **kwargs,
        )
        if response.status_code >= 400:
            try:
                detail = response.json().get("detail", "Request failed")
            except ValueError:
                detail = "Request failed"
            st.error(f"API {response.status_code}: {detail}")
            return None
        return response
    except httpx.RequestError:
        st.error("Cannot reach API. Start: uvicorn app.api.main:app --host 0.0.0.0 --port 8000")
        return None


def get(path):
    response = api("GET", path)
    return response.json() if response else None


def post(path, body):
    response = api("POST", path, json=body)
    return response.json() if response else None


def download(path, label, filename, key=None):
    response = api("GET", path)
    if response:
        st.download_button(label, response.content, file_name=filename, key=key)


def show_result(result, compact=False):
    st.session_state["last_result"] = result
    st.subheader("Validation results")
    status = result["status"]
    if status == "Passed Tested Cases":
        st.success(f"✓ {status} — this is finite test evidence, not a proof of equivalence.")
    elif status == "Counterexample Found":
        st.error("Counterexample Found — a plausible formula failed when the input changed.")
    else:
        st.warning(status)
    if result.get("error"):
        st.error(result["error"])
    cols = st.columns(4)
    cols[0].metric("Passed cases", result["passed"])
    cols[1].metric("Failed cases", result["failed"])
    denominator = result["passed"] + result["failed"]
    cols[2].metric(
        "Execution accuracy",
        f"{result['accuracy']:.0%}" if result["accuracy"] is not None else "Not scored",
        f"{denominator} scored cases",
        delta_color="off",
    )
    cols[3].metric("Calculation time", f"{result['latency_seconds']} s")
    a, b = st.columns(2)
    with a:
        st.caption("CANDIDATE FORMULA")
        st.code(result["request"]["candidate"], language="excel")
    with b:
        st.caption(
            "VALIDATED REFERENCE"
            if not result["request"]["upload_id"]
            else "USER REFERENCE • NO INDEPENDENT ORACLE"
        )
        st.code(result["reference"], language="excel")
    if result["cases"]:
        frame = pd.DataFrame(result["cases"])
        view = frame[
            ["index", "expected", "actual", "passed", "reference_validated", "mutation"]
        ].copy()
        for column in ("expected", "actual"):
            view[column] = view[column].astype(str)
        st.dataframe(
            view,
            hide_index=True,
            width="stretch",
            column_config={
                "passed": st.column_config.CheckboxColumn("Passed"),
                "reference_validated": st.column_config.CheckboxColumn("Oracle checked"),
            },
        )
    failure = result.get("counterexample")
    if failure:
        st.subheader("Counterexample evidence")
        st.write(failure["explanation"])
        c1, c2, c3 = st.columns(3)
        c1.metric("Expected", str(failure["expected"]))
        c2.metric("Actual", str(failure["actual"]))
        c3.metric("Reproducible case", f"#{failure['index']} · seed {failure['seed']}")
        changes = [
            {"Cell": k, "Before": str(v["before"]), "After": str(v["after"])}
            for k, v in failure["changes"].items()
        ]
        st.dataframe(pd.DataFrame(changes), hide_index=True, width="stretch")
        if failure.get("minimized"):
            st.info(
                "A smaller failing workbook was produced by bounded greedy cell deletion. The minimized reference was re-executed; its business oracle was not independently recomputed."
            )
        left, right = st.columns(2)
        if left.button("Replay saved counterexample", key=f"replay-{result['id']}"):
            with st.spinner("Recalculating the preserved workbook pair…"):
                replay = post(f"/runs/{result['id']}/replay", {})
                if replay:
                    if replay["reproduced"]:
                        st.success("Failure reproduced from saved XLSX inputs")
                    else:
                        st.error("Replay did not reproduce")
                    st.json(replay)
        if right.button("Retest suggested correction", key=f"repair-{result['id']}"):
            with st.spinner("Running reference substitution against the same test budget…"):
                repair = post(f"/runs/{result['id']}/repair", {})
                if repair:
                    st.session_state["repair_result"] = repair["repair"]
                    st.success(
                        f"Correction: {repair['repair']['status']} ({repair['repair']['passed']} passed)"
                    )
        with st.expander("Download original and minimized failing workbooks"):
            for name in result["artifacts"]:
                download(
                    f"/runs/{result['id']}/artifacts/{name}", name, name, key=result["id"] + name
                )
    with st.expander("Static analysis • references, warnings and engine limitations"):
        st.caption("Tokenized references (not a claim of semantic correctness)")
        st.code(" · ".join(result["inspection"]["references"]) or "No references")
        st.json(result["inspection"])
        st.json(result["backend"])
        for warning in result["warnings"]:
            st.caption(warning)
    with st.expander("Download evaluation report", expanded=not compact):
        cols = st.columns(3)
        for col, fmt in zip(cols, ("json", "csv", "html")):
            with col:
                download(
                    f"/runs/{result['id']}/report/{fmt}",
                    f"Download {fmt.upper()}",
                    f"evaluation-{result['id'][:8]}.{fmt}",
                    key=f"{result['id']}-{fmt}",
                )


with st.sidebar:
    st.markdown("## 🔎 FormulaLens")
    st.caption("AI EXCEL FORMULA VALIDATOR")
    page = st.radio(
        "Workspace",
        [
            "Overview",
            "Formula Playground",
            "Workbook Upload",
            "Benchmark Explorer",
            "AI Provider Settings",
            "Model Comparison",
            "Batch Evaluation",
            "Counterexample Explorer",
            "Execution History",
            "Help & Documentation",
        ],
        label_visibility="collapsed",
    )
    st.divider()
    st.caption("REAL CALCULATION · REPRODUCIBLE EVIDENCE")
    st.caption("Offline-ready. No AI subscription required.")

password = os.getenv("VERIFIER_DASHBOARD_PASSWORD", "")
if password and not st.session_state.get("authenticated"):
    st.title("FormulaLens • Sign in")
    entered = st.text_input("Dashboard password", type="password")
    if st.button("Sign in", type="primary"):
        if hmac.compare_digest(entered, password):
            st.session_state["authenticated"] = True
            st.rerun()
        else:
            st.error("Incorrect dashboard password")
    st.stop()

health = get("/health")
if not health:
    st.stop()
benchmarks = get("/benchmarks") or []
library = {b["id"]: b for b in benchmarks}
history = get("/runs") or []

if page == "Overview":
    st.markdown(
        '<div class="hero"><div class="eyebrow">TRUST EVIDENCE, NOT PLAUSIBILITY</div><h1>Looks right. But does it calculate right?</h1><p>Challenge AI-generated Excel formulas with changing data.<br>Discover the workbook that proves a hidden bug.</p></div>',
        unsafe_allow_html=True,
    )
    cols = st.columns(4)
    cols[0].metric("Benchmark scenarios", len(benchmarks))
    cols[1].metric("Saved evaluations", len(history))
    cols[2].metric(
        "Counterexamples found", sum(r["status"] == "Counterexample Found" for r in history)
    )
    cols[3].metric(
        "Calculation backend",
        "LibreOffice",
        "Network isolated" if health["engine"]["isolated"] else "Trusted inputs only",
        delta_color="off",
    )
    a, b = st.columns([1.2, 1])
    with a:
        st.subheader("A correct sample can hide an incorrect formula")
        st.write(
            "The initial sales workbook totals 100. Its final row contains zero, so `=SUM(B2:B5)` appears correct. Change B6 to 7: the reference returns 107, but the candidate still returns 100."
        )
        st.code(
            "Reference   =SUM(B2:B100)\nCandidate   =SUM(B2:B5)\nMutation    B6: 0 → 7\nEvidence    Expected 107 ≠ Actual 100"
        )
        if st.button("Run hidden-bug demonstration", type="primary"):
            with st.spinner(
                "Generating workbooks, validating the oracle, calculating both formulas…"
            ):
                result = post("/evaluate", {"cases": 10})
                if result:
                    st.session_state["demo_result"] = result
    with b:
        st.subheader("Evidence-first workflow")
        st.markdown(
            "**01 · Inspect**\n\nTokenize references and flag unsupported features.\n\n**02 · Challenge**\n\nCalculate on boundary cases, adversarial inputs and seeded mutations.\n\n**03 · Reproduce**\n\nInspect changed cells, replay the failure and export real XLSX evidence."
        )
    if st.session_state.get("demo_result"):
        show_result(st.session_state["demo_result"])
    elif history:
        st.subheader("Recent evaluations")
        st.dataframe(pd.DataFrame(history[:5]), hide_index=True, width="stretch")

elif page == "Formula Playground":
    st.title("Formula Playground")
    st.caption("Same inputs. Independent reference oracle. Real spreadsheet calculation.")
    key = st.selectbox("Benchmark task", list(library), format_func=lambda k: library[k]["title"])
    task = library[key]
    st.info(task["description"])
    mode = st.radio(
        "Formula source",
        ["Deliberately defective example", "Validated reference example", "Manual / AI-generated"],
        horizontal=True,
    )
    default = task["reference"] if mode == "Validated reference example" else task["defective"]
    candidate = st.text_area(
        "Candidate formula", default, key=f"candidate-{key}-{mode}", height=100
    )
    with st.expander("Reference formula & task intention"):
        reference = st.text_input("Reference formula", task["reference"], key=f"ref-{key}")
        st.text_area(
            "Intended calculation (notes; not used as an oracle)",
            task["description"],
            key=f"notes-{key}",
        )
    cols = st.columns(4)
    cases = cols[0].selectbox("Testing budget", [10, 50, 100, 200])
    seed = cols[1].number_input("Random seed", 0, 2147483647, 42)
    project = cols[2].text_input("Saved project", "Default")
    minimize = cols[3].checkbox("Minimize counterexample", True)
    if st.button("Validate formula", type="primary"):
        with st.spinner(f"Calculating {cases} independent workbook pairs; this may take a minute…"):
            result = post(
                "/evaluate",
                {
                    "benchmark": key,
                    "candidate": candidate,
                    "reference": reference,
                    "cases": cases,
                    "seed": seed,
                    "project": project,
                    "minimize": minimize,
                },
            )
            if result:
                st.session_state["playground_result"] = result
    if st.session_state.get("playground_result"):
        show_result(st.session_state["playground_result"])

elif page == "Workbook Upload":
    st.title("Workbook Upload & Preview")
    st.write(
        "Macro-free XLSX only · 5 MiB · 20 sheets · 20,000 used cells. Upload content is never sent to AI providers by this workflow."
    )
    file = st.file_uploader("Choose XLSX workbook", type=["xlsx"])
    if file and st.button("Validate and preview upload"):
        response = api(
            "POST",
            "/uploads",
            files={
                "file": (
                    file.name,
                    file.getvalue(),
                    "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                )
            },
        )
        if response:
            st.session_state["upload"] = response.json()
    upload = st.session_state.get("upload")
    if upload:
        sheet = st.selectbox("Worksheet", upload["sheets"])
        st.dataframe(
            pd.DataFrame(upload["preview"][sheet]).astype(str), hide_index=True, width="stretch"
        )
        if not upload["execution_allowed"]:
            st.warning(
                "Strong worker isolation unavailable: preview works, upload execution is disabled."
            )
        st.warning(
            "Uploaded references have no independent business-rule oracle. Results establish agreement with your reference only."
        )
        target = st.text_input("Target cell", "H2")
        ref = st.text_input("Your validated reference", "=SUM(B2:B100)")
        candidate = st.text_input("Candidate formula", "=SUM(B2:B5)")
        cells = st.multiselect(
            "Numeric input cells to mutate (do not select output cells)",
            upload["numeric_cells"][sheet],
            default=upload["numeric_cells"][sheet][:10],
        )
        if st.button(
            "Evaluate uploaded workbook",
            disabled=not upload["execution_allowed"] or not cells,
            type="primary",
        ):
            with st.spinner("Calculating isolated upload mutations…"):
                result = post(
                    "/evaluate",
                    {
                        "upload_id": upload["id"],
                        "sheet": sheet,
                        "target": target,
                        "mutation_cells": cells,
                        "reference": ref,
                        "candidate": candidate,
                        "cases": 10,
                    },
                )
                if result:
                    st.session_state["upload_result"] = result
        if st.session_state.get("upload_result"):
            show_result(st.session_state["upload_result"])
        if st.button("Delete uploaded source workbook"):
            if api("DELETE", f"/uploads/{upload['id']}"):
                del st.session_state["upload"]
                st.rerun()

elif page == "Benchmark Explorer":
    st.title("Benchmark Explorer")
    st.write("Versioned, reproducible business tasks with independent reference oracles.")
    category = st.selectbox("Category", ["All"] + sorted({b["category"] for b in benchmarks}))
    filtered = [b for b in benchmarks if category == "All" or b["category"] == category]
    st.dataframe(
        pd.DataFrame(filtered)[["id", "title", "category", "difficulty", "version"]],
        hide_index=True,
        width="stretch",
    )
    key = st.selectbox("Explore benchmark", [b["id"] for b in filtered])
    task = library[key]
    st.subheader(task["title"])
    st.write(task["description"])
    st.code(task["reference"], language="excel")
    st.warning(task["failure"])
    st.json({k: task[k] for k in ("schema", "expected_behavior", "generator", "version")})
    download(f"/benchmarks/{key}/sample", "Download sample workbook", f"{key}.xlsx")

elif page == "AI Provider Settings":
    st.title("AI Provider Settings")
    st.info(
        "A ChatGPT subscription is not OpenAI API access and does not include API credentials or billing. Never provide browser cookies or session tokens."
    )
    st.write(
        "API keys stay in server environment variables, outside the database and browser. Set the variable before starting the backend. This screen never accepts or reveals secret values."
    )
    profiles = get("/providers") or []
    presets = {
        "Offline demo (no API, no cost)": {
            "kind": "offline",
            "base_url": "",
            "key_env": "AI_API_KEY",
        },
        "OpenAI API (ChatGPT API key)": {
            "kind": "openai",
            "base_url": "https://api.openai.com/v1",
            "key_env": "AI_API_KEY",
        },
        "Anthropic Claude API": {
            "kind": "anthropic",
            "base_url": "https://api.anthropic.com/v1",
            "key_env": "ANTHROPIC_API_KEY",
        },
        "OpenRouter": {
            "kind": "openrouter",
            "base_url": "https://openrouter.ai/api/v1",
            "key_env": "OPENROUTER_API_KEY",
        },
        "Ollama (local, no key)": {
            "kind": "ollama",
            "base_url": "http://localhost:11434",
            "key_env": "AI_API_KEY",
        },
        "Custom OpenAI-compatible endpoint": {
            "kind": "compatible",
            "base_url": "",
            "key_env": "AI_API_KEY",
        },
    }
    kinds = ["offline", "compatible", "openai", "anthropic", "openrouter", "ollama"]
    field_defaults = {
        "f_name": "offline-demo",
        "f_kind": "offline",
        "f_base": "",
        "f_env": "AI_API_KEY",
        "f_model": "",
        "f_default": False,
        "f_tokens": 256,
        "f_limit": 20,
        "f_budget": 0.0,
        "f_iprice": 0.0,
        "f_oprice": 0.0,
        "f_temp": 0.0,
        "f_timeout": 30.0,
    }

    def load_profile():
        chosen = next((p for p in profiles if p["name"] == st.session_state["profile_choice"]), {})
        st.session_state.update(
            {
                key: chosen.get(attr, default)
                for key, (attr, default) in {
                    "f_name": ("name", "offline-demo"),
                    "f_kind": ("kind", "offline"),
                    "f_base": ("base_url", ""),
                    "f_env": ("key_env", "AI_API_KEY"),
                    "f_model": ("model", ""),
                    "f_default": ("default", False),
                    "f_tokens": ("max_tokens", 256),
                    "f_limit": ("request_limit", 20),
                    "f_budget": ("budget_usd", 0.0),
                    "f_iprice": ("input_per_million", 0.0),
                    "f_oprice": ("output_per_million", 0.0),
                    "f_temp": ("temperature", 0.0),
                    "f_timeout": ("timeout", 30.0),
                }.items()
            }
        )
        st.session_state["f_budget"] = float(st.session_state["f_budget"] or 0)
        st.session_state["f_iprice"] = float(st.session_state["f_iprice"] or 0)
        st.session_state["f_oprice"] = float(st.session_state["f_oprice"] or 0)
        st.session_state["f_temp"] = float(st.session_state["f_temp"] or 0)
        st.session_state["f_timeout"] = float(st.session_state["f_timeout"] or 30)

    def apply_preset():
        preset = presets[st.session_state["preset"]]
        st.session_state["f_kind"] = preset["kind"]
        st.session_state["f_base"] = preset["base_url"]
        st.session_state["f_env"] = preset["key_env"]

    if "profile_choice" not in st.session_state:
        st.session_state["profile_choice"] = "New profile"
    for field, default in field_defaults.items():
        st.session_state.setdefault(field, default)
    st.selectbox(
        "Configuration profile",
        ["New profile"] + [p["name"] for p in profiles],
        key="profile_choice",
        on_change=load_profile,
    )
    st.selectbox(
        "Quick connect preset (fills protocol, Base URL and key variable)",
        list(presets),
        key="preset",
        on_change=apply_preset,
    )
    with st.form("provider", clear_on_submit=False):
        a, b = st.columns(2)
        name = a.text_input("Profile name", key="f_name")
        kind = b.selectbox("Provider protocol", kinds, key="f_kind")
        base = a.text_input(
            "AI Base URL",
            key="f_base",
            help="OpenAI https://api.openai.com/v1; Anthropic https://api.anthropic.com/v1; OpenRouter https://openrouter.ai/api/v1; Ollama http://localhost:11434",
        )
        env = b.text_input("API Key • server environment variable name", key="f_env")
        model = a.text_input("Model identifier (optional: discover automatically)", key="f_model")
        default = b.checkbox("Default provider", key="f_default")
        tokens = a.number_input("Maximum output tokens", 32, 4096, key="f_tokens")
        limit = b.number_input("Lifetime request limit per profile", 1, 10000, key="f_limit")
        budget = a.number_input("Spending budget USD (0 = disabled)", 0.0, 10000.0, key="f_budget")
        iprice = a.number_input(
            "Input price / million tokens (0 if unknown)", 0.0, 10000.0, key="f_iprice"
        )
        oprice = b.number_input(
            "Output price / million tokens (0 if unknown)", 0.0, 10000.0, key="f_oprice"
        )
        temperature = b.slider("Temperature", 0.0, 2.0, key="f_temp")
        timeout = b.number_input("Timeout seconds", 1.0, 120.0, key="f_timeout")
        save = st.form_submit_button("Save provider profile", type="primary")
    if save:
        response = api(
            "PUT",
            "/providers",
            json={
                "name": name,
                "kind": kind,
                "base_url": base,
                "key_env": env,
                "model": model,
                "max_tokens": tokens,
                "request_limit": limit,
                "budget_usd": budget or None,
                "input_per_million": iprice or None,
                "output_per_million": oprice or None,
                "temperature": temperature,
                "timeout": timeout,
                "default": default,
            },
        )
        if response:
            st.success("Profile saved. No secrets stored in profile.")
    opt_in = st.checkbox("Allow outbound connection test to this configured endpoint", False)
    if st.button("Test connection / discover models"):
        tested = post("/providers/test", {"provider": name, "opt_in": opt_in})
        if tested:
            st.success("Connection test succeeded")
            st.json(tested)
    st.caption(
        "Discoverable models are sorted by identifier; the first is selected if none is specified. Confirm suitability for your task. Budgets conservatively reserve maximum cost; retries and failed attempts may still be billed externally."
    )

elif page == "Model Comparison":
    st.title("Model Comparison")
    st.caption(
        "Execution correctness only. Explanation quality is not scored. Offline fixtures are labeled, never presented as live model results."
    )
    profiles = get("/providers") or []
    selected = st.multiselect(
        "Provider/model profiles to compare",
        [p["name"] for p in profiles],
        default=[p["name"] for p in profiles if p.get("default")],
    )
    key = st.selectbox("Shared benchmark", list(library))
    prompt = st.text_area(
        "Natural-language task sent to selected providers",
        library[key]["description"]
        + " Schema: Data!A group/key/date; B amount; C cost/weight; F2 parameter. Result H2.",
    )
    opt_in = st.checkbox(
        "I permit sending this prompt to the selected third-party providers", False
    )
    if st.button("Generate and evaluate selected profiles", disabled=not selected, type="primary"):
        results = []
        progress = st.progress(0, text="Starting model comparison")
        for i, name in enumerate(selected):
            generated = post("/generate", {"provider": name, "prompt": prompt, "opt_in": opt_in})
            if generated:
                result = post(
                    "/evaluate",
                    {
                        "benchmark": key,
                        "candidate": generated["formula"],
                        "provider": name,
                        "model": generated["model"],
                        "cases": 10,
                        "generation": {
                            k: generated[k]
                            for k in ("latency_seconds", "usage", "estimated_cost_usd")
                        },
                    },
                )
                if result:
                    results.append(result)
            progress.progress(
                (i + 1) / len(selected), text=f"Completed {i + 1}/{len(selected)} profiles"
            )
        st.session_state["comparison_results"] = results
        history = get("/runs") or []
    rows = []
    for run in history:
        if run["provider"] != "manual":
            rows.append(run)
    if rows:
        frame = pd.DataFrame(rows)
        frame["scored_cases"] = frame.passed + frame.failed
        frame["accuracy"] = frame.passed.div(frame.scored_cases.replace(0, float("nan"))).where(
            frame.status.isin(["Passed Tested Cases", "Counterexample Found", "Syntax Error"])
        )
        st.subheader("Historical execution evidence")
        st.dataframe(frame, hide_index=True, width="stretch")
        scored = frame[
            (frame.scored_cases > 0)
            & frame.status.isin(["Passed Tested Cases", "Counterexample Found", "Syntax Error"])
        ]
        if not scored.empty:
            # Weighted case-level accuracy; retain task identity, no arbitrary score.
            grouped = scored.groupby(["provider", "model", "benchmark"], as_index=False)[
                ["passed", "failed"]
            ].sum()
            grouped["accuracy"] = grouped.passed / (grouped.passed + grouped.failed)
            figure = px.bar(
                grouped,
                x="model",
                y="accuracy",
                color="benchmark",
                barmode="group",
                hover_data=["provider", "passed", "failed"],
                title="Passed cases / scored cases • grouped by task",
            )
            figure.update_layout(
                yaxis_range=[0, 1], paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="white"
            )
            st.plotly_chart(figure, width="stretch")
    else:
        st.info(
            "No model evaluations yet. Create an offline profile to try the connected workflow free, or configure real providers."
        )
    for result in st.session_state.get("comparison_results", []):
        with st.expander(f"{result['request']['provider']} • {result['status']}"):
            show_result(result, compact=True)

elif page == "Batch Evaluation":
    st.title("Batch Evaluation")
    st.write(
        "Import reusable evaluation requests from JSON or CSV. Max 20 formulas / 500 total cases. Each row uses the same REST request fields."
    )
    example = [
        {"benchmark": "sales_total", "candidate": "=SUM(B2:B5)", "cases": 10},
        {"benchmark": "sales_total", "candidate": "=SUM(B2:B100)", "cases": 10},
    ]
    text = st.text_area("JSON evaluation requests", json.dumps(example, indent=2), height=230)
    file = st.file_uploader("Or import JSON / CSV", type=["json", "csv"])
    if st.button("Run batch", type="primary"):
        with st.spinner("Processing workbook pairs…"):
            if file:
                response = api(
                    "POST", "/batch/import", files={"file": (file.name, file.getvalue())}
                )
                results = response.json() if response else None
            else:
                try:
                    results = post("/batch", json.loads(text))
                except ValueError:
                    st.error("Invalid JSON")
                    results = None
            if results:
                st.session_state["batch_results"] = results
    for result in st.session_state.get("batch_results", []):
        with st.expander(f"{result['request']['candidate']} — {result['status']}"):
            show_result(result, compact=True)

elif page in {"Counterexample Explorer", "Execution History"}:
    st.title(page)
    if page == "Counterexample Explorer":
        groups = get("/counterexamples") or []
        if groups:
            st.caption(
                "Identical first-failure signatures are grouped; original runs and evidence are preserved."
            )
            frame = pd.DataFrame(groups).drop(columns=["run_ids"])
            # Expected/actual mix ints, text and error strings; cast to text so the
            # table serializes cleanly instead of tripping Arrow type inference.
            for column in ("expected", "actual"):
                if column in frame:
                    frame[column] = frame[column].astype(str)
            st.dataframe(frame, hide_index=True, width="stretch")
    projects = sorted({r["project"] for r in history})
    project = st.selectbox("Project", ["All projects"] + projects)
    filtered = [r for r in history if project == "All projects" or r["project"] == project]
    if page == "Counterexample Explorer":
        filtered = [r for r in filtered if r["status"] == "Counterexample Found"]
    if not filtered:
        st.info(
            "No saved evaluations in this view. Start in Formula Playground or run the hidden-bug demo."
        )
    else:
        st.dataframe(pd.DataFrame(filtered), hide_index=True, width="stretch")
        key = st.selectbox(
            "Inspect saved run",
            [r["id"] for r in filtered],
            format_func=lambda k: next(
                f"{r['benchmark']} · {r['status']} · {r['id'][:8]}"
                for r in filtered
                if r["id"] == k
            ),
        )
        result = get(f"/runs/{key}")
        if result:
            show_result(result)
        confirmed = st.checkbox("Confirm permanent deletion of this run and its workbooks")
        if st.button("Delete run", disabled=not confirmed):
            if api("DELETE", f"/runs/{key}"):
                st.rerun()

else:
    st.title("Help & Documentation")
    st.markdown("""### Quick start
1. Open **Formula Playground** and choose a benchmark.
2. Validate the deliberately defective example with 10 cases.
3. Inspect expected versus actual values and the changed cells.
4. Replay the counterexample and download the failing XLSX pair.
5. Retest the reference correction or enter your own alternative formula.

### What does a pass mean?
**Passed Tested Cases** means agreement on the specified generated inputs, not mathematical equivalence. Unknown/unsupported functions and infrastructure failures are never counted as successes. Reference-oracle failures stop scoring the case.

### Supported domain
Scalar A1 formulas; bounded ranges; SUM/AVERAGE, conditional aggregations, INDEX/MATCH, exact VLOOKUP, IF logic, dates and multi-sheet references. Percentages and currency are numeric values; formatting is not business semantics. Dynamic array spills, macros, external data, full-column/structured references and volatile functions are excluded.

### Custom tasks and regression projects
Upload a workbook and supply a trusted reference plus numeric mutation cells. Save a project label and export JSON evaluation requests for batch regression. Upload references are not independently certified. Built-in benchmark definitions and Python oracles live in `app/benchmarks/library.py` and are versioned together.

### Privacy and trust model
Uploads never go to AI services automatically. Only explicit prompts in Model Comparison are sent after opt-in. Keys are configured in the backend environment, never the UI. This is a **single-user local tool**, not a multi-tenant hosted service. Add an API token and a TLS/authentication reverse proxy before sharing it.

### Execution engine
openpyxl writes and inspects files; **LibreOffice actually calculates**. A network-disabled bubblewrap worker uses read-only runtime mounts, a private writable work directory, timeouts and resource limits. When unavailable, only trusted generated workbooks may execute. Results may differ from Microsoft Excel, especially around date systems, floating point, lookup ordering and newer functions.

See the repository README and `docs/` for API, Windows/Linux setup, Docker and troubleshooting.
""")
    st.json(health["engine"])
