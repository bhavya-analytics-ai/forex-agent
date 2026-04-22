"""
dashboard/app.py — Local web dashboard at http://localhost:5000

UPDATES:
- News data wired into /api/signals response
- /api/news endpoint for live news ticker
- Post-news spike alerts
- Session timer in response
"""

import logging
import threading
import time
from datetime import datetime, timezone
from flask import Flask, render_template, jsonify, request
from config import DASHBOARD_CONFIG, PAIRS

logger = logging.getLogger(__name__)
app    = Flask(__name__, template_folder="templates")


def _sanitize(obj):
    """Recursively convert numpy types to JSON-serializable Python types."""
    if isinstance(obj, dict):  return {k: _sanitize(v) for k, v in obj.items()}
    if isinstance(obj, list):  return [_sanitize(v) for v in obj]
    if hasattr(obj, "item"):   return obj.item()  # numpy scalar → Python native
    return obj

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
            "ict_conflict":  scored.get("ict_conflict", False),
            "against_trend": scored.get("against_h1_trend", False),
            "news_blocked":  scored.get("hard_blocked", False),
            "news_caution":  scored.get("news_check", {}).get("caution", False),
            "spike_watch":   scored.get("news_check", {}).get("spike_watch", False),
            "updated_at":    datetime.now(timezone.utc).strftime("%H:%M:%S"),
            "breakdown":     scored.get("breakdown", {}),
            "early_entry":   scored.get("early_entry", False),
            "entry_type":    scored.get("entry_type", "confirmed"),
            "signal_id":     scored.get("signal_id", ""),
            "entry_state":   scored.get("entry_state", ""),
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
                "ict_summary": "", "ict_conflict": False,
                "against_trend": False, "news_blocked": False,
                "news_caution": False, "spike_watch": False,
                "updated_at": "—", "breakdown": {},
            })

    grade_order = {"A+": 0, "A": 1, "B": 2, "C": 3, "—": 4}
    data.sort(key=lambda x: (grade_order.get(x["grade"], 4), -x["score"]))

    # Get news data (includes panel_events fix)
    news_data = {}
    try:
        from filters.news import get_news_dashboard_data, get_upcoming_news
        news_data                  = get_news_dashboard_data(PAIRS)
        news_data["panel_events"]  = get_upcoming_news(hours_ahead=6)
    except Exception as e:
        logger.warning(f"News dashboard data failed: {e}")

    # Get active strategy mode
    mode_info = {}
    try:
        from filters.mode_manager import get_mode_info
        mode_info = get_mode_info()
    except Exception as e:
        logger.warning(f"Mode info failed: {e}")

    return jsonify(_sanitize({
        "signals":     data,
        "updated_at":  datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC"),
        "total_pairs": len(PAIRS),
        "alert_count": sum(1 for s in data if s.get("should_alert")),
        "news":        news_data,
        "mode":        mode_info,
    }))


@app.route("/api/news")
def api_news():
    try:
        from filters.news import get_news_dashboard_data, get_upcoming_news
        data = get_news_dashboard_data(PAIRS)
        data["panel_events"] = get_upcoming_news(hours_ahead=6)
        return jsonify(data)
    except Exception as e:
        return jsonify({"error": str(e), "upcoming": [], "blocking": [], "caution": [], "panel_events": []}), 500


@app.route("/api/signal/<pair>")
def api_signal_detail(pair: str):
    with _store_lock:
        signal = _signal_store.get(pair.upper())
    if not signal:
        return jsonify({"error": f"No data for {pair}"}), 404
    return jsonify(_sanitize(signal))


@app.route("/api/vibe")
def api_vibe():
    """Market Vibe headlines for a pair. Called on-demand from dashboard panel."""
    pair = request.args.get("pair", "XAU_USD").upper()
    try:
        from filters.news_vibe import get_vibe_headlines
        return jsonify(_sanitize(get_vibe_headlines(pair)))
    except Exception as e:
        return jsonify({"error": str(e), "headlines": [], "pair": pair}), 500


@app.route("/api/mode", methods=["GET"])
def api_mode():
    """Get current strategy mode."""
    try:
        from filters.mode_manager import get_mode_info
        return jsonify(get_mode_info())
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/api/mode/toggle", methods=["POST"])
def api_mode_toggle():
    """
    Toggle strategy mode manually.
    POST body: {"mode": "news_sniper"} or {"mode": "normal"} or {"mode": null} to clear override.
    """
    try:
        from filters.mode_manager import set_manual_mode, clear_manual_override, get_mode_info
        body = request.get_json(silent=True) or {}
        mode = body.get("mode")

        if mode is None:
            clear_manual_override()
        else:
            set_manual_mode(mode)

        return jsonify({"ok": True, "mode": get_mode_info()})
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/api/recent_signals")
def api_recent_signals():
    """Returns last 20 ENTER_NOW signals — SQLite first, CSV fallback."""
    try:
        from db.database import get_recent_agent_signals
        rows = get_recent_agent_signals(limit=20)
        if rows:
            return jsonify({"signals": _sanitize(rows)})
    except Exception as e:
        logger.warning(f"SQLite recent_signals failed, falling back to CSV: {e}")

    # CSV fallback
    try:
        import pandas as pd
        from config import LOG_CONFIG
        path = LOG_CONFIG["signal_log_path"]
        if not __import__("os").path.exists(path):
            return jsonify({"signals": []})
        df = pd.read_csv(path)
        cols = ["signal_id", "timestamp_utc", "pair", "direction",
                "setup_type", "grade", "score", "entry_price",
                "sl_pips", "tp1_pips", "outcome", "outcome_pips", "taken"]
        for c in cols:
            if c not in df.columns:
                df[c] = ""
        recent = df[cols].tail(20).iloc[::-1].fillna("").to_dict("records")
        return jsonify({"signals": recent})
    except Exception as e:
        logger.error(f"recent_signals CSV fallback error: {e}")
        return jsonify({"signals": [], "error": str(e)}), 500


@app.route("/api/mark_taken", methods=["POST"])
def api_mark_taken():
    """Mark a signal as taken (you actually entered this trade)."""
    try:
        from alerts.logger import mark_taken_by_id
        body      = request.get_json(silent=True) or {}
        signal_id = body.get("signal_id", "").strip()
        if not signal_id:
            return jsonify({"ok": False, "error": "signal_id required"}), 400
        ok = mark_taken_by_id(signal_id)
        return jsonify({"ok": ok, "signal_id": signal_id})
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)}), 500


@app.route("/api/mark_outcome", methods=["POST"])
def api_mark_outcome():
    """
    Manually mark a signal outcome from the dashboard.
    Body: { "signal_id": "XAU_USD_20260409_143022", "outcome": "WIN" | "LOSS", "notes": "" }
    Calls update_outcome() in alerts/logger.py — no new logic, just an API wrapper.
    """
    try:
        from alerts.logger import update_outcome
        body      = request.get_json(silent=True) or {}
        signal_id = body.get("signal_id", "").strip()
        outcome   = body.get("outcome", "").upper().strip()
        notes     = body.get("notes", "")

        if not signal_id:
            return jsonify({"ok": False, "error": "signal_id required"}), 400
        if outcome not in ("WIN", "LOSS", "NEUTRAL"):
            return jsonify({"ok": False, "error": "outcome must be WIN, LOSS, or NEUTRAL"}), 400

        update_outcome(signal_id, outcome, pips=0, notes=notes)
        return jsonify({"ok": True, "signal_id": signal_id, "outcome": outcome})
    except Exception as e:
        logger.error(f"mark_outcome error: {e}")
        return jsonify({"ok": False, "error": str(e)}), 500


@app.route("/api/performance")
def api_performance():
    """Returns performance summary — SQLite first, CSV fallback."""
    try:
        from db.database import get_performance_summary_db
        summary = get_performance_summary_db()
        return jsonify(_sanitize(summary))
    except Exception as e:
        logger.warning(f"SQLite performance failed, falling back to CSV: {e}")
    try:
        from alerts.logger import get_performance_summary
        summary = get_performance_summary()
        return jsonify(_sanitize(summary))
    except Exception as e:
        logger.error(f"performance endpoint error: {e}")
        return jsonify({"error": str(e)}), 500


# ── OUTCOME LABELER BACKGROUND THREAD ────────────────────────────────────────

def _run_outcome_labeler():
    """
    Background thread: runs outcome_labeler every 5 minutes.
    Labels WIN/LOSS/NEUTRAL on signals that are 15+ min old.
    Started once when dashboard launches.
    """
    logger.info("Outcome labeler thread started — checking every 5 minutes")
    while True:
        try:
            from ml.outcome_labeler import label_pending_signals
            labeled = label_pending_signals()
            if labeled:
                logger.info(f"Auto-labeler: {labeled} signal(s) labeled")
        except Exception as e:
            logger.warning(f"Outcome labeler error: {e}")
        time.sleep(300)   # 5 minutes


@app.route("/api/log_manual_trade", methods=["POST"])
def api_log_manual_trade():
    """
    Log a trade you took manually on TradingView / paper trading.
    Body: { "pair": "XAU_USD", "direction": "bullish", "entry_price": 2345.50,
            "setup_type": "manual", "notes": "" }
    Calculates SL/TP automatically, starts monitoring for TP/SL hit.
    Saves to logs/manual_trades.csv (separate from agent signals).
    """
    try:
        from ml.manual_trade_logger import log_manual_trade
        body        = request.get_json(silent=True) or {}
        pair        = body.get("pair", "").upper().strip()
        direction   = body.get("direction", "").lower().strip()
        entry_price = body.get("entry_price")
        setup_type  = body.get("setup_type", "manual").strip()
        notes       = body.get("notes", "")

        if not pair:
            return jsonify({"ok": False, "error": "pair required"}), 400
        if direction not in ("bullish", "bearish"):
            return jsonify({"ok": False, "error": "direction must be bullish or bearish"}), 400
        if not entry_price:
            return jsonify({"ok": False, "error": "entry_price required"}), 400

        signal_id = log_manual_trade(pair, direction, float(entry_price), setup_type, notes)
        return jsonify({"ok": True, "signal_id": signal_id, "pair": pair,
                        "direction": direction, "entry_price": entry_price})
    except Exception as e:
        logger.error(f"log_manual_trade error: {e}")
        return jsonify({"ok": False, "error": str(e)}), 500


@app.route("/api/close_manual_trade", methods=["POST"])
def api_close_manual_trade():
    """
    Manually close a monitored trade from the dashboard.
    Body: { "signal_id": "...", "outcome": "WIN"|"LOSS", "pips": 25.5, "notes": "" }
    """
    try:
        from ml.manual_trade_logger import close_trade_manually
        body      = request.get_json(silent=True) or {}
        signal_id = body.get("signal_id", "").strip()
        outcome   = body.get("outcome", "").upper().strip()
        pips      = float(body.get("pips", 0))
        notes     = body.get("notes", "")

        if not signal_id:
            return jsonify({"ok": False, "error": "signal_id required"}), 400
        if outcome not in ("WIN", "LOSS"):
            return jsonify({"ok": False, "error": "outcome must be WIN or LOSS"}), 400

        ok, err = close_trade_manually(signal_id, outcome, pips, notes)
        if ok:
            return jsonify({"ok": True, "signal_id": signal_id, "outcome": outcome, "pips": pips})
        return jsonify({"ok": False, "error": err}), 400
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)}), 500


@app.route("/api/update_trade_levels", methods=["POST"])
def api_update_trade_levels():
    """
    Update SL and TP1 for an open manual trade mid-trade.
    Body: { "signal_id": "...", "sl_price": 1.2345, "tp1_price": 1.2500 }
    Restarts the monitor thread with the new levels.
    """
    try:
        from ml.manual_trade_logger import update_trade_levels
        body      = request.get_json(silent=True) or {}
        signal_id = body.get("signal_id", "").strip()
        sl_price  = body.get("sl_price")
        tp1_price = body.get("tp1_price")
        reason    = body.get("reason", "").strip()

        if not signal_id:
            return jsonify({"ok": False, "error": "signal_id required"}), 400
        if sl_price is None or tp1_price is None:
            return jsonify({"ok": False, "error": "sl_price and tp1_price required"}), 400

        ok, err = update_trade_levels(signal_id, float(sl_price), float(tp1_price), reason)
        if ok:
            return jsonify({"ok": True, "signal_id": signal_id, "sl_price": sl_price, "tp1_price": tp1_price})
        return jsonify({"ok": False, "error": err}), 400
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)}), 500


@app.route("/api/recent_manual_trades")
def api_recent_manual_trades():
    """Returns last 20 manual trades — SQLite first, CSV fallback."""
    try:
        from db.database import get_recent_manual_trades
        rows = get_recent_manual_trades(limit=20)
        if rows:
            return jsonify({"trades": _sanitize(rows)})
    except Exception as e:
        logger.warning(f"SQLite recent_manual_trades failed, falling back to CSV: {e}")

    # CSV fallback
    try:
        import pandas as pd
        import os
        from config import LOG_CONFIG
        path = LOG_CONFIG["manual_log_path"]
        if not os.path.exists(path):
            return jsonify({"trades": []})
        df   = pd.read_csv(path)
        cols = ["signal_id", "timestamp_utc", "pair", "direction", "setup_type",
                "entry_price", "sl_price", "tp1_price", "sl_pips", "tp1_pips",
                "rr1", "outcome", "outcome_pips", "post_mortem", "notes"]
        for c in cols:
            if c not in df.columns:
                df[c] = ""
        trades = df[cols].tail(20).iloc[::-1].fillna("").to_dict("records")
        return jsonify({"trades": trades})
    except Exception as e:
        return jsonify({"trades": [], "error": str(e)}), 500


def start_dashboard():
    host = DASHBOARD_CONFIG.get("host", "127.0.0.1")
    port = DASHBOARD_CONFIG.get("port", 5000)
    logger.info(f"Dashboard at http://{host}:{port}")

    # Init SQLite on startup
    try:
        from db.database import init_db
        init_db()
    except Exception as e:
        logger.warning(f"SQLite init failed: {e}")

    # Resume monitors for any open manual trades from last session
    try:
        from ml.manual_trade_logger import resume_monitors_on_startup
        resume_monitors_on_startup()
    except Exception as e:
        logger.warning(f"Could not resume manual trade monitors: {e}")

    # Start outcome labeler in background — auto-labels agent signals after 15 min
    labeler_thread = threading.Thread(target=_run_outcome_labeler, daemon=True, name="OutcomeLabeler")
    labeler_thread.start()

    app.run(host=host, port=port, debug=False, use_reloader=False)