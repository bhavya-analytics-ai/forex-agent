"""
dashboard/app.py — Local web dashboard at http://localhost:5000

UPDATES:
- News data wired into /api/signals response
- /api/news endpoint for live news ticker
- Post-news spike alerts
- Session timer in response
"""

import logging
import os
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


@app.route("/api/bulk_archive", methods=["POST"])
def api_bulk_archive():
    """
    Bulk archive records by pair + outcome filter.
    Body: {"pair_like": "XAG%", "outcome": "LOSS"}
    """
    try:
        import sqlite3, os
        DB_PATH = "/data/forex.db" if os.path.exists("/data") else os.path.join(os.path.dirname(__file__), "..", "logs", "trades.db")
        body    = request.get_json(silent=True) or {}
        pair_p  = body.get("pair_like", "").strip()
        outcome = body.get("outcome", "").strip().upper()
        if not pair_p or not outcome:
            return jsonify({"error": "pair_like and outcome required"}), 400
        conn = sqlite3.connect(os.path.abspath(DB_PATH))
        r1 = conn.execute(
            "UPDATE agent_signals SET is_archived=1 WHERE pair LIKE ? AND outcome=?",
            (pair_p, outcome)
        )
        r2 = conn.execute(
            "UPDATE manual_trades SET is_archived=1 WHERE pair LIKE ? AND outcome=?",
            (pair_p, outcome)
        )
        conn.commit()
        conn.close()
        return jsonify({"ok": True, "agent_archived": r1.rowcount, "manual_archived": r2.rowcount})
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/api/recent_signals")
def api_recent_signals():
    """Returns last 20 ENTER_NOW signals — SQLite first, CSV fallback."""
    try:
        from db.database import get_recent_agent_signals
        rows = get_recent_agent_signals(limit=500)
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
        recent = df[cols].tail(500).iloc[::-1].fillna("").to_dict("records")
        return jsonify({"signals": recent})
    except Exception as e:
        logger.error(f"recent_signals CSV fallback error: {e}")
        return jsonify({"signals": [], "error": str(e)}), 500


@app.route("/api/mark_taken", methods=["POST"])
def api_mark_taken():
    """
    Mark a signal as taken. Optionally saves user's actual SL/TP.
    Body: { "signal_id": "...", "user_sl": 1.2345, "user_tp1": 1.2600 }
    user_sl/tp1 are optional — if omitted, actual levels fall back to scanner levels.
    """
    try:
        from alerts.logger import mark_taken_by_id
        from db.database import update_agent_signal_took_it
        body      = request.get_json(silent=True) or {}
        signal_id = body.get("signal_id", "").strip()
        user_sl   = body.get("user_sl")
        user_tp1  = body.get("user_tp1")
        notes     = body.get("notes", "").strip()

        if not signal_id:
            return jsonify({"ok": False, "error": "signal_id required"}), 400

        mark_taken_by_id(signal_id)
        update_agent_signal_took_it(
            signal_id,
            float(user_sl)  if user_sl  not in (None, "") else None,
            float(user_tp1) if user_tp1 not in (None, "") else None,
        )
        if notes:
            from db.database import save_note
            save_note(signal_id, notes, "agent")
        return jsonify({"ok": True, "signal_id": signal_id})
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)}), 500


@app.route("/api/mark_outcome", methods=["POST"])
def api_mark_outcome():
    """
    Manually mark a signal outcome from the dashboard.
    Body: { "signal_id": "XAU_USD_20260409_143022", "outcome": "WIN" | "LOSS", "notes": "" }
    SQLite is source of truth — written first. CSV update is best-effort (may not exist on Railway).
    """
    try:
        from db.database import update_agent_signal_outcome
        body      = request.get_json(silent=True) or {}
        signal_id = body.get("signal_id", "").strip()
        outcome   = body.get("outcome", "").upper().strip()
        notes     = body.get("notes", "")

        if not signal_id:
            return jsonify({"ok": False, "error": "signal_id required"}), 400
        if outcome not in ("WIN", "LOSS", "NEUTRAL"):
            return jsonify({"ok": False, "error": "outcome must be WIN, LOSS, or NEUTRAL"}), 400

        # SQLite first — this is the source of truth on Railway
        update_agent_signal_outcome(signal_id, outcome, pips=0, notes=notes)

        # CSV best-effort (may not exist on Railway — that's fine)
        try:
            from alerts.logger import update_outcome
            update_outcome(signal_id, outcome, pips=0, notes=notes)
        except Exception as csv_err:
            logger.warning(f"CSV update_outcome skipped (non-fatal): {csv_err}")

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


@app.route("/api/close_agent_trade", methods=["POST"])
def api_close_agent_trade():
    """
    Close an agent signal mid-trade at a specific exit price.
    Body: { "signal_id": "...", "exit_price": 4620.5 }
    Calculates WIN/LOSS + pips direction-aware, saves exit_price to DB.
    """
    try:
        from db.database import close_agent_trade, get_agent_signal
        from core.fetcher import pip_size
        body       = request.get_json(silent=True) or {}
        signal_id  = body.get("signal_id", "").strip()
        exit_price = float(body.get("exit_price", 0))

        if not signal_id:
            return jsonify({"ok": False, "error": "signal_id required"}), 400
        if exit_price <= 0:
            return jsonify({"ok": False, "error": "exit_price required"}), 400

        sig = get_agent_signal(signal_id)
        if not sig:
            return jsonify({"ok": False, "error": "signal not found"}), 404

        entry_price = float(sig.get("entry_price") or 0)
        direction   = sig.get("direction", "")
        pip         = pip_size(sig.get("pair", ""))

        if not entry_price:
            return jsonify({"ok": False, "error": "entry_price missing on signal"}), 400

        result = close_agent_trade(signal_id, exit_price, entry_price, direction, pip)
        return jsonify({"ok": True, "signal_id": signal_id, **result})
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
        notes     = body.get("notes", "").strip()

        if not signal_id:
            return jsonify({"ok": False, "error": "signal_id required"}), 400
        if sl_price is None or tp1_price is None:
            return jsonify({"ok": False, "error": "sl_price and tp1_price required"}), 400

        ok, err = update_trade_levels(signal_id, float(sl_price), float(tp1_price), reason)
        if ok:
            if notes:
                from db.database import save_note
                save_note(signal_id, notes, "manual")
            return jsonify({"ok": True, "signal_id": signal_id, "sl_price": sl_price, "tp1_price": tp1_price})
        return jsonify({"ok": False, "error": err}), 400
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)}), 500


@app.route("/api/recent_manual_trades")
def api_recent_manual_trades():
    """Returns last 20 manual trades — SQLite first, CSV fallback."""
    try:
        from db.database import get_recent_manual_trades
        rows = get_recent_manual_trades(limit=100)
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
        trades = df[cols].tail(100).iloc[::-1].fillna("").to_dict("records")
        return jsonify({"trades": trades})
    except Exception as e:
        return jsonify({"trades": [], "error": str(e)}), 500


@app.route("/api/save_note", methods=["POST"])
def api_save_note():
    """Append a note to any signal. Body: { signal_id, note, kind: 'manual'|'agent' }"""
    try:
        from db.database import save_note
        body      = request.get_json(silent=True) or {}
        signal_id = body.get("signal_id", "").strip()
        note      = body.get("note", "").strip()
        kind      = body.get("kind", "manual")
        if not signal_id or not note:
            return jsonify({"ok": False, "error": "signal_id and note required"}), 400
        ok = save_note(signal_id, note, kind)
        return jsonify({"ok": ok})
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)}), 500


@app.route("/api/update_agent_levels", methods=["POST"])
def api_update_agent_levels():
    """
    Update user SL/TP on an agent signal.
    Body: { signal_id, user_sl, user_tp1, reason (optional) }

    Also:
    - Logs the change to level_edits (source=agent) with timestamp
    - If oanda_trade_id is set, updates the live GTC order on OANDA practice account
      so the actual execution level matches the DB
    """
    try:
        from db.database import update_agent_signal_levels, get_agent_signal, insert_level_edit
        body      = request.get_json(silent=True) or {}
        signal_id = body.get("signal_id", "").strip()
        user_sl   = body.get("user_sl")
        user_tp1  = body.get("user_tp1")
        reason    = body.get("reason", "manual adjustment").strip() or "manual adjustment"

        if not signal_id:
            return jsonify({"ok": False, "error": "signal_id required"}), 400

        new_sl  = float(user_sl)  if user_sl  not in (None, "") else None
        new_tp1 = float(user_tp1) if user_tp1 not in (None, "") else None

        # Get current levels before update (for level_edits log)
        current = get_agent_signal(signal_id)
        if not current:
            return jsonify({"ok": False, "error": "signal not found"}), 404

        old_sl  = float(current.get("actual_sl")  or current.get("sl_price")  or 0)
        old_tp1 = float(current.get("actual_tp1") or current.get("tp1_price") or 0)

        # Update DB
        ok = update_agent_signal_levels(signal_id, new_sl, new_tp1)
        if not ok:
            return jsonify({"ok": False, "error": "DB update failed"}), 500

        # ── Sync to OANDA live GTC order if trade ID is stored ────────────────
        oanda_synced = 0
        oanda_trade_id = current.get("oanda_trade_id")
        if oanda_trade_id and new_sl and new_tp1:
            try:
                import oandapyV20
                import oandapyV20.endpoints.trades as oanda_trades
                from core.fetcher import pip_size
                pip = pip_size(current["pair"])
                if pip >= 0.01:    price_fmt = "{:.2f}"
                elif pip >= 0.001: price_fmt = "{:.3f}"
                else:              price_fmt = "{:.5f}"

                api_key    = os.environ.get("OANDA_API_KEY", "")
                account_id = os.environ.get("OANDA_ACCOUNT_ID", "")
                env        = os.environ.get("OANDA_ENVIRONMENT", "practice")
                client     = oandapyV20.API(
                    access_token=api_key,
                    environment="practice" if env == "practice" else "live"
                )
                order_body = {
                    "stopLoss":   {"price": price_fmt.format(new_sl),  "timeInForce": "GTC"},
                    "takeProfit": {"price": price_fmt.format(new_tp1), "timeInForce": "GTC"},
                }
                r = oanda_trades.TradeCRCDO(account_id, oanda_trade_id, data=order_body)
                client.request(r)
                oanda_synced = 1
                logger.info(f"OANDA GTC updated: {signal_id} | trade={oanda_trade_id} | SL={new_sl} TP={new_tp1}")
            except Exception as oanda_err:
                # Log warning but don't fail — DB update already succeeded
                logger.warning(f"OANDA GTC update failed for {signal_id}: {oanda_err}")

        # ── Log to level_edits ────────────────────────────────────────────────
        try:
            insert_level_edit(
                signal_id  = signal_id,
                old_sl     = old_sl,
                new_sl     = new_sl or old_sl,
                old_tp1    = old_tp1,
                new_tp1    = new_tp1 or old_tp1,
                reason     = reason,
                source     = "agent",
                oanda_synced = oanda_synced,
            )
        except Exception as le_err:
            logger.warning(f"level_edits insert failed for {signal_id}: {le_err}")

        return jsonify({
            "ok":           True,
            "signal_id":    signal_id,
            "oanda_synced": bool(oanda_synced),
        })
    except Exception as e:
        logger.error(f"update_agent_levels error: {e}", exc_info=True)
        return jsonify({"ok": False, "error": str(e)}), 500


@app.route("/api/debate_signal", methods=["POST"])
def api_debate_signal():
    """
    Run bull/bear debate on an agent signal via NIM.
    Body: { "signal_id": "..." }
    Returns: { ok, bull, bear, verdict, reason }
    """
    try:
        from db.database import get_agent_signal
        from core.debate import debate_signal
        body      = request.get_json(silent=True) or {}
        signal_id = body.get("signal_id", "").strip()
        if not signal_id:
            return jsonify({"ok": False, "error": "signal_id required"}), 400
        signal = get_agent_signal(signal_id)
        if not signal:
            return jsonify({"ok": False, "error": "signal not found"}), 404
        result = debate_signal(signal)
        return jsonify(result)
    except Exception as e:
        logger.error(f"debate_signal error: {e}")
        return jsonify({"ok": False, "error": str(e)}), 500


@app.route("/api/archive_signal", methods=["POST"])
def api_archive_signal():
    """Toggle is_archived on an agent signal. Body: { "signal_id": "...", "archived": true/false }"""
    try:
        from db.database import _get_conn, _write_lock
        body      = request.get_json(silent=True) or {}
        signal_id = body.get("signal_id", "").strip()
        archived  = 1 if body.get("archived", True) else 0
        if not signal_id:
            return jsonify({"ok": False, "error": "signal_id required"}), 400
        conn = _get_conn()
        with _write_lock:
            conn.execute("UPDATE agent_signals SET is_archived=? WHERE signal_id=?",
                         (archived, signal_id))
            conn.commit()
        return jsonify({"ok": True, "signal_id": signal_id, "is_archived": archived})
    except Exception as e:
        logger.error(f"archive_signal error: {e}")
        return jsonify({"ok": False, "error": str(e)}), 500


@app.route("/api/archive_manual_trade", methods=["POST"])
def api_archive_manual_trade():
    """Toggle is_archived on a manual trade. Body: { "signal_id": "...", "archived": true/false }"""
    try:
        from db.database import _get_conn, _write_lock
        body      = request.get_json(silent=True) or {}
        signal_id = body.get("signal_id", "").strip()
        archived  = 1 if body.get("archived", True) else 0
        if not signal_id:
            return jsonify({"ok": False, "error": "signal_id required"}), 400
        conn = _get_conn()
        with _write_lock:
            conn.execute("UPDATE manual_trades SET is_archived=? WHERE signal_id=?",
                         (archived, signal_id))
            conn.commit()
        return jsonify({"ok": True, "signal_id": signal_id, "is_archived": archived})
    except Exception as e:
        logger.error(f"archive_manual_trade error: {e}")
        return jsonify({"ok": False, "error": str(e)}), 500


@app.route("/api/delete_signal", methods=["POST"])
def api_delete_signal():
    """Delete an agent signal by signal_id. Body: { "signal_id": "..." }"""
    try:
        from db.database import _get_conn, _write_lock
        body      = request.get_json(silent=True) or {}
        signal_id = body.get("signal_id", "").strip()
        if not signal_id:
            return jsonify({"ok": False, "error": "signal_id required"}), 400
        conn = _get_conn()
        with _write_lock:
            conn.execute("DELETE FROM agent_signals WHERE signal_id=?", (signal_id,))
            conn.commit()
        return jsonify({"ok": True, "signal_id": signal_id})
    except Exception as e:
        logger.error(f"delete_signal error: {e}")
        return jsonify({"ok": False, "error": str(e)}), 500


@app.route("/api/delete_manual", methods=["POST"])
def api_delete_manual():
    """Delete a manual trade by signal_id. Body: { "signal_id": "..." }"""
    try:
        from db.database import _get_conn, _write_lock
        body      = request.get_json(silent=True) or {}
        signal_id = body.get("signal_id", "").strip()
        if not signal_id:
            return jsonify({"ok": False, "error": "signal_id required"}), 400
        conn = _get_conn()
        with _write_lock:
            conn.execute("DELETE FROM manual_trades WHERE signal_id=?", (signal_id,))
            conn.commit()
        return jsonify({"ok": True, "signal_id": signal_id})
    except Exception as e:
        logger.error(f"delete_manual error: {e}")
        return jsonify({"ok": False, "error": str(e)}), 500


@app.route("/api/take_trade", methods=["POST"])
def api_take_trade():
    """
    Fire a market order to OANDA practice account.
    Body: { signal_id, units, sl_price, tp1_price }
    On success: marks signal as taken + saves user SL/TP to agent_signals.
    Returns: { ok, order_id, fill_price, units }
    """
    try:
        import oandapyV20
        import oandapyV20.endpoints.orders as orders
        from db.database import get_agent_signal, update_agent_signal_took_it

        body      = request.get_json(silent=True) or {}
        signal_id = body.get("signal_id", "").strip()
        units     = body.get("units")
        sl_price  = body.get("sl_price")
        tp1_price = body.get("tp1_price")

        if not signal_id:
            return jsonify({"ok": False, "error": "signal_id required"}), 400
        if units is None or sl_price is None or tp1_price is None:
            return jsonify({"ok": False, "error": "units, sl_price, tp1_price required"}), 400

        signal = get_agent_signal(signal_id)
        if not signal:
            return jsonify({"ok": False, "error": "signal not found"}), 404

        pair      = signal["pair"]
        direction = signal["direction"]
        units_int = int(units)
        if direction == "bearish":
            units_int = -abs(units_int)
        else:
            units_int = abs(units_int)

        # Price precision: metals 2dp, JPY pairs 3dp, others 5dp
        from core.fetcher import pip_size
        pip = pip_size(pair)
        if pip >= 0.01:       price_fmt = "{:.2f}"   # metals
        elif pip >= 0.001:    price_fmt = "{:.3f}"   # JPY
        else:                 price_fmt = "{:.5f}"   # majors

        sl_str  = price_fmt.format(float(sl_price))
        tp_str  = price_fmt.format(float(tp1_price))

        api_key    = os.environ.get("OANDA_API_KEY", "")
        account_id = os.environ.get("OANDA_ACCOUNT_ID", "")
        env        = os.environ.get("OANDA_ENVIRONMENT", "practice")

        if not api_key or not account_id:
            return jsonify({"ok": False, "error": "OANDA credentials not set"}), 500

        client = oandapyV20.API(
            access_token=api_key,
            environment="practice" if env == "practice" else "live"
        )

        order_data = {
            "order": {
                "type":      "MARKET",
                "instrument": pair,
                "units":     str(units_int),
                "stopLossOnFill":   {"price": sl_str,  "timeInForce": "GTC"},
                "takeProfitOnFill": {"price": tp_str,  "timeInForce": "GTC"},
            }
        }

        r = orders.OrderCreate(account_id, data=order_data)
        client.request(r)
        resp = r.response

        # Extract fill price + order ID from OANDA response
        fill_price = None
        order_id   = None
        trade_id   = None
        if "orderFillTransaction" in resp:
            fill = resp["orderFillTransaction"]
            fill_price = float(fill.get("price", 0))
            trade_id   = fill.get("tradeOpened", {}).get("tradeID")
        if "relatedTransactionIDs" in resp:
            order_id = resp["relatedTransactionIDs"][0]

        # Mark taken + save user levels + OANDA trade ID in DB
        update_agent_signal_took_it(
            signal_id,
            float(sl_price),
            float(tp1_price),
            oanda_trade_id=str(trade_id) if trade_id else None,
        )
        if body.get("notes"):
            from db.database import save_note
            save_note(signal_id, body["notes"], "agent")

        logger.info(f"OANDA order placed: {pair} {units_int} units | fill={fill_price} | trade={trade_id}")
        return jsonify({
            "ok":         True,
            "signal_id":  signal_id,
            "order_id":   order_id,
            "trade_id":   trade_id,
            "fill_price": fill_price,
            "units":      units_int,
            "pair":       pair,
        })

    except oandapyV20.exceptions.V20Error as e:
        logger.error(f"OANDA API error: {e}")
        return jsonify({"ok": False, "error": f"OANDA: {e}"}), 400
    except Exception as e:
        logger.error(f"take_trade error: {e}")
        return jsonify({"ok": False, "error": str(e)}), 500


@app.route("/api/export")
def api_export():
    """
    Full DB export — all 4 tables as JSON.
    Used by backup.py + sync.py for Railway → local mirror.
    """
    try:
        from db.database import (get_recent_manual_trades, get_recent_agent_signals,
                                  get_all_level_edits, get_all_journal_entries)
        manual   = get_recent_manual_trades(limit=100_000)
        signals  = get_recent_agent_signals(limit=100_000)
        edits    = get_all_level_edits(limit=100_000)
        journal  = get_all_journal_entries(limit=100_000)
        return jsonify(_sanitize({
            "exported_at":    datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC"),
            "manual_trades":  manual,
            "agent_signals":  signals,
            "level_edits":    edits,
            "journal_entries": journal,
            "counts": {
                "manual_trades":   len(manual),
                "agent_signals":   len(signals),
                "level_edits":     len(edits),
                "journal_entries": len(journal),
            }
        }))
    except Exception as e:
        logger.error(f"api_export error: {e}")
        return jsonify({"error": str(e)}), 500


@app.route("/api/import", methods=["POST"])
def api_import():
    """
    Bulk import all 4 tables from JSON (output of /api/export).
    Used by seed_railway.py + sync to push data to Railway.
    Skips rows that already exist (INSERT OR IGNORE).
    """
    try:
        from db.database import (insert_manual_trade, insert_agent_signal,
                                  insert_level_edit_row, insert_journal_entry_row)
        body    = request.get_json(silent=True) or {}
        manual  = body.get("manual_trades",   [])
        signals = body.get("agent_signals",   [])
        edits   = body.get("level_edits",     [])
        journal = body.get("journal_entries", [])

        def _bulk(rows, fn):
            ok = skip = 0
            for row in rows:
                try:    fn(row); ok += 1
                except: skip += 1
            return ok, skip

        m_ok,  m_skip  = _bulk(manual,  insert_manual_trade)
        s_ok,  s_skip  = _bulk(signals, insert_agent_signal)
        e_ok,  e_skip  = _bulk(edits,   insert_level_edit_row)
        j_ok,  j_skip  = _bulk(journal, insert_journal_entry_row)

        return jsonify({
            "ok": True,
            "manual_trades":   {"inserted": m_ok,  "skipped": m_skip},
            "agent_signals":   {"inserted": s_ok,  "skipped": s_skip},
            "level_edits":     {"inserted": e_ok,  "skipped": e_skip},
            "journal_entries": {"inserted": j_ok,  "skipped": j_skip},
        })
    except Exception as e:
        logger.error(f"api_import error: {e}")
        return jsonify({"ok": False, "error": str(e)}), 500


@app.route("/api/journal", methods=["GET"])
def api_journal_get():
    """
    Fetch journal entries.
    Query params: tag=, session=, limit= (default 200)
    """
    try:
        from db.database import get_journal_entries
        tag     = request.args.get("tag", "").strip()
        session = request.args.get("session", "").strip()
        limit   = int(request.args.get("limit", 200))
        entries = get_journal_entries(limit=limit, tag=tag, session=session)
        return jsonify({"ok": True, "entries": _sanitize(entries)})
    except Exception as e:
        logger.error(f"api_journal_get error: {e}")
        return jsonify({"ok": False, "error": str(e)}), 500


@app.route("/api/journal", methods=["POST"])
def api_journal_post():
    """
    Add a journal entry.
    Body: { "entry_date": "YYYY-MM-DD", "session": "london", "tags": "pattern,mistake", "content": "..." }
    """
    try:
        from db.database import add_journal_entry
        body    = request.get_json(silent=True) or {}
        date    = body.get("entry_date", "").strip()
        session = body.get("session", "any").strip()
        tags    = body.get("tags", "").strip()
        content = body.get("content", "").strip()
        if not date or not content:
            return jsonify({"ok": False, "error": "entry_date and content required"}), 400
        entry_id = add_journal_entry(date, session, tags, content)
        return jsonify({"ok": True, "id": entry_id})
    except Exception as e:
        logger.error(f"api_journal_post error: {e}")
        return jsonify({"ok": False, "error": str(e)}), 500


@app.route("/api/journal/<int:entry_id>", methods=["DELETE"])
def api_journal_delete(entry_id: int):
    """Delete a journal entry by id."""
    try:
        from db.database import delete_journal_entry
        ok = delete_journal_entry(entry_id)
        return jsonify({"ok": ok})
    except Exception as e:
        logger.error(f"api_journal_delete error: {e}")
        return jsonify({"ok": False, "error": str(e)}), 500


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