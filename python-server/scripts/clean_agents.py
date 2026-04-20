"""
Clears conversation history (responses) stored by the Llama Stack responses API.

In llama-stack 0.7.0, conversation history is stored in sql_store.db.
Run this while the Llama Stack server is STOPPED to avoid conflicts.

Usage:
    poetry run python scripts/clean_agents.py
    poetry run python scripts/clean_agents.py --dry-run
    poetry run python scripts/clean_agents.py --traces   # also clear trace_store.db
"""

import argparse
import sqlite3
from pathlib import Path

DISTRO_DIR = Path.home() / ".llama/distributions/llamastack-NewLlamaStack"
SQL_STORE = DISTRO_DIR / "sql_store.db"
TRACE_STORE = DISTRO_DIR / "trace_store.db"


def clear_db(path: Path, dry_run: bool):
    if not path.exists():
        print(f"  {path.name} not found — skipping")
        return

    try:
        con = sqlite3.connect(path, timeout=3)
        tables = con.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()
        table_names = [t[0] for t in tables]

        total = 0
        for name in table_names:
            count = con.execute(f"SELECT COUNT(*) FROM [{name}]").fetchone()[0]
            print(f"  {path.name} / {name}: {count} row(s)")
            total += count

        if dry_run:
            print(f"  [dry-run] would delete {total} row(s) from {path.name}")
        else:
            for name in table_names:
                con.execute(f"DELETE FROM [{name}]")
            con.commit()
            print(f"  Cleared {total} row(s) from {path.name}")
        con.close()
    except sqlite3.OperationalError as e:
        print(f"  Error reading {path.name}: {e}")
        print("  Stop the Llama Stack server before running this script.")


def main():
    parser = argparse.ArgumentParser(description="Clear Llama Stack conversation history.")
    parser.add_argument("--dry-run", action="store_true", help="Show what would be deleted without deleting")
    parser.add_argument("--traces", action="store_true", help="Also clear trace_store.db")
    args = parser.parse_args()

    if args.dry_run:
        print("Dry run — no changes will be made.\n")

    print("Clearing conversation history (sql_store.db)...")
    clear_db(SQL_STORE, args.dry_run)

    if args.traces:
        print("\nClearing traces (trace_store.db)...")
        clear_db(TRACE_STORE, args.dry_run)

    print("\nDone.")


if __name__ == "__main__":
    main()
