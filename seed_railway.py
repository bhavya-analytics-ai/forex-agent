#!/usr/bin/env python3
"""
seed_railway.py — Push local SQLite data to Railway on first deploy.

Usage:
  python seed_railway.py --url https://forex-agent.up.railway.app

Reads local DB directly (no local server needed), POSTs to Railway /api/import.
Safe to run multiple times — Railway uses INSERT OR IGNORE, no duplicates.
"""

import argparse
import json
import sys
import os

try:
    import requests
except ImportError:
    print("ERROR: pip install requests")
    sys.exit(1)

sys.path.insert(0, os.path.dirname(__file__))


def read_local_db():
    from db.database import get_recent_manual_trades, get_recent_agent_signals, init_db
    init_db()
    manual  = get_recent_manual_trades(limit=100_000)
    signals = get_recent_agent_signals(limit=100_000)
    return manual, signals


def seed(base_url: str, manual: list, signals: list):
    url  = base_url.rstrip("/") + "/api/import"
    print(f"→ Seeding {url}")
    print(f"  Sending {len(manual)} manual trades + {len(signals)} agent signals ...")
    resp = requests.post(url, json={
        "manual_trades": manual,
        "agent_signals": signals,
    }, timeout=60)
    resp.raise_for_status()
    result = resp.json()
    print(f"  manual_trades : {result['manual_trades']['inserted']} inserted, {result['manual_trades']['skipped']} skipped")
    print(f"  agent_signals : {result['agent_signals']['inserted']} inserted, {result['agent_signals']['skipped']} skipped")
    print("✓ Done — Railway DB seeded.")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--url", required=True, help="Railway app URL e.g. https://forex-agent.up.railway.app")
    args = parser.parse_args()

    print("Reading local DB ...")
    manual, signals = read_local_db()
    print(f"  Found {len(manual)} manual trades + {len(signals)} agent signals locally")

    if not manual and not signals:
        print("Nothing to seed. Local DB is empty.")
        sys.exit(0)

    seed(args.url, manual, signals)


if __name__ == "__main__":
    main()
