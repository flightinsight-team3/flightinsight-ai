"""FlightInsight AI chat. Run from the repo root:

    streamlit run app/ui/streamlit_app.py

Needs Ollama running (embeddings, and the chat model when "ollama" is chosen), `az login` or
COSMOS_NOSQL_KEY for Cosmos, and GOOGLE_API_KEY in .env for Gemini.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))  # `streamlit run` adds only app/ui

import streamlit as st  # noqa: E402

from app.agent.agent import ask, build_agent  # noqa: E402
from app.agent.llm import PROVIDERS, default_model  # noqa: E402

EXAMPLES = [
    "How on time was ATL to ORD in January 2024, and which airline was best?",
    "Are there safety reports about crews feeling rushed by delays?",
    "Find reports about de-icing problems in snow for B737 aircraft.",
]

st.set_page_config(page_title="FlightInsight AI", page_icon="✈️")
st.title("✈️ FlightInsight AI")
st.caption("Route delay statistics (BTS, Jan 2024) and NASA ASRS safety reports (Jan–Mar 2024)")

with st.sidebar:
    provider = st.radio("Model provider", PROVIDERS, format_func=str.capitalize)
    model = st.text_input("Model", default_model(provider), key=f"model_{provider}")
    if st.button("New conversation"):
        st.session_state.pop("history", None)
        st.session_state.pop("turns", None)
    st.markdown("**Try:**\n" + "\n".join(f"- {q}" for q in EXAMPLES))


@st.cache_resource(show_spinner=False)
def agent_for(provider: str, model: str):
    return build_agent(provider, model)


def show_turn(turn: dict) -> None:
    with st.chat_message("user"):
        st.markdown(turn["question"])
    with st.chat_message("assistant"):
        st.markdown(turn["text"] or "_(no answer)_")
        label = f"{turn['model']} · {turn['seconds']:.1f}s · {len(turn['tools'])} tool call(s)"
        with st.expander(label):
            for call in turn["tools"]:
                st.markdown(f"**{call.name}**")
                st.code(json.dumps(call.args, ensure_ascii=False), language="json")
                st.text(call.output[:3000] + (" ..." if len(call.output) > 3000 else ""))


turns = st.session_state.setdefault("turns", [])
for turn in turns:
    show_turn(turn)

if question := st.chat_input("Ask about a route, a delay, or safety reports"):
    with st.spinner(f"Thinking with {model}..."):
        try:
            answer = ask(agent_for(provider, model), question, st.session_state.get("history", []))
        except Exception as e:  # e.g. Gemini overloaded (503), Ollama not running
            st.error(f"{type(e).__name__}: {e}")
            st.stop()
    st.session_state["history"] = answer.messages
    turn = {
        "question": question,
        "text": answer.text,
        "tools": answer.tool_calls,
        "seconds": answer.seconds,
        "model": answer.model or f"{provider}/{model}",
    }
    turns.append(turn)
    show_turn(turn)
