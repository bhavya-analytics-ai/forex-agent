#!/usr/bin/env python3
"""
backup.py — Daily local backup of the SQLite DB via /api/export.

Usage:
  python backup.py                     # hits localhost:5000 by default
  python backup.py --url https://...   # use Railway URL
  python backup.py --out backups/      # custom output dir

Output: backups/forex_backup_YYYYMMDD_HHMMSS.json
        backups/forex_backup_latest.json  (always overwritten — quick restore ref)

Recommended: add to cron for daily automatic backup
  0 6 * * * cd /path/to/forex-agent && python backup.py --url https://YOUR.railway.app
"""

import argparse
import json
import os
import sqlite3
import sys
from datetime import datetime, timezone

try:
    import requests
except ImportError:
    print("ERROR: requests not installed. Run: pip install requests")
    sys.exit(1)

DEFAULT_URL     = "http://localhost:5000"
DEFAULT_OUT_DIR = os.path.join(os.path.dirname(__file__), "backups")


def fetch_export(base_url: str) -> dict:
    url = base_url.rstrip("/") + "/api/export"
    print(f"→ Fetching {url} ...")
    resp = requests.get(url, timeout=30)
    resp.raise_for_status()
    return resp.json()


def save_json(data: dict, out_dir: str) -> str:
    os.makedirs(out_dir, exist_ok=True)
    ts       = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    filename = f"forex_backup_{ts}.json"
    path     = os.path.join(out_dir, filename)
    with open(path, "w") as f:
        json.dump(data, f, indent=2, default=str)
    # Also write "latest" copy for quick access
    latest = os.path.join(out_dir, "forex_backup_latest.json")
    with open(latest, "w") as f:
        json.dump(data, f, indent=2, default=str)
    return path


def build_sqlite_backup(data: dict, out_dir: str) -> str:
    """
    Optional: also write a local SQLite backup from the exported JSON.
    Creates backups/forex_backup_YYYYMMDD.db
    """
    os.makedirs(out_dir, exist_ok=True)
    ts   = datetime.now(timezone.utc).strftime("%Y%m%d")
    path = os.path.join(out_dir, f"forex_backup_{ts}.db")

    conn = sqlite3.connect(path)
    manual_trades  = data.get("manual_trades",  [])
    agent_signals  = data.get("agent_signals",  [])

    if manual_trades:
        cols   = list(manual_trades[0].keys())
        ph     = ", ".join("?" * len(cols))
        conn.execute(f"CREATE TABLE IF NOT EXISTS manual_trades ({', '.join(cols)})")
        conn.executemany(
            f"INSERT OR REPLACE INTO manual_trades VALUES ({ph})",
            [tuple(r.get(c) for c in cols) for r in manual_trades]
        )

    if agent_signals:
        cols   = list(agent_signals[0].keys())
        ph     = ", ".join("?" * len(cols))
        conn.execute(f"CREATE TABLE IF NOT EXISTS agent_signals ({', '.join(cols)})")
        conn.executemany(
            f"INSERT OR REPLACE INTO agent_signals VALUES ({ph})",
            [tuple(r.get(c) for c in cols) for r in agent_signals]
        )

    conn.commit()
    conn.close()
    return path


def prune_old_backups(out_dir: str, keep: int = 30):
    """Keep only the most recent `keep` JSON backups."""
    files = sorted([
        f for f in os.listdir(out_dir)
        if f.startswith("forex_backup_") and f.endswith(".json") and "latest" not in f
    ])
    to_delete = files[:-keep] if len(files) > keep else []
    for f in to_delete:
        os.remove(os.path.join(out_dir, f))
        print(f"  pruned old backup: {f}")


def main():
    parser = argparse.ArgumentParser(description="Daily backup of forex-agent SQLite DB")
    parser.add_argument("--url",    default=DEFAULT_URL,     help="Base URL of the dashboard")
    parser.add_argument("--out",    default=DEFAULT_OUT_DIR, help="Output directory for backups")
    parser.add_argument("--sqlite", action="store_true",     help="Also write a .db SQLite backup")
    parser.add_argument("--keep",   type=int, default=30,    help="How many daily JSON backups to keep")
    args = parser.parse_args()

    try:
        data = fetch_export(args.url)
    except requests.exceptions.ConnectionError:
        print(f"ERROR: Could not connect to {args.url}")
        print("  → Is the dashboard running? Start with: python main.py live")
        sys.exit(1)
    except requests.exceptions.HTTPError as e:
        print(f"ERROR: HTTP {e.response.status_code} from {args.url}/api/export")
        sys.exit(1)

    counts = data.get("counts", {})
    print(f"  manual_trades : {counts.get('manual_trades', '?')}")
    print(f"  agent_signals : {counts.get('agent_signals', '?')}")

    json_path = save_json(data, args.out)
    print(f"✓ JSON backup saved → {json_path}")

    if args.sqlite:
        db_path = build_sqlite_backup(data, args.out)
        print(f"✓ SQLite backup saved → {db_path}")

    prune_old_backups(args.out, keep=args.keep)
    print(f"  (keeping last {args.keep} daily backups)")
    print("Done.")


if __name__ == "__main__":
    main()
