
from fastapi import FastAPI, UploadFile, File, HTTPException
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from pathlib import Path
import shutil, os, json, httpx, asyncio, logging
from dotenv import load_dotenv
load_dotenv()

UPLOAD_DIR = Path("uploaded_docs"); UPLOAD_DIR.mkdir(exist_ok=True)
app = FastAPI(title="Agentic RAG MCP API")

class QueryRequest(BaseModel):
    question: str

# --- MCP client (unchanged except more-tolerant parsing) ---
class MCPClient:
    def __init__(self, url: str, protocol_version: str = "2025-06-18"):
        self.url = url
        self.protocol_version = protocol_version
        self.session_id: str | None = None

    async def initialize(self):
        payload = {
            "jsonrpc": "2.0",
            "method": "initialize",
            "params": {
                "protocolVersion": self.protocol_version,
                "clientInfo": {"name": "AgenticRAGClient", "version": "0.1"},
                "capabilities": {"tools": {}},
            },
            "id": 0,
        }
        headers = {
            "Content-Type": "application/json",
            "Accept": "application/json, text/event-stream",
            "User-Agent": "Agentic-RAG-Client/1.0",
            "MCP-Protocol-Version": self.protocol_version,
        }
        async with httpx.AsyncClient(timeout=None) as client:
            async with client.stream("POST", self.url, data=json.dumps(payload), headers=headers) as resp:
                resp.raise_for_status()
                sid = resp.headers.get("Mcp-Session-Id")
                if not sid:
                    raise RuntimeError("Did not receive session ID from initialize")
                self.session_id = sid
                async for line in resp.aiter_lines():
                    if line.startswith("data: "):
                        dl = line[len("data: "):].strip()
                        if dl == "[DONE]": break
                        try: return json.loads(dl)
                        except: return None
        return None

    async def send_initialized_notification(self):
        if self.session_id is None:
            raise RuntimeError("Session not initialized")
        payload = {"jsonrpc":"2.0","method":"notifications/initialized","params":{},"id":None}
        headers = {
            "Content-Type": "application/json",
            "Accept": "application/json, text/event-stream",
            "User-Agent": "Agentic-RAG-Client/1.0",
            "Mcp-Session-Id": self.session_id,
            "MCP-Protocol-Version": self.protocol_version,
        }
        async with httpx.AsyncClient(timeout=None) as client:
            async with client.stream("POST", self.url, data=json.dumps(payload), headers=headers) as resp:
                resp.raise_for_status()
                async for _ in resp.aiter_lines(): pass

    async def call_tool(self, name: str, arguments: dict, request_id: int):
        if self.session_id is None:
            await self.initialize()
            await self.send_initialized_notification()
        payload = {"jsonrpc":"2.0","method":"tools/call","params":{"name":name,"arguments":arguments},"id":request_id}
        headers = {
            "Content-Type": "application/json",
            "Accept": "application/json, text/event-stream",
            "User-Agent": "Agentic-RAG-Client/1.0",
            "Mcp-Session-Id": self.session_id,
            "MCP-Protocol-Version": self.protocol_version,
        }
        results = []
        async with httpx.AsyncClient(timeout=None) as client:
            async with client.stream("POST", self.url, data=json.dumps(payload), headers=headers) as resp:
                resp.raise_for_status()
                async for line in resp.aiter_lines():
                    if line.startswith("data: "):
                        dl = line[len("data: "):].strip()
                        if dl == "[DONE]": break
                        try:
                            obj = json.loads(dl)
                            results.append(obj)
                        except:
                            results.append({"result": dl})
        return results[-1] if results else None

    async def terminate_session(self):
        if self.session_id is None: return
        headers = {"Mcp-Session-Id": self.session_id, "User-Agent":"Agentic-RAG-Client/1.0"}
        async with httpx.AsyncClient(timeout=None) as client:
            await client.delete(self.url, headers=headers)
        self.session_id = None

MCP_URL = os.getenv("MCP_URL", "http://mcp-server:8000/mcp")
mcp_client = MCPClient(MCP_URL)

# ---------- Helpers ----------
def _parse_mcp_text(result_obj) -> str:
    # tolerate different MCP shapes
    if not result_obj: return ""
    r = result_obj.get("result")
    if isinstance(r, dict):
        content = r.get("content")
        if isinstance(content, list) and content and isinstance(content[0], dict) and "text" in content[0]:
            return content[0]["text"]
        if "text" in r: return r["text"]
    if isinstance(r, str): return r
    return ""

def _make_prompt(question: str, hits: list[dict]) -> str:
    cites = []
    for i,h in enumerate(hits, start=1):
        src = h.get("source") or "unknown"
        pg = f" p.{h.get('page')}" if h.get("page") else ""
        cites.append(f"[{i}] {src}{pg}")
    context = "\n\n".join([f"[{i}] {h['text']}" for i,h in enumerate(hits, start=1)])
    guidelines = (
        "Answer the user question using only the context. "
        "Cite sources in-line like [1], [2]. If unsure, say you couldn't find it.\n"
        "Be precise, concise, and quote exact phrases sparingly when helpful."
    )
    return f"{guidelines}\n\nSOURCES:\n" + "\n".join(cites) + f"\n\nCONTEXT:\n{context}\n\nQUESTION: {question}\n\nANSWER:"

def _extractive_answer(question: str, hits: list[dict]) -> tuple[str, list[dict]]:
    # simple extractive “good enough” fallback: show top 3 chunks as the answer with citations
    top = hits[:3]
    parts = []
    for i,h in enumerate(top, start=1):
        snippet = h["text"].strip()
        if len(snippet) > 600:
            snippet = snippet[:580].rsplit(" ", 1)[0] + "…"
        src = h.get("source") or "unknown"
        pg = f" p.{h.get('page')}" if h.get("page") else ""
        parts.append(f"{snippet} [{i}]")
    answer = "\n\n".join(parts)
    return answer, top



# backend.py
from collections import deque
# ...
RECENT_SOURCES = deque(maxlen=5)  # keep last few uploaded filenames

@app.post("/upload_document/")
async def upload_document(file: UploadFile = File(...)):
    if not file.filename.lower().endswith((".txt", ".pdf")):
        raise HTTPException(status_code=400, detail="Unsupported file type")
    file_path = UPLOAD_DIR / file.filename
    with open(file_path, "wb") as buffer:
        shutil.copyfileobj(file.file, buffer)

    # ingest just this file
    from load_data import ingest_file
    added = ingest_file(file_path)
    if added == 0:
        raise HTTPException(status_code=400, detail="Could not extract text from file (is it scanned?).")

    # remember this filename for scoping
    RECENT_SOURCES.append(file.filename)
    return {"message": f"File '{file.filename}' uploaded and ingested successfully! ({added} chunks)"}

@app.post("/query/")
async def query_agent(payload: QueryRequest):
    q = payload.question.strip()

    # ask MCP to search only in the last uploaded files
    sources = list(RECENT_SOURCES) or None
    doc_result = await mcp_client.call_tool("document_search", {"query": q, "top_k": 8, "sources": sources}, 1)

    # parse the returned JSON hits
    def _parse(obj):
        if not obj: return []
        r = obj.get("result")
        if isinstance(r, dict):
            content = r.get("content")
            if isinstance(content, list) and content and "text" in content[0]:
                try:
                    return json.loads(content[0]["text"]).get("hits", [])
                except:
                    return []
        if isinstance(r, str):
            try:
                return json.loads(r).get("hits", [])
            except:
                return []
        return []

    hits = _parse(doc_result)

    if not hits and sources:
        # If we expected resume content but found nothing, say so explicitly (don't dump web JSON).
        return JSONResponse(content={
            "answer": "I couldn’t find anything about that in the uploaded documents. "
                      "If your document is a scanned PDF, enable OCR or upload a text-based PDF/TXT.",
            "sources": []
        })

    if not hits:
        # fallback (optional): web
        web_result = await mcp_client.call_tool("web_search", {"query": q}, 2)
        # return a simple friendly message rather than raw JSON
        return JSONResponse(content={"answer": "No relevant info in your docs; here are some web results instead.", "web": web_result})

    # Synthesize a concise answer from the  hits (no external web).
    context = "\n\n".join([f"[{i+1}] {h['text']}" for i, h in enumerate(hits[:6])])
    prompt = (
        "Use ONLY the context to answer the user's question. "
        "If the context lacks the info, say you couldn't find it. "
        "Be concise and include inline citations like [1].\n\n"
        f"CONTEXT:\n{context}\n\nQUESTION: {q}\n\nANSWER:"
    )

    openai_key = os.getenv("OPENAI_API_KEY")
    if openai_key:
        try:
            from openai import OpenAI
            client = OpenAI(api_key=openai_key)
            resp = client.chat.completions.create(
                model="gpt-4o",
                messages=[{"role": "user", "content": prompt}],
                temperature=0.2, max_tokens=250
            )
            ans = resp.choices[0].message.content.strip()
            return JSONResponse(content={"answer": ans, "sources": hits[:6]})
        except Exception:
            pass

    # extractive fallback
    snippets = []
    for i, h in enumerate(hits[:3], start=1):
        t = h["text"].strip()
        if len(t) > 500: t = t[:480].rsplit(" ", 1)[0] + "…"
        snippets.append(f"{t} [{i}]")
    return JSONResponse(content={"answer": "\n\n".join(snippets), "sources": hits[:3]})
