"""
Wipes all agents and sessions from the Llama Stack agents_store.db.
Also removes the local .service_state.json.

Run this while the LS server is STOPPED to avoid conflicts.
Usage: python clean_up.py [--dry-run]
"""

import argparse
from contextlib import contextmanager
import sqlite3
from pathlib import Path

AGENTS_DB = Path.home() / ".llama/distributions/llamastack-NewLlamaStack/agents_store.db"
STATE_FILE = Path(__file__).parent / ".service_state.json"

def with_sqlite3(func):
    def wrapper(*args, **kwargs):
        con = sqlite3.connect(AGENTS_DB, timeout=3)
        try:
            return func(con, *args, **kwargs)
        finally:
            con.close()
    return wrapper


@with_sqlite3
def main(con):
    parser = argparse.ArgumentParser()
    parser.add_argument("--dry-run", action="store_true", help="Show what would be deleted without deleting")
    args = parser.parse_args()

    if not AGENTS_DB.exists():
        print(f"DB not found: {AGENTS_DB}")
        return

    try:
        with con:
            cur = con.cursor()
            rows = cur.execute("SELECT key FROM kvstore").fetchall()
    except sqlite3.OperationalError as e:
        print(f"Error: {e}")
        print("Stop the Llama Stack server before running this script.")
        return

    agents = [r[0] for r in rows if r[0].startswith("agent:")]
    sessions = [r[0] for r in rows if not r[0].startswith("agent:")]

    print(f"Found {len(agents)} agent(s), {len(sessions)} other entry(s) in agents_store.db")

    print("Double-check the entries below before continuing.")

    if not args.dry_run:
        confirm = input("Type 'yes' to confirm deletion: ").strip().lower()
        if confirm != "yes":
            print("Aborted. No changes made.")
            return

    for key in agents:
        print(f"  {key}")

    if not args.dry_run:
        try:
            cur.execute("DELETE FROM kvstore")
            con.commit()
            print("Deleted all rows from agents_store.db")
        except sqlite3.OperationalError as e:
            print(f"Error: {e}")
            print("Stop the Llama Stack server before running this script.")
            return
    else:
        print("[dry-run] No changes made")

    if STATE_FILE.exists():
        if not args.dry_run:
            STATE_FILE.unlink()
            print(f"Deleted {STATE_FILE}")
        else:
            print(f"[dry-run] Would delete {STATE_FILE}")


if __name__ == "__main__":
    main()
