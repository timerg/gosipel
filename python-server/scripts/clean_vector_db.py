"""
Deletes the RAG vector DB from the running Llama Stack server.
Also removes the local docs/.index_manifest.json.

Use --hard to also delete the physical faiss_store.db file (requires
the Llama Stack server to be STOPPED first).

Usage:
    poetry run python scripts/clean_vector_db.py
    poetry run python scripts/clean_vector_db.py --hard   # full reset including physical file
    poetry run python scripts/clean_vector_db.py --config configs/rag-config.json
"""

import argparse
import json
import os
from pathlib import Path

from llama_stack_client import LlamaStackClient

SERVER_URL = os.environ.get("SERVER_URL", "http://localhost:8321")
DISTRO_DIR = Path.home() / ".llama/distributions/llamastack-NewLlamaStack"


def main(config: dict, docs_dir: str = "docs", hard: bool = False):
    vector_db_name = config["vector_db_id"]
    manifest_path = Path(docs_dir) / ".index_manifest.json"

    # Read vector_store_id from manifest (server-assigned ID)
    vector_store_id = None
    if manifest_path.exists():
        try:
            manifest = json.loads(manifest_path.read_text())
            vector_store_id = manifest.get("vector_store_id")
        except Exception:
            pass

    if not hard:
        if not vector_store_id:
            print(f"No vector store ID found in manifest for '{vector_db_name}' — nothing to delete.")
        else:
            with LlamaStackClient(base_url=SERVER_URL) as client:
                try:
                    client.vector_stores.delete(vector_store_id=vector_store_id)
                    print(f"Deleted vector store '{vector_db_name}' (id={vector_store_id}).")
                except Exception as e:
                    if "not found" in str(e).lower():
                        print(f"Vector store '{vector_store_id}' not found on server — may already be deleted.")
                    else:
                        raise
    else:
        for db_file in ["kvstore.db", "sql_store.db"]:
            path = DISTRO_DIR / db_file
            if path.exists():
                path.unlink()
                print(f"Deleted {path}")
            else:
                print(f"{db_file} not found at {path} — skipping.")

    manifest_path = Path(docs_dir) / ".index_manifest.json"
    if manifest_path.exists():
        manifest_path.unlink()
        print(f"Deleted {manifest_path}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Delete the RAG vector DB and index manifest.")
    parser.add_argument("--config", default="configs/rag-config.json", help="Path to RAG config JSON")
    parser.add_argument("--docs-dir", default="docs", help="Path to docs folder (default: docs)")
    parser.add_argument("--hard", action="store_true", help="Also delete the physical faiss_store.db (stop Llama Stack server first)")
    args = parser.parse_args()

    cfg = json.loads(Path(args.config).read_text())
    main(config=cfg, docs_dir=args.docs_dir, hard=args.hard)
