# mcp-agentic-rag
A small, end-to-end system that lets users upload docs and ask questions.  
It uses **Streamlit** for the UI, a **FastAPI** backend, an **MCP** (Model Context Protocol) server for tools (document search + web fallback), **ChromaDB** for embeddings storage, **SentenceTransformers** for embeddings, and **OpenAI Chat Completions** for answer synthesis. :contentReference[oaicite:0]{index=0}

---

## Features

- Upload `.txt` / `.pdf` and query them via Streamlit. 
- Vector store backed by **Chroma PersistentClient** (data lives on disk under `./chroma_db`). 
- Embeddings with `all-MiniLM-L6-v2` (384-dim, fast, general-purpose). 
- Answer synthesis with **OpenAI Chat Completions**. 
- MCP server exposing tools:
  - `document_search` → Chroma query (optionally scoped to recent uploads)
  - `web_search` → Serper.dev fallback (if no doc hits)

---

![Architecture Diagram](./architechture_diag/Arch_diagram.png)
