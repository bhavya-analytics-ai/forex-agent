#!/usr/bin/env python3
"""
local_status_server.py — Tiny read-only server on port 5001.
Serves sync_status.json so the Railway dashboard can show local counts.

Started automatically via launchd (com.forexagent.localstatus.plist).
No writes. No impact on any other system.
"""

import json
import os
from flask import Flask, jsonify

app = Flask(__name__)

STATUS_FILE = os.path.join(os.path.dirname(__file__), "logs", "sync_status.json")


@app.route("/local/status")
def local_status():
    resp = jsonify(_read_status())
    resp.headers["Access-Control-Allow-Origin"] = "*"
    return resp


def _read_status() -> dict:
    try:
        with open(STATUS_FILE) as f:
            return json.load(f)
    except FileNotFoundError:
        return {"error": "no sync run yet", "agent_signals": None, "manual_trades": None, "synced_at": None}
    except Exception as e:
        return {"error": str(e), "agent_signals": None, "manual_trades": None, "synced_at": None}


if __name__ == "__main__":
    app.run(host="127.0.0.1", port=5001, debug=False)
