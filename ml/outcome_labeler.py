"""
ml/outcome_labeler.py — Auto outcome labeler

Runs every 5 minutes via scheduler.
Finds all taken signals with no outcome + valid user_sl/user_tp1.
Fetches full M5 candle history from entry_time → now via OANDA.
Walks candles in order — first level touched is the outcome.

WIN:  TP1 hit first
LOSS: SL hit first
Neither hit yet → stays unlabeled, checked again next cycle

Reads + writes SQLite only. CSV never touched. Railway-safe.

Usage:
  python -m ml.outcome_labeler          # label pending
  python -m ml.outcome_labeler backfill # same thing, alias
"""

import os
import sys
import time
import logging

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

logger = logging.getLogger(__name__)

# Wait at least this long after signal before checking (trade needs time to develop)
LABEL_DELAY_MINUTES = 15


def label_pending_signals() -> int:
    """
    Find all taken signals with no outcome and valid user SL/TP.
    Fetch M5 candles from entry_time → now, determine WIN/LOSS.
    Returns count of newly labeled signals.
    """
    from datetime import datetime, timezone, timedelta
    from db.database import get_unlabeled_taken_signals, update_agent_signal_outcome
    from core.fetcher import fetch_candles_from, pip_size

    signals = get_unlabeled_taken_signals()
    if not signals:
        logger.debug("[labeler] No unlabeled taken signals.")
        return 0

    now    = datetime.now(timezone.utc)
    cutoff = now - timedelta(minutes=LABEL_DELAY_MINUTES)

    # Only process signals old enough to have developed
    pending = [s for s in signals if _parse_utc(s["timestamp_utc"]) <= cutoff]

    if not pending:
        logger.debug("[labeler] All unlabeled signals are too recent (<15 min).")
        return 0

    logger.info(f"[labeler] Checking {len(pending)} unlabeled taken signals...")
    labeled = 0

    for sig in pending:
        sig_id    = sig["signal_id"]
        pair      = sig["pair"]
        direction = (sig["direction"] or "").lower()
        entry_px = _safe_float(sig["entry_price"])
        # Use user levels → actual levels → scanner levels (whichever is set first)
        user_sl  = (_safe_float(sig.get("user_sl"))  or
                    _safe_float(sig.get("actual_sl")) or
                    _safe_float(sig.get("sl_price")))
        user_tp1 = (_safe_float(sig.get("user_tp1"))  or
                    _safe_float(sig.get("actual_tp1")) or
                    _safe_float(sig.get("tp1_price")))
        sig_time = _parse_utc(sig["timestamp_utc"])

        if not all([pair, direction, entry_px, user_sl, user_tp1, sig_time]):
            logger.warning(f"[labeler] {sig_id} — missing fields, skipping")
            continue

        pip = pip_size(pair)

        try:
            df = fetch_candles_from(pair, "M5", sig_time)
        except Exception as e:
            logger.warning(f"[labeler] {sig_id} — candle fetch failed: {e}")
            continue

        if df is None or df.empty:
            logger.debug(f"[labeler] {sig_id} — no candles returned yet")
            continue

        # Only candles AFTER signal fired
        after = df[df.index > sig_time]
        if after.empty:
            logger.debug(f"[labeler] {sig_id} — no candles after signal time")
            continue

        outcome, pips = _determine_outcome(after, direction, entry_px, user_sl, user_tp1, pip)

        if outcome is None:
            logger.debug(f"[labeler] {sig_id} — neither SL nor TP hit yet")
            continue

        note = _build_note(sig, outcome, pips)
        try:
            update_agent_signal_outcome(sig_id, outcome, pips, note)
            labeled += 1
            logger.info(f"[labeler] {pair} {direction} {sig_id[:8]} → {outcome} ({pips:+.1f} pips)")
        except Exception as e:
            logger.warning(f"[labeler] {sig_id} — write failed: {e}")

        # Small sleep between signals to avoid OANDA rate limit
        time.sleep(0.3)

    if labeled:
        logger.info(f"[labeler] Labeled {labeled} signal(s) this run.")
    return labeled


def _determine_outcome(after, direction: str, entry_px: float,
                        sl: float, tp: float, pip: float) -> tuple:
    """
    Walk M5 candles in order. Return (outcome, pips) when SL or TP is hit,
    or (None, 0) if neither hit yet.

    BULL: price goes UP to hit TP (high >= tp), DOWN to hit SL (low <= sl)
    BEAR: price goes DOWN to hit TP (low <= tp), UP to hit SL (high >= sl)
    """
    is_bull = "bull" in direction

    for _, candle in after.iterrows():
        high = candle["high"]
        low  = candle["low"]

        if is_bull:
            tp_hit = high >= tp
            sl_hit = low  <= sl
        else:
            tp_hit = low  <= tp
            sl_hit = high >= sl

        if tp_hit and sl_hit:
            # Both hit same candle — use open price to determine which side
            # If open is closer to TP side, TP was hit first
            if is_bull:
                # Opened closer to TP (high) → TP first, closer to SL (low) → SL first
                tp_dist = abs(candle["open"] - tp)
                sl_dist = abs(candle["open"] - sl)
            else:
                tp_dist = abs(candle["open"] - tp)
                sl_dist = abs(candle["open"] - sl)

            if tp_dist <= sl_dist:
                return "WIN",  round(abs(tp - entry_px) / pip, 1)
            else:
                return "LOSS", -round(abs(sl - entry_px) / pip, 1)

        elif tp_hit:
            return "WIN",  round(abs(tp - entry_px) / pip, 1)

        elif sl_hit:
            return "LOSS", -round(abs(sl - entry_px) / pip, 1)

    return None, 0


def _build_note(sig: dict, outcome: str, pips: float) -> str:
    pair      = sig.get("pair", "")
    direction = sig.get("direction", "")
    setup     = sig.get("setup_type", "")
    tag       = f"+{abs(pips):.1f}p" if outcome == "WIN" else f"{pips:.1f}p"
    return f"[auto-labeled] {outcome} {tag} | {pair} {direction} | {setup}"


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


if __name__ == "__main__":
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(message)s",
    )
    from db.database import init_db
    init_db()
    count = label_pending_signals()
    print(f"\nLabeled {count} signal(s).")
