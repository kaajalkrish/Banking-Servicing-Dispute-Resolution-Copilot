"""A simple Streamlit chat UI for the copilot (optional extra; ref-doc.md §4 lists
the CLI as the required interface and FastAPI streaming as optional, and does not
evaluate interface polish, §2).

Run (one command; it also starts the streaming API if it is not already running,
which takes about a minute in the background while the UI is already open):

    streamlit run src/ui/app.py      # or: python -m src.ui

It is a thin client of ``POST /chat/stream`` (src/ui/client.py), so every
control in the graph applies unchanged. Design decisions:

- Only node *names* are shown while a turn runs, never node content: a worker's
  draft has not yet passed the output guard and risk gate. The customer sees one
  answer, the one ``finalize`` produced.
- The answer is masked again here (defence in depth); the API already masks it.
- **No authentication.** The customer picked in the sidebar is trusted, exactly
  like the CLI's ``--customer-id`` and the API's ``customer_id``. Local use only
  (docs/security-approach.md).
"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Any

# `streamlit run src/ui/app.py` puts src/ui on sys.path, not the repo root.
_ROOT = Path(__file__).resolve().parents[2]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

import streamlit as st  # noqa: E402

from src.common.masking import mask_text  # noqa: E402
from src.ui import api_process, client  # noqa: E402

NODE_LABELS = {
    "input_guard": "Checked your message",
    "load_memory": "Recalled earlier context",
    "build_context": "Prepared the context",
    "supervisor": "Chose the right specialist",
    "intake": "Asked a clarifying question",
    "account_servicing": "Looked up your account",
    "dispute": "Handled the dispute request",
    "product_info": "Searched the policy library",
    "escalate_human": "Handed off to a human",
    "finalize": "Checked the answer",
    "save_memory": "Saved context for next time",
}


def _label(node: str) -> str:
    return f"{NODE_LABELS.get(node, node)} ({node})"


def _citation_text(citation: Any) -> str:
    if isinstance(citation, dict):
        doc, section = citation.get("doc_id", "?"), citation.get("section")
        return f"{doc} / {section}" if section else str(doc)
    return str(citation)


def _render_meta(meta: dict[str, Any]) -> None:
    if meta.get("error"):
        st.warning(f"The copilot hit a problem ({meta['error']}); the answer is a safe hand-off.")
    if meta.get("citations"):
        st.caption("Sources: " + "; ".join(_citation_text(c) for c in meta["citations"]))
    if meta.get("tier"):
        st.caption(f"Risk tier: {meta['tier']}")
    if meta.get("review"):
        st.warning("Flagged for human review: a banking agent will follow up.")


def _reset_conversation() -> None:
    st.session_state.messages = []
    st.session_state.thread_id = client.new_thread_id()


def _init_state(customer_id: str) -> None:
    if "messages" not in st.session_state:
        _reset_conversation()
    if st.session_state.get("customer_id") != customer_id:
        st.session_state.customer_id = customer_id
        _reset_conversation()


@st.cache_resource
def _api_process() -> Any:
    """Start the API once per Streamlit server (not per rerun or session), unless it
    is already running or COPILOT_START_API=0. Stopped again when the server exits."""
    return api_process.ensure_api(client.DEFAULT_API_URL)


@st.fragment(run_every=3)
def _api_status(api_url: str, ready_at_render: bool) -> None:
    """Poll /health every few seconds; re-run the page when the API comes up (or goes away)."""
    ready = client.api_health(api_url) is not None
    if ready != ready_at_render:
        st.rerun()
    proc = _api_process()
    if ready:
        st.success("API ready")
    elif proc is not None and proc.poll() is not None:
        st.error(f"The API stopped while starting. Last of its log:\n\n```\n{api_process.log_tail()}\n```")
    else:
        st.error(
            "API not ready yet. It is loading in the background (about a minute); this switches "
            "to ready by itself. If it never does, start it yourself with: python -m src.api"
        )


def _sidebar() -> tuple[str, str]:
    _api_process()  # kicks off the API on the first render of a server
    st.sidebar.header("Session")
    api_url = st.sidebar.text_input("API URL", value=client.DEFAULT_API_URL)
    customers = client.load_customers()
    labels = {cid: f"{cid} ({name})" for cid, name in customers}
    customer_id = st.sidebar.selectbox("Customer (synthetic)", options=list(labels), format_func=labels.get)
    if st.sidebar.button("New conversation"):
        _reset_conversation()
    with st.sidebar:
        _api_status(api_url, client.api_health(api_url) is not None)
    return api_url, customer_id


def _run_turn(api_url: str, customer_id: str, prompt: str) -> dict[str, Any]:
    """Stream one turn, showing progress, and return the message record."""
    final: dict[str, Any] | None = None
    error: str | None = None
    with st.chat_message("assistant"):
        status = st.status("Working on it...", expanded=True)
        try:
            for event, data in client.stream_chat(api_url, customer_id, prompt, st.session_state.thread_id):
                if event == "progress":
                    status.write(_label(str(data.get("node", "?"))))
                elif event == "error":
                    error = str(data.get("type", "error"))
                elif event == "final":
                    final = data
        except client.ApiError as exc:
            status.update(label="Could not get an answer", state="error", expanded=False)
            st.error(str(exc))
            return {"role": "assistant", "content": f"Error: {exc}", "meta": {}}
        status.update(label="Done", state="complete", expanded=False)
        final = final or {}
        answer = mask_text(str(final.get("answer", "(no answer)")))
        meta = {
            "error": error,
            "citations": final.get("citations") or [],
            "tier": final.get("risk_tier"),
            "review": bool(final.get("requires_human_review")),
        }
        st.markdown(answer)
        _render_meta(meta)
    return {"role": "assistant", "content": answer, "meta": meta}


def main() -> None:
    st.set_page_config(page_title="Banking Servicing Copilot", page_icon="🏦")
    api_url, customer_id = _sidebar()
    _init_state(customer_id)

    st.title("Banking Servicing Copilot")

    for message in st.session_state.messages:
        with st.chat_message(message["role"]):
            st.markdown(message["content"])
            _render_meta(message.get("meta") or {})

    ready = client.api_health(api_url) is not None
    prompt = st.chat_input("Ask about your accounts, a dispute or a bank policy", disabled=not ready)
    if prompt:
        st.session_state.messages.append({"role": "user", "content": prompt, "meta": {}})
        with st.chat_message("user"):
            st.markdown(prompt)
        st.session_state.messages.append(_run_turn(api_url, customer_id, prompt))


main()
