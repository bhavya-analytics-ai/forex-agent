"""
dashboard/app.py — Local web dashboard at http://localhost:5000
Auto-refreshes every 30 seconds.
Shows all 11 pairs with Entry/SL/TP1/TP2 on click.
"""

import logging
import threading
from datetime import datetime, timezone
from flask import Flask, render_template, jsonify
from config import DASHBOARD_CONFIG, PAIRS

logger = logging.getLogger(__name__)
app    = Flask(__name__, template_folder="templates")

_signal_store = {}
_store_lock   = threading.Lock()


def update_dashboard(pair: str, scored: dict, confluence: dict, ict: dict = None):
    """Push latest signal to dashboard. Thread-safe."""
    with _store_lock:
        _signal_store[pair] = {
            "pair":          pair,
            "score":         scored.get("score", 0),
            "grade":         scored.get("grade", "C"),
            "direction":     scored.get("direction", "neutral"),
            "setup_type":    scored.get("setup_type", ""),
            "current_price": scored.get("current_price", 0),
            "h1_trend":      scored.get("h1_trend", "—"),
            "m15_trend":     scored.get("m15_trend", "—"),
            "m5_trend":      scored.get("m5_trend", "—"),
            "session":       scored.get("session_ctx", {}).get("session", "—"),
            "flags":         scored.get("flags", []),
            "top_zone":      scored.get("top_zone"),
            "entry_pattern": scored.get("entry_pattern"),
            "trade_levels":  scored.get("trade_levels", {}),
            "should_alert":  scored.get("should_alert", False),
            "grade_meaning": scored.get("grade_meaning", ""),
            "ict_summary":   _ict_summary(ict) if ict else "",
            "updated_at":    datetime.now(timezone.utc).strftime("%H:%M:%S"),
            "breakdown":     scored.get("breakdown", {}),
        }


def _ict_summary(ict: dict) -> str:
    if not ict:
        return ""
    parts = []
    if ict.get("has_mss"):
        t = (ict.get("mss_m5") or ict.get("mss_m15") or {}).get("type", "")
        parts.append(f"MSS {t}")
    if ict.get("has_choch"):
        t = (ict.get("choch_m5") or ict.get("choch_m15") or {}).get("type", "")
        parts.append(f"ChoCH {t}")
    if ict.get("has_sweep"):
        parts.append("Sweep")
    if ict.get("has_ob"):
        parts.append("OB")
    pd_zone = ict.get("premium_discount", {}).get("zone", "")
    if pd_zone in ["premium", "discount"]:
        pct = round(ict["premium_discount"].get("pct", 0) * 100)
        parts.append(f"{pd_zone.upper()} {pct}%")
    return " | ".join(parts)


@app.route("/")
def index():
    return render_template(
        "dashboard.html",
        pairs=PAIRS,
        refresh=DASHBOARD_CONFIG.get("refresh_seconds", 30),
    )


@app.route("/api/signals")
def api_signals():
    with _store_lock:
        data = list(_signal_store.values())

    # Fill missing pairs
    active = {s["pair"] for s in data}
    for pair in PAIRS:
        if pair not in active:
            data.append({
                "pair": pair, "score": 0, "grade": "—",
                "direction": "—", "setup_type": "scanning...",
                "current_price": 0, "h1_trend": "—",
                "m15_trend": "—", "m5_trend": "—",
                "session": "—", "flags": [], "top_zone": None,
                "entry_pattern": None, "trade_levels": {},
                "should_alert": False, "grade_meaning": "",
                "ict_summary": "", "updated_at": "—", "breakdown": {},
            })

    grade_order = {"A+": 0, "A": 1, "B": 2, "C": 3, "—": 4}
    data.sort(key=lambda x: (grade_order.get(x["grade"], 4), -x["score"]))

    return jsonify({
        "signals":     data,
        "updated_at":  datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC"),
        "total_pairs": len(PAIRS),
        "alert_count": sum(1 for s in data if s.get("should_alert")),
    })


@app.route("/api/signal/<pair>")
def api_signal_detail(pair: str):
    with _store_lock:
        signal = _signal_store.get(pair.upper())
    if not signal:
        return jsonify({"error": f"No data for {pair}"}), 404
    return jsonify(signal)


def start_dashboard():
    host = DASHBOARD_CONFIG.get("host", "127.0.0.1")
    port = DASHBOARD_CONFIG.get("port", 5000)
    logger.info(f"Dashboard at http://{host}:{port}")
    app.run(host=host, port=port, debug=False, use_reloader=False)