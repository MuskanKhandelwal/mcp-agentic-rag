# import os
# from pathlib import Path
# from chromadb import PersistentClient
# from chromadb.utils.embedding_functions import SentenceTransformerEmbeddingFunction
# from pypdf import PdfReader

# # Paths
# DATA_DIR = Path("data/sample_docs")

# def load_txt(file_path: Path) -> str:
#     """Load a .txt file into a string"""
#     with open(file_path, "r", encoding="utf-8") as f:
#         return f.read()

# def load_pdf(file_path: Path) -> str:
#     """Extract text from a PDF"""
#     reader = PdfReader(str(file_path))
#     text = []
#     for page in reader.pages:
#         text.append(page.extract_text() or "")
#     return "\n".join(text)


# def ingest_documents():
#     # Set up ChromaDB with embeddings and persistence
#     embedding_func = SentenceTransformerEmbeddingFunction(model_name="all-MiniLM-L6-v2")
#     client = PersistentClient(path="./chroma_db")
#     try:
#         collection = client.get_collection(name="docs")
#     except Exception:
#         collection = client.create_collection(name="docs", embedding_function=embedding_func)

#     # Scan folder for .txt and .pdf files
#     docs, ids = [], []
#     for file_path in DATA_DIR.glob("*"):
#         if file_path.suffix.lower() == ".txt":
#             content = load_txt(file_path)
#         elif file_path.suffix.lower() == ".pdf":
#             content = load_pdf(file_path)
#         else:
#             continue  # skip unsupported file types

#         if content.strip():
#             docs.append(content)
#             ids.append(file_path.stem)  # filename without extension

#     if docs:
#         collection.add(documents=docs, ids=ids)
#         print(f"Loaded {len(docs)} documents into ChromaDB")
#     else:
#         print("No valid documents found in data/sample_docs")



# if __name__ == "__main__":
#     ingest_documents()



# import os
# from pathlib import Path
# from chromadb import PersistentClient
# from chromadb.utils.embedding_functions import SentenceTransformerEmbeddingFunction
# from pypdf import PdfReader

# DATA_DIR = Path("data/sample_docs")

# def _chunk_text(text: str, chunk_size: int = 900, overlap: int = 150):
#     chunks = []
#     start = 0
#     n = len(text)
#     while start < n:
#         end = min(n, start + chunk_size)
#         # avoid splitting mid-sentence if possible
#         slice_ = text[start:end]
#         last_period = slice_.rfind(". ")
#         if last_period > chunk_size * 0.5:
#             end = start + last_period + 1
#             slice_ = text[start:end]
#         chunks.append(slice_.strip())
#         start = max(end - overlap, start + 1)
#     return [c for c in chunks if c]

# def _pdf_to_chunks(file_path: Path, **kw):
#     reader = PdfReader(str(file_path))
#     all_chunks, all_meta = [], []
#     for page_idx, page in enumerate(reader.pages, start=1):
#         page_text = page.extract_text() or ""
#         for i, ch in enumerate(_chunk_text(page_text, **kw)):
#             all_chunks.append(ch)
#             all_meta.append({
#                 "source": file_path.name,
#                 "page": page_idx,
#                 "chunk_id": f"{file_path.stem}-p{page_idx}-c{i}"
#             })
#     return all_chunks, all_meta

# def _txt_to_chunks(file_path: Path, **kw):
#     txt = file_path.read_text(encoding="utf-8", errors="ignore")
#     chunks = _chunk_text(txt, **kw)
#     metas = [{
#         "source": file_path.name,
#         "page": None,
#         "chunk_id": f"{file_path.stem}-c{i}"
#     } for i in range(len(chunks))]
#     return chunks, metas

# def ingest_documents():
#     embedding_func = SentenceTransformerEmbeddingFunction(model_name="all-MiniLM-L6-v2")
#     client = PersistentClient(path="./chroma_db")
#     try:
#         collection = client.get_collection(name="docs")
#     except Exception:
#         collection = client.create_collection(name="docs", embedding_function=embedding_func)

#     docs, ids, metas = [], [], []
#     for file_path in DATA_DIR.glob("*"):
#         if file_path.suffix.lower() == ".txt":
#             ch, md = _txt_to_chunks(file_path)
#         elif file_path.suffix.lower() == ".pdf":
#             ch, md = _pdf_to_chunks(file_path)
#         else:
#             continue
#         if ch:
#             base = file_path.stem
#             docs.extend(ch)
#             metas.extend(md)
#             ids.extend([m["chunk_id"] for m in md])

#     if docs:
#         collection.add(documents=docs, metadatas=metas, ids=ids)
#         print(f"Loaded {len(docs)} chunks into ChromaDB")
#     else:
#         print("No valid documents found in data/sample_docs")

# if __name__ == "__main__":
#     ingest_documents()





# # load_data.py
# from pathlib import Path
# from chromadb import PersistentClient
# from chromadb.utils.embedding_functions import SentenceTransformerEmbeddingFunction
# from pypdf import PdfReader
# from uuid import uuid4
# import re

# def _reflow(text: str) -> str:
#     # normalize newlines
#     t = text.replace("\r", "")
#     # remove hyphenation across line breaks: "predict-\nive" -> "predictive"
#     t = re.sub(r"-\n(?=\w)", "", t)
#     # join single line breaks inside paragraphs into spaces (keep blank lines)
#     t = re.sub(r"(?<!\n)\n(?!\n)", " ", t)
#     # collapse multi spaces
#     t = re.sub(r"[ \t]+", " ", t)
#     # squeeze 3+ newlines to just 2
#     t = re.sub(r"\n{3,}", "\n\n", t)
#     return t.strip()

# def _pdf_text(file_path: Path) -> str:
#     try:
#         reader = PdfReader(str(file_path))
#         raw = "\n".join((p.extract_text() or "") for p in reader.pages)
#         return _reflow(raw)              # <— reflow here
#     except Exception:
#         return ""

# def _chunk_text(text: str, chunk_size: int = 900, overlap: int = 150):
#     chunks, start, n = [], 0, len(text)
#     while start < n:
#         end = min(n, start + chunk_size)
#         slice_ = text[start:end]
#         last_period = slice_.rfind(". ")
#         if last_period > chunk_size * 0.5:
#             end = start + last_period + 1
#             slice_ = text[start:end]
#         slice_ = (slice_ or "").strip()
#         if slice_:
#             chunks.append(slice_)
#         start = max(end - overlap, start + 1)
#     return chunks

# # def _pdf_text(file_path: Path) -> str:
# #     try:
# #         reader = PdfReader(str(file_path))
# #         return "\n".join((p.extract_text() or "") for p in reader.pages)
# #     except Exception:
# #         return ""

# def _to_chunks_with_meta(file_path: Path):
#     ext = file_path.suffix.lower()
#     if ext == ".pdf":
#         txt = _pdf_text(file_path)
#     elif ext == ".txt":
#         txt = _reflow(file_path.read_text(encoding="utf-8", errors="ignore"))
#     else:
#         return [], []
#     chunks = _chunk_text(txt)

#     # NO None values in metadata. Also make IDs globally unique.
#     uid = uuid4().hex
#     metas = [{
#         "source": str(file_path.name),    # string
#         "page": -1,                       # int placeholder instead of None
#         "chunk_id": f"{file_path.stem}-{uid}-c{i}"  # unique per upload
#     } for i in range(len(chunks))]
#     return chunks, metas

# def _get_collection():
#     embedding_func = SentenceTransformerEmbeddingFunction(model_name="all-MiniLM-L6-v2")
#     client = PersistentClient(path="./chroma_db")
#     try:
#         col = client.get_collection(name="docs")
#     except Exception:
#         col = client.create_collection(name="docs", embedding_function=embedding_func)
#     return col

# def ingest_file(file_path: Path) -> int:
#     col = _get_collection()
#     chunks, metas = _to_chunks_with_meta(file_path)
#     if not chunks:
#         return 0
#     ids = [m["chunk_id"] for m in metas]
#     # ensure every metadata value is a supported primitive
#     for m in metas:
#         for k, v in list(m.items()):
#             if v is None:
#                 del m[k]                 # <- or set to "" / 0; but no None
#     col.add(documents=chunks, metadatas=metas, ids=ids)
#     return len(chunks)



# # at top


from pathlib import Path
from chromadb import PersistentClient
from chromadb.utils.embedding_functions import SentenceTransformerEmbeddingFunction
from pypdf import PdfReader
from uuid import uuid4
import re
import logging

logger = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO)

def _reflow(text: str) -> str:
    t = text.replace("\r", "")
    t = re.sub(r"-\n(?=\w)", "", t)
    t = re.sub(r"(?<!\n)\n(?!\n)", " ", t)
    t = re.sub(r"[ \t]+", " ", t)
    t = re.sub(r"\n{3,}", "\n\n", t)
    return t.strip()

def _pdf_text(file_path: Path) -> str:
    try:
        reader = PdfReader(str(file_path))
        raw = "\n".join((p.extract_text() or "") for p in reader.pages)
        return _reflow(raw)
    except Exception as e:
        logger.error("Failed to extract PDF text for %s: %s", file_path, e)
        return ""

def _chunk_text(text: str, chunk_size: int = 900, overlap: int = 150):
    chunks = []
    start = 0
    n = len(text)
    while start < n:
        end = min(n, start + chunk_size)
        slice_ = text[start:end]
        last_period = slice_.rfind(". ")
        if last_period > chunk_size * 0.5:
            end = start + last_period + 1
            slice_ = text[start:end]
        slice_ = slice_.strip()
        if slice_:
            chunks.append(slice_)
        start = max(end - overlap, start + 1)
    return chunks

def _to_chunks_with_meta(file_path: Path):
    ext = file_path.suffix.lower()
    if ext == ".pdf":
        txt = _pdf_text(file_path)
    elif ext == ".txt":
        raw = file_path.read_text(encoding="utf-8", errors="ignore")
        txt = _reflow(raw)
    else:
        return [], []
    chunks = _chunk_text(txt)
    uid = uuid4().hex
    metas = []
    ids = []
    for i, ch in enumerate(chunks):
        meta = {
            "source": file_path.name,
            "page": -1,  # using -1 instead of None
            "chunk_id": f"{file_path.stem}-{uid}-c{i}"
        }
        metas.append(meta)
        ids.append(meta["chunk_id"])
    return chunks, metas, ids

def _get_collection():
    embedding_func = SentenceTransformerEmbeddingFunction(model_name="all-MiniLM-L6-v2")
    client = PersistentClient(path="./chroma_db")
    try:
        col = client.get_collection(name="docs")
        logger.info("Got existing Chroma collection 'docs'")
    except Exception as e:
        logger.warning("Could not get existing collection: %s. Creating new one.", e)
        col = client.create_collection(name="docs", embedding_function=embedding_func)
    return col

def ingest_file(file_path: Path) -> int:
    col = _get_collection()
    chunks, metas, ids = _to_chunks_with_meta(file_path)
    if not chunks:
        logger.warning("No chunks generated for file %s", file_path)
        return 0
    # Sanitization: no None in metadata values
    for m in metas:
        for k, v in list(m.items()):
            if v is None:
                # Remove or set to default
                del m[k]
    try:
        col.add(documents=chunks, metadatas=metas, ids=ids)
        logger.info("Ingested %d chunks from %s", len(chunks), file_path)
        return len(chunks)
    except Exception as e:
        logger.error("Error adding to Chroma collection for file %s: %s", file_path, e, exc_info=True)
        return 0

def ingest_documents_in_dir(dir_path: Path):
    count = 0
    for fp in dir_path.glob("*"):
        if fp.suffix.lower() not in {".pdf", ".txt"}:
            continue
        added = ingest_file(fp)
        count += added
    logger.info("Total chunks ingested from %s: %d", dir_path, count)
    return count

# If run as script
if __name__ == "__main__":
    import sys
    path = Path(sys.argv[1]) if len(sys.argv) > 1 else Path("data/sample_docs")
    ingest_documents_in_dir(path)
