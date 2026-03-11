"""
scorer.py — Score every signal 0-100 before alerting
Only signals above threshold get sent to Slack.
"""

import logging
from config import SCORING
from filters.news import is_news_safe
from filters.session import get_session_context

logger = logging.getLogger(__name__)

WEIGHTS = SCORING["weights"]


def score_signal(confluence: dict, pair: str) -> dict:
    """
    Score a confluence signal from 0–100.

    Components:
    - Zone strength     (25 pts): quality of the H1 zone being tapped
    - TF confluence     (30 pts): how many timeframes agree
    - Candle pattern    (20 pts): strength of entry confirmation candle
    - Session context   (15 pts): is this the right session for this pair?
    - News clearance    (10 pts): is it safe from high-impact events?

    Returns score dict with breakdown and final score.
    """
    score_breakdown = {}
    total = 0

    # --- 1. Zone Strength (max 25) ---
    active_zones = confluence["h1"]["active_zones"]
    if active_zones:
        top_zone     = max(active_zones, key=lambda z: z["strength"])
        zone_raw     = top_zone["strength"]  # 0-100
        zone_score   = round((zone_raw / 100) * WEIGHTS["zone_strength"])
    else:
        zone_score = 0
        top_zone   = None

    score_breakdown["zone_strength"] = zone_score
    total += zone_score

    # --- 2. TF Confluence (max 30) ---
    confidence   = confluence["confidence"]  # 0, 1, 2, 3
    tf_score     = round((confidence / 3) * WEIGHTS["tf_confluence"])
    score_breakdown["tf_confluence"] = tf_score
    total += tf_score

    # --- 3. Candle Pattern (max 20) ---
    pattern = confluence.get("entry_pattern")
    if pattern:
        pattern_raw  = pattern.get("strength", 50)  # 0-100
        candle_score = round((pattern_raw / 100) * WEIGHTS["candle_pattern"])
    else:
        candle_score = 0
    score_breakdown["candle_pattern"] = candle_score
    total += candle_score

    # --- 4. Session Context (max 15) ---
    session_ctx   = get_session_context(pair)
    session_score = session_ctx["score"]  # Already 0-15
    score_breakdown["session_context"] = session_score
    total += session_score

    # --- 5. News Clearance (max 10) ---
    news_check = is_news_safe(pair)
    news_score = WEIGHTS["news_clearance"] if news_check["safe"] else 0
    score_breakdown["news_clearance"] = news_score
    total += news_score

    # Hard block: no alert if news is not safe, regardless of score
    hard_blocked = not news_check["safe"]

    # --- FVG Overlap Bonus (up to +15, uncapped bonus) ---
    fvg_bonus = 0
    if confluence.get("has_fvg_overlap"):
        fvg_bonus = 15  # FVG overlapping a zone = premium setup
    elif confluence.get("active_fvgs"):
        fvg_bonus = 7   # FVG present but not overlapping a zone

    final_score = min(total + fvg_bonus, 100)

    result = {
        "pair":           pair,
        "score":          final_score,
        "breakdown":      score_breakdown,
        "fvg_bonus":      fvg_bonus,
        "has_fvg_overlap": confluence.get("has_fvg_overlap", False),
        "active_fvgs":    confluence.get("active_fvgs", []),
        "hard_blocked":   hard_blocked,
        "news_check":     news_check,
        "session_ctx":    session_ctx,
        "top_zone":       top_zone,
        "should_alert":   final_score >= SCORING["min_score_alert"] and not hard_blocked,
        "should_log":     final_score >= SCORING["min_score_log"],
        "direction":      confluence["direction"],
        "setup_type":     confluence["setup_type"],
        "entry_pattern":  confluence.get("entry_pattern"),
        "current_price":  confluence["current_price"],
    }

    logger.info(
        f"{pair} score: {final_score}/100 | "
        f"Zone:{zone_score} TF:{tf_score} Candle:{candle_score} "
        f"Session:{session_score} News:{news_score} | "
        f"Alert: {result['should_alert']}"
    )

    return result


def format_score_bar(score: int, width: int = 10) -> str:
    """Visual score bar for Slack messages. e.g. ████████░░ 82/100"""
    filled = round(score / 100 * width)
    bar    = "█" * filled + "░" * (width - filled)
    return f"{bar} {score}/100"


def score_label(score: int) -> str:
    if score >= 80:
        return "🔥 STRONG"
    elif score >= 65:
        return "✅ VALID"
    elif score >= 50:
        return "⚠️ WEAK"
    else:
        return "❌ SKIP"