import os
import json
import math
import logging
from typing import List, Dict, Optional

from fastmcp import FastMCP
from chromadb import PersistentClient
from chromadb.utils.embedding_functions import SentenceTransformerEmbeddingFunction
from openai import OpenAI

# --- Logging ---
logger = logging.getLogger("mcp_server")
logging.basicConfig(level=logging.INFO)

# --- Setup ChromaDB / Embedding ---
chromadb_client = PersistentClient(path="./chroma_db")
embedding_func = SentenceTransformerEmbeddingFunction(model_name="all-MiniLM-L6-v2")

try:
    collection = chromadb_client.get_collection(name="docs")
    logger.info("Loaded existing collection 'docs'")
except Exception as e:
    logger.warning("Could not load collection: %s", e)
    collection = chromadb_client.create_collection(
        name="docs", embedding_function=embedding_func
    )
    logger.info("Created new collection 'docs'")


# --- Utils ---
def _cosine_sim(a: List[float], b: List[float]) -> float:
    dot = sum(x * y for x, y in zip(a, b))
    na = math.sqrt(sum(x * x for x in a))
    nb = math.sqrt(sum(y * y for y in b))
    return dot / (na * nb + 1e-9)



def synthesize_answer(query: str, hits: list) -> str:
    """
    Normalize hits (dicts or strings), dedupe, and synthesize an answer via OpenAI.
    """
    from openai import OpenAI
    client = OpenAI(api_key=os.environ.get("OPENAI_API_KEY"))

    # Normalize hits → always list of dicts with "text"
    normalized = []
    for h in hits:
        if isinstance(h, str):  # raw string
            normalized.append({"text": h})
        elif isinstance(h, dict):
            normalized.append(h)

    # Deduplicate chunks
    seen, context_chunks = set(), []
    for h in normalized:
        txt = h.get("text", "").strip()
        if txt and txt[:80] not in seen:
            seen.add(txt[:80])
            context_chunks.append(txt)

    context_text = "\n\n".join(context_chunks) if context_chunks else "No context found."

    resp = client.chat.completions.create(
        model=os.environ.get("OPENAI_MODEL", "gpt-4o"),
        messages=[
            {"role": "system", "content": (
                "You are a helpful assistant answering ONLY from the provided context.\n"
                "- If the user asks for skills, extract them into a clean bullet list.\n"
                "- If the user asks for experience, summarize roles and achievements.\n"
                "- Always add inline citations [1], [2] based on order of chunks.\n"
                "- If nothing matches, reply 'Not found in documents.'"
            )},
            {"role": "user", "content": f"Question: {query}\n\nContext:\n{context_text}"}
        ],
        temperature=0,
        max_tokens=400
    )
    return resp.choices[0].message.content.strip()



# --- MCP Server ---
def create_mcp_server() -> FastMCP:
    mcp = FastMCP("agentic-rag-server")

    @mcp.tool
    def document_search(query: str, top_k: int = 8, sources: Optional[List[str]] = None) -> str:
        """
        Search ChromaDB for relevant chunks. 
        If no hits, fall back to web_search.
        Returns: {"answer": str, "hits": List[Dict]}
        """
        logger.info("document_search called with query='%s', sources=%s", query, sources)

        include = ["documents", "metadatas", "distances"]
        where = {"source": {"$in": sources}} if sources else None

        hits = []
        try:
            raw = collection.query(
                query_texts=[query],
                n_results=max(20, top_k * 3),
                include=include,
                where=where
            )
            docs = raw.get("documents", [[]])[0]
            metas = raw.get("metadatas", [[]])[0]
            dists = raw.get("distances", [[]])[0]

            count = min(len(docs), len(metas), len(dists))
            pairs = list(zip(docs[:count], metas[:count], dists[:count]))
            pairs = sorted(pairs, key=lambda x: x[2])[:top_k]

            seen = set()
            for d, m, dist in pairs:
                txt = (d or "").strip()
                if not txt or txt[:100] in seen:
                    continue
                seen.add(txt[:100])
                hits.append({
                    "text": txt,
                    "source": m.get("source"),
                    "page": m.get("page"),
                    "id": m.get("chunk_id"),
                    "score": 1.0 / (1.0 + (dist or 0.0))
                })
        except Exception as e:
            logger.error("Chroma query error: %s", e, exc_info=True)

        # If hits found → synthesize from docs
        if hits:
            answer = synthesize_answer(query, [h["text"] for h in hits])
            return json.dumps({"answer": answer, "hits": hits})

        # Fallback: Web search
        logger.info("No doc hits, falling back to web search for query='%s'", query)
        try:
            res = web_search(query)
            parsed = json.loads(res)
            web_hits = parsed.get("hits", [])
            if web_hits:
                answer_web = synthesize_answer(query, [h.get("snippet", "") or h.get("body", "") for h in web_hits])
                return json.dumps({"answer": "From web: " + answer_web, "hits": web_hits})
        except Exception as e:
            logger.error("Web search fallback failed: %s", e, exc_info=True)

        return json.dumps({"answer": "I couldn’t find anything in documents or web search.", "hits": []})

    @mcp.tool
    def web_search(query: str) -> str:
        """
        Fallback web search using Serper.dev API.
        Returns: {"hits": List[Dict]} with title, link, snippet.
        """
        logger.info("web_search called with query='%s'", query)
        api_key = os.getenv("SERPER_API_KEY")
        if not api_key:
            return json.dumps({"error": "SERPER_API_KEY not configured"})

        url = "https://google.serper.dev/search"
        headers = {"X-API-KEY": api_key, "Content-Type": "application/json"}
        payload = json.dumps({"q": query})

        try:
            import requests
            resp = requests.post(url, headers=headers, data=payload)
            resp.raise_for_status()
            data = resp.json()
            results = data.get("organic", [])[:5]
            return json.dumps({"hits": results})
        except Exception as e:
            logger.error("Web search failed: %s", e, exc_info=True)
            return json.dumps({"error": f"Web search failed: {e}"})

    return mcp


mcp = create_mcp_server()

if __name__ == "__main__":
    mcp.run(transport="http", host="0.0.0.0", port=8000)
