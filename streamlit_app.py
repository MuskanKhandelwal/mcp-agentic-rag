import os
import socket
import streamlit as st
import requests

API_URL = "http://rag-backend:8001"
try:
    socket.gethostbyname("rag-backend")
except socket.error:
    API_URL = "http://localhost:8001"

st.title("Agentic RAG MCP Document Q&A")

# — Session state initialization —
for key, default in {
    "question": "",
    "answer": None,
    "sources": [],
    "is_querying": False,
    "query_count": 0,
    "uploaded_ok": False
}.items():
    if key not in st.session_state:
        st.session_state[key] = default

def do_query():
    st.session_state.is_querying = True
    st.session_state.query_count += 1
    # Use placeholder or st.write for debug if needed
    #st.write(f"DEBUG → [frontend] Sending query attempt #{st.session_state.query_count}")
    payload = {"question": st.session_state.question.strip()}
    try:
        resp = requests.post(f"{API_URL}/query/", json=payload)
        st.write(f"DEBUG → HTTP status: {resp.status_code}")
        if resp.status_code == 200:
            data = resp.json()
            st.write(f"DEBUG → response JSON: {data}")
            st.session_state.answer = data.get("answer")
            st.session_state.sources = data.get("sources", [])
        else:
            st.session_state.answer = f"Error: {resp.status_code} – {resp.text}"
            st.session_state.sources = []
    except Exception as e:
        st.session_state.answer = f"Exception during query: {e}"
        st.session_state.sources = []
    finally:
        st.session_state.is_querying = False

# — Document upload section —
st.header("Upload a Document")
uploaded_file = st.file_uploader("Choose a .txt or .pdf file", type=["txt", "pdf"])

if uploaded_file is not None and not st.session_state.uploaded_ok:
    files = {"file": (uploaded_file.name, uploaded_file.getvalue())}
    with st.spinner("Uploading and ingesting the document..."):
        resp = requests.post(f"{API_URL}/upload_document/", files=files)
    if resp.status_code == 200:
        st.success("Document uploaded successfully!")
        st.session_state.uploaded_ok = True
        # Reset previous query / answer
        st.session_state.answer = None
        st.session_state.sources = []
        st.session_state.query_count = 0
    else:
        st.error(f"Upload error: {resp.status_code} – {resp.text}")

# — Question + Query section —
st.header("Ask a Question")
st.text_input("Your question:", key="question")

# Place the button in a separate row, so layout is clearer
if st.button("Get Answer", on_click=do_query, disabled=st.session_state.is_querying):
    pass  # on_click will call do_query

if st.session_state.is_querying:
    st.info("Querying…")

# Use placeholder to avoid ghost/duplicate text
answer_placeholder = st.empty()

if st.session_state.answer is not None:
    answer_placeholder.markdown(f"**Answer (query #{st.session_state.query_count}):**\n\n{st.session_state.answer}")

    if st.session_state.sources:
        st.markdown("### Sources")
        for i, s in enumerate(st.session_state.sources, start=1):
            src = s.get("source") or "unknown"
            pg = f"p.{s.get('page')}" if s.get("page") is not None else ""
            with st.expander(f"[{i}] {src} {pg} — score {s.get('score')}"):
                st.write(s.get("text", "")[:2000])
