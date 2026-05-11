"""
ml/outcome_labeler.py — Auto outcome labeler

Runs automatically in background every 5 minutes.
Checks agent signals without outcome — looks at ALL M5 candles since signal
time until TP1 or SL is hit. No fixed time window — trades run as long as needed.

Reads + writes SQLite (Railway-safe). CSV never touched.

WIN:     TP1 hit
LOSS:    SL hit
(neither → stays unlabeled, checked again next cycle)

Usage:
  python -m ml.outcome_labeler          # label pending
  python -m ml.outcome_labeler backfill # label all historical
"""

import os
import sys
import logging

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core.fetcher import fetch_candles, pip_size

logger = logging.getLogger(__name__)

LABEL_DELAY_MINUTES = 15   # wait before first check (signal needs time to develop)
LABEL_MAX_HOURS     = 72   # skip signals older than this — M5 history doesn't go back far enough


def label_pending_signals() -> int:
    """
    Find agent signals without outcome that are 15+ min old.
    Checks all M5 candles since signal time — labels WIN/LOSS if hit.
    Returns count of newly labeled signals.
    """
    from datetime import datetime, timezone, timedelta
    from db.database import get_recent_agent_signals, update_agent_signal_outcome

    rows = get_recent_agent_signals(limit=500)
    if not rows:
        logger.debug("No signals in DB")
        return 0

    now    = datetime.now(timezone.utc)
    cutoff = now - timedelta(minutes=LABEL_DELAY_MINUTES)
    oldest = now - timedelta(hours=LABEL_MAX_HOURS)
    pending = [
        r for r in rows
        if not r.get("outcome")
        and r.get("timestamp_utc")
        and oldest <= _parse_utc(r["timestamp_utc"]) <= cutoff
    ]

    if not pending:
        logger.debug("No pending signals to label")
        return 0

    logger.info(f"Checking {len(pending)} pending signals...")
    labeled = 0

    for row in pending:
        outcome, pips = _check_outcome(row)
        if outcome is None:
            continue

        note = _build_post_mortem(row, outcome, pips)
        try:
            update_agent_signal_outcome(row["signal_id"], outcome, pips, note)
            labeled += 1
            logger.info(f"  {row['signal_id']} → {outcome} ({pips:+.1f} pips)")
        except Exception as e:
            logger.warning(f"Failed to write outcome for {row['signal_id']}: {e}")

    if labeled:
        logger.info(f"Labeled {labeled} signals.")
    return labeled


def _check_outcome(row: dict) -> tuple:
    """
    Fetch all M5 candles since signal time.
    Return (outcome, pips) or (None, 0) if neither hit yet.
    """
    pair      = str(row.get("pair", ""))
    direction = str(row.get("direction", "")).lower()
    sig_time  = _parse_utc(row.get("timestamp_utc"))

    if not pair or not direction or not sig_time:
        return None, 0

    entry_px = _safe_float(row.get("entry_price"))
    sl_px    = _safe_float(row.get("actual_sl") or row.get("sl_price"))
    tp1_px   = _safe_float(row.get("actual_tp1") or row.get("tp1_price"))

    if not entry_px:
        return None, 0

    pip = pip_size(pair)

    if not sl_px or not tp1_px:
        sl_px, tp1_px = _fallback_levels(pair, direction, entry_px, pip)

    try:
        df = fetch_candles(pair, "M5")
        if df is None or df.empty:
            return None, 0

        # All candles AFTER signal fired
        after = df[df.index > sig_time]
        if after.empty:
            return None, 0

        if direction == "bullish":
            tp_hit = (after["high"] >= tp1_px).any()
            sl_hit = (after["low"]  <= sl_px).any()
        else:
            tp_hit = (after["low"]  <= tp1_px).any()
            sl_hit = (after["high"] >= sl_px).any()

        if tp_hit and not sl_hit:
            return "WIN", round(abs(tp1_px - entry_px) / pip, 1)

        elif sl_hit and not tp_hit:
            return "LOSS", -round(abs(sl_px - entry_px) / pip, 1)

        elif tp_hit and sl_hit:
            # Both hit — whichever came first
            if direction == "bullish":
                tp_time = after[after["high"] >= tp1_px].index[0]
                sl_time = after[after["low"]  <= sl_px].index[0]
            else:
                tp_time = after[after["low"]  <= tp1_px].index[0]
                sl_time = after[after["high"] >= sl_px].index[0]

            if tp_time <= sl_time:
                return "WIN", round(abs(tp1_px - entry_px) / pip, 1)
            else:
                return "LOSS", -round(abs(sl_px - entry_px) / pip, 1)

        # Neither hit yet — keep watching
        return None, 0

    except Exception as e:
        logger.warning(f"Could not check outcome for {row.get('signal_id','?')}: {e}")
        return None, 0


def _build_post_mortem(row: dict, outcome: str, pips: float) -> str:
    pair      = row.get("pair", "")
    direction = row.get("direction", "")
    setup     = row.get("setup_type", "")

    conditions_present, conditions_missing = [], []
    for col, label in {
        "score_zone":    "zone quality",
        "score_tf":      "TF alignment",
        "score_pattern": "entry pattern",
        "score_session": "session timing",
        "score_news":    "news clear",
        "score_fvg":     "FVG",
        "score_ict":     "ICT confluence",
    }.items():
        try:
            val = float(row.get(col) or 0)
        except (TypeError, ValueError):
            val = 0
        (conditions_present if val > 0 else conditions_missing).append(label)

    present = ", ".join(conditions_present) or "none"
    missing = ", ".join(conditions_missing) or "none"

    if outcome == "WIN":
        return f"WIN +{abs(pips):.1f}p | {pair} {direction} | {setup} | worked: {present}"
    elif outcome == "LOSS":
        return (f"LOSS {pips:.1f}p | {pair} {direction} | {setup} | "
                f"worked: {present} | missing: {missing}")
    return f"NEUTRAL | {pair} {direction} | {setup}"


def _fallback_levels(pair: str, direction: str, entry: float, pip: float) -> tuple:
    sl_pips = {"XAU_USD": 200, "XAG_USD": 150}.get(pair, 20)
    dist = sl_pips * pip
    if direction == "bullish":
        return entry - dist, entry + dist * 2
    return entry + dist, entry - dist * 2


def _parse_utc(ts_str):
    if not ts_str:
        return None
    try:
        from datetime import timezone
        import pandas as pd
        ts = pd.to_datetime(ts_str, utc=True)
        return ts.to_pydatetime().replace(tzinfo=timezone.utc)
    except Exception:
        return None


def _safe_float(val) -> float:
    try:
        v = float(val)
        return v if v > 0 else 0.0
    except (TypeError, ValueError):
        return 0.0


def backfill_outcomes():
    """Label all historical agent signals that don't have an outcome yet."""
    from db.database import get_recent_agent_signals, update_agent_signal_outcome, init_db
    init_db()

    rows = get_recent_agent_signals(limit=100_000)
    unlabeled = [r for r in rows if not r.get("outcome")]
    logger.info(f"Backfilling {len(unlabeled)} signals...")

    labeled = 0
    for row in unlabeled:
        outcome, pips = _check_outcome(row)
        if outcome is None:
            continue
        note = _build_post_mortem(row, outcome, pips)
        update_agent_signal_outcome(row["signal_id"], outcome, pips, note)
        labeled += 1
        print(f"  {row['signal_id']} → {outcome} ({pips:+.1f}p)")

    print(f"\nBackfill complete — labeled {labeled} signals.")


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    import sys
    from db.database import init_db
    init_db()
    if len(sys.argv) > 1 and sys.argv[1] == "backfill":
        backfill_outcomes()
    else:
        count = label_pending_signals()
        print(f"Labeled {count} signals.")
