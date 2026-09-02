"""
Streamlit showcase UI for the IT Support Ticket Classifier Agent.

Run with:
    streamlit run streamlit_app.py

If GEMINI_API_KEY is not set, the app automatically falls back to a
built-in demo client (simple keyword rules) so the UI is fully explorable
without any credentials or network access.
"""

import os
import io
import time
from datetime import datetime

import pandas as pd
import streamlit as st
from dotenv import load_dotenv

from agent import (
    TicketClassifierAgent,
    GeminiClient,
    LLMClientError,
    ClassificationParseError,
    VALID_CATEGORIES,
    VALID_PRIORITIES,
)

load_dotenv()

# --------------------------------------------------------------------------
# Demo / offline fallback client
# --------------------------------------------------------------------------


class DemoLLMClient:
    """
    A tiny keyword-based stand-in for GeminiClient.

    Used automatically when no GEMINI_API_KEY is configured, so the app
    can always be demoed end-to-end without a real key or network access.
    Returns the same JSON shape the real prompt asks the LLM for.
    """

    def generate(self, prompt: str) -> str:
        text = prompt.lower()

        if any(k in text for k in ["password", "locked out", "login", "log in", "mfa", "2fa", "access"]):
            category, priority, action = "Access", "High", "Reset credentials / verify identity"
        elif any(k in text for k in ["wifi", "wi-fi", "vpn", "internet", "network", "dns"]):
            category, priority, action = "Network", "High", "Check network/DNS connectivity"
        elif any(k in text for k in ["laptop won't", "laptop wont", "won't turn on", "wont turn on", "dead", "broken screen", "hardware", "battery", "monitor"]):
            category, priority, action = "Hardware", "Critical", "Dispatch replacement hardware"
        elif any(k in text for k in ["outlook", "excel", "word", "software", "app crashes", "install", "update failed"]):
            category, priority, action = "Software", "Medium", "Reinstall or update the application"
        else:
            category, priority, action = "Other", "Low", "Route to general IT queue for triage"

        return (
            '{"category": "%s", "priority": "%s", "suggested_action": "%s"}'
            % (category, priority, action)
        )


@st.cache_resource(show_spinner=False)
def get_agent():
    """Build the agent once per session: real Gemini client if key is set, else demo."""
    api_key = os.getenv("GEMINI_API_KEY")
    if api_key:
        try:
            client = GeminiClient(api_key=api_key)
            return TicketClassifierAgent(llm_client=client), False
        except LLMClientError:
            return TicketClassifierAgent(llm_client=DemoLLMClient()), True
    return TicketClassifierAgent(llm_client=DemoLLMClient()), True


# --------------------------------------------------------------------------
# Page setup
# --------------------------------------------------------------------------

st.set_page_config(
    page_title="IT Ticket Classifier",
    page_icon="🎫",
    layout="wide",
)

if "history" not in st.session_state:
    st.session_state.history = []

agent, is_demo = get_agent()

PRIORITY_COLOR = {
    "Critical": "#e03131",
    "High": "#f08c00",
    "Medium": "#1971c2",
    "Low": "#2f9e44",
}
CATEGORY_ICON = {
    "Network": "🌐",
    "Access": "🔐",
    "Software": "💾",
    "Hardware": "🖥️",
    "Other": "❓",
}

EXAMPLE_TICKETS = {
    "Wi-Fi issue": "My laptop is connected to Wi-Fi but the internet is not working.",
    "Password reset": "I forgot my company password and cannot log in.",
    "Outlook crash": "Outlook keeps crashing every time I try to open a shared calendar.",
    "Dead laptop": "My laptop won't turn on at all, the screen stays completely black.",
}

# --------------------------------------------------------------------------
# Sidebar
# --------------------------------------------------------------------------

with st.sidebar:
    st.header("🎫 Ticket Classifier")
    st.caption("LLM agent for IT support triage")

    if is_demo:
        st.warning(
            "**Demo mode** — no `GEMINI_API_KEY` found (or it failed to "
            "initialize), so responses come from a local rule-based stand-in, "
            "not the real model.",
            icon="⚠️",
        )
    else:
        st.success(f"Connected to `{os.getenv('GEMINI_MODEL', 'gemini-3.6-flash')}`", icon="✅")

    st.divider()
    st.subheader("About")
    st.markdown(
        "Classifies employee IT tickets into:\n"
        "- **Category** — Network / Access / Software / Hardware / Other\n"
        "- **Priority** — Low / Medium / High / Critical\n"
        "- **Suggested Action**\n"
    )

    st.divider()
    if st.session_state.history:
        st.subheader("Session stats")
        df_hist = pd.DataFrame(st.session_state.history)
        st.metric("Tickets classified", len(df_hist))
        st.bar_chart(df_hist["priority"].value_counts())

    if st.button("Clear history", use_container_width=True):
        st.session_state.history = []
        st.rerun()

# --------------------------------------------------------------------------
# Main tabs
# --------------------------------------------------------------------------

tab_single, tab_batch, tab_history = st.tabs(
    ["🔍 Classify a ticket", "📄 Batch (CSV)", "🕒 History"]
)

# ---- Tab 1: single ticket -------------------------------------------------
with tab_single:
    st.subheader("Classify a single ticket")

    cols = st.columns(len(EXAMPLE_TICKETS))
    for col, (label, text) in zip(cols, EXAMPLE_TICKETS.items()):
        if col.button(label, use_container_width=True):
            st.session_state["ticket_text"] = text

    ticket_text = st.text_area(
        "Employee ticket text",
        key="ticket_text",
        height=140,
        placeholder="e.g. My laptop is connected to Wi-Fi but the internet is not working.",
    )

    classify_clicked = st.button("Classify ticket", type="primary")

    if classify_clicked:
        if not ticket_text or not ticket_text.strip():
            st.error("Please enter some ticket text first.")
        else:
            with st.spinner("Classifying..."):
                try:
                    start = time.time()
                    result = agent.classify(ticket_text)
                    elapsed = time.time() - start
                except (LLMClientError, ClassificationParseError, ValueError) as exc:
                    st.error(f"Classification failed: {exc}")
                    result = None

            if result is not None:
                color = PRIORITY_COLOR.get(result.priority, "#495057")
                icon = CATEGORY_ICON.get(result.category, "❓")

                st.markdown("#### Result")
                r1, r2, r3 = st.columns(3)
                r1.markdown(
                    f"**Category**<br><span style='font-size:1.4em'>{icon} {result.category}</span>",
                    unsafe_allow_html=True,
                )
                r2.markdown(
                    f"**Priority**<br><span style='font-size:1.4em;color:{color};font-weight:700'>"
                    f"● {result.priority}</span>",
                    unsafe_allow_html=True,
                )
                r3.markdown(
                    f"**Latency**<br><span style='font-size:1.4em'>{elapsed:.2f}s</span>",
                    unsafe_allow_html=True,
                )
                st.info(f"**Suggested action:** {result.suggested_action}")

                st.session_state.history.append(
                    {
                        "time": datetime.now().strftime("%H:%M:%S"),
                        "ticket": ticket_text.strip(),
                        "category": result.category,
                        "priority": result.priority,
                        "suggested_action": result.suggested_action,
                    }
                )

# ---- Tab 2: batch CSV ------------------------------------------------------
with tab_batch:
    st.subheader("Batch classify from CSV")
    st.caption("Upload a CSV with a column named **ticket** (one ticket per row).")

    sample_csv = pd.DataFrame({"ticket": list(EXAMPLE_TICKETS.values())})
    st.download_button(
        "Download sample CSV",
        data=sample_csv.to_csv(index=False).encode("utf-8"),
        file_name="sample_tickets.csv",
        mime="text/csv",
    )

    uploaded = st.file_uploader("Upload tickets CSV", type=["csv"])

    if uploaded is not None:
        try:
            df_in = pd.read_csv(uploaded)
        except Exception as exc:  # noqa: BLE001
            st.error(f"Could not read CSV: {exc}")
            df_in = None

        if df_in is not None:
            if "ticket" not in df_in.columns:
                st.error("CSV must contain a column named 'ticket'.")
            else:
                if st.button("Classify all rows", type="primary"):
                    progress = st.progress(0, text="Classifying tickets...")
                    rows = []
                    n = len(df_in)
                    for i, ticket in enumerate(df_in["ticket"].astype(str)):
                        try:
                            res = agent.classify(ticket)
                            rows.append(
                                {
                                    "ticket": ticket,
                                    "category": res.category,
                                    "priority": res.priority,
                                    "suggested_action": res.suggested_action,
                                }
                            )
                        except Exception as exc:  # noqa: BLE001
                            rows.append(
                                {
                                    "ticket": ticket,
                                    "category": "ERROR",
                                    "priority": "ERROR",
                                    "suggested_action": str(exc),
                                }
                            )
                        progress.progress((i + 1) / n, text=f"Classifying tickets... {i + 1}/{n}")

                    progress.empty()
                    df_out = pd.DataFrame(rows)
                    st.dataframe(df_out, use_container_width=True)

                    st.download_button(
                        "Download results CSV",
                        data=df_out.to_csv(index=False).encode("utf-8"),
                        file_name="classified_tickets.csv",
                        mime="text/csv",
                    )

# ---- Tab 3: history ---------------------------------------------------------
with tab_history:
    st.subheader("Session history")
    if not st.session_state.history:
        st.caption("No tickets classified yet in this session.")
    else:
        df_hist = pd.DataFrame(st.session_state.history)
        st.dataframe(df_hist[::-1], use_container_width=True)
        st.download_button(
            "Download history CSV",
            data=df_hist.to_csv(index=False).encode("utf-8"),
            file_name="ticket_history.csv",
            mime="text/csv",
        )
