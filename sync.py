#!/usr/bin/env python3
"""
sync.py — Full two-way sync: Railway → local trades.db

Railway is the master. Local mirrors it exactly:
  - New rows on Railway   → inserted locally
  - Updated rows          → updated locally
  - Deleted rows          → deleted locally

Usage:
  python sync.py                    # sync from Railway
  python sync.py --dry-run          # show what would change, don't write

Scheduled via launchd to run every night at 2am.
"""

import argparse
import json
import os
import sqlite3
import sys
from datetime import datetime, timezone

RAILWAY_URL = "https://forex-agent.up.railway.app"
LOCAL_DB    = os.path.join(os.path.dirname(__file__), "logs", "trades.db")
LOG_FILE    = os.path.join(os.path.dirname(__file__), "logs", "sync.log")


def log(msg: str):
    ts  = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")
    line = f"[{ts}] {msg}"
    print(line)
    os.makedirs(os.path.dirname(LOG_FILE), exist_ok=True)
    with open(LOG_FILE, "a") as f:
        f.write(line + "\n")


def fetch_railway() -> dict:
    try:
        import requests
    except ImportError:
        log("ERROR: requests not installed. Run: pip install requests")
        sys.exit(1)

    url = RAILWAY_URL.rstrip("/") + "/api/export"
    log(f"Fetching {url} ...")
    resp = requests.get(url, timeout=30)
    resp.raise_for_status()
    return resp.json()


def get_local_conn() -> sqlite3.Connection:
    conn = sqlite3.connect(LOCAL_DB)
    conn.row_factory = sqlite3.Row
    return conn


def sync_table(conn: sqlite3.Connection, table: str, railway_rows: list, id_col: str, dry_run: bool):
    """
    Sync one table. Railway is master:
      1. Upsert all Railway rows into local
      2. Delete local rows whose IDs are not in Railway
    """
    if not railway_rows:
        log(f"  {table}: 0 rows from Railway — skipping")
        return

    railway_ids = {str(r[id_col]) for r in railway_rows}

    # Get local IDs
    local_ids = {str(r[0]) for r in conn.execute(f"SELECT {id_col} FROM {table}").fetchall()}

    to_delete = local_ids - railway_ids
    cols      = list(railway_rows[0].keys())
    ph        = ", ".join("?" * len(cols))
    col_str   = ", ".join(cols)
    update_ph = ", ".join(f"{c}=excluded.{c}" for c in cols if c != id_col)

    inserted = updated = deleted = 0

    if not dry_run:
        # Upsert all Railway rows
        for row in railway_rows:
            vals = [row.get(c) for c in cols]
            conn.execute(
                f"INSERT INTO {table} ({col_str}) VALUES ({ph}) "
                f"ON CONFLICT({id_col}) DO UPDATE SET {update_ph}",
                vals
            )
            if str(row[id_col]) in local_ids:
                updated += 1
            else:
                inserted += 1

        # Delete rows not in Railway
        for rid in to_delete:
            conn.execute(f"DELETE FROM {table} WHERE {id_col} = ?", (rid,))
            deleted += 1

        conn.commit()
    else:
        inserted = len(railway_ids - local_ids)
        updated  = len(railway_ids & local_ids)
        deleted  = len(to_delete)

    log(f"  {table}: +{inserted} inserted, ~{updated} updated, -{deleted} deleted")


def main():
    parser = argparse.ArgumentParser(description="Sync Railway DB → local trades.db")
    parser.add_argument("--dry-run", action="store_true", help="Show changes without writing")
    args = parser.parse_args()

    log("=" * 50)
    log(f"Sync started {'(DRY RUN) ' if args.dry_run else ''}— Railway → local")

    try:
        data = fetch_railway()
    except Exception as e:
        log(f"ERROR fetching Railway data: {e}")
        sys.exit(1)

    counts = data.get("counts", {})
    log(f"Railway has: {counts.get('agent_signals', '?')} agent signals, {counts.get('manual_trades', '?')} manual trades")

    conn = get_local_conn()

    sync_table(conn, "agent_signals", data.get("agent_signals", []), "signal_id", args.dry_run)
    sync_table(conn, "manual_trades", data.get("manual_trades", []), "signal_id", args.dry_run)

    conn.close()
    log("Sync complete.")
    log("=" * 50)


if __name__ == "__main__":
    main()
