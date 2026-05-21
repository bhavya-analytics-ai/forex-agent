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
_audit_store  = {}          # XAU/XAG only — full proof payload
_extra_store  = {}          # extra strategy candidates keyed by "pair|signal_mode"
_store_lock   = threading.Lock()
_GOLD_PAIRS   = {"XAU_USD", "XAG_USD"}


def update_extra_candidate(pair: str, signal_mode: str, candidate: dict):
    """
    Push an extra strategy candidate (e.g. om_gold_scalp) to the isolated
    extra store. Never touches _signal_store — existing /api/signals is unaffected.
    Thread-safe.

    Stores the FULL candidate dict so all audit/debug fields (evaluated_branches,
    sweep_detected, rejection_stage, displacement_body_pts, etc.) are available
    to the /api/signals/extra endpoint and dashboard. Metadata fields (pair,
    signal_mode, updated_at) are overlaid after copy to ensure they are always
    correct regardless of what the strategy dict contains.
    """
    key = f"{pair}|{signal_mode}"
    with _store_lock:
        stored = dict(candidate)          # shallow copy — never mutate the live candidate
        stored["pair"]       = pair       # always authoritative from caller
        stored["signal_mode"] = signal_mode
        stored["updated_at"] = datetime.now(timezone.utc).strftime("%H:%M:%S")
        _extra_store[key] = stored


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

        # For gold pairs: build full audit proof from data already in scope
        if pair in _GOLD_PAIRS:
            _audit_store[pair] = _build_audit_payload(pair, scored, confluence, ict or {})


def _build_audit_payload(pair: str, scored: dict, confluence: dict, ict: dict) -> dict:
    """
    Assemble signal audit proof for XAU/XAG.
    Reads ONLY from scored/confluence/ict already passed into update_dashboard.
    No engine calls, no new computation, no logic files touched.
    Missing fields → None (rendered as 'not available' in UI).
    """
    # ── SWEEP ─────────────────────────────────────────────────────────────────
    sweep = (ict.get("recent_sweep") or {})
    sweep_out = {
        "found":         bool(sweep),
        "type":          sweep.get("type"),            # "buy_side" | "sell_side"
        "time":          str(sweep.get("time")) if sweep.get("time") else None,
        "swept_level":   sweep.get("swept_level"),     # the swing price that was swept
        "candle_high":   sweep.get("candle_high"),     # wick extreme (buy-side)
        "candle_low":    sweep.get("candle_low"),      # wick extreme (sell-side)
        "candle_close":  sweep.get("candle_close"),
        "wick_size":     round(float(sweep["wick_size"]), 3) if sweep.get("wick_size") else None,
        "bars_ago":      sweep.get("bars_ago"),
        "bias":          sweep.get("bias"),            # "bullish" | "bearish"
        "description":   sweep.get("description"),
    }

    # ── CHoCH ─────────────────────────────────────────────────────────────────
    choch_m5  = ict.get("choch_m5",  {}) or {}
    choch_m15 = ict.get("choch_m15", {}) or {}
    if choch_m5.get("detected"):
        choch_raw, choch_src = choch_m5, "M5"
    elif choch_m15.get("detected"):
        choch_raw, choch_src = choch_m15, "M15"
    else:
        choch_raw, choch_src = {}, None
    choch_out = {
        "found":       bool(choch_raw.get("detected")),
        "source":      choch_src,
        "type":        choch_raw.get("type"),          # "bullish" | "bearish"
        "level":       choch_raw.get("level"),
        "bars_ago":    choch_raw.get("bars_ago"),
        "description": choch_raw.get("description"),
    }

    # ── OB ────────────────────────────────────────────────────────────────────
    ob = ict.get("top_ob") or {}
    ob_out = {
        "found":      bool(ob),
        "type":       ob.get("type"),
        "high":       ob.get("high"),
        "low":        ob.get("low"),
        "mid":        ob.get("mid"),
        "formed_at":  str(ob.get("formed_at")) if ob.get("formed_at") else None,
        "timeframe":  ob.get("timeframe"),
    }

    # ── H1 CONTEXT ────────────────────────────────────────────────────────────
    h1         = (confluence.get("h1") or {})
    h1_struct  = h1.get("structure") or {}
    h1_ema     = confluence.get("h1_ema_50")
    price      = confluence.get("current_price", 0)
    below_ema  = confluence.get("price_below_h1_ema")   # bool or None
    h1_out = {
        "bias":            h1.get("bias"),
        "trend":           h1_struct.get("trend"),
        "phase":           h1_struct.get("phase"),
        "strength":        h1_struct.get("strength"),
        "last_high":       h1_struct.get("last_high"),
        "last_low":        h1_struct.get("last_low"),
        "ema_50":          round(float(h1_ema), 2) if h1_ema else None,
        "price":           round(float(price),  2) if price  else None,
        "price_vs_ema":    (
            "BELOW" if below_ema is True  else
            "ABOVE" if below_ema is False else
            None
        ),
        "ema_dist_pct":    round(abs(price - h1_ema) / h1_ema * 100, 2)
                           if (h1_ema and price) else None,
        # H1 candle color lives in gold_strategy — if it blocked, reason string has it
        "block_reason":    scored.get("dl_block_reason") or None,
    }

    # ── PREMIUM / DISCOUNT ────────────────────────────────────────────────────
    pd = (ict.get("premium_discount") or {})
    pd_out = {
        "zone":        pd.get("zone"),
        "pct":         round(float(pd["pct"]) * 100, 1) if pd.get("pct") is not None else None,
        "swing_high":  pd.get("swing_high"),
        "swing_low":   pd.get("swing_low"),
        "equilibrium": pd.get("equilibrium"),
        "description": pd.get("description"),
    }

    # ── SESSION / KILLZONE ────────────────────────────────────────────────────
    sess     = (scored.get("session_ctx") or {})
    kz_label = None
    kz_mins  = None
    in_kz    = (scored.get("conditions") or {}).get("in_killzone", False)
    # Richer killzone data from ict flags if available
    kz_out = {
        "session":         sess.get("session"),
        "in_killzone":     in_kz,
        "killzone_label":  kz_label,
        "mins_left":       kz_mins,
    }

    # ── NEWS ──────────────────────────────────────────────────────────────────
    news    = (scored.get("news_check") or {})
    news_out = {
        "safe":        news.get("safe"),
        "caution":     news.get("caution"),
        "spike_watch": news.get("spike_watch"),
        "reason":      news.get("reason"),
    }

    # ── SCORE PROOF ───────────────────────────────────────────────────────────
    # Likelihood table is a constant in scorer — import it read-only
    try:
        from alerts.scorer import STANDARD_LIKELIHOODS, BASE_RATES
        lk_table   = STANDARD_LIKELIHOODS
        base_rates = BASE_RATES
    except Exception:
        lk_table   = {}
        base_rates = {}

    conditions  = (scored.get("conditions") or {})
    bayes_setup = scored.get("bayes_setup", "default")
    base_rate   = base_rates.get(bayes_setup, base_rates.get("default", 0.45))

    cond_rows = []
    for cname, present in conditions.items():
        if cname not in lk_table:
            continue
        mult = lk_table[cname]["yes" if present else "no"]
        cond_rows.append({
            "name":      cname,
            "present":   present,
            "mult":      mult,
            "effect":    "boost" if mult > 1.0 else ("penalty" if mult < 1.0 else "neutral"),
        })
    # Sort: biggest penalties first, then biggest boosts last
    cond_rows.sort(key=lambda r: r["mult"])

    score_out = {
        "setup_type":    bayes_setup,
        "base_rate":     base_rate,
        "base_rate_pct": round(base_rate * 100, 1),
        "conditions":    cond_rows,
        "p_win":         scored.get("p_win"),
        "p_win_pct":     round(scored.get("p_win", 0) * 100, 1),
        "ev":            scored.get("ev"),
        "grade":         scored.get("grade"),
    }

    # ── VERDICT ───────────────────────────────────────────────────────────────
    tl = (scored.get("trade_levels") or {})
    verdict_out = {
        "entry_state":  scored.get("entry_state"),
        "blocked":      scored.get("dl_blocked", False),
        "block_reason": scored.get("dl_block_reason"),
        "grade":        scored.get("grade"),
        "score":        scored.get("score"),
        "trade_levels": tl,
        "flags":        scored.get("flags", []),
        "signal_id":    scored.get("signal_id"),
    }

    return {
        "pair":       pair,
        "scanned_at": datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC"),
        "sweep":      sweep_out,
        "choch":      choch_out,
        "ob":         ob_out,
        "h1":         h1_out,
        "pd":         pd_out,
        "session":    kz_out,
        "news":       news_out,
        "score":      score_out,
        "verdict":    verdict_out,
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


def _no_cache_response(data):
    """
    Build a JSON response with cache-busting headers.
    Prevents browser and CDN from serving stale signal/performance data.
    """
    from flask import make_response
    resp = make_response(jsonify(data))
    resp.headers["Cache-Control"] = "no-store, no-cache, must-revalidate, max-age=0"
    resp.headers["Pragma"]        = "no-cache"
    resp.headers["Expires"]       = "0"
    return resp


@app.route("/api/recent_signals")
def api_recent_signals():
    """
    Returns recent ENTER_NOW signals — SQLite first, CSV fallback.

    Query params:
      include_archived=0  (default) — only active signals (is_archived=0)
      include_archived=1            — all signals including archived

    Response has Cache-Control: no-store to prevent stale browser cache.
    Archived/bad-run rows are NEVER returned unless include_archived=1.
    """
    from flask import request as _req
    include_archived = _req.args.get("include_archived", "0") == "1"

    try:
        from db.database import get_recent_agent_signals
        rows = get_recent_agent_signals(limit=500, include_archived=include_archived)
        return _no_cache_response({"signals": _sanitize(rows), "include_archived": include_archived})
    except Exception as e:
        logger.warning(f"SQLite recent_signals failed, falling back to CSV: {e}")

    # CSV fallback — archived filter not supported in CSV, always returns active only
    try:
        import pandas as pd
        from config import LOG_CONFIG
        path = LOG_CONFIG["signal_log_path"]
        if not __import__("os").path.exists(path):
            return _no_cache_response({"signals": [], "include_archived": False})
        df = pd.read_csv(path)
        cols = ["signal_id", "timestamp_utc", "pair", "direction",
                "setup_type", "grade", "score", "entry_price",
                "sl_pips", "tp1_pips", "outcome", "outcome_pips", "taken"]
        for c in cols:
            if c not in df.columns:
                df[c] = ""
        # CSV fallback: apply bad-window exclusion — archived rows not in CSV anyway
        from alerts.logger import _is_bad_window_csv
        if "timestamp_utc" in df.columns:
            df = df[~df["timestamp_utc"].apply(_is_bad_window_csv)]
        recent = df[cols].tail(500).iloc[::-1].fillna("").to_dict("records")
        return _no_cache_response({"signals": recent, "include_archived": False})
    except Exception as e:
        logger.error(f"recent_signals CSV fallback error: {e}")
        return _no_cache_response({"signals": [], "error": str(e)})


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

        # Start lifecycle monitor for this taken signal
        try:
            from db.database import get_agent_signal
            from ml.agent_trade_monitor import start_agent_monitor
            sig2  = get_agent_signal(signal_id)
            if sig2:
                _sl   = float(sig2.get("actual_sl")  or sig2.get("user_sl")  or sig2.get("sl_price")  or 0)
                _tp1  = float(sig2.get("actual_tp1") or sig2.get("user_tp1") or sig2.get("tp1_price") or 0)
                _entr = float(sig2.get("entry_price") or 0)
                if _sl > 0 and _tp1 > 0 and _entr > 0:
                    start_agent_monitor(signal_id, sig2["pair"], sig2["direction"], _entr, _sl, _tp1)
        except Exception as _me:
            logger.warning(f"Could not start agent monitor for {signal_id}: {_me}")

        return jsonify({"ok": True, "signal_id": signal_id})
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)}), 500


@app.route("/api/mark_outcome", methods=["POST"])
def api_mark_outcome():
    """
    Manually mark a signal outcome from the dashboard.
    Body: {
        "signal_id": "...",
        "outcome":   "WIN" | "LOSS" | "NEUTRAL",
        "notes":     "",
        "override_reason": ""  ← REQUIRED if signal is taken+open (monitor active)
    }

    Gate: If the signal is taken+open (monitor running), a plain W/L click is rejected
    with HTTP 409 {"requires_override": true}. The caller must provide override_reason
    to confirm they understand the monitor will be stopped and the close is manual.

    SQLite is source of truth — written first. CSV update is best-effort.
    """
    try:
        from db.database import get_agent_signal, update_agent_signal_outcome, update_agent_signal_forensic
        body            = request.get_json(silent=True) or {}
        signal_id       = body.get("signal_id", "").strip()
        outcome         = body.get("outcome", "").upper().strip()
        notes           = body.get("notes", "")
        override_reason = body.get("override_reason", "").strip()

        if not signal_id:
            return jsonify({"ok": False, "error": "signal_id required"}), 400
        if outcome not in ("WIN", "LOSS", "NEUTRAL"):
            return jsonify({"ok": False, "error": "outcome must be WIN, LOSS, or NEUTRAL"}), 400

        # ── W/L integrity gate: taken+open signals require override_reason ─────
        sig = get_agent_signal(signal_id)
        if sig:
            _is_taken = sig.get("taken") == 1 or sig.get("taken") is True
            _is_open  = not sig.get("outcome") or sig.get("outcome") == ""
            _has_exit = bool(sig.get("exit_timestamp"))
            if _is_taken and _is_open and not _has_exit:
                if not override_reason:
                    return jsonify({
                        "ok": False,
                        "error": (
                            "Signal is taken and open — the monitor will auto-close on TP/SL. "
                            "Provide override_reason to mark manually."
                        ),
                        "requires_override": True,
                    }), 409

                # Valid manual override — stop monitor and write with forensic fields
                try:
                    from ml.agent_trade_monitor import stop_agent_monitor
                    stop_agent_monitor(signal_id)
                except Exception as _se:
                    logger.warning(f"Could not stop agent monitor for {signal_id}: {_se}")

                now_utc          = datetime.now(timezone.utc)
                exit_ts          = now_utc.strftime("%Y-%m-%d %H:%M:%S")
                duration_minutes = None
                entry_ts_str     = sig.get("timestamp_utc")
                if entry_ts_str:
                    try:
                        entry_dt = datetime.strptime(str(entry_ts_str), "%Y-%m-%d %H:%M:%S").replace(tzinfo=timezone.utc)
                        duration_minutes = max(0, int((now_utc - entry_dt).total_seconds() / 60))
                    except Exception:
                        pass

                override_note = f"[MANUAL_OVERRIDE] {outcome} | reason: {override_reason}"
                if notes:
                    override_note += f" | {notes}"

                update_agent_signal_forensic(
                    signal_id              = signal_id,
                    outcome                = outcome,
                    outcome_pips           = 0,
                    notes                  = override_note,
                    exit_timestamp         = exit_ts,
                    exit_reason            = "MANUAL_OVERRIDE",
                    trade_duration_minutes = duration_minutes,
                )
                try:
                    from alerts.logger import update_outcome
                    update_outcome(signal_id, outcome, pips=0, notes=override_note)
                except Exception:
                    pass

                logger.info(
                    f"Manual override: {signal_id} → {outcome} "
                    f"| reason: {override_reason} | duration={duration_minutes}min"
                )
                return jsonify({
                    "ok":          True,
                    "signal_id":   signal_id,
                    "outcome":     outcome,
                    "exit_reason": "MANUAL_OVERRIDE",
                })

        # ── Normal path: not taken+open — plain outcome write ─────────────────
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


@app.route("/api/sync_status", methods=["GET"])
def api_sync_status_get():
    """Return last known local sync counts (posted by sync.py after each run)."""
    try:
        from db.database import get_sync_status
        return jsonify(get_sync_status())
    except Exception as e:
        return jsonify({"error": str(e), "agent_signals": None, "manual_trades": None, "synced_at": None})


@app.route("/api/sync_status", methods=["POST"])
def api_sync_status_post():
    """sync.py POSTs local counts here after every sync run."""
    try:
        from db.database import set_sync_status
        body = request.get_json(silent=True) or {}
        set_sync_status(
            agent_signals = int(body.get("agent_signals", 0)),
            manual_trades = int(body.get("manual_trades", 0)),
            synced_at     = body.get("synced_at", ""),
        )
        return jsonify({"ok": True})
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)}), 500


@app.route("/api/audit/<pair>")
def api_audit(pair: str):
    """
    Signal audit for XAU_USD / XAG_USD.
    Returns the full proof payload from the last scan — no new computation.
    """
    key = pair.upper().replace("-", "_")
    with _store_lock:
        payload = _audit_store.get(key)
    if payload is None:
        return jsonify({"error": f"No audit data for {key} — waiting for first scan"}), 404
    return jsonify(_sanitize(payload))


@app.route("/api/performance")
def api_performance():
    """
    Returns performance summary — SQLite first, CSV fallback.

    Always excludes:
      - Archived signals (is_archived=1): closed-market windows (Sat/Sun-pre-22/Fri-21:30+)
      - Bad-run window signals (May 15–18 2026): approved manual exclusion for scanner
        over-signaling period. Rows are marked is_archived=1 / manual_exclusion=1 in DB.

    Response audit fields:
      stats_source              "sqlite" or "csv"
      excluded_archived_count   rows excluded by is_archived (DB path)
      excluded_bad_window_count rows excluded by market-hours filter (CSV path)
      excluded_bad_run_count    rows excluded by bad-run window
      bad_run_window_applied    true
    """
    from db.database import BAD_RUN_WINDOW_START, BAD_RUN_WINDOW_END
    _bad_run = (BAD_RUN_WINDOW_START, BAD_RUN_WINDOW_END)

    try:
        from db.database import get_performance_summary_db
        # DB path: bad-run rows are already is_archived=1 (stamped at startup),
        # so they are excluded by the base is_archived filter. The bad_run_window
        # param adds the count to the audit response even if they're already archived.
        summary = get_performance_summary_db(bad_run_window=_bad_run)
        return _no_cache_response(_sanitize(summary))
    except Exception as e:
        logger.warning(f"SQLite performance failed, falling back to CSV: {e}")

    try:
        from alerts.logger import get_performance_summary
        # CSV fallback: apply both market-hours filter AND bad-run window exclusion.
        # Also write excluded rows to audit file (idempotent).
        summary = get_performance_summary(bad_run_window=_bad_run)
        _write_bad_run_audit_csv(bad_run_window=_bad_run)
        return _no_cache_response(_sanitize(summary))
    except Exception as e:
        logger.error(f"performance endpoint error: {e}")
        return _no_cache_response({"error": str(e)})


def _write_bad_run_audit_csv(bad_run_window: tuple) -> None:
    """
    Write CSV rows that fall inside bad_run_window to a separate audit file.
    Rows are NOT removed from the original CSV — this is additive only.
    Output: logs/excluded_bad_run_signals_2026-05-15_to_2026-05-18.csv
    Idempotent — rewrites the audit file on every call (safe because source CSV is read-only here).
    """
    import os, csv as _csv
    import pandas as pd
    from config import LOG_CONFIG

    src_path  = LOG_CONFIG["signal_log_path"]
    audit_path = os.path.join(
        os.path.dirname(src_path),
        "excluded_bad_run_signals_2026-05-15_to_2026-05-18.csv",
    )

    try:
        if not os.path.exists(src_path):
            return
        df = pd.read_csv(src_path)
        if "timestamp_utc" not in df.columns:
            return
        start_str, end_str = bad_run_window
        mask = (df["timestamp_utc"] >= start_str) & (df["timestamp_utc"] <= end_str)
        excluded = df[mask]
        if excluded.empty:
            return
        excluded.to_csv(audit_path, index=False)
        logger.info(
            f"Bad-run audit CSV written: {audit_path} ({len(excluded)} rows)"
        )
    except Exception as e:
        logger.warning(f"_write_bad_run_audit_csv failed (non-fatal): {e}")


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
        sl_price    = body.get("sl_price")
        tp1_price   = body.get("tp1_price")
        setup_type  = body.get("setup_type", "manual").strip()
        notes       = body.get("notes", "")

        if not pair:
            return jsonify({"ok": False, "error": "pair required"}), 400
        if direction not in ("bullish", "bearish"):
            return jsonify({"ok": False, "error": "direction must be bullish or bearish"}), 400
        if not entry_price:
            return jsonify({"ok": False, "error": "entry_price required"}), 400

        sl_val  = float(sl_price)  if sl_price  else None
        tp1_val = float(tp1_price) if tp1_price else None

        signal_id = log_manual_trade(pair, direction, float(entry_price), setup_type, notes,
                                     sl_price=sl_val, tp1_price=tp1_val)
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

        result = close_agent_trade(signal_id, exit_price, entry_price, direction, pip,
                                   exit_reason="MANUAL_CLOSE")

        # Stop the lifecycle monitor — trade is now closed
        try:
            from ml.agent_trade_monitor import stop_agent_monitor
            stop_agent_monitor(signal_id)
        except Exception as _me:
            logger.warning(f"Could not stop agent monitor after manual close {signal_id}: {_me}")

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

        # Restart lifecycle monitor with updated levels (if signal is still open+taken)
        try:
            from ml.agent_trade_monitor import stop_agent_monitor, start_agent_monitor
            stop_agent_monitor(signal_id)
            _updated = get_agent_signal(signal_id)
            if _updated:
                _is_open  = not _updated.get("outcome") or _updated.get("outcome") == ""
                _is_taken = _updated.get("taken") == 1 or _updated.get("taken") is True
                _no_exit  = not _updated.get("exit_timestamp")
                if _is_open and _is_taken and _no_exit:
                    _new_sl   = float(_updated.get("actual_sl")  or _updated.get("sl_price")  or 0)
                    _new_tp1  = float(_updated.get("actual_tp1") or _updated.get("tp1_price") or 0)
                    _entry_px = float(_updated.get("entry_price") or 0)
                    if _new_sl > 0 and _new_tp1 > 0 and _entry_px > 0:
                        start_agent_monitor(signal_id, current["pair"], current["direction"],
                                            _entry_px, _new_sl, _new_tp1)
        except Exception as _me:
            logger.warning(f"Could not restart agent monitor after level update {signal_id}: {_me}")

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

        # Start lifecycle monitor — use fill_price as entry if available
        try:
            from ml.agent_trade_monitor import start_agent_monitor
            _entry_px = fill_price or float(signal.get("entry_price") or 0)
            _sl_px    = float(sl_price)
            _tp_px    = float(tp1_price)
            if _entry_px > 0 and _sl_px > 0 and _tp_px > 0:
                start_agent_monitor(signal_id, pair, direction, _entry_px, _sl_px, _tp_px)
        except Exception as _me:
            logger.warning(f"Could not start agent monitor after take_trade {signal_id}: {_me}")

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


@app.route("/api/signals/extra")
def api_signals_extra():
    """
    Extra strategy candidates (e.g. om_gold_scalp) that run in parallel
    with the legacy scanner but are stored separately.

    Keyed by "pair|signal_mode". All entries have should_log=False and
    should_alert=False while OM_STRATEGY_ENABLED / per-strategy flags are off.

    This endpoint does NOT affect /api/signals — existing dashboard is unchanged.
    """
    with _store_lock:
        data = _sanitize(list(_extra_store.values()))
    return jsonify({
        "candidates":  data,
        "count":       len(data),
        "updated_at":  datetime.now(timezone.utc).strftime("%H:%M:%S UTC"),
    })


@app.route("/api/agent_monitors")
def api_agent_monitors():
    """Return list of signal_ids currently being monitored by the agent trade monitor."""
    try:
        from ml.agent_trade_monitor import get_active_agent_monitors
        active = get_active_agent_monitors()
        return jsonify({"ok": True, "active": active, "count": len(active)})
    except Exception as e:
        return jsonify({"ok": False, "active": [], "error": str(e)})


@app.route("/api/debug/status")
def api_debug_status():
    """
    Trusted live debug/status endpoint.

    Read-only. Safe if DB or tables are missing.
    Returns: version identity, live env flags, DB introspection, scanner mode.
    Use this instead of `railway run` guessing for post-deploy verification.
    """
    import os
    import sqlite3 as _sqlite3

    # ── VERSION ───────────────────────────────────────────────────────────────
    from version import get_version
    _v = get_version()
    version_block = {
        "git_sha":        _v["git_sha"],
        "branch":         _v["git_branch"],
        "build_time_utc": _v["build_time_utc"],
    }

    # ── ENV (read live from os.getenv — not the module-level cached config) ──
    def _flag(key: str) -> bool:
        return os.getenv(key, "false").lower() == "true"

    env_block = {
        "OM_STRATEGY_ENABLED":   _flag("OM_STRATEGY_ENABLED"),
        "LEGACY_GOLD_ENABLED":   _flag("LEGACY_GOLD_ENABLED"),
        "LEGACY_FOREX_ENABLED":  _flag("LEGACY_FOREX_ENABLED"),
        "OM_GOLD_SCALP_ENABLED": _flag("OM_GOLD_SCALP_ENABLED"),
    }

    # ── DATABASE ──────────────────────────────────────────────────────────────
    from db.database import _db_path
    db_path   = _db_path()
    db_exists = os.path.exists(db_path)

    tables          = []
    signals_table   = None
    recent_count    = None
    last_ts         = None
    db_error        = None

    if db_exists:
        try:
            conn = _sqlite3.connect(db_path)
            cur  = conn.cursor()

            # List all tables — no hardcoded assumptions
            cur.execute("SELECT name FROM sqlite_master WHERE type='table' ORDER BY name")
            tables = [r[0] for r in cur.fetchall()]

            # Auto-detect signals table: prefer agent_signals, then any table
            # whose name contains "signal"
            _candidates = ["agent_signals"] + [
                t for t in tables
                if "signal" in t.lower() and t != "agent_signals"
            ]
            for _c in _candidates:
                if _c in tables:
                    signals_table = _c
                    break

            if signals_table:
                # Auto-detect timestamp column
                cur.execute(f"PRAGMA table_info({signals_table})")
                _cols = [r[1] for r in cur.fetchall()]
                _ts_col = next(
                    (c for c in ("timestamp_utc", "created_at", "timestamp") if c in _cols),
                    None,
                )

                if _ts_col:
                    cur.execute(
                        f"SELECT COUNT(*) FROM {signals_table} "          # nosec (no user input)
                        f"WHERE {_ts_col} > datetime('now', '-30 minutes')"
                    )
                    recent_count = cur.fetchone()[0]

                    cur.execute(
                        f"SELECT {_ts_col} FROM {signals_table} "
                        f"ORDER BY {_ts_col} DESC LIMIT 1"
                    )
                    _row = cur.fetchone()
                    last_ts = _row[0] if _row else None

            conn.close()
        except Exception as _e:
            db_error = str(_e)

    db_block = {
        "resolved_path":           db_path,
        "exists":                  db_exists,
        "tables":                  tables,
        "signals_table":           signals_table,
        "recent_signal_count_30m": recent_count,
        "last_signal_timestamp":   last_ts,
    }
    if db_error:
        db_block["error"] = db_error

    # ── SCANNER ───────────────────────────────────────────────────────────────
    try:
        from filters.mode_manager import get_active_mode
        _mode = get_active_mode()
    except Exception as _e:
        _mode = f"ERROR: {_e}"

    scanner_block = {
        "mode":       _mode,
        "watch_only": not _flag("OM_STRATEGY_ENABLED"),
    }

    return jsonify({
        "version":  version_block,
        "env":      env_block,
        "database": db_block,
        "scanner":  scanner_block,
    })


@app.route("/api/live-price")
def api_live_price():
    """
    Real-time OANDA bid/ask/mid for a single pair.
    Used by the manual trades tracker to get true live price every 3-5s.

    Query param: ?pair=XAU_USD  (also accepts XAU/USD, USD_JPY, USD/JPY)

    Returns:
      {pair, bid, ask, mid, timestamp_utc, source, cache_age_ms}

    Server-side cache: 2s TTL per pair — prevents hammering OANDA.
    Returns 503 JSON on OANDA failure (never crashes dashboard).
    """
    import time as _time
    from datetime import datetime, timezone

    pair_raw = request.args.get("pair", "").strip()
    if not pair_raw:
        return jsonify({"error": "pair parameter required", "code": 400}), 400

    # Normalize: XAU/USD or XAU_USD → XAU_USD
    pair = pair_raw.upper().replace("/", "_")

    # ── Cache check ───────────────────────────────────────────────────────────
    _now = _time.time()
    cached = _live_price_cache.get(pair)
    if cached and (_now - cached["cached_at"]) < _LIVE_PRICE_CACHE_TTL:
        age_ms = int((_now - cached["cached_at"]) * 1000)
        return jsonify({
            "pair":          pair,
            "bid":           cached["bid"],
            "ask":           cached["ask"],
            "mid":           cached["mid"],
            "timestamp_utc": cached["timestamp_utc"],
            "source":        "oanda_pricing_cached",
            "cache_age_ms":  age_ms,
        })

    # ── Live OANDA fetch ──────────────────────────────────────────────────────
    try:
        from core.fetcher import get_live_bid_ask
        bid, ask = get_live_bid_ask(pair)
        if bid is None or ask is None:
            raise ValueError("OANDA returned None prices")
        mid = round((bid + ask) / 2, 5)
        ts  = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")

        _live_price_cache[pair] = {
            "bid":          bid,
            "ask":          ask,
            "mid":          mid,
            "timestamp_utc": ts,
            "cached_at":    _time.time(),
        }
        return jsonify({
            "pair":          pair,
            "bid":           bid,
            "ask":           ask,
            "mid":           mid,
            "timestamp_utc": ts,
            "source":        "oanda_pricing",
            "cache_age_ms":  0,
        })

    except Exception as e:
        logger.warning(f"/api/live-price error for {pair}: {e}")
        return jsonify({
            "error":  f"OANDA unavailable: {e}",
            "pair":   pair,
            "code":   503,
        }), 503


# Per-pair live price cache: pair -> {bid, ask, mid, timestamp_utc, cached_at}
_live_price_cache: dict = {}
_LIVE_PRICE_CACHE_TTL   = 2.0  # seconds


@app.route("/api/version")
def api_version():
    """
    Deploy identity — returns git SHA, branch, and process start time.

    Use this to prove which commit is actually running on Railway.
    git_sha resolution order:
      1. GIT_SHA env var
      2. RAILWAY_GIT_COMMIT_SHA env var (Railway injects on git-linked deploys)
      3. RAILWAY_GIT_COMMIT env var (older Railway name)
      4. Local git rev-parse HEAD (dev only — not available in Railway container)
      5. "unknown"
    """
    from version import get_version
    return jsonify(get_version())


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

    # Resume monitors for any taken+open agent signals from last session
    try:
        from ml.agent_trade_monitor import resume_agent_monitors_on_startup
        resume_agent_monitors_on_startup()
    except Exception as e:
        logger.warning(f"Could not resume agent trade monitors: {e}")

    # Start outcome labeler in background — auto-labels agent signals after 15 min
    labeler_thread = threading.Thread(target=_run_outcome_labeler, daemon=True, name="OutcomeLabeler")
    labeler_thread.start()

    app.run(host=host, port=port, debug=False, use_reloader=False)