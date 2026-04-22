"""
logger.py — Signal logger with trade levels and cooldown tracking

New columns added:
  grade, sl_price, tp1_price, tp2_price, sl_pips, tp1_pips, tp2_pips, taken

Signal cooldown:
  Same pair can only log once every COOLDOWN_MINUTES
  Prevents 10 identical signals for same pair in the CSV
"""

import os
import csv
import logging
from datetime import datetime, timedelta
from config import LOG_CONFIG

logger   = logging.getLogger(__name__)
LOG_PATH = LOG_CONFIG["signal_log_path"]

# Cooldown — don't log same pair more than once per N minutes
COOLDOWN_MINUTES = 15
_last_logged     = {}  # pair → datetime

COLUMNS = [
    "signal_id",
    "timestamp_utc",
    "pair",
    "direction",
    "grade",
    "setup_type",
    "entry_price",
    "sl_price",
    "tp1_price",
    "tp2_price",
    "sl_pips",
    "tp1_pips",
    "tp2_pips",
    "score",
    "score_zone",
    "score_tf",
    "score_pattern",
    "score_session",
    "score_news",
    "score_quality_bonus",
    "score_fvg",
    "score_ict",
    "h1_zone_type",
    "h1_zone_high",
    "h1_zone_low",
    "h1_zone_strength",
    "h1_trend",
    "m15_trend",
    "m5_trend",
    "entry_pattern",
    "session",
    "killzone",
    "news_safe",
    "alerted",
    "taken",
    "outcome",
    "outcome_pips",
    "notes",
]


def _ensure_log_file():
    os.makedirs(os.path.dirname(LOG_PATH), exist_ok=True)
    if not os.path.exists(LOG_PATH):
        with open(LOG_PATH, "w", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=COLUMNS)
            writer.writeheader()
        logger.info(f"Created signal log at {LOG_PATH}")


def is_cooldown_active(pair: str) -> bool:
    """Returns True if this pair was logged too recently."""
    last = _last_logged.get(pair)
    if last is None:
        return False
    return (datetime.utcnow() - last).total_seconds() < COOLDOWN_MINUTES * 60


def log_signal(scored_signal: dict, confluence: dict, alerted: bool) -> str:
    """
    Log a scored signal to CSV.
    Skips if same pair logged within COOLDOWN_MINUTES.
    Returns signal_id or empty string if skipped.
    """
    _ensure_log_file()

    pair = scored_signal["pair"]

    # Cooldown check — skip duplicate signals
    if is_cooldown_active(pair):
        logger.debug(f"Cooldown active for {pair} — skipping log")
        return ""

    now       = datetime.utcnow()
    signal_id = f"{pair}_{now.strftime('%Y%m%d_%H%M%S')}"

    h1        = confluence.get("h1", {})
    top_zone  = scored_signal.get("top_zone") or {}
    breakdown = scored_signal.get("breakdown", {})
    pattern   = scored_signal.get("entry_pattern") or {}
    session   = scored_signal.get("session_ctx", {}).get("session", "unknown")
    kz        = scored_signal.get("kz_ctx", {}).get("killzone") or {}
    kz_name   = kz.get("name", "") if isinstance(kz, dict) else ""
    levels    = scored_signal.get("trade_levels", {})

    row = {
        "signal_id":          signal_id,
        "timestamp_utc":      now.strftime("%Y-%m-%d %H:%M:%S"),
        "pair":               pair,
        "direction":          scored_signal.get("direction", ""),
        "grade":              scored_signal.get("grade", ""),
        "setup_type":         scored_signal.get("setup_type", ""),
        "entry_price":        levels.get("entry_price", scored_signal.get("current_price", "")),
        "sl_price":           levels.get("sl_price", ""),
        "tp1_price":          levels.get("tp1_price", ""),
        "tp2_price":          levels.get("tp2_price", ""),
        "sl_pips":            levels.get("sl_pips", ""),
        "tp1_pips":           levels.get("tp1_pips", ""),
        "tp2_pips":           levels.get("tp2_pips", ""),
        "score":              scored_signal.get("score", 0),
        "score_zone":         breakdown.get("zone", 0),
        "score_tf":           breakdown.get("tf", 0),
        "score_pattern":      breakdown.get("pattern", 0),
        "score_session":      breakdown.get("session", 0),
        "score_news":         breakdown.get("news", 0),
        "score_quality_bonus": breakdown.get("quality_bonus", 0),
        "score_fvg":          breakdown.get("fvg", 0),
        "score_ict":          breakdown.get("ict", 0),
        "h1_zone_type":       top_zone.get("type", ""),
        "h1_zone_high":       top_zone.get("high", ""),
        "h1_zone_low":        top_zone.get("low", ""),
        "h1_zone_strength":   top_zone.get("strength", 0),
        "h1_trend":           h1.get("structure", {}).get("trend", ""),
        "m15_trend":          confluence.get("m15", {}).get("structure", {}).get("trend", ""),
        "m5_trend":           confluence.get("m5", {}).get("structure", {}).get("trend", ""),
        "entry_pattern":      pattern.get("pattern", ""),
        "session":            session,
        "killzone":           kz_name,
        "news_safe":          scored_signal.get("news_check", {}).get("safe", True),
        "alerted":            alerted,
        "taken":              False,
        "outcome":            "",
        "outcome_pips":       "",
        "notes":              "",
    }

    with open(LOG_PATH, "a", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=COLUMNS)
        writer.writerow(row)

    # SQLite (primary store going forward)
    try:
        from db.database import insert_agent_signal
        insert_agent_signal({**row, "outcome_pips": None})
    except Exception as e:
        logger.warning(f"SQLite agent signal write failed: {e}")

    _last_logged[pair] = now
    logger.info(f"Logged signal {signal_id} grade={row['grade']} alerted={alerted}")
    return signal_id


def mark_taken(pair: str) -> bool:
    """Mark the most recent signal for a pair as taken=True."""
    import pandas as pd

    if not os.path.exists(LOG_PATH):
        logger.warning("Signal log not found")
        return False

    df   = pd.read_csv(LOG_PATH)
    mask = df["pair"] == pair

    if not mask.any():
        logger.warning(f"No signals found for {pair}")
        return False

    last_idx             = df[mask].index[-1]
    df.loc[last_idx, "taken"] = True
    df.to_csv(LOG_PATH, index=False)

    signal_id = df.loc[last_idx, "signal_id"]
    logger.info(f"Marked {signal_id} as taken")
    return True


def mark_taken_by_id(signal_id: str) -> bool:
    """Mark a specific signal as taken=True by signal_id."""
    import pandas as pd

    if not os.path.exists(LOG_PATH):
        return False

    df   = pd.read_csv(LOG_PATH)
    mask = df["signal_id"] == signal_id

    if not mask.any():
        logger.warning(f"Signal {signal_id} not found")
        return False

    df.loc[mask, "taken"] = True
    df.to_csv(LOG_PATH, index=False)
    try:
        from db.database import update_agent_signal_taken
        update_agent_signal_taken(signal_id)
    except Exception as e:
        logger.warning(f"SQLite mark_taken_by_id failed: {e}")
    logger.info(f"Marked {signal_id} as taken")
    return True


def update_outcome(signal_id: str, outcome: str, pips: float, notes: str = ""):
    """Update a signal with its outcome. outcome: WIN | LOSS | NEUTRAL"""
    import pandas as pd

    if not os.path.exists(LOG_PATH):
        return

    df   = pd.read_csv(LOG_PATH)
    mask = df["signal_id"] == signal_id

    if not mask.any():
        logger.warning(f"Signal {signal_id} not found")
        return

    df.loc[mask, "outcome"]      = outcome
    df.loc[mask, "outcome_pips"] = pips
    df.loc[mask, "notes"]        = notes
    df.to_csv(LOG_PATH, index=False)
    try:
        from db.database import update_agent_signal_outcome
        update_agent_signal_outcome(signal_id, outcome, pips, notes)
    except Exception as e:
        logger.warning(f"SQLite update_outcome failed: {e}")
    logger.info(f"Updated {signal_id}: {outcome} ({pips} pips)")


def get_performance_summary() -> dict:
    import pandas as pd

    if not os.path.exists(LOG_PATH):
        return {"error": "No signal log found"}

    df        = pd.read_csv(LOG_PATH)
    completed = df[df["outcome"].isin(["WIN", "LOSS", "NEUTRAL"])]

    if completed.empty:
        return {"total_signals": len(df), "completed": 0}

    wins     = (completed["outcome"] == "WIN").sum()
    losses   = (completed["outcome"] == "LOSS").sum()
    total    = len(completed)
    win_rate = round(wins / total * 100, 1) if total > 0 else 0
    avg_pips = completed["outcome_pips"].astype(float).mean()

    # By grade
    by_grade = {}
    for grade in ["A+", "A", "B", "C"]:
        if "grade" in df.columns:
            g = completed[completed["grade"] == grade]
            if len(g) > 0:
                gw = (g["outcome"] == "WIN").sum()
                by_grade[grade] = {
                    "count":    len(g),
                    "wins":     int(gw),
                    "win_rate": round(gw / len(g) * 100, 1),
                }

    return {
        "total_signals": len(df),
        "completed":     total,
        "wins":          int(wins),
        "losses":        int(losses),
        "win_rate":      win_rate,
        "avg_pips":      round(float(avg_pips), 1),
        "taken_count":   int(df["taken"].sum()) if "taken" in df.columns else 0,
        "by_grade":      by_grade,
        "by_pair":       completed.groupby("pair")["outcome"].value_counts().to_dict(),
    }