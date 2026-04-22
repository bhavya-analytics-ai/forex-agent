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
from datetime import datetime

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
                     setup_type: str = "manual", notes: str = "") -> str:
    """
    Log a manual trade. Calculates SL/TP, writes to SQLite + CSV backup,
    starts background monitor for TP/SL hit.
    Returns signal_id.
    """
    _ensure_log_file()

    now       = datetime.utcnow()
    signal_id = _make_signal_id(pair, now)
    levels    = _calculate_levels(pair, direction, entry_price)

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
    }

    # Primary: SQLite
    try:
        from db.database import insert_manual_trade
        insert_manual_trade(row)
    except Exception as e:
        logger.warning(f"SQLite write failed for {signal_id}: {e}")

    # Backup: CSV
    path = _get_log_path()
    with open(path, "a", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=_MANUAL_COLUMNS)
        writer.writerow(row)

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
    Polls M5 candles every 5 minutes until TP1 or SL is hit.
    No timeout — runs until one side is hit.
    """
    from core.fetcher import fetch_candles, pip_size
    pip = pip_size(pair)

    logger.info(f"Monitoring {signal_id} | {pair} {direction} | SL={sl} TP1={tp1}")

    while True:
        time.sleep(300)  # check every 5 minutes
        try:
            sig_time = datetime.utcnow()
            df = fetch_candles(pair, "M5")
            if df is None or df.empty:
                continue

            # Only look at candles after trade was logged
            import pandas as pd
            log_time = _get_log_time(signal_id)
            if log_time:
                df = df[df.index >= pd.Timestamp(log_time, tz="UTC")]

            if df.empty:
                continue

            if direction == "bullish":
                tp_hit = (df["high"] >= tp1).any()
                sl_hit = (df["low"]  <= sl).any()
            else:
                tp_hit = (df["low"]  <= tp1).any()
                sl_hit = (df["high"] >= sl).any()

            if tp_hit and not sl_hit:
                _close_trade(signal_id, pair, direction, entry, sl, tp1, pip, "WIN")
                break
            elif sl_hit and not tp_hit:
                _close_trade(signal_id, pair, direction, entry, sl, tp1, pip, "LOSS")
                break
            elif tp_hit and sl_hit:
                # Both hit — check which came first
                if direction == "bullish":
                    tp_time = df[df["high"] >= tp1].index[0]
                    sl_time = df[df["low"]  <= sl ].index[0]
                else:
                    tp_time = df[df["low"]  <= tp1].index[0]
                    sl_time = df[df["high"] >= sl ].index[0]
                result = "WIN" if tp_time <= sl_time else "LOSS"
                _close_trade(signal_id, pair, direction, entry, sl, tp1, pip, result)
                break

        except Exception as e:
            logger.warning(f"Monitor error for {signal_id}: {e}")
            time.sleep(60)

    with _monitor_lock:
        _active_monitors.pop(signal_id, None)


def _get_log_time(signal_id: str) -> str:
    """Read the logged timestamp for a signal from the CSV."""
    try:
        import pandas as pd
        df = pd.read_csv(_get_log_path())
        row = df[df["signal_id"] == signal_id]
        if not row.empty:
            return row.iloc[0]["timestamp_utc"]
    except Exception:
        pass
    return None


def _close_trade(signal_id, pair, direction, entry, sl, tp1, pip, result):
    """Write outcome + post-mortem note to CSV."""
    import pandas as pd

    path = _get_log_path()
    try:
        df   = pd.read_csv(path)
        mask = df["signal_id"] == signal_id
        if not mask.any():
            return

        pips = round(abs(tp1 - entry) / pip, 1) if result == "WIN" else round(abs(sl - entry) / pip, 1)
        if result == "LOSS":
            pips = -pips

        note = _build_post_mortem(direction, result, entry, sl, tp1, pips)

        df.loc[mask, "outcome"]      = result
        df.loc[mask, "outcome_pips"] = pips
        df.loc[mask, "post_mortem"]  = note
        df.to_csv(path, index=False)

        # SQLite
        try:
            from db.database import update_manual_trade_outcome
            update_manual_trade_outcome(signal_id, result, pips, note)
        except Exception as e:
            logger.warning(f"SQLite outcome update failed for {signal_id}: {e}")

        logger.info(f"Manual trade closed: {signal_id} → {result} ({pips:+.1f} pips)")
        logger.info(f"Post-mortem: {note}")

    except Exception as e:
        logger.warning(f"Could not close manual trade {signal_id}: {e}")


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
    Stops the monitor thread and writes outcome to CSV.
    Returns (ok: bool, error: str)
    """
    import pandas as pd

    path = _get_log_path()
    if not __import__("os").path.exists(path):
        return False, "manual_trades.csv not found"

    try:
        df   = pd.read_csv(path, dtype=str)
        mask = df["signal_id"] == signal_id
        if not mask.any():
            return False, f"Signal {signal_id} not found in CSV"

        row       = df[mask].iloc[0]
        direction = str(row.get("direction", "bullish"))
        final_pips = pips if outcome == "WIN" else -abs(pips)

        # Build post-mortem safely — don't crash if SL/TP are missing
        try:
            entry = float(row["entry_price"]) if row["entry_price"] != "" else 0
            sl    = float(row["sl_price"])    if str(row.get("sl_price", "")) not in ("", "nan") else 0
            tp1   = float(row["tp1_price"])   if str(row.get("tp1_price", "")) not in ("", "nan") else 0
            note  = _build_post_mortem(direction, outcome, entry, sl, tp1, final_pips)
        except Exception:
            note  = f"{outcome} {final_pips:+.1f} pips | manual close"

        if notes:
            note += f" | Note: {notes}"

        df.loc[mask, "outcome"]      = str(outcome)
        df.loc[mask, "outcome_pips"] = str(final_pips)
        df.loc[mask, "post_mortem"]  = str(note)
        df.to_csv(path, index=False)

        # SQLite
        try:
            from db.database import update_manual_trade_outcome
            update_manual_trade_outcome(signal_id, outcome, final_pips, note)
        except Exception as e:
            logger.warning(f"SQLite manual close failed for {signal_id}: {e}")

        # Stop the monitor thread
        with _monitor_lock:
            _active_monitors.pop(signal_id, None)

        logger.info(f"Manual close: {signal_id} → {outcome} ({final_pips:+.1f} pips)")
        return True, ""

    except Exception as e:
        logger.warning(f"close_trade_manually error: {e}", exc_info=True)
        return False, str(e) or "Unknown error in close_trade_manually"


def update_trade_levels(signal_id: str, sl_price: float, tp1_price: float, reason: str = "") -> tuple:
    """
    Update SL and TP1 for an open manual trade.
    Rewrites the CSV row, recalculates pips/RR, restarts the monitor with new levels.
    Returns (ok: bool, error: str)
    """
    import pandas as pd
    from core.fetcher import pip_size

    path = _get_log_path()
    if not __import__("os").path.exists(path):
        return False, "manual_trades.csv not found"

    try:
        df   = pd.read_csv(path, dtype=str)
        mask = df["signal_id"] == signal_id
        if not mask.any():
            return False, f"Signal {signal_id} not found"

        row       = df[mask].iloc[0]
        pair      = str(row["pair"])
        direction = str(row["direction"])
        entry     = float(row["entry_price"]) if row["entry_price"] not in ("", "nan") else 0

        pip  = pip_size(pair)
        sl_pips  = round(abs(sl_price  - entry) / pip, 1)
        tp1_pips = round(abs(tp1_price - entry) / pip, 1)
        rr1      = f"1:{round(tp1_pips / sl_pips, 1)}" if sl_pips > 0 else "1:2"

        # Grab old levels before overwriting (for level_edits log)
        old_sl  = float(row["sl_price"])  if str(row.get("sl_price",  "")) not in ("", "nan") else 0
        old_tp1 = float(row["tp1_price"]) if str(row.get("tp1_price", "")) not in ("", "nan") else 0

        df.loc[mask, "sl_price"]  = str(sl_price)
        df.loc[mask, "tp1_price"] = str(tp1_price)
        df.loc[mask, "sl_pips"]   = str(sl_pips)
        df.loc[mask, "tp1_pips"]  = str(tp1_pips)
        df.loc[mask, "rr1"]       = rr1
        df.to_csv(path, index=False)

        # SQLite: update levels + log the edit
        try:
            from db.database import update_manual_trade_levels, insert_level_edit
            update_manual_trade_levels(signal_id, sl_price, tp1_price, sl_pips, tp1_pips, rr1)
            insert_level_edit(signal_id, old_sl, sl_price, old_tp1, tp1_price, reason)
        except Exception as e:
            logger.warning(f"SQLite level update failed for {signal_id}: {e}")

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
    On app restart, resume monitoring any open trades from the CSV
    (trades with no outcome yet).
    """
    path = _get_log_path()
    if not os.path.exists(path):
        return

    try:
        import pandas as pd
        df = pd.read_csv(path)
        open_trades = df[df["outcome"].isna() | (df["outcome"] == "")]

        if open_trades.empty:
            return

        logger.info(f"Resuming monitors for {len(open_trades)} open manual trades")
        for _, row in open_trades.iterrows():
            try:
                _start_monitor(
                    signal_id = row["signal_id"],
                    pair      = row["pair"],
                    direction = row["direction"],
                    entry     = float(row["entry_price"]),
                    sl        = float(row["sl_price"]),
                    tp1       = float(row["tp1_price"]),
                    sl_pips   = float(row.get("sl_pips", 20)),
                )
            except Exception as e:
                logger.warning(f"Could not resume monitor for {row.get('signal_id','?')}: {e}")

    except Exception as e:
        logger.warning(f"resume_monitors_on_startup failed: {e}")
