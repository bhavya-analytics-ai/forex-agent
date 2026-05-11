#!/usr/bin/env python3
"""
sync.py — Full Railway → local mirror. All 4 tables.

Railway is the master. Local mirrors it exactly:
  - New rows on Railway   → inserted locally
  - Updated rows          → updated locally
  - Deleted rows          → deleted locally

Tables synced:
  agent_signals    (signal_id PK)
  manual_trades    (signal_id PK)
  level_edits      (id PK)       — every SL/TP change, source, oanda_synced
  journal_entries  (id PK)       — session diary entries

Usage:
  python sync.py              # full sync
  python sync.py --dry-run    # show what would change, don't write

Scheduled via launchd: nightly 2am + on Mac login.
Logs to logs/sync.log
"""

import argparse
import os
import sqlite3
import sys
from datetime import datetime, timezone

RAILWAY_URL = "https://forex-agent.up.railway.app"
LOCAL_DB    = os.path.join(os.path.dirname(__file__), "logs", "trades.db")
LOG_FILE    = os.path.join(os.path.dirname(__file__), "logs", "sync.log")


def log(msg: str):
    ts   = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")
    line = f"[{ts}] {msg}"
    print(line)
    os.makedirs(os.path.dirname(LOG_FILE), exist_ok=True)
    with open(LOG_FILE, "a") as f:
        f.write(line + "\n")


def fetch_railway() -> dict:
    try:
        import requests
    except ImportError:
        log("ERROR: pip install requests")
        sys.exit(1)
    url = RAILWAY_URL.rstrip("/") + "/api/export"
    log(f"Fetching {url} ...")
    resp = requests.get(url, timeout=60)
    resp.raise_for_status()
    return resp.json()


def get_local_conn() -> sqlite3.Connection:
    conn = sqlite3.connect(LOCAL_DB)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA busy_timeout=5000")
    return conn


def ensure_local_tables(conn: sqlite3.Connection):
    """Make sure all 4 tables exist locally (in case local DB is fresh)."""
    sys.path.insert(0, os.path.dirname(__file__))
    from db.database import init_db as _init
    _init()   # creates tables + runs migrations on local DB


def sync_table(conn: sqlite3.Connection, table: str, railway_rows: list,
               id_col: str, dry_run: bool) -> dict:
    """
    Sync one table. Railway is master.
    Returns dict with inserted/updated/deleted counts.
    """
    if not railway_rows:
        log(f"  {table}: 0 rows from Railway")
        return {"inserted": 0, "updated": 0, "deleted": 0}

    railway_ids = {str(r[id_col]) for r in railway_rows}
    local_ids   = {str(r[0]) for r in conn.execute(
        f"SELECT {id_col} FROM {table}").fetchall()}

    to_delete = local_ids - railway_ids
    cols      = list(railway_rows[0].keys())
    ph        = ", ".join("?" * len(cols))
    col_str   = ", ".join(f'"{c}"' for c in cols)
    update_ph = ", ".join(f'"{c}"=excluded."{c}"' for c in cols if c != id_col)

    inserted = updated = deleted = 0

    if not dry_run:
        for row in railway_rows:
            vals = [row.get(c) for c in cols]
            conn.execute(
                f'INSERT INTO "{table}" ({col_str}) VALUES ({ph}) '
                f'ON CONFLICT("{id_col}") DO UPDATE SET {update_ph}',
                vals
            )
            if str(row[id_col]) in local_ids:
                updated += 1
            else:
                inserted += 1
        for rid in to_delete:
            conn.execute(f'DELETE FROM "{table}" WHERE "{id_col}" = ?', (rid,))
            deleted += 1
        conn.commit()
    else:
        inserted = len(railway_ids - local_ids)
        updated  = len(railway_ids & local_ids)
        deleted  = len(to_delete)

    log(f"  {table}: +{inserted} new  ~{updated} updated  -{deleted} deleted")
    return {"inserted": inserted, "updated": updated, "deleted": deleted}


def print_health(conn: sqlite3.Connection, railway_counts: dict):
    """Print a health table comparing Railway vs local row counts."""
    tables = ["agent_signals", "manual_trades", "level_edits", "journal_entries"]
    log("")
    log("  ── SYNC HEALTH ───────────────────────────────────")
    log(f"  {'TABLE':<22} {'RAILWAY':>8} {'LOCAL':>8} {'MATCH':>7}")
    log(f"  {'─'*22} {'─'*8} {'─'*8} {'─'*7}")
    all_match = True
    for t in tables:
        railway_n = railway_counts.get(t, 0)
        local_n   = conn.execute(f"SELECT COUNT(*) FROM {t}").fetchone()[0]
        match     = "✓" if railway_n == local_n else "✗ DIFF"
        if railway_n != local_n:
            all_match = False
        log(f"  {t:<22} {railway_n:>8} {local_n:>8} {match:>7}")
    log(f"  {'─'*49}")
    log(f"  {'Overall':22} {'':>8} {'':>8} {'✓ IN SYNC' if all_match else '✗ OUT OF SYNC':>7}")
    log("")


def main():
    parser = argparse.ArgumentParser(description="Sync Railway DB → local trades.db (all 4 tables)")
    parser.add_argument("--dry-run", action="store_true", help="Show what would change, don't write")
    args = parser.parse_args()

    log("=" * 55)
    log(f"Sync started {'(DRY RUN) ' if args.dry_run else ''}— Railway → local | all 4 tables")
    log(f"Local DB: {LOCAL_DB}")

    try:
        data = fetch_railway()
    except Exception as e:
        log(f"ERROR fetching Railway: {e}")
        sys.exit(1)

    rc = data.get("counts", {})
    log(f"Railway: {rc.get('agent_signals','?')} signals | "
        f"{rc.get('manual_trades','?')} trades | "
        f"{rc.get('level_edits','?')} edits | "
        f"{rc.get('journal_entries','?')} journal")

    conn = get_local_conn()
    ensure_local_tables(conn)

    sync_table(conn, "agent_signals",   data.get("agent_signals",   []), "signal_id", args.dry_run)
    sync_table(conn, "manual_trades",   data.get("manual_trades",   []), "signal_id", args.dry_run)
    sync_table(conn, "level_edits",     data.get("level_edits",     []), "id",        args.dry_run)
    sync_table(conn, "journal_entries", data.get("journal_entries", []), "id",        args.dry_run)

    print_health(conn, rc)
    conn.close()

    log(f"Sync {'(dry run) ' if args.dry_run else ''}complete.")
    log("=" * 55)


if __name__ == "__main__":
    main()
