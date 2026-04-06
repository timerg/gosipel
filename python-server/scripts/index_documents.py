"""
Index documents from the docs/ folder into the FAISS vector DB.

Run this script manually whenever documents in docs/ are added or updated.
The Llama Stack server must be running before indexing.

Usage:
    poetry run python scripts/index_documents.py
    poetry run python scripts/index_documents.py --docs-dir path/to/docs
"""

import argparse
from http import client
import json
import os
import re
import sys
import signal
from datetime import datetime, timezone
from pathlib import Path

from llama_stack_client import LlamaStackClient

SERVER_URL = os.environ.get("SERVER_URL", "http://localhost:8321")


# ---------------------------------------------------------------------------
# Text extraction
# ---------------------------------------------------------------------------

def _extract_txt(path: Path) -> str:
    return path.read_text(encoding="utf-8", errors="replace")


def _extract_pdf(path: Path) -> str:
    try:
        from pypdf import PdfReader
    except ImportError:
        print(f"  [skip] {path.name}: pypdf not installed. Run: poetry add pypdf")
        return ""
    reader = PdfReader(str(path))
    return "\n\n".join(page.extract_text() or "" for page in reader.pages)


def _extract_urls(path: Path) -> str:
    try:
        import httpx
        from bs4 import BeautifulSoup
    except ImportError:
        print(f"  [skip] {path.name}: httpx/beautifulsoup4 not installed. Run: poetry add httpx beautifulsoup4")
        return ""

    parts = []
    for line in path.read_text(encoding="utf-8").splitlines():
        url = line.strip()
        if not url or url.startswith("#"):
            continue
        try:
            resp = httpx.get(url, timeout=10, follow_redirects=True)
            resp.raise_for_status()
            soup = BeautifulSoup(resp.text, "html.parser")
            for tag in soup(["script", "style", "nav", "footer"]):
                tag.decompose()
            text = soup.get_text(separator="\n")
            text = re.sub(r"\n{3,}", "\n\n", text).strip()
            parts.append(f"[Source: {url}]\n{text}")
            print(f"    fetched {url} ({len(text)} chars)")
        except Exception as e:
            print(f"    [warn] failed to fetch {url}: {e}")
    return "\n\n".join(parts)


def _extract_text(path: Path) -> str:
    suffix = path.suffix.lower()
    if suffix == ".pdf":
        return _extract_pdf(path)
    if path.name == "urls.txt":
        return _extract_urls(path)
    return _extract_txt(path)


# ---------------------------------------------------------------------------
# Chunking
# ---------------------------------------------------------------------------

def _chunk_text(text: str, chunk_size: int, overlap: int) -> list[str]:
    """Split text into overlapping chunks by approximate token count (chars/4)."""
    char_size = chunk_size * 4
    char_overlap = overlap * 4
    step = char_size - char_overlap

    chunks = []
    start = 0
    while start < len(text):
        end = start + char_size
        chunk = text[start:end].strip()
        if chunk:
            chunks.append(chunk)
        start += step
    return chunks


# ---------------------------------------------------------------------------
# Manifest
# ---------------------------------------------------------------------------

def _load_manifest(docs_dir: Path) -> dict:
    manifest_path = docs_dir / ".index_manifest.json"
    if manifest_path.exists():
        try:
            return json.loads(manifest_path.read_text())
        except Exception:
            pass
    return {}


def _save_manifest(docs_dir: Path, manifest: dict):
    manifest_path = docs_dir / ".index_manifest.json"
    manifest_path.write_text(json.dumps(manifest, indent=2))


class ChunkingError(Exception):
    def __init__(self, error: Exception, chunk_index=None):
        super().__init__(str(error))
        self.chunk_index = chunk_index
        self.original_error = error


def insert_chunks(client: LlamaStackClient, vector_db_id: str, chunk_objects: list[dict], batch_size: int, start_from: int = 0):
    total_batches = -(-len(chunk_objects) // batch_size)
    print(f"    inserting {len(chunk_objects)} chunk(s) into vector DB '{vector_db_id}'" + (f" (resuming from chunk {start_from})" if start_from else ""))

    # Defer Ctrl+C to between batches so we never interrupt a FAISS write mid-flight.
    interrupted = False

    def _handle_sigint(s, f):
        nonlocal interrupted
        interrupted = True
        print("\n    [interrupt received] finishing current batch before stopping...")

    original_handler = signal.signal(signal.SIGINT, _handle_sigint)

    try:
        for i in range(0, len(chunk_objects), batch_size):
            if i < start_from:
                continue
            if interrupted:
                raise ChunkingError(KeyboardInterrupt(), chunk_index=i)
            batch_num = i // batch_size + 1
            print(f"    inserting batch {batch_num}/{total_batches}...")
            batch = chunk_objects[i:i + batch_size]
            client.vector_io.insert(
                vector_db_id=vector_db_id,
                chunks=batch
            )
            print(f"    inserted batch {batch_num}/{total_batches}")
    except ChunkingError:
        raise
    except Exception as e:
        print(f"    [error] failed at batch {batch_num}: {e}, first chunk: {batch[0]['metadata']['document_id']} ({len(batch[0]['content'])} chars)")
        raise ChunkingError(e, chunk_index=i)
    finally:
        signal.signal(signal.SIGINT, original_handler)




# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main(config: dict, docs_dir: str = "docs", override: bool = False):
    """
    Index documents into the FAISS vector DB.

    Args:
        config: RAG configuration dict with keys:
                vector_db_id, embedding_model, embedding_dimension,
                chunk_size, chunk_overlap
        docs_dir: Path to the folder containing documents to index.
        override: If True, re-index all documents even if they are in the manifest.
    """
    vector_db_id = config["vector_db_id"]
    embedding_model = config["embedding_model"]
    embedding_dimension = config["embedding_dimension"]
    chunk_size = config["chunk_size"]
    chunk_overlap = config["chunk_overlap"]
    batch_size = config.get("batch_size", 7)

    docs_path = Path(docs_dir)
    if not docs_path.exists():
        print(f"docs/ folder not found at: {docs_path.resolve()}")
        print("Create it and add .txt, .md, .pdf, or urls.txt files.")
        sys.exit(1)

    files = [
        f for f in sorted(docs_path.iterdir())
        if f.is_file() and not f.name.startswith(".")
    ]
    if not files:
        print(f"No documents found in {docs_path.resolve()}")
        sys.exit(0)

    with LlamaStackClient(base_url=SERVER_URL) as client:
        # Register vector DB (idempotent)
        try:
            client.vector_dbs.register(
                vector_db_id=vector_db_id,
                embedding_model=embedding_model,
                embedding_dimension=embedding_dimension,
                provider_id="faiss",
            )
            print(f"Vector DB '{vector_db_id}' registered.")
        except Exception as e:
            if "already" in str(e).lower() or "exists" in str(e).lower():
                print(f"Vector DB '{vector_db_id}' already registered.")
            else:
                raise

        manifest = _load_manifest(docs_path)
        total_chunks = 0
        indexed_files = 0

        for file_path in files:
            entry = manifest.get(file_path.name, {})
            status = entry.get("status")

            if status == "complete" and not override:
                print(f"  [skip] {file_path.name}: already indexed")
                continue

            start_from = 0
            if status in ("error", "processing") and not override:
                start_from = entry.get("chunk_index", 0)
                print(f"  [resume] {file_path.name}: resuming from chunk {start_from}")
            else:
                print(f"  processing {file_path.name}...")
            text = _extract_text(file_path)
            if not text.strip():
                print(f"    [skip] empty content")
                continue

            chunks = _chunk_text(text, chunk_size, chunk_overlap)

            print(f"    extracted {len(text)} chars, split into {len(chunks)} chunk(s)")

            if not chunks:
                continue

            chunk_objects = [
                {
                    "content": chunk,
                    "metadata": {
                        "document_id": f"{file_path.stem}_{i}",
                        "source": file_path.name,
                    },
                }
                for i, chunk in enumerate(chunks)
            ]

            manifest[file_path.name] = {
                "status": "processing",
                "chunks": len(chunks),
                "indexed_at": None,
            }
            _save_manifest(docs_path, manifest)


            try:
                insert_chunks(client, vector_db_id, chunk_objects, batch_size, start_from=start_from)

            except ChunkingError as e:
                manifest[file_path.name] = {
                    "status": "error",
                    "error": str(e.original_error),
                    "chunk_index": e.chunk_index,
                }
                _save_manifest(docs_path, manifest)
                raise e.original_error

            manifest[file_path.name] = {
                "status": "complete",
                "indexed_at": datetime.now(timezone.utc).isoformat(),
                "chunks": len(chunks),
            }
            _save_manifest(docs_path, manifest)

            total_chunks += len(chunks)
            indexed_files += 1
            print(f"    indexed {len(chunks)} chunk(s)")

        print(f"\nDone. Indexed {total_chunks} chunk(s) from {indexed_files} document(s).")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Index documents into the FAISS vector DB.")
    parser.add_argument("--docs-dir", default="docs", help="Path to docs folder (default: docs)")
    parser.add_argument("--config", default="configs/rag-config.json", help="Path to RAG config JSON (default: configs/rag-config.json)")
    parser.add_argument("--override", action="store_true", help="Override existing indexed documents")
    args = parser.parse_args()

    cfg = json.loads(Path(args.config).read_text())
    main(config=cfg, docs_dir=args.docs_dir, override=args.override)
