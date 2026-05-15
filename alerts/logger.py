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

# Legacy in-memory cooldown (fast pre-check, resets on restart)
COOLDOWN_MINUTES = 15
_last_logged     = {}  # pair → datetime

# DB-backed forex dedup — survives deploy restarts
# Fingerprint: (pair, signal_mode, direction, setup_type, h1_trend)
# A new log is allowed only when the fingerprint changes OR window expires.
FOREX_DEDUP_WINDOW_MINUTES = 60


def _get_signal_mode() -> str:
    """Return the active strategy mode — 'normal' or 'news_sniper'. Never raises."""
    try:
        from filters.mode_manager import get_active_mode
        return get_active_mode()
    except Exception:
        return "normal"

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
    "user_sl",
    "user_tp1",
    "actual_sl",
    "actual_tp1",
    "outcome",
    "outcome_pips",
    "notes",
    "signal_mode",
]


def _ensure_log_file():
    os.makedirs(os.path.dirname(LOG_PATH), exist_ok=True)
    if not os.path.exists(LOG_PATH):
        with open(LOG_PATH, "w", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=COLUMNS)
            writer.writeheader()
        logger.info(f"Created signal log at {LOG_PATH}")


def _is_duplicate_forex_signal(
    pair: str,
    signal_mode: str,
    direction: str,
    setup_type: str,
    h1_trend: str,
) -> bool:
    """
    DB-backed fingerprint dedup for forex (non-gold, non-sniper) signals.

    Fingerprint: (pair, signal_mode, direction, setup_type, h1_trend)
    Returns True (block) if a non-archived signal with the same fingerprint
    was logged within FOREX_DEDUP_WINDOW_MINUTES.

    Fails OPEN on any DB error — allows logging if the check cannot run.
    """
    try:
        from db.database import _get_conn
        conn   = _get_conn()
        cutoff = (
            datetime.utcnow() - timedelta(minutes=FOREX_DEDUP_WINDOW_MINUTES)
        ).strftime("%Y-%m-%d %H:%M:%S")
        row = conn.execute(
            """
            SELECT MAX(timestamp_utc) FROM agent_signals
            WHERE pair                          = ?
              AND COALESCE(signal_mode, 'normal') = ?
              AND direction                     = ?
              AND setup_type                    = ?
              AND h1_trend                      = ?
              AND COALESCE(is_archived, 0)      = 0
              AND timestamp_utc                 > ?
            """,
            (pair, signal_mode, direction, setup_type, h1_trend, cutoff),
        ).fetchone()
        is_dup = bool(row and row[0])
        if is_dup:
            logger.debug(
                f"Dedup block {pair} [{signal_mode}] {direction}/{setup_type}/{h1_trend} "
                f"— same fingerprint logged within {FOREX_DEDUP_WINDOW_MINUTES}m"
            )
        return is_dup
    except Exception as e:
        logger.warning(f"Dedup DB check failed for {pair}: {e} — allowing log")
        return False


def is_cooldown_active(pair: str) -> bool:
    """Returns True if this pair was logged too recently."""
    last = _last_logged.get(pair)
    if last is None:
        return False
    return (datetime.utcnow() - last).total_seconds() < COOLDOWN_MINUTES * 60


def log_signal(scored_signal: dict, confluence: dict, alerted: bool) -> str:
    """
    Log a scored signal to CSV + SQLite.

    Dedup strategy:
      Gold / news-sniper  — caller gate (entry_state == ENTER_NOW) is the dedup.
                            Legacy in-memory cooldown also applies as a safety net.
      Forex (all others)  — DB-backed fingerprint dedup via _is_duplicate_forex_signal().
                            Fingerprint: (pair, signal_mode, direction, setup_type, h1_trend).
                            Window: FOREX_DEDUP_WINDOW_MINUTES (60 min). Survives restarts.

    Returns signal_id string, or "" if skipped.
    """
    _ensure_log_file()

    pair        = scored_signal["pair"]
    gold_mode   = scored_signal.get("gold_mode", False)
    signal_mode = scored_signal.get("signal_mode") or _get_signal_mode()
    is_sniper   = signal_mode == "news_sniper"

    if gold_mode or is_sniper:
        # Gold / sniper path — legacy in-memory cooldown as safety net only
        if is_cooldown_active(pair):
            logger.debug(f"Cooldown active for {pair} [{signal_mode}] — skipping log")
            return ""
    else:
        # Forex path — DB-backed fingerprint dedup
        direction  = scored_signal.get("direction", "")
        setup_type = scored_signal.get("setup_type", "")
        h1_trend   = scored_signal.get("h1_trend", "")
        if _is_duplicate_forex_signal(pair, signal_mode, direction, setup_type, h1_trend):
            return ""

    now       = datetime.utcnow()
    signal_id = f"{pair}_{now.strftime('%Y%m%d_%H%M%S')}"

    h1        = confluence.get("h1", {})
    top_zone  = scored_signal.get("top_zone") or {}
    breakdown = scored_signal.get("breakdown", {})
    pattern   = scored_signal.get("entry_pattern") or {}
    session   = scored_signal.get("session_ctx", {}).get("session", "unknown")
    levels    = scored_signal.get("trade_levels", {})

    # kz_ctx is not in scored_signal output — call directly to get real killzone name
    try:
        from filters.killzones import get_killzone_context
        _kz_ctx = get_killzone_context(pair)
        _kz     = _kz_ctx.get("killzone") or {}
        kz_name = _kz.get("name", "") if isinstance(_kz, dict) else ""
    except Exception:
        kz_name = ""

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
        # ── LEGACY BREAKDOWN FIELDS (dead) ────────────────────────────────────
        # scorer.breakdown is now the boolean conditions dict, not a numeric
        # sub-score dict. Keys "zone","tf","pattern","session","news",
        # "quality_bonus","fvg","ict" do not exist in it.
        # Logged as "" (empty) so training data is not polluted with fake zeros.
        # TODO: replace with real boolean conditions once training pipeline is ready.
        "score_zone":         breakdown.get("zone", ""),
        "score_tf":           breakdown.get("tf", ""),
        "score_pattern":      breakdown.get("pattern", ""),
        "score_session":      breakdown.get("session", ""),
        "score_news":         breakdown.get("news", ""),
        "score_quality_bonus": breakdown.get("quality_bonus", ""),
        "score_fvg":          breakdown.get("fvg", ""),
        "score_ict":          breakdown.get("ict", ""),
        # ──────────────────────────────────────────────────────────────────────
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
        "user_sl":            "",
        "user_tp1":           "",
        "actual_sl":          "",
        "actual_tp1":         "",
        "outcome":            "",
        "outcome_pips":       "",
        "notes":              "",
        "signal_mode":        _get_signal_mode(),
    }

    # TODO: SQLite is intended as the primary source of truth, but the write
    # order here is CSV-first. A CSV write failure raises and skips SQLite
    # entirely. A SQLite failure after CSV success is caught and swallowed,
    # leaving the two stores permanently diverged. Flip order (SQLite-first,
    # CSV as backup) once SQLite schema is confirmed stable.
    with open(LOG_PATH, "a", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=COLUMNS)
        writer.writerow(row)

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