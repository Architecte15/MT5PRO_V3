from __future__ import annotations


def run_dashboard(state_provider):
    try:
        import streamlit as st
    except ImportError as exc:
        raise RuntimeError("Install streamlit to use the dashboard") from exc
    st.set_page_config(page_title="Python Trading Engine", layout="wide")
    st.title("Python Trading Engine")
    state = state_provider()
    cols = st.columns(4)
    items = [
        ("Symbol", state.get("symbol")), ("HTF Trend", state.get("trend")),
        ("Structure", state.get("structure")), ("State", state.get("state")),
        ("Score", state.get("score")), ("Spread", state.get("spread")),
        ("SL", state.get("sl")), ("TP", state.get("tp")),
    ]
    for i, (label, value) in enumerate(items):
        cols[i % 4].metric(label, value if value is not None else "—")
    st.json(state)
