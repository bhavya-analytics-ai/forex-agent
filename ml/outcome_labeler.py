"""
ml/outcome_labeler.py — Auto outcome labeler

Runs automatically in background every 5 minutes.
15 minutes after a signal fires:
  → checks if TP1 or SL was hit
  → labels WIN / LOSS / NEUTRAL
  → writes back to CSV automatically

WIN:     TP1 hit (price reached 1:2 target)
LOSS:    SL hit
NEUTRAL: neither hit in 15 min window

Metal-aware:
  XAU/XAG use dollar thresholds not pip thresholds

Usage:
  python -m ml.outcome_labeler          # label pending
  python -m ml.outcome_labeler backfill # label all historical
"""

import os
import sys
import logging
import pandas as pd
from datetime import datetime, timedelta

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from config import LOG_CONFIG
from core.fetcher import fetch_candles, pip_size

logger   = logging.getLogger(__name__)
LOG_PATH = LOG_CONFIG["signal_log_path"]

LABEL_DELAY_MINUTES = 15   # Wait this long before labeling


def label_pending_signals() -> int:
    """
    Find signals without outcome that are 15+ min old.
    Label them WIN/LOSS/NEUTRAL based on whether TP1 or SL was hit.
    Returns count of newly labeled signals.
    """
    if not os.path.exists(LOG_PATH):
        logger.warning("No signal log found.")
        return 0

    df = pd.read_csv(LOG_PATH, dtype=str)

    # Ensure columns exist
    for col in ["outcome", "outcome_pips", "tp1_price", "sl_price"]:
        if col not in df.columns:
            df[col] = ""

    df["timestamp_utc"] = pd.to_datetime(df["timestamp_utc"])

    cutoff = datetime.utcnow() - timedelta(minutes=LABEL_DELAY_MINUTES)
    mask   = (df["outcome"].isna() | (df["outcome"] == "")) & (df["timestamp_utc"] <= cutoff)
    pending = df[mask]

    if len(pending) == 0:
        logger.debug("No pending signals to label")
        return 0

    logger.info(f"Labeling {len(pending)} pending signals...")
    labeled = 0

    for idx, row in pending.iterrows():
        outcome, pips = _check_outcome(row)
        if outcome is None:
            continue

        df.loc[idx, "outcome"]      = str(outcome)
        df.loc[idx, "outcome_pips"] = str(pips)
        df.loc[idx, "notes"]        = str(_build_post_mortem(row, outcome, pips))
        labeled += 1
        logger.info(f"  {row.get('signal_id','?')} → {outcome} ({pips:+.1f} pips)")

    if labeled > 0:
        df.to_csv(LOG_PATH, index=False)
        logger.info(f"Labeled {labeled} signals and saved CSV.")

    return labeled


def _check_outcome(row) -> tuple:
    """
    Check if TP1 or SL was hit after the signal fired.
    Uses TP1/SL from CSV if available, else falls back to pip-based logic.
    Returns (outcome_str, pips) or (None, 0).
    """
    pair      = str(row.get("pair", ""))
    direction = str(row.get("direction", "")).lower()
    sig_time  = pd.to_datetime(row.get("timestamp_utc"), utc=True)

    if not pair or not direction or direction == "none":
        return None, 0

    # Get entry, SL, TP1 from CSV
    entry_px = _safe_float(row.get("entry_price"))
    sl_px    = _safe_float(row.get("sl_price"))
    tp1_px   = _safe_float(row.get("tp1_price"))

    if not entry_px:
        return None, 0

    pip = pip_size(pair)

    # Fallback if SL/TP not in CSV (old signals)
    if not sl_px or not tp1_px:
        sl_px, tp1_px = _fallback_levels(pair, direction, entry_px, pip)

    try:
        # Fetch M5 candles after signal — 3 candles = 15 min window
        df_m5 = fetch_candles(pair, "M5")
        if df_m5.empty:
            return None, 0

        after = df_m5[df_m5.index > sig_time].head(3)
        if after.empty:
            return None, 0

        if direction == "bullish":
            tp1_hit = (after["high"] >= tp1_px).any()
            sl_hit  = (after["low"]  <= sl_px).any()
        else:
            tp1_hit = (after["low"]  <= tp1_px).any()
            sl_hit  = (after["high"] >= sl_px).any()

        if tp1_hit and not sl_hit:
            pips = round(abs(tp1_px - entry_px) / pip, 1)
            return "WIN", pips

        elif sl_hit and not tp1_hit:
            pips = round(abs(sl_px - entry_px) / pip, 1)
            return "LOSS", -pips

        elif tp1_hit and sl_hit:
            # Both hit — whichever came first
            if direction == "bullish":
                tp1_time = after[after["high"] >= tp1_px].index[0]
                sl_time  = after[after["low"]  <= sl_px].index[0]
            else:
                tp1_time = after[after["low"]  <= tp1_px].index[0]
                sl_time  = after[after["high"] >= sl_px].index[0]

            if tp1_time <= sl_time:
                pips = round(abs(tp1_px - entry_px) / pip, 1)
                return "WIN", pips
            else:
                pips = round(abs(sl_px - entry_px) / pip, 1)
                return "LOSS", -pips

        else:
            # Neither hit yet — keep monitoring (return None so labeler skips)
            return None, 0

    except Exception as e:
        logger.warning(f"Could not check outcome for {row.get('signal_id','?')}: {e}")
        return None, 0


def _build_post_mortem(row, outcome: str, pips: float) -> str:
    """
    Build a plain-English note explaining what went right or wrong.
    Reads condition columns from the signal row.
    """
    direction  = str(row.get("direction", "")).lower()
    setup_type = str(row.get("setup_type", "")).strip()
    pair       = str(row.get("pair", ""))

    # Read which conditions were true at signal time
    conditions_present = []
    conditions_missing = []

    condition_labels = {
        "score_zone":    "zone quality",
        "score_tf":      "timeframe alignment",
        "score_pattern": "entry pattern",
        "score_session": "session timing",
        "score_news":    "news filter",
        "score_fvg":     "FVG present",
        "score_ict":     "ICT confluence",
    }

    for col, label in condition_labels.items():
        val = row.get(col, 0)
        try:
            val = float(val)
        except (TypeError, ValueError):
            val = 0
        if val > 0:
            conditions_present.append(label)
        else:
            conditions_missing.append(label)

    present_str = ", ".join(conditions_present) if conditions_present else "none"
    missing_str = ", ".join(conditions_missing) if conditions_missing else "none"

    if outcome == "WIN":
        return (
            f"WIN +{abs(pips):.1f}p | {pair} {direction} | setup: {setup_type} | "
            f"What worked: {present_str}"
        )
    elif outcome == "LOSS":
        return (
            f"LOSS {pips:.1f}p | {pair} {direction} | setup: {setup_type} | "
            f"What worked: {present_str} | "
            f"What was missing: {missing_str} | "
            f"Review: check if entry was too early or zone was weak"
        )
    else:
        return f"NEUTRAL | {pair} {direction} | {setup_type} | neither TP nor SL hit"


def _fallback_levels(pair: str, direction: str, entry: float, pip: float) -> tuple:
    """Fallback SL/TP when not stored in CSV (old signals)."""
    sl_pips_default = {
        "XAU_USD": 200, "XAG_USD": 150,
    }.get(pair, 20)

    sl_dist = sl_pips_default * pip

    if direction == "bullish":
        sl  = entry - sl_dist
        tp1 = entry + sl_dist * 2
    else:
        sl  = entry + sl_dist
        tp1 = entry - sl_dist * 2

    return sl, tp1


def _safe_float(val) -> float:
    try:
        v = float(val)
        return v if v > 0 else 0
    except (TypeError, ValueError):
        return 0


def backfill_outcomes():
    """Label all historical signals that don't have an outcome yet."""
    if not os.path.exists(LOG_PATH):
        logger.warning("No signal log found.")
        return

    df = pd.read_csv(LOG_PATH)

    for col in ["outcome", "outcome_pips", "tp1_price", "sl_price"]:
        if col not in df.columns:
            df[col] = ""

    unlabeled = df[df["outcome"].isna() | (df["outcome"] == "")]
    logger.info(f"Backfilling {len(unlabeled)} signals...")

    labeled = 0
    for idx, row in unlabeled.iterrows():
        outcome, pips = _check_outcome(row)
        if outcome is None:
            continue
        df.loc[idx, "outcome"]      = outcome
        df.loc[idx, "outcome_pips"] = pips
        labeled += 1

    df.to_csv(LOG_PATH, index=False)
    logger.info(f"Backfill complete — labeled {labeled} signals.")
    _print_summary(df)


def _print_summary(df: pd.DataFrame):
    completed = df[df["outcome"].isin(["WIN", "LOSS", "NEUTRAL"])]
    if completed.empty:
        print("No completed signals to summarize.")
        return

    wins  = (completed["outcome"] == "WIN").sum()
    total = len(completed)
    rate  = round(wins / total * 100, 1)

    print(f"\n📊 Outcome Summary")
    print(f"   Total labeled: {total}")
    print(f"   Win rate:      {rate}%")

    if "grade" in df.columns:
        print(f"\n   By grade:")
        for grade in ["A+", "A", "B", "C"]:
            g = completed[completed["grade"] == grade]
            if len(g) >= 2:
                gw   = (g["outcome"] == "WIN").sum()
                gr   = round(gw / len(g) * 100, 1)
                print(f"     {grade}: {gw}/{len(g)} = {gr}%")

    print(f"\n   By pair:")
    for pair in completed["pair"].unique():
        p  = completed[completed["pair"] == pair]
        pw = (p["outcome"] == "WIN").sum()
        pr = round(pw / len(p) * 100, 1)
        print(f"     {pair}: {pw}/{len(p)} = {pr}%")


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    cmd = sys.argv[1] if len(sys.argv) > 1 else "label"

    if cmd == "backfill":
        backfill_outcomes()
    else:
        count = label_pending_signals()
        print(f"Labeled {count} signals.")