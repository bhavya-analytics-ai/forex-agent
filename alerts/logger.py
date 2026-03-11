"""
logger.py — Log every signal to CSV for future ML training and performance tracking.
Every signal gets logged. Outcome (TP/SL) updated separately.
"""

import os
import csv
import logging
from datetime import datetime
from config import LOG_CONFIG

logger = logging.getLogger(__name__)

LOG_PATH = LOG_CONFIG["signal_log_path"]
COLUMNS  = [
    "signal_id",
    "timestamp_utc",
    "pair",
    "direction",
    "setup_type",
    "entry_price",
    "score",
    "score_zone",
    "score_tf",
    "score_candle",
    "score_session",
    "score_news",
    "h1_zone_type",
    "h1_zone_high",
    "h1_zone_low",
    "h1_zone_strength",
    "h1_trend",
    "m15_trend",
    "m5_trend",
    "entry_pattern",
    "session",
    "news_safe",
    "alerted",
    "outcome",       # WIN / LOSS / BREAKEVEN — filled later
    "outcome_pips",  # filled later
    "notes",
]


def _ensure_log_file():
    """Create log file with headers if it doesn't exist."""
    os.makedirs(os.path.dirname(LOG_PATH), exist_ok=True)
    if not os.path.exists(LOG_PATH):
        with open(LOG_PATH, "w", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=COLUMNS)
            writer.writeheader()
        logger.info(f"Created signal log at {LOG_PATH}")


def log_signal(scored_signal: dict, confluence: dict, alerted: bool) -> str:
    """
    Log a scored signal to CSV.
    Returns the signal_id for future outcome updates.
    """
    _ensure_log_file()

    now       = datetime.utcnow()
    signal_id = f"{scored_signal['pair']}_{now.strftime('%Y%m%d_%H%M%S')}"

    h1         = confluence.get("h1", {})
    top_zone   = scored_signal.get("top_zone") or {}
    breakdown  = scored_signal.get("breakdown", {})
    pattern    = scored_signal.get("entry_pattern") or {}
    session    = scored_signal.get("session_ctx", {}).get("session", "unknown")

    row = {
        "signal_id":       signal_id,
        "timestamp_utc":   now.strftime("%Y-%m-%d %H:%M:%S"),
        "pair":            scored_signal["pair"],
        "direction":       scored_signal["direction"],
        "setup_type":      scored_signal["setup_type"],
        "entry_price":     scored_signal["current_price"],
        "score":           scored_signal["score"],
        "score_zone":      breakdown.get("zone_strength", 0),
        "score_tf":        breakdown.get("tf_confluence", 0),
        "score_candle":    breakdown.get("candle_pattern", 0),
        "score_session":   breakdown.get("session_context", 0),
        "score_news":      breakdown.get("news_clearance", 0),
        "h1_zone_type":    top_zone.get("type", ""),
        "h1_zone_high":    top_zone.get("high", ""),
        "h1_zone_low":     top_zone.get("low", ""),
        "h1_zone_strength": top_zone.get("strength", 0),
        "h1_trend":        h1.get("structure", {}).get("trend", ""),
        "m15_trend":       confluence.get("m15", {}).get("structure", {}).get("trend", ""),
        "m5_trend":        confluence.get("m5", {}).get("structure", {}).get("trend", ""),
        "entry_pattern":   pattern.get("pattern", ""),
        "session":         session,
        "news_safe":       scored_signal.get("news_check", {}).get("safe", True),
        "alerted":         alerted,
        "outcome":         "",
        "outcome_pips":    "",
        "notes":           "",
    }

    with open(LOG_PATH, "a", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=COLUMNS)
        writer.writerow(row)

    logger.info(f"Logged signal {signal_id} (alerted={alerted})")
    return signal_id


def update_outcome(signal_id: str, outcome: str, pips: float, notes: str = ""):
    """
    Update a logged signal with its outcome (WIN/LOSS/BREAKEVEN).
    Call this manually or via a future outcome tracker.

    outcome: 'WIN' | 'LOSS' | 'BREAKEVEN'
    pips:    positive or negative pip result
    """
    import pandas as pd

    if not os.path.exists(LOG_PATH):
        logger.warning("Signal log not found")
        return

    df = pd.read_csv(LOG_PATH)
    mask = df["signal_id"] == signal_id

    if not mask.any():
        logger.warning(f"Signal {signal_id} not found in log")
        return

    df.loc[mask, "outcome"]      = outcome
    df.loc[mask, "outcome_pips"] = pips
    df.loc[mask, "notes"]        = notes

    df.to_csv(LOG_PATH, index=False)
    logger.info(f"Updated outcome for {signal_id}: {outcome} ({pips} pips)")


def get_performance_summary() -> dict:
    """
    Quick performance stats from the signal log.
    """
    import pandas as pd

    if not os.path.exists(LOG_PATH):
        return {"error": "No signal log found"}

    df = pd.read_csv(LOG_PATH)
    completed = df[df["outcome"].isin(["WIN", "LOSS", "BREAKEVEN"])]

    if completed.empty:
        return {"total_signals": len(df), "completed": 0}

    wins       = (completed["outcome"] == "WIN").sum()
    losses     = (completed["outcome"] == "LOSS").sum()
    total      = len(completed)
    win_rate   = round(wins / total * 100, 1) if total > 0 else 0
    avg_pips   = completed["outcome_pips"].astype(float).mean()

    return {
        "total_signals": len(df),
        "completed":     total,
        "wins":          int(wins),
        "losses":        int(losses),
        "win_rate":      win_rate,
        "avg_pips":      round(float(avg_pips), 1),
        "by_pair":       completed.groupby("pair")["outcome"].value_counts().to_dict(),
        "by_setup":      completed.groupby("setup_type")["outcome"].value_counts().to_dict(),
    }