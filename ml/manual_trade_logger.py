"""
ml/manual_trade_logger.py — Manual trade logger

Separate from agent signals. Logs trades YOU take manually.
Schema matches agent_signals.csv so both can be merged for model training.

Flow:
  1. You click "Log Trade" on dashboard → fills pair, direction, entry price
  2. System calculates SL/TP using same gold_strategy logic
  3. Trade saved to logs/manual_trades.csv with source="manual"
  4. Monitor thread checks M5 candles every 5 min until TP or SL hit
  5. On close → writes WIN/LOSS + post-mortem note (what went right/wrong)
"""

import os
import csv
import logging
import threading
import time
import hashlib
from datetime import datetime, timezone

logger   = logging.getLogger(__name__)

_MANUAL_COLUMNS = [
    "signal_id",
    "source",           # always "manual"
    "timestamp_utc",
    "pair",
    "direction",
    "setup_type",
    "entry_price",
    "sl_price",
    "tp1_price",
    "tp2_price",
    "sl_pips",
    "tp1_pips",
    "tp2_pips",
    "rr1",
    "outcome",
    "outcome_pips",
    "post_mortem",      # what went right / wrong in plain English
    "notes",
    "session",
    "killzone",
    "h1_trend",
    "m15_trend",
    "m5_trend",
    "news_safe",
]

# Active monitors: signal_id → thread watching for TP/SL hit
_active_monitors = {}
_monitor_lock    = threading.Lock()


def _get_log_path() -> str:
    from config import LOG_CONFIG
    return LOG_CONFIG["manual_log_path"]


def _ensure_log_file():
    path = _get_log_path()
    os.makedirs(os.path.dirname(path), exist_ok=True)
    if not os.path.exists(path):
        with open(path, "w", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=_MANUAL_COLUMNS)
            writer.writeheader()
        logger.info(f"Created manual trade log at {path}")


def _make_signal_id(pair: str, timestamp: datetime) -> str:
    raw = f"manual_{pair}_{timestamp.strftime('%Y%m%d_%H%M%S')}"
    return raw


def _calculate_levels(pair: str, direction: str, entry: float) -> dict:
    """
    Calculate SL/TP using gold_strategy logic for gold pairs,
    pip-based fallback for forex pairs.
    """
    try:
        from core.fetcher import pip_size
        pip = pip_size(pair)

        # Gold/Silver: dollar-based levels
        if pair in ("XAU_USD", "XAG_USD"):
            sl_dist  = 20.0 * pip   # 200 pips default for gold
            tp1_dist = sl_dist * 2
            tp2_dist = sl_dist * 3
        else:
            sl_dist  = 20 * pip
            tp1_dist = sl_dist * 2
            tp2_dist = sl_dist * 3

        if direction == "bullish":
            sl   = round(entry - sl_dist,  5)
            tp1  = round(entry + tp1_dist, 5)
            tp2  = round(entry + tp2_dist, 5)
        else:
            sl   = round(entry + sl_dist,  5)
            tp1  = round(entry - tp1_dist, 5)
            tp2  = round(entry - tp2_dist, 5)

        sl_pips  = round(sl_dist  / pip, 1)
        tp1_pips = round(tp1_dist / pip, 1)
        tp2_pips = round(tp2_dist / pip, 1)
        rr1      = f"1:{round(tp1_dist / sl_dist, 1)}"

        return {
            "sl_price":  sl,
            "tp1_price": tp1,
            "tp2_price": tp2,
            "sl_pips":   sl_pips,
            "tp1_pips":  tp1_pips,
            "tp2_pips":  tp2_pips,
            "rr1":       rr1,
        }

    except Exception as e:
        logger.warning(f"Could not calculate levels for {pair}: {e}")
        return {
            "sl_price": 0, "tp1_price": 0, "tp2_price": 0,
            "sl_pips": 0,  "tp1_pips": 0,  "tp2_pips": 0, "rr1": "1:2",
        }


def log_manual_trade(pair: str, direction: str, entry_price: float,
                     setup_type: str = "manual", notes: str = "",
                     sl_price: float = None, tp1_price: float = None) -> str:
    """
    Log a manual trade. Uses provided SL/TP if given, otherwise calculates defaults.
    Writes to SQLite + CSV backup, starts background monitor for TP/SL hit.
    Returns signal_id.
    """
    _ensure_log_file()

    now       = datetime.utcnow()
    signal_id = _make_signal_id(pair, now)

    # Use provided SL/TP if valid, otherwise fall back to calculated defaults
    if sl_price and tp1_price and sl_price > 0 and tp1_price > 0:
        from core.fetcher import pip_size
        pip      = pip_size(pair)
        sl_dist  = abs(sl_price  - entry_price)
        tp1_dist = abs(tp1_price - entry_price)
        levels   = {
            "sl_price":  round(sl_price,  5),
            "tp1_price": round(tp1_price, 5),
            "tp2_price": round(tp1_price, 5),  # tp2 same as tp1 when user sets manually
            "sl_pips":   round(sl_dist  / pip, 1),
            "tp1_pips":  round(tp1_dist / pip, 1),
            "tp2_pips":  round(tp1_dist / pip, 1),
            "rr1":       f"1:{round(tp1_dist / sl_dist, 1)}" if sl_dist > 0 else "1:2",
        }
    else:
        levels = _calculate_levels(pair, direction, entry_price)

    # Capture session/killzone/trend context at time of entry (for model training)
    session = killzone = h1_trend = m15_trend = m5_trend = None
    news_safe = None
    try:
        from filters.killzones import get_killzone
        from filters.session import get_session
        from core.fetcher import fetch_candles
        from core.structure import detect_structure
        session  = get_session()
        killzone = get_killzone() or ""
        for tf, key in [("H1", "h1_trend"), ("M15", "m15_trend"), ("M5", "m5_trend")]:
            df = fetch_candles(pair, tf)
            if df is not None and not df.empty:
                st = detect_structure(df)
                val = st.get("trend", "unknown") if st else "unknown"
                if key == "h1_trend":   h1_trend  = val
                elif key == "m15_trend": m15_trend = val
                else:                    m5_trend  = val
    except Exception as e:
        logger.warning(f"Context capture failed (non-fatal): {e}")
    try:
        from filters.news import is_news_safe
        news_safe = 1 if is_news_safe(pair) else 0
    except Exception:
        pass

    # Capture current system mode — news_sniper or normal
    signal_mode = "normal"
    try:
        from filters.mode_manager import get_active_mode
        signal_mode = get_active_mode()
    except Exception:
        pass

    row = {
        "signal_id":     signal_id,
        "source":        "manual",
        "timestamp_utc": now.strftime("%Y-%m-%d %H:%M:%S"),
        "pair":          pair,
        "direction":     direction,
        "setup_type":    setup_type,
        "entry_price":   entry_price,
        "sl_price":      levels["sl_price"],
        "tp1_price":     levels["tp1_price"],
        "tp2_price":     levels["tp2_price"],
        "sl_pips":       levels["sl_pips"],
        "tp1_pips":      levels["tp1_pips"],
        "tp2_pips":      levels["tp2_pips"],
        "rr1":           levels["rr1"],
        "outcome":       "",
        "outcome_pips":  "",
        "post_mortem":   "",
        "notes":         notes,
        "session":       session,
        "killzone":      killzone,
        "h1_trend":      h1_trend,
        "m15_trend":     m15_trend,
        "m5_trend":      m5_trend,
        "news_safe":     news_safe,
        "signal_mode":   signal_mode,
    }

    # Primary: SQLite
    try:
        from db.database import insert_manual_trade
        insert_manual_trade(row)
    except Exception as e:
        logger.warning(f"SQLite write failed for {signal_id}: {e}")

    # Backup: CSV (best-effort — never crash the trade log if CSV missing)
    try:
        _ensure_log_file()
        path = _get_log_path()
        with open(path, "a", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=_MANUAL_COLUMNS)
            writer.writerow(row)
    except Exception as e:
        logger.warning(f"CSV backup failed (non-fatal, SQLite already saved): {e}")

    logger.info(f"Manual trade logged: {signal_id} {pair} {direction} @ {entry_price}")

    # Start background monitor
    _start_monitor(signal_id, pair, direction, entry_price,
                   levels["sl_price"], levels["tp1_price"], levels["sl_pips"])

    return signal_id


def _start_monitor(signal_id, pair, direction, entry, sl, tp1, sl_pips):
    """Start a background thread watching M5 candles for TP/SL hit."""
    with _monitor_lock:
        if signal_id in _active_monitors:
            return

    t = threading.Thread(
        target=_monitor_trade,
        args=(signal_id, pair, direction, entry, sl, tp1, sl_pips),
        daemon=True,
        name=f"Monitor-{signal_id}",
    )
    with _monitor_lock:
        _active_monitors[signal_id] = t
    t.start()
    logger.info(f"Monitor started for {signal_id}")


def _monitor_trade(signal_id, pair, direction, entry, sl, tp1, sl_pips):
    """
    Real-time SL/TP monitor — polls live OANDA bid/ask price every 15s.
    Falls back to M5 candle check if live price unavailable.
    Reads SL/TP from DB on every cycle — picks up user edits automatically.
    No timeout — runs until one side is hit.

    BID/ASK correctness:
      LONG:  SL and TP both trigger when BID reaches the level.
      SHORT: SL and TP both trigger when ASK reaches the level.
    Using mid-price (previous behaviour) created a half-spread gap causing
    OANDA to fire before the monitor detected the hit.

    MFE/MAE tracked on every live-price poll cycle. Written to DB on close.
    """
    from core.fetcher import fetch_candles, get_live_bid_ask, pip_size
    import pandas as pd
    pip = pip_size(pair)

    # Wait 30s on startup — gives user time to save their real SL/TP before first check
    time.sleep(30)

    # Read SL/TP from DB — always use whatever is currently saved
    def _current_levels():
        db = _get_levels_from_db(signal_id)
        return db.get("sl", sl), db.get("tp1", tp1)

    cur_sl, cur_tp1 = _current_levels()
    logger.info(f"Monitoring {signal_id} | {pair} {direction} | SL={cur_sl} TP1={cur_tp1}")

    # Running MFE/MAE accumulators (pips, always positive magnitudes)
    mfe_pips = 0.0
    mae_pips = 0.0

    def _update_excursion(trigger_px):
        """Update running MFE/MAE from a live trigger price."""
        nonlocal mfe_pips, mae_pips
        if trigger_px is None:
            return
        if direction == "bullish":
            favorable = (trigger_px - entry) / pip
            adverse   = (entry - trigger_px) / pip
        else:
            favorable = (entry - trigger_px) / pip
            adverse   = (trigger_px - entry) / pip
        if favorable > mfe_pips:
            mfe_pips = round(favorable, 1)
        if adverse > mae_pips:
            mae_pips = round(adverse, 1)

    # Catch-up check: look at candle history since trade was logged using DB levels
    # NOTE: uses mid-price M5 candles (OANDA price="M") — close enough for catch-up;
    # precise bid/ask only available via live polling below.
    try:
        log_time = _get_log_time(signal_id)
        df_hist  = fetch_candles(pair, "M5")
        if df_hist is not None and not df_hist.empty and log_time:
            df_hist = df_hist[df_hist.index > pd.Timestamp(log_time, tz="UTC")]
            if not df_hist.empty:
                if direction == "bullish":
                    tp_hit = (df_hist["high"] >= cur_tp1).any()
                    sl_hit = (df_hist["low"]  <= cur_sl).any()
                else:
                    tp_hit = (df_hist["low"]  <= cur_tp1).any()
                    sl_hit = (df_hist["high"] >= cur_sl).any()
                if tp_hit or sl_hit:
                    if tp_hit and sl_hit:
                        tp_time = df_hist[df_hist["high"] >= cur_tp1].index[0] if direction == "bullish" else df_hist[df_hist["low"] <= cur_tp1].index[0]
                        sl_time = df_hist[df_hist["low"]  <= cur_sl ].index[0] if direction == "bullish" else df_hist[df_hist["high"] >= cur_sl].index[0]
                        result  = "WIN" if tp_time <= sl_time else "LOSS"
                    elif tp_hit:
                        result = "WIN"
                    else:
                        result = "LOSS"
                    logger.info(f"Catch-up: {signal_id} → {result} | SL={cur_sl} TP={cur_tp1}")
                    # No live trigger price available for historical catch-up — pass None
                    _close_trade(signal_id, pair, direction, entry, cur_sl, cur_tp1, pip,
                                 result, exit_price=None, mfe_pips=mfe_pips, mae_pips=mae_pips)
                    return
    except Exception as e:
        logger.warning(f"Catch-up check failed for {signal_id}: {e}")

    # ── Live price polling loop ────────────────────────────────────────────────
    # Checks every 15s using OANDA PricingInfo (real-time bid/ask).
    # LONG:  uses BID for SL and TP trigger evaluation.
    # SHORT: uses ASK for SL and TP trigger evaluation.
    # Falls back to M5 candle high/low if live prices return None.
    while True:
        time.sleep(15)
        try:
            # Always read fresh SL/TP from DB — picks up any user edits
            cur_sl, cur_tp1 = _current_levels()

            # ── Primary: live bid/ask check ────────────────────────────────────
            bid, ask = get_live_bid_ask(pair)

            # Select the correct execution-side price
            if direction == "bullish":
                trigger_px = bid   # closing a long = selling at bid
            else:
                trigger_px = ask   # closing a short = buying at ask

            if trigger_px is not None:
                # Update running MFE/MAE before evaluating trigger
                _update_excursion(trigger_px)

                if direction == "bullish":
                    tp_hit = trigger_px >= cur_tp1
                    sl_hit = trigger_px <= cur_sl
                else:
                    tp_hit = trigger_px <= cur_tp1
                    sl_hit = trigger_px >= cur_sl

                if tp_hit and not sl_hit:
                    logger.info(f"TP hit (bid/ask) {signal_id}: {direction} trigger={trigger_px} TP={cur_tp1}")
                    _close_trade(signal_id, pair, direction, entry, cur_sl, cur_tp1, pip,
                                 "WIN", exit_price=trigger_px, mfe_pips=mfe_pips, mae_pips=mae_pips)
                    break
                elif sl_hit and not tp_hit:
                    logger.info(f"SL hit (bid/ask) {signal_id}: {direction} trigger={trigger_px} SL={cur_sl}")
                    _close_trade(signal_id, pair, direction, entry, cur_sl, cur_tp1, pip,
                                 "LOSS", exit_price=trigger_px, mfe_pips=mfe_pips, mae_pips=mae_pips)
                    break
                elif tp_hit and sl_hit:
                    # Both at once — use direction to decide (price crossed both levels)
                    result = "WIN" if direction == "bullish" else "LOSS"
                    logger.info(f"Both hit (bid/ask) {signal_id}: trigger={trigger_px} → {result}")
                    _close_trade(signal_id, pair, direction, entry, cur_sl, cur_tp1, pip,
                                 result, exit_price=trigger_px, mfe_pips=mfe_pips, mae_pips=mae_pips)
                    break
                continue  # still open — loop

            # ── Fallback: M5 candle check if live prices unavailable ───────────
            # Uses mid-price candles. Timestamp filter ALWAYS applied — log_time
            # is read from DB (Railway-safe) so this is guaranteed non-None
            # on any environment where the trade was correctly stored.
            log_time = _get_log_time(signal_id)
            df = fetch_candles(pair, "M5")
            if df is None or df.empty:
                continue
            if log_time:
                df = df[df.index > pd.Timestamp(log_time, tz="UTC")]
            if df.empty:
                continue

            if direction == "bullish":
                tp_hit = (df["high"] >= cur_tp1).any()
                sl_hit = (df["low"]  <= cur_sl).any()
            else:
                tp_hit = (df["low"]  <= cur_tp1).any()
                sl_hit = (df["high"] >= cur_sl).any()

            if tp_hit and not sl_hit:
                _close_trade(signal_id, pair, direction, entry, cur_sl, cur_tp1, pip,
                             "WIN", exit_price=None, mfe_pips=mfe_pips, mae_pips=mae_pips)
                break
            elif sl_hit and not tp_hit:
                _close_trade(signal_id, pair, direction, entry, cur_sl, cur_tp1, pip,
                             "LOSS", exit_price=None, mfe_pips=mfe_pips, mae_pips=mae_pips)
                break
            elif tp_hit and sl_hit:
                if direction == "bullish":
                    tp_time = df[df["high"] >= cur_tp1].index[0]
                    sl_time = df[df["low"]  <= cur_sl ].index[0]
                else:
                    tp_time = df[df["low"]  <= cur_tp1].index[0]
                    sl_time = df[df["high"] >= cur_sl ].index[0]
                result = "WIN" if tp_time <= sl_time else "LOSS"
                _close_trade(signal_id, pair, direction, entry, cur_sl, cur_tp1, pip,
                             result, exit_price=None, mfe_pips=mfe_pips, mae_pips=mae_pips)
                break

        except Exception as e:
            logger.warning(f"Monitor error for {signal_id}: {e}")
            time.sleep(15)

    with _monitor_lock:
        _active_monitors.pop(signal_id, None)


def _get_log_time(signal_id: str) -> str:
    """
    Read the entry timestamp for a signal.

    DB first (always works on Railway — no CSV on Railway).
    CSV fallback for local dev environments.

    FIX: previously CSV-only. On Railway no CSV exists → returned None →
    timestamp filter was skipped → ALL historical M5 candles were scanned →
    old candles from before trade entry could falsely trigger SL/TP close.
    """
    # ── Primary: SQLite (Railway-safe) ────────────────────────────────────────
    try:
        from db.database import get_manual_trade
        row = get_manual_trade(signal_id)
        if row and row.get("timestamp_utc"):
            return str(row["timestamp_utc"])
    except Exception as e:
        logger.warning(f"_get_log_time DB read failed for {signal_id}: {e}")
    # ── Fallback: CSV (local dev only) ────────────────────────────────────────
    try:
        import pandas as pd
        df  = pd.read_csv(_get_log_path())
        row = df[df["signal_id"] == signal_id]
        if not row.empty:
            return row.iloc[0]["timestamp_utc"]
    except Exception:
        pass
    return None


def _get_levels_from_db(signal_id: str) -> dict:
    """Read current sl_price and tp1_price from DB — picks up user edits."""
    try:
        from db.database import get_manual_trade
        row = get_manual_trade(signal_id)
        if row:
            sl  = float(row.get("sl_price")  or 0)
            tp1 = float(row.get("tp1_price") or 0)
            if sl > 0 and tp1 > 0:
                return {"sl": sl, "tp1": tp1}
    except Exception as e:
        logger.warning(f"_get_levels_from_db failed for {signal_id}: {e}")
    return {}


def _close_trade(signal_id, pair, direction, entry, sl, tp1, pip, result,
                 exit_price=None, mfe_pips=0.0, mae_pips=0.0):
    """
    Write outcome + forensic fields. SQLite first (always), CSV best-effort.

    Forensic fields persisted:
      exit_timestamp          — UTC HH:MM:SS when close was detected
      exit_reason             — SL_HIT | TP_HIT
      exit_price              — bid/ask price that triggered (None for candle fallback)
      max_favorable_excursion — MFE in pips (from live polling loop)
      max_adverse_excursion   — MAE in pips (from live polling loop)
      trade_duration_minutes  — entry → exit elapsed minutes
    """
    pips = round(abs(tp1 - entry) / pip, 1) if result == "WIN" else round(abs(sl - entry) / pip, 1)
    if result == "LOSS":
        pips = -pips
    note = _build_post_mortem(direction, result, entry, sl, tp1, pips)

    # ── Compute forensic fields ────────────────────────────────────────────────
    now_utc         = datetime.now(timezone.utc)
    exit_ts         = now_utc.strftime("%Y-%m-%d %H:%M:%S")
    exit_reason_str = "TP_HIT" if result == "WIN" else "SL_HIT"

    duration_minutes = None
    log_time_str = _get_log_time(signal_id)
    if log_time_str:
        try:
            entry_dt = datetime.strptime(log_time_str, "%Y-%m-%d %H:%M:%S").replace(tzinfo=timezone.utc)
            duration_minutes = max(0, int((now_utc - entry_dt).total_seconds() / 60))
        except Exception:
            pass

    # ── SQLite first — source of truth ────────────────────────────────────────
    try:
        from db.database import update_manual_trade_outcome
        update_manual_trade_outcome(
            signal_id, result, pips, note,
            exit_timestamp=exit_ts,
            exit_reason=exit_reason_str,
            exit_price=round(exit_price, 5) if exit_price is not None else None,
            max_favorable_excursion=round(mfe_pips, 1) if mfe_pips else None,
            max_adverse_excursion=round(mae_pips, 1) if mae_pips else None,
            trade_duration_minutes=duration_minutes,
        )
        logger.info(
            f"Manual trade closed: {signal_id} → {result} ({pips:+.1f} pips) "
            f"| exit_reason={exit_reason_str} exit_price={exit_price} "
            f"MFE={mfe_pips:.1f}p MAE={mae_pips:.1f}p duration={duration_minutes}min"
        )
        logger.info(f"Post-mortem: {note}")
    except Exception as e:
        logger.warning(f"SQLite outcome update failed for {signal_id}: {e}")

    # ── CSV best-effort (Railway has no CSV — that's fine) ───────────────────
    try:
        import pandas as pd
        path = _get_log_path()
        if not __import__("os").path.exists(path):
            return
        df   = pd.read_csv(path)
        mask = df["signal_id"] == signal_id
        if not mask.any():
            return
        df.loc[mask, "outcome"]      = result
        df.loc[mask, "outcome_pips"] = pips
        df.loc[mask, "post_mortem"]  = note
        df.to_csv(path, index=False)
    except Exception as e:
        logger.debug(f"CSV close skipped (non-fatal): {e}")


def _build_post_mortem(direction: str, result: str, entry: float,
                       sl: float, tp1: float, pips: float) -> str:
    """Build a plain-English note on what happened."""
    rr = round(abs(tp1 - entry) / abs(sl - entry), 1) if abs(sl - entry) > 0 else 0

    if result == "WIN":
        return (
            f"WIN +{abs(pips):.1f}p | manual {direction} trade | "
            f"TP1 hit at {tp1} | RR achieved: 1:{rr} | "
            f"What worked: entered at your own discretion, price moved in direction"
        )
    else:
        return (
            f"LOSS {pips:.1f}p | manual {direction} trade | "
            f"SL hit at {sl} | RR was 1:{rr} | "
            f"What went wrong: price reversed before TP1 — review entry timing and zone quality"
        )


def close_trade_manually(signal_id: str, outcome: str, pips: float, notes: str = "") -> tuple:
    """
    Manually close a trade from the dashboard.
    SQLite is source of truth — written first. CSV update is best-effort (may not exist on Railway).
    Returns (ok: bool, error: str)
    """
    from db.database import get_manual_trade, update_manual_trade_outcome

    try:
        final_pips = pips if outcome == "WIN" else -abs(pips)

        # Read row from SQLite to build post-mortem (works on Railway, no CSV needed)
        db_row = get_manual_trade(signal_id)
        if db_row:
            direction = str(db_row.get("direction", "bullish"))
            try:
                entry = float(db_row.get("entry_price") or 0)
                sl    = float(db_row.get("sl_price")    or 0)
                tp1   = float(db_row.get("tp1_price")   or 0)
                note  = _build_post_mortem(direction, outcome, entry, sl, tp1, final_pips)
            except Exception:
                note  = f"{outcome} {final_pips:+.1f} pips | manual close"
        else:
            note = f"{outcome} {final_pips:+.1f} pips | manual close"

        if notes:
            note += f" | Note: {notes}"

        # ── Forensic fields for manual close ──────────────────────────────────
        now_utc          = datetime.now(timezone.utc)
        exit_ts          = now_utc.strftime("%Y-%m-%d %H:%M:%S")
        duration_minutes = None
        log_time_str     = _get_log_time(signal_id)
        if log_time_str:
            try:
                entry_dt = datetime.strptime(log_time_str, "%Y-%m-%d %H:%M:%S").replace(tzinfo=timezone.utc)
                duration_minutes = max(0, int((now_utc - entry_dt).total_seconds() / 60))
            except Exception:
                pass

        # SQLite first — source of truth on Railway
        update_manual_trade_outcome(
            signal_id, outcome, final_pips, note,
            exit_timestamp=exit_ts,
            exit_reason="MANUAL_CLOSE",
            exit_price=None,               # not system-detected; user initiated
            max_favorable_excursion=None,  # MFE/MAE not tracked for manual closes
            max_adverse_excursion=None,
            trade_duration_minutes=duration_minutes,
        )

        # CSV best-effort (may not exist on Railway — that's fine)
        try:
            import pandas as pd
            path = _get_log_path()
            if __import__("os").path.exists(path):
                df   = pd.read_csv(path, dtype=str)
                mask = df["signal_id"] == signal_id
                if mask.any():
                    df.loc[mask, "outcome"]      = str(outcome)
                    df.loc[mask, "outcome_pips"] = str(final_pips)
                    df.loc[mask, "post_mortem"]  = str(note)
                    df.to_csv(path, index=False)
        except Exception as csv_err:
            logger.warning(f"CSV manual close skipped (non-fatal): {csv_err}")

        # Stop the monitor thread
        with _monitor_lock:
            _active_monitors.pop(signal_id, None)

        logger.info(f"Manual close: {signal_id} → {outcome} ({final_pips:+.1f} pips) | duration={duration_minutes}min")
        return True, ""

    except Exception as e:
        logger.warning(f"close_trade_manually error: {e}", exc_info=True)
        return False, str(e) or "Unknown error in close_trade_manually"


def update_trade_levels(signal_id: str, sl_price: float, tp1_price: float, reason: str = "") -> tuple:
    """
    Update SL and TP1 for an open manual trade.
    SQLite-first. CSV update is best-effort only.
    Returns (ok: bool, error: str)
    """
    from core.fetcher import pip_size

    try:
        from db.database import _get_conn, update_manual_trade_levels, insert_level_edit
        conn = _get_conn()
        row = conn.execute(
            "SELECT signal_id, pair, direction, entry_price, sl_price, tp1_price "
            "FROM manual_trades WHERE signal_id = ?", (signal_id,)
        ).fetchone()

        if not row:
            return False, f"Signal {signal_id} not found"

        pair      = row["pair"]
        direction = row["direction"]
        entry     = float(row["entry_price"])
        old_sl    = float(row["sl_price"])
        old_tp1   = float(row["tp1_price"])

        pip      = pip_size(pair)
        sl_pips  = round(abs(sl_price  - entry) / pip, 1)
        tp1_pips = round(abs(tp1_price - entry) / pip, 1)
        rr1      = f"1:{round(tp1_pips / sl_pips, 1)}" if sl_pips > 0 else "1:2"

        # Primary: SQLite
        update_manual_trade_levels(signal_id, sl_price, tp1_price, sl_pips, tp1_pips, rr1)
        insert_level_edit(signal_id, old_sl, sl_price, old_tp1, tp1_price, reason)

        # Backup: CSV best-effort
        try:
            import pandas as pd
            path = _get_log_path()
            if os.path.exists(path):
                df   = pd.read_csv(path, dtype=str)
                mask = df["signal_id"] == signal_id
                if mask.any():
                    df.loc[mask, "sl_price"]  = str(sl_price)
                    df.loc[mask, "tp1_price"] = str(tp1_price)
                    df.loc[mask, "sl_pips"]   = str(sl_pips)
                    df.loc[mask, "tp1_pips"]  = str(tp1_pips)
                    df.loc[mask, "rr1"]       = rr1
                    df.to_csv(path, index=False)
        except Exception as e:
            logger.warning(f"CSV level update failed (non-fatal): {e}")

        # Stop old monitor, restart with new levels
        with _monitor_lock:
            _active_monitors.pop(signal_id, None)
        _start_monitor(signal_id, pair, direction, entry, sl_price, tp1_price, sl_pips)

        logger.info(f"Levels updated: {signal_id} SL={sl_price} TP1={tp1_price} reason='{reason}' | monitor restarted")
        return True, ""

    except Exception as e:
        logger.warning(f"update_trade_levels error: {e}", exc_info=True)
        return False, str(e)


def get_active_monitors() -> list:
    """Returns list of signal_ids currently being monitored."""
    with _monitor_lock:
        return list(_active_monitors.keys())


def resume_monitors_on_startup():
    """
    On app restart, resume monitoring any open trades from SQLite
    (trades with no outcome yet). CSV is unreliable on Railway (ephemeral FS).
    """
    try:
        from db.database import _get_conn
        conn = _get_conn()
        rows = conn.execute(
            "SELECT signal_id, pair, direction, entry_price, sl_price, tp1_price, sl_pips "
            "FROM manual_trades WHERE outcome IS NULL OR outcome = ''"
        ).fetchall()

        if not rows:
            return

        logger.info(f"Resuming monitors for {len(rows)} open manual trades")
        for row in rows:
            try:
                _start_monitor(
                    signal_id = row["signal_id"],
                    pair      = row["pair"],
                    direction = row["direction"],
                    entry     = float(row["entry_price"]),
                    sl        = float(row["sl_price"]),
                    tp1       = float(row["tp1_price"]),
                    sl_pips   = float(row["sl_pips"] or 20),
                )
            except Exception as e:
                logger.warning(f"Could not resume monitor for {row['signal_id']}: {e}")

    except Exception as e:
        logger.warning(f"resume_monitors_on_startup failed: {e}")
