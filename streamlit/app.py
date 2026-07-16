"""Agentic RAG Console — operator UI over the FastAPI backend.

Not a generic chatbot: the left pane curates the knowledge base, the right pane
asks questions answered by the multi-agent graph and grounded in citations.
The UI is a pure HTTP client; all logic lives in the API.
"""

import json
import os
import time
import uuid

import requests
import streamlit as st

st.set_page_config(
    page_title="Agentic RAG",
    layout="wide",
    initial_sidebar_state="collapsed",
)

API_URL = os.getenv("CORE_API_URL", "http://localhost:8089")
DEFAULT_TENANT = "default"
REQUEST_TIMEOUT = 300


# --- Styling: typography, layout polish, login card ------------------------
st.markdown(
    """
    <style>
      html, body, [class*="css"], button, input, textarea {
        font-family: 'Inter', -apple-system, BlinkMacSystemFont, 'Segoe UI',
          Roboto, Helvetica, Arial, sans-serif;
      }
      #MainMenu, header[data-testid="stHeader"], footer { visibility: hidden; }
      .block-container {
        padding-top: 2.2rem; padding-bottom: 3rem;
        padding-left: 3rem; padding-right: 3rem; max-width: 100%;
      }
      /* Stack the two panes on narrow screens instead of squeezing them. */
      @media (max-width: 900px) {
        .block-container { padding-left: 1rem; padding-right: 1rem; }
        div[data-testid="stHorizontalBlock"] { flex-wrap: wrap; }
        div[data-testid="stHorizontalBlock"] > div[data-testid="stColumn"] {
          min-width: 100% !important;
        }
      }
      h1, h2, h3, h4 { color: #3a3f4b; font-weight: 700; letter-spacing: -0.015em; }
      .stButton > button {
        border-radius: 10px; font-weight: 600; padding: 0.45rem 1rem;
        border: 1px solid #e7e5e1;
      }
      .stButton > button[kind="primary"] { border: none; }
      div[data-testid="stVerticalBlockBorderWrapper"] { border-radius: 14px; }
      .brand { font-size: 1.45rem; font-weight: 800; color: #3a3f4b;
        letter-spacing: -0.02em; }
      .brand span { color: #6c75c1; }
      .subtle { color: #8a8f99; font-size: 0.88rem; }
      .eyebrow { color: #6c75c1; font-weight: 700; font-size: 0.78rem;
        text-transform: uppercase; letter-spacing: 0.08em; }
      .doc-card {
        background: #f3f2f8; border: 1px solid #e8e6f0;
        border-left: 3px solid #6c75c1; border-radius: 10px;
        padding: 0.7rem 0.9rem;
      }
      .doc-name { font-weight: 600; color: #3a3f4b; font-size: 0.95rem;
        word-break: break-word; }
      .doc-meta { margin-top: 6px; display: flex; align-items: center; gap: 8px; }
      .chip { background: #e4e2f2; color: #6c75c1; border-radius: 6px;
        padding: 2px 8px; font-size: 0.72rem; font-weight: 600; }
      .doc-date { color: #a8acb5; font-size: 0.76rem; }
    </style>
    """,
    unsafe_allow_html=True,
)


# --- Session state ---------------------------------------------------------
def init_state() -> None:
    st.session_state.setdefault("access_token", None)
    st.session_state.setdefault("user_email", None)
    st.session_state.setdefault("tenant_id", DEFAULT_TENANT)
    st.session_state.setdefault("last_answer", None)
    # Stable per-session conversation thread so a write approval targets the same
    # paused run. The operator persists state under this id (Redis checkpoint).
    st.session_state.setdefault("thread_id", f"ui-{uuid.uuid4().hex[:12]}")
    # A destructive write the operator proposed and is waiting on (Approve/Reject).
    st.session_state.setdefault("pending_approval", None)


init_state()


def auth_headers() -> dict:
    return {"Authorization": f"Bearer {st.session_state.access_token}"}


def api_error(resp: requests.Response) -> str:
    """Pull a human-readable message out of an error response."""
    try:
        body = resp.json()
        return body.get("error", {}).get("message") or body.get("detail") or resp.text
    except Exception:
        return resp.text


# ===========================================================================
# LOGIN — centered, full page
# ===========================================================================
def render_login() -> None:
    _, mid, _ = st.columns([1, 1.1, 1])
    with mid:
        st.write("")
        st.write("")
        st.markdown("<div class='brand'>Agentic <span>RAG</span></div>", True)
        st.markdown("<div class='subtle'>Enterprise knowledge assistant</div>", True)
        st.write("")
        with st.container(border=True):
            st.markdown("#### Sign in")
            email = st.text_input("Email", value="ece@qkare.com")
            password = st.text_input("Password", type="password", value="changeme123")
            if st.button("Sign in", use_container_width=True, type="primary"):
                try:
                    resp = requests.post(
                        f"{API_URL}/auth/login",
                        json={"email": email, "password": password},
                        timeout=10,
                    )
                    if resp.status_code == 200:
                        tok = resp.json()["data"]["access_token"]
                        st.session_state.access_token = tok
                        st.session_state.user_email = email
                        st.rerun()
                    else:
                        st.error(f"Login failed: {api_error(resp)}")
                except Exception as exc:
                    st.error(f"Cannot reach API: {exc}")


if st.session_state.access_token is None:
    render_login()
    st.stop()


# ===========================================================================
# WORKSPACE — top header + two panes
# ===========================================================================
tenant = st.session_state.tenant_id

brand_col, tenant_col, user_col = st.columns([4, 2, 1.4])
with brand_col:
    st.markdown("<div class='brand'>Agentic <span>RAG</span></div>", True)
with tenant_col:
    st.session_state.tenant_id = st.text_input(
        "Workspace", value=tenant, label_visibility="collapsed"
    )
    tenant = st.session_state.tenant_id
with user_col:
    if st.button("Sign out", use_container_width=True):
        st.session_state.access_token = None
        st.session_state.user_email = None
        st.session_state.last_answer = None
        st.session_state.pending_approval = None
        st.session_state.thread_id = f"ui-{uuid.uuid4().hex[:12]}"
        st.rerun()

st.divider()
left, right = st.columns([1, 1.8], gap="large")


# --- LEFT: Knowledge base --------------------------------------------------
with left:
    st.markdown("<div class='eyebrow'>Knowledge base</div>", True)
    st.markdown(f"<div class='subtle'>Workspace: {tenant}</div>", True)
    st.write("")

    with st.expander("Add a document"):
        up_tab, paste_tab = st.tabs(["Upload file", "Paste text"])
        with up_tab:
            uploaded = st.file_uploader(
                "PDF, Markdown, or text", type=["pdf", "md", "txt"], key="uploader"
            )
            if uploaded is not None and st.button("Ingest file", type="primary"):
                with st.spinner("Ingesting…"):
                    resp = requests.post(
                        f"{API_URL}/documents/upload",
                        data={"tenant_id": tenant},
                        files={"file": (uploaded.name, uploaded.getvalue())},
                        headers=auth_headers(),
                        timeout=REQUEST_TIMEOUT,
                    )
                if resp.status_code == 200:
                    st.success(f"Added {resp.json()['data']['chunk_count']} chunk(s)")
                    st.rerun()
                else:
                    st.error(api_error(resp))
        with paste_tab:
            source_name = st.text_input("Source name", placeholder="release-notes.md")
            content = st.text_area("Content", height=120, placeholder="Paste text…")
            if st.button("Ingest text"):
                if source_name and content:
                    with st.spinner("Ingesting…"):
                        resp = requests.post(
                            f"{API_URL}/documents/ingest",
                            json={
                                "source_name": source_name,
                                "content": content,
                                "tenant_id": tenant,
                            },
                            headers=auth_headers(),
                            timeout=REQUEST_TIMEOUT,
                        )
                    if resp.status_code == 200:
                        st.success(
                            f"Added {resp.json()['data']['chunk_count']} chunk(s)"
                        )
                        st.rerun()
                    else:
                        st.error(api_error(resp))
                else:
                    st.warning("Source name and content are required.")

    resp = requests.get(
        f"{API_URL}/documents",
        params={"tenant_id": tenant},
        headers=auth_headers(),
        timeout=30,
    )
    if resp.status_code == 200:
        result = resp.json()["data"]
        st.markdown(f"<div class='subtle'>{result['count']} document(s)</div>", True)
        if not result["documents"]:
            st.info("No documents yet. Add one above to get started.")
        for doc in result["documents"]:
            info, action = st.columns([8, 1], vertical_alignment="center")
            info.markdown(
                f"<div class='doc-card'>"
                f"<div class='doc-name'>{doc['source_name']}</div>"
                f"<div class='doc-meta'>"
                f"<span class='chip'>{doc['chunk_count']} chunks</span>"
                f"<span class='doc-date'>{doc['created_at'][:10]}</span>"
                f"</div></div>",
                unsafe_allow_html=True,
            )
            with action:
                if st.button(
                    "",
                    icon=":material/delete:",
                    key=f"del_{doc['document_id']}",
                    help="Delete document",
                ):
                    d = requests.delete(
                        f"{API_URL}/documents/{doc['document_id']}",
                        params={"tenant_id": tenant},
                        headers=auth_headers(),
                        timeout=30,
                    )
                    if d.status_code == 200:
                        st.rerun()
                    else:
                        st.error(api_error(d))
    else:
        st.error(f"Could not list documents: {api_error(resp)}")


# --- RIGHT: Ask ------------------------------------------------------------

NODE_LABEL = {
    "researcher": "Research Agent",
    "analyst": "Analysis Agent",
    "auditor": "Review Agent",
    "finalizer": "Response Agent",
}

with right:
    st.markdown("<div class='eyebrow'>Ask</div>", True)
    st.markdown(
        "<div class='subtle'>The operator answers from your documents and data, "
        "and asks for approval before making any change.</div>",
        True,
    )
    st.write("")

    with st.form("ask_form", clear_on_submit=False):
        question = st.text_area(
            "Question",
            height=90,
            placeholder="How many days do I have to request a refund?",
            label_visibility="collapsed",
        )
        submitted = st.form_submit_button("Ask", type="primary")

    if submitted:
        if not question.strip():
            st.warning("Type a question first.")
        else:
            try:
                with requests.post(
                    f"{API_URL}/chat/stream",
                    json={
                        "question": question.strip(),
                        "tenant_id": tenant,
                        "thread_id": st.session_state.thread_id,
                    },
                    headers=auth_headers(),
                    timeout=REQUEST_TIMEOUT,
                    stream=True,
                ) as resp:
                    if resp.status_code != 200:
                        st.error(f"Error {resp.status_code}: {api_error(resp)}")
                    else:
                        status = st.status("Agent thinking…", expanded=True)
                        token_box = st.empty()

                        for raw in resp.iter_lines():
                            if not raw:
                                continue
                            line = raw.decode() if isinstance(raw, bytes) else raw
                            if not line.startswith("data:"):
                                continue
                            event = json.loads(line[5:].strip())
                            kind = event.get("type")
                            node = event.get("node")
                            data = event.get("data", {})

                            if kind == "node_start":
                                label = NODE_LABEL.get(node, node)
                                status.write(f"{label}…")

                            elif kind == "node_end" and node == "auditor":
                                verdict = data.get("verdict", {})
                                icon = "✓" if verdict.get("faithful") else "↩ revising"
                                reason = verdict.get("reason", "")[:80]
                                status.write(f"Review: {icon} — {reason}")

                            elif kind == "tool_call":
                                tool = data.get("tool", "tool")
                                inp = data.get("input") or {}
                                hint = (
                                    inp.get("query") or inp.get("sql") or str(inp)[:60]
                                )
                                status.write(f"Tool Use: `{tool}` ← {hint}")

                            elif kind == "approval_required":
                                status.update(
                                    label="Approval required",
                                    state="complete",
                                    expanded=False,
                                )
                                st.session_state.pending_approval = {
                                    "thread_id": data.get("thread_id"),
                                    "sql": data.get("sql", ""),
                                    "description": data.get("description", ""),
                                    "question": question.strip(),
                                }
                                st.rerun()

                            elif kind == "final":
                                status.update(
                                    label="Done", state="complete", expanded=False
                                )
                                answer_text = data.get("answer", "")
                                buf = ""
                                for i, word in enumerate(answer_text.split(" ")):
                                    buf += ("" if i == 0 else " ") + word
                                    token_box.markdown(buf + " ▌")
                                    time.sleep(0.012)
                                token_box.empty()
                                st.session_state.last_answer = {
                                    "question": question.strip(),
                                    "answer": answer_text,
                                    "citations": data.get("citations", []),
                                }

                            elif kind == "error":
                                status.update(
                                    label="Error", state="error", expanded=True
                                )
                                msg = data.get(
                                    "message", data.get("error", "Agent error")
                                )
                                st.error(f"[{data.get('code', 'ERR')}] {msg}")

            except Exception as exc:
                st.error(f"Request failed: {exc}")

    # --- Pending write approval (HITL) -------------------------------------
    def _apply_resume(resp: requests.Response, question: str) -> None:
        """Handle an /chat/approve|reject response: answer, or another pause."""
        if resp.status_code != 200:
            st.error(api_error(resp))
            return
        data = resp.json()["data"]
        if data.get("status") == "pending_approval":
            # The operator proposed a further write — loop the approval UI.
            st.session_state.pending_approval = {
                "thread_id": data.get("thread_id"),
                "sql": data.get("sql", ""),
                "description": data.get("description", ""),
                "question": question,
            }
        else:
            st.session_state.pending_approval = None
            st.session_state.last_answer = {
                "question": question,
                "answer": data.get("answer", ""),
                "citations": data.get("citations", []),
            }
        st.rerun()

    pending = st.session_state.pending_approval
    if pending:
        with st.container(border=True):
            st.markdown(
                "<div class='eyebrow'>Approval required</div>"
                "<div class='subtle'>The assistant wants to run a change. It will "
                "not execute until you approve.</div>",
                unsafe_allow_html=True,
            )
            st.code(pending["sql"], language="sql")
            if pending.get("description"):
                st.caption(pending["description"])
            reason = st.text_input(
                "Rejection reason (optional)", key="reject_reason", placeholder="…"
            )
            approve_col, reject_col = st.columns(2)
            if approve_col.button(
                "Approve & run", type="primary", use_container_width=True
            ):
                with st.spinner("Applying the change…"):
                    r = requests.post(
                        f"{API_URL}/chat/approve/{pending['thread_id']}",
                        json={"tenant_id": tenant},
                        headers=auth_headers(),
                        timeout=REQUEST_TIMEOUT,
                    )
                _apply_resume(r, pending["question"])
            if reject_col.button("Reject", use_container_width=True):
                with st.spinner("Cancelling…"):
                    r = requests.post(
                        f"{API_URL}/chat/reject/{pending['thread_id']}",
                        json={"tenant_id": tenant, "reason": reason or None},
                        headers=auth_headers(),
                        timeout=REQUEST_TIMEOUT,
                    )
                _apply_resume(r, pending["question"])

    answer = st.session_state.last_answer
    if answer:
        with st.container(border=True):
            st.markdown(f"<div class='subtle'>{answer['question']}</div>", True)
            st.write("")
            st.markdown(answer["answer"] or "_(empty answer)_")
        citations = answer["citations"]
        if citations:
            st.markdown(f"**Sources ({len(citations)})**")
            for i, c in enumerate(citations, 1):
                path = " › ".join(c.get("heading_path", [])) or "—"
                with st.expander(f"{i}. {c.get('source_name', 'unknown')} · {path}"):
                    st.markdown(
                        f"<span class='subtle'>Document {c.get('document_id', '')}"
                        "</span>",
                        unsafe_allow_html=True,
                    )
                    st.write(c.get("snippet", ""))
        else:
            st.caption("No sources cited — the answer may not be grounded.")

    with st.expander("Inspect retrieval (advanced)"):
        st.markdown(
            "<div class='subtle'>Raw hybrid-search chunks and scores — no LLM, "
            "no synthesis.</div>",
            True,
        )
        rq = st.text_input("Query", key="dbg_query", placeholder="refund days")
        rk = st.slider("top_k", 1, 20, 5, key="dbg_topk")
        if st.button("Run retrieval"):
            if rq.strip():
                r = requests.post(
                    f"{API_URL}/search",
                    json={"query": rq, "tenant_id": tenant, "top_k": rk},
                    headers=auth_headers(),
                    timeout=60,
                )
                if r.status_code == 200:
                    for i, res in enumerate(r.json()["data"]["results"], 1):
                        st.markdown(
                            f"**{i}. {res.get('source_name', '?')}** · "
                            f"score {res['score']:.3f}"
                        )
                        st.caption(res.get("text", "")[:300])
                else:
                    st.error(api_error(r))
            else:
                st.warning("Enter a query.")
