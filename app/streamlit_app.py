"""SignBridge Streamlit demo.

Renders a patient-intake form on the left and the orchestrator's activity log
+ final pre-visit Markdown brief on the right. Talks to the IRIS-side
SignBridge.Orchestrator via the MCP HTTP endpoint at /mcp/signbridge.

Run on the host (after `docker compose up -d --build` for the iris service):

    pip install -r app/requirements.txt
    streamlit run app/streamlit_app.py
"""

from __future__ import annotations

import asyncio
import base64
import json
import os
import re
from typing import Any

import streamlit as st
from langchain_mcp_adapters.client import MultiServerMCPClient

# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------

DEFAULT_MCP_URL = os.environ.get("SIGNBRIDGE_MCP_URL", "http://localhost:8080/mcp/signbridge")
DEFAULT_USER = os.environ.get("SIGNBRIDGE_USER", "SuperUser")
DEFAULT_PASS = os.environ.get("SIGNBRIDGE_PASS", "SYS")

SIGN_STYLES = ["ASL", "BSL", "PSL", "Chinese", "Singaporean", "Malay", "Other"]

# Three demo prompts the judges can drive in one click.
DEMO_PRESETS: dict[str, dict[str, Any]] = {
    "Routine — mild asthma (ESI 4 expected)": {
        "patient_id": None,
        "chief_complaint": "wheezing and shortness of breath",
        "duration": "since this morning",
        "age": 34,
        "sex": "F",
        "sign_style": "ASL",
        "known_conditions": ["asthma"],
        "current_meds": ["albuterol inhaler", "fluticasone inhaler"],
        "free_text": "Used inhaler twice today. No fever. Peak flow about 75% of personal best.",
    },
    "Red-flag — chest pain in diabetic (ESI 1 expected)": {
        "patient_id": None,
        "chief_complaint": "chest pain radiating to left arm",
        "duration": "2 hours",
        "age": 58,
        "sex": "M",
        "sign_style": "BSL",
        "known_conditions": ["type 2 diabetes", "hypertension"],
        "current_meds": ["metformin 1000mg BID", "lisinopril 20mg"],
        "free_text": "Crushing pressure, sweaty, nauseated. No nitroglycerin tried. Pain not relieved at rest.",
    },
    "History-driven — dizziness in elderly patient": {
        "patient_id": None,
        "chief_complaint": "dizziness on standing",
        "duration": "since this morning",
        "age": 71,
        "sex": "F",
        "sign_style": "PSL",
        "known_conditions": ["hypertension"],
        "current_meds": ["amlodipine 10mg", "hydrochlorothiazide 25mg"],
        "free_text": "Light-headed when getting up. No chest pain, no headache, no vision change. Has felt off-balance the past two days.",
    },
}

# ---------------------------------------------------------------------------
# MCP client
# ---------------------------------------------------------------------------


@st.cache_resource(show_spinner=False)
def _get_event_loop() -> asyncio.AbstractEventLoop:
    """Persistent event loop so MCP connections survive across Streamlit reruns."""
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    return loop


def _auth_header(user: str, password: str) -> str:
    raw = f"{user}:{password}".encode()
    return "Basic " + base64.b64encode(raw).decode()


async def _list_tools(url: str, auth: str) -> list[Any]:
    client = MultiServerMCPClient(
        {
            "signbridge": {
                "transport": "http",
                "url": url,
                "headers": {"Authorization": auth},
            }
        }
    )
    return await client.get_tools()


async def _invoke_process_intake(url: str, auth: str, intake: dict) -> dict:
    client = MultiServerMCPClient(
        {
            "signbridge": {
                "transport": "http",
                "url": url,
                "headers": {"Authorization": auth},
            }
        }
    )
    tools = await client.get_tools()
    target = None
    for t in tools:
        # Tool names are namespaced like 'mcp_signbridge_ProcessIntake'.
        if t.name.endswith("ProcessIntake"):
            target = t
            break
    if target is None:
        raise RuntimeError(
            f"ProcessIntake tool not discovered. Tools available: {[t.name for t in tools]}"
        )
    raw = await target.ainvoke({"intakeJson": json.dumps(intake)})
    if isinstance(raw, str):
        try:
            return json.loads(raw)
        except json.JSONDecodeError:
            return {"ok": False, "error": "Non-JSON response", "brief": raw}
    return raw


def run_async(coro):
    loop = _get_event_loop()
    return loop.run_until_complete(coro)


# ---------------------------------------------------------------------------
# Render helpers
# ---------------------------------------------------------------------------


def split_activity_and_brief(content: str) -> tuple[list[str], str]:
    """Pull `> step ...` lines out of the orchestrator output and return (activity, brief).

    The orchestrator INSTRUCTIONS direct it to emit `> step N: ...` lines before
    every tool call and then the final Markdown brief. We split on those lines.
    """
    activity = []
    brief_lines = []
    for line in content.splitlines():
        stripped = line.lstrip()
        if stripped.startswith(">") and not brief_lines:
            activity.append(stripped[1:].strip())
        else:
            brief_lines.append(line)
    brief = "\n".join(brief_lines).strip()
    # Strip leading code fence if the model wrapped the brief.
    brief = re.sub(r"^```(?:markdown)?\s*", "", brief)
    brief = re.sub(r"\s*```$", "", brief)
    return activity, brief


def esi_badge(brief_md: str) -> str | None:
    """Pull `ESI N` out of the brief for a quick visual badge."""
    m = re.search(r"ESI\s*(\d)", brief_md)
    return f"ESI {m.group(1)}" if m else None


# ---------------------------------------------------------------------------
# Streamlit UI
# ---------------------------------------------------------------------------

st.set_page_config(page_title="SignBridge — Pre-Visit Triage", layout="wide")

st.title("SignBridge")
st.caption(
    "Agentic pre-visit triage for deaf patients. "
    "Built on InterSystems IRIS AI Hub — orchestrator + four specialist sub-agents + FastEmbed RAG, "
    "exposed over MCP."
)

with st.sidebar:
    st.header("Connection")
    mcp_url = st.text_input("MCP endpoint", value=DEFAULT_MCP_URL)
    mcp_user = st.text_input("IRIS user", value=DEFAULT_USER)
    mcp_pass = st.text_input("IRIS password", value=DEFAULT_PASS, type="password")
    auth_header = _auth_header(mcp_user, mcp_pass)

    st.divider()
    st.header("Demo presets")
    preset = st.selectbox("Load a preset intake", ["(custom)"] + list(DEMO_PRESETS.keys()))
    if preset != "(custom)":
        st.session_state["intake"] = DEMO_PRESETS[preset]

    if st.button("Discover MCP tools"):
        try:
            tools = run_async(_list_tools(mcp_url, auth_header))
            st.success(f"{len(tools)} tools discovered")
            for t in sorted(tools, key=lambda x: x.name):
                st.caption(f"• {t.name}")
        except Exception as exc:  # noqa: BLE001
            st.error(f"Discovery failed: {exc}")

# Initialise default intake state.
if "intake" not in st.session_state:
    st.session_state["intake"] = DEMO_PRESETS[list(DEMO_PRESETS.keys())[0]]

intake = st.session_state["intake"]

col_form, col_brief = st.columns([1, 2])

with col_form:
    st.subheader("Patient intake")
    chief_complaint = st.text_input("Chief complaint", intake.get("chief_complaint", ""))
    duration = st.text_input("Duration", intake.get("duration", ""))
    age = st.number_input("Age", min_value=0, max_value=120, value=int(intake.get("age", 30)))
    sex = st.selectbox("Sex", ["M", "F", "Other"], index=["M", "F", "Other"].index(intake.get("sex", "F") if intake.get("sex") in {"M", "F", "Other"} else "F"))
    sign_style = st.selectbox(
        "Sign-language style",
        SIGN_STYLES,
        index=SIGN_STYLES.index(intake.get("sign_style", "ASL")) if intake.get("sign_style") in SIGN_STYLES else 0,
    )
    known_conditions_raw = st.text_area(
        "Known conditions (one per line)",
        "\n".join(intake.get("known_conditions", [])),
    )
    current_meds_raw = st.text_area(
        "Current medications (one per line)",
        "\n".join(intake.get("current_meds", [])),
    )
    free_text = st.text_area("Free-text intake notes", intake.get("free_text", ""), height=140)
    patient_id = st.text_input("Patient ID (optional)", intake.get("patient_id") or "")

    submit = st.button("Run SignBridge orchestrator", type="primary")

with col_brief:
    st.subheader("Orchestrator output")

    if not submit:
        st.info(
            "Fill out the intake on the left and click **Run SignBridge orchestrator**. "
            "Watch the activity log appear as the four specialist sub-agents fire."
        )
    else:
        intake_payload = {
            "patient_id":      patient_id or None,
            "chief_complaint": chief_complaint,
            "duration":        duration,
            "age":             int(age),
            "sex":             sex,
            "sign_style":      sign_style,
            "known_conditions":[s.strip() for s in known_conditions_raw.splitlines() if s.strip()],
            "current_meds":    [s.strip() for s in current_meds_raw.splitlines() if s.strip()],
            "free_text":       free_text,
        }
        st.session_state["intake"] = intake_payload

        with st.expander("Intake JSON sent to orchestrator", expanded=False):
            st.code(json.dumps(intake_payload, indent=2), language="json")

        with st.spinner("Orchestrator planning, delegating, and synthesizing..."):
            try:
                resp = run_async(_invoke_process_intake(mcp_url, auth_header, intake_payload))
            except Exception as exc:  # noqa: BLE001
                st.error(f"Orchestrator call failed: {exc}")
                resp = None

        if resp:
            if not resp.get("ok"):
                st.error(resp.get("error", "Unknown orchestrator error."))
                if resp.get("brief"):
                    st.text(resp["brief"])
            else:
                brief = resp.get("brief", "")
                activity, brief_md = split_activity_and_brief(brief)
                badge = esi_badge(brief_md)
                if badge:
                    color = {"ESI 1": "red", "ESI 2": "red", "ESI 3": "orange", "ESI 4": "green", "ESI 5": "green"}.get(badge, "blue")
                    st.markdown(
                        f"<div style='display:inline-block;padding:6px 14px;border-radius:6px;"
                        f"background:{color};color:white;font-weight:600;'>{badge}</div>",
                        unsafe_allow_html=True,
                    )

                if activity:
                    with st.expander("Agent activity log (orchestrator's planning trace)", expanded=True):
                        for line in activity:
                            st.markdown(f"`{line}`")

                st.markdown("### Pre-Visit Brief")
                st.markdown(brief_md or brief)

                tokens = resp.get("tokens")
                if tokens:
                    st.caption(
                        f"Token usage — prompt: {tokens.get('prompt', '?')}, "
                        f"completion: {tokens.get('completion', '?')}, "
                        f"tool calls: {tokens.get('tool_calls', '?')}"
                    )
