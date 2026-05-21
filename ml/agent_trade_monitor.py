"""
ml/agent_trade_monitor.py — Real-time SL/TP monitor for taken agent signals.

Mirrors manual_trade_logger.py monitor logic but targets the agent_signals table.
Writes full forensic fields on close:
  exit_timestamp, exit_reason, exit_price,
  trade_duration_minutes, max_favorable_excursion, max_adverse_excursion.

BID/ASK correctness (same as manual trade monitor):
  LONG:  SL and TP both trigger when BID reaches the level.
  SHORT: SL and TP both trigger when ASK reaches the level.

Lifecycle:
  start_agent_monitor()            — called by api_mark_taken / api_take_trade
  stop_agent_monitor()             — called by api_close_agent_trade / manual override
  resume_agent_monitors_on_startup() — called at Flask startup, re-arms open signals
  get_active_agent_monitors()      — returns list of currently monitored signal_ids
"""

import threading
import time
import logging
from datetime import datetime, timezone

logger = logging.getLogger(__name__)

# Active monitors: signal_id → thread
_active_agent_monitors: dict = {}
_monitor_lock = threading.Lock()


# ── Public API ────────────────────────────────────────────────────────────────

def start_agent_monitor(signal_id: str, pair: str, direction: str,
                        entry: float, sl: float, tp1: float):
    """
    Start a background SL/TP monitor for a taken agent signal.
    No-op if a monitor is already running for this signal_id (idempotent).

    Thread is created and inserted into _active_agent_monitors inside a single
    lock acquisition (atomic check-and-insert) to prevent TOCTOU races where
    two concurrent callers both pass the presence check before either inserts.
    """
    with _monitor_lock:
        if signal_id in _active_agent_monitors:
            logger.debug(f"Agent monitor already active for {signal_id} — skipping duplicate start")
            return
        t = threading.Thread(
            target=_monitor_agent_trade,
            args=(signal_id, pair, direction, entry, sl, tp1),
            daemon=True,
            name=f"AgentMonitor-{signal_id}",
        )
        _active_agent_monitors[signal_id] = t
    # start() called outside lock — holding the lock while starting a thread
    # could deadlock if the new thread immediately tried to acquire _monitor_lock.
    t.start()
    logger.info(
        f"Agent monitor started: {signal_id} | {pair} {direction} "
        f"entry={entry} SL={sl} TP1={tp1}"
    )


def stop_agent_monitor(signal_id: str):
    """
    Remove signal_id from active monitors.
    The thread will exit naturally on next loop iteration (it checks the dict).
    """
    removed = False
    with _monitor_lock:
        if signal_id in _active_agent_monitors:
            _active_agent_monitors.pop(signal_id, None)
            removed = True
    if removed:
        logger.info(f"Agent monitor stopped: {signal_id}")


def get_active_agent_monitors() -> list:
    """Return list of signal_ids currently being monitored."""
    with _monitor_lock:
        return list(_active_agent_monitors.keys())


def resume_agent_monitors_on_startup():
    """
    On app restart, re-arm monitors for all taken+open agent signals.
    Reads from SQLite (Railway-safe — no CSV dependency).
    Only re-arms signals with resolvable SL/TP levels.
    """
    try:
        from db.database import get_open_taken_agent_signals
        rows = get_open_taken_agent_signals()
        if not rows:
            logger.info("Agent monitor resume: no open taken signals found")
            return
        logger.info(f"Resuming agent monitors for {len(rows)} open taken signal(s)")
        for row in rows:
            try:
                sl_val  = float(row.get("resolved_sl")  or 0)
                tp1_val = float(row.get("resolved_tp1") or 0)
                entry   = float(row.get("entry_price")  or 0)
                if sl_val <= 0 or tp1_val <= 0 or entry <= 0:
                    logger.warning(f"Skipping resume for {row['signal_id']} — missing SL/TP/entry")
                    continue
                start_agent_monitor(
                    signal_id = row["signal_id"],
                    pair      = row["pair"],
                    direction = row["direction"],
                    entry     = entry,
                    sl        = sl_val,
                    tp1       = tp1_val,
                )
            except Exception as e:
                logger.warning(f"Could not resume agent monitor for {row.get('signal_id')}: {e}")
    except Exception as e:
        logger.warning(f"resume_agent_monitors_on_startup failed: {e}")


# ── Internal helpers ──────────────────────────────────────────────────────────

def _get_agent_levels_from_db(signal_id: str) -> dict:
    """
    Read current resolved SL/TP from agent_signals.
    Picks up any user edits made mid-trade.
    Priority: actual_sl → user_sl → sl_price (same for TP).
    """
    try:
        from db.database import get_agent_signal
        row = get_agent_signal(signal_id)
        if row:
            sl  = float(row.get("actual_sl")  or row.get("user_sl")  or row.get("sl_price")  or 0)
            tp1 = float(row.get("actual_tp1") or row.get("user_tp1") or row.get("tp1_price") or 0)
            if sl > 0 and tp1 > 0:
                return {"sl": sl, "tp1": tp1}
    except Exception as e:
        logger.warning(f"_get_agent_levels_from_db failed for {signal_id}: {e}")
    return {}


def _get_agent_log_time(signal_id: str) -> str | None:
    """Read entry timestamp for an agent signal from DB."""
    try:
        from db.database import get_agent_signal
        row = get_agent_signal(signal_id)
        if row and row.get("timestamp_utc"):
            return str(row["timestamp_utc"])
    except Exception as e:
        logger.warning(f"_get_agent_log_time failed for {signal_id}: {e}")
    return None


def _close_agent_trade(signal_id: str, pair: str, direction: str,
                       entry: float, sl: float, tp1: float, pip: float,
                       result: str, exit_price=None,
                       mfe_pips: float = 0.0, mae_pips: float = 0.0):
    """
    Write outcome + forensic fields to agent_signals.
    Called by monitor on TP/SL hit.
    """
    pips = round(abs(tp1 - entry) / pip, 1) if result == "WIN" else round(abs(sl - entry) / pip, 1)
    if result == "LOSS":
        pips = -pips

    now_utc         = datetime.now(timezone.utc)
    exit_ts         = now_utc.strftime("%Y-%m-%d %H:%M:%S")
    exit_reason_str = "TP_HIT" if result == "WIN" else "SL_HIT"

    duration_minutes = None
    log_time_str = _get_agent_log_time(signal_id)
    if log_time_str:
        try:
            entry_dt = datetime.strptime(log_time_str, "%Y-%m-%d %H:%M:%S").replace(tzinfo=timezone.utc)
            duration_minutes = max(0, int((now_utc - entry_dt).total_seconds() / 60))
        except Exception:
            pass

    note = (
        f"[monitor] {exit_reason_str} {result} {pips:+.1f}p "
        f"@ {round(exit_price, 5) if exit_price is not None else 'candle'}"
    )

    try:
        from db.database import update_agent_signal_forensic
        update_agent_signal_forensic(
            signal_id        = signal_id,
            outcome          = result,
            outcome_pips     = pips,
            notes            = note,
            exit_timestamp   = exit_ts,
            exit_reason      = exit_reason_str,
            exit_price       = round(exit_price, 5) if exit_price is not None else None,
            trade_duration_minutes  = duration_minutes,
            max_favorable_excursion = round(mfe_pips, 1) if mfe_pips else None,
            max_adverse_excursion   = round(mae_pips, 1) if mae_pips else None,
        )
        logger.info(
            f"Agent trade closed: {signal_id} → {result} ({pips:+.1f} pips) "
            f"| {exit_reason_str} exit_price={exit_price} "
            f"MFE={mfe_pips:.1f}p MAE={mae_pips:.1f}p duration={duration_minutes}min"
        )
    except Exception as e:
        logger.warning(f"Agent forensic write failed for {signal_id}: {e}")


# ── Monitor thread ────────────────────────────────────────────────────────────

def _monitor_agent_trade(signal_id: str, pair: str, direction: str,
                         entry: float, sl: float, tp1: float):
    """
    Real-time SL/TP monitor for a taken agent signal.

    Polls OANDA live bid/ask every 15s.
    Falls back to M5 candle check if live price unavailable.
    Reads SL/TP from DB on every cycle — picks up user edits via api_update_agent_levels.

    BID/ASK correctness:
      LONG:  uses BID for SL and TP evaluation (closing a long = selling at bid).
      SHORT: uses ASK for SL and TP evaluation (closing a short = buying at ask).
    """
    try:
        from core.fetcher import get_live_bid_ask, fetch_candles, pip_size
        import pandas as pd
    except Exception as e:
        logger.warning(f"Agent monitor import failed for {signal_id}: {e}")
        with _monitor_lock:
            _active_agent_monitors.pop(signal_id, None)
        return

    pip = pip_size(pair)

    # 30s startup grace — gives user time to edit SL/TP before first check
    time.sleep(30)

    def _current_levels():
        db = _get_agent_levels_from_db(signal_id)
        return db.get("sl", sl), db.get("tp1", tp1)

    cur_sl, cur_tp1 = _current_levels()
    logger.info(
        f"Agent monitoring active: {signal_id} | {pair} {direction} "
        f"| SL={cur_sl} TP1={cur_tp1}"
    )

    # Running MFE/MAE accumulators
    mfe_pips = 0.0
    mae_pips = 0.0

    def _update_excursion(trigger_px: float):
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

    # ── Catch-up: scan M5 candles since entry ─────────────────────────────────
    try:
        log_time = _get_agent_log_time(signal_id)
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
                        if direction == "bullish":
                            tp_t = df_hist[df_hist["high"] >= cur_tp1].index[0]
                            sl_t = df_hist[df_hist["low"]  <= cur_sl].index[0]
                        else:
                            tp_t = df_hist[df_hist["low"]  <= cur_tp1].index[0]
                            sl_t = df_hist[df_hist["high"] >= cur_sl].index[0]
                        result = "WIN" if tp_t <= sl_t else "LOSS"
                    elif tp_hit:
                        result = "WIN"
                    else:
                        result = "LOSS"
                    logger.info(f"Agent catch-up: {signal_id} → {result} | SL={cur_sl} TP={cur_tp1}")
                    _close_agent_trade(signal_id, pair, direction, entry, cur_sl, cur_tp1, pip,
                                       result, exit_price=None,
                                       mfe_pips=mfe_pips, mae_pips=mae_pips)
                    with _monitor_lock:
                        _active_agent_monitors.pop(signal_id, None)
                    return
    except Exception as e:
        logger.warning(f"Agent catch-up check failed for {signal_id}: {e}")

    # ── Live polling loop ──────────────────────────────────────────────────────
    while True:
        # Check if we were externally stopped (manual override / close ✕)
        with _monitor_lock:
            if signal_id not in _active_agent_monitors:
                logger.info(f"Agent monitor {signal_id} was stopped externally — exiting")
                return

        time.sleep(15)

        try:
            cur_sl, cur_tp1 = _current_levels()

            # ── Primary: live bid/ask check ────────────────────────────────────
            bid, ask = get_live_bid_ask(pair)
            trigger_px = bid if direction == "bullish" else ask

            if trigger_px is not None:
                _update_excursion(trigger_px)

                if direction == "bullish":
                    tp_hit = trigger_px >= cur_tp1
                    sl_hit = trigger_px <= cur_sl
                else:
                    tp_hit = trigger_px <= cur_tp1
                    sl_hit = trigger_px >= cur_sl

                if tp_hit and not sl_hit:
                    logger.info(
                        f"Agent TP hit {signal_id}: {direction} trigger={trigger_px} TP={cur_tp1}"
                    )
                    _close_agent_trade(signal_id, pair, direction, entry, cur_sl, cur_tp1, pip,
                                       "WIN", exit_price=trigger_px,
                                       mfe_pips=mfe_pips, mae_pips=mae_pips)
                    break
                elif sl_hit and not tp_hit:
                    logger.info(
                        f"Agent SL hit {signal_id}: {direction} trigger={trigger_px} SL={cur_sl}"
                    )
                    _close_agent_trade(signal_id, pair, direction, entry, cur_sl, cur_tp1, pip,
                                       "LOSS", exit_price=trigger_px,
                                       mfe_pips=mfe_pips, mae_pips=mae_pips)
                    break
                elif tp_hit and sl_hit:
                    # Both triggered simultaneously — use direction to decide
                    result = "WIN" if direction == "bullish" else "LOSS"
                    logger.info(
                        f"Agent both hit {signal_id}: trigger={trigger_px} → {result}"
                    )
                    _close_agent_trade(signal_id, pair, direction, entry, cur_sl, cur_tp1, pip,
                                       result, exit_price=trigger_px,
                                       mfe_pips=mfe_pips, mae_pips=mae_pips)
                    break
                continue  # still open — next poll cycle

            # ── Fallback: M5 candle check (when live price unavailable) ────────
            log_time = _get_agent_log_time(signal_id)
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
                _close_agent_trade(signal_id, pair, direction, entry, cur_sl, cur_tp1, pip,
                                   "WIN", exit_price=None,
                                   mfe_pips=mfe_pips, mae_pips=mae_pips)
                break
            elif sl_hit and not tp_hit:
                _close_agent_trade(signal_id, pair, direction, entry, cur_sl, cur_tp1, pip,
                                   "LOSS", exit_price=None,
                                   mfe_pips=mfe_pips, mae_pips=mae_pips)
                break
            elif tp_hit and sl_hit:
                if direction == "bullish":
                    tp_t = df[df["high"] >= cur_tp1].index[0]
                    sl_t = df[df["low"]  <= cur_sl].index[0]
                else:
                    tp_t = df[df["low"]  <= cur_tp1].index[0]
                    sl_t = df[df["high"] >= cur_sl].index[0]
                result = "WIN" if tp_t <= sl_t else "LOSS"
                _close_agent_trade(signal_id, pair, direction, entry, cur_sl, cur_tp1, pip,
                                   result, exit_price=None,
                                   mfe_pips=mfe_pips, mae_pips=mae_pips)
                break

        except Exception as e:
            logger.warning(f"Agent monitor error for {signal_id}: {e}")
            time.sleep(15)

    with _monitor_lock:
        _active_agent_monitors.pop(signal_id, None)
