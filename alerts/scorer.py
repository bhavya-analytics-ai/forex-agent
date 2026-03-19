"""
scorer.py — Strict, honest signal scoring.

Scoring philosophy:
- Score reflects ACTUAL setup quality, not optimistic potential
- Pattern direction conflict = automatic C grade, heavy penalty
- No M5 confirmation candle = hard cap at B grade
- Quality C structure = drag grade down
- Bonuses only stack on already-solid signals

Score breakdown (max 100 base):
  Zone:       25  — quality of H1 zone being tapped
  TF:         25  — how many TFs agree (H1/M15/M5)
  Pattern:    20  — M5 candle strength and alignment
  Session:    15  — right session for this pair
  News:       10  — no high-impact events nearby
  Quality:   +15  — A+ setup bonus (pullback in confirmed trend)
  FVG:       +10  — fair value gap at zone

Penalties applied before grading:
  Conflict:       -25  — M5 pattern opposes signal direction
  No zone:        -15  — price not at any key H1 level
  Consolidating:  -15  — price chopping, no clear direction
  Stale pattern:  -8   — pattern formed 3+ bars ago
"""

import logging
from config import SCORING
from filters.news import is_news_safe
from filters.session import get_session_context

logger  = logging.getLogger(__name__)
WEIGHTS = SCORING["weights"]


def score_signal(confluence: dict, pair: str) -> dict:
    score_breakdown = {}
    flags           = []
    total           = 0

    direction     = confluence.get("direction", "none")
    h1            = confluence.get("h1", {})
    m5            = confluence.get("m5", {})
    h1_structure  = h1.get("structure", {})
    setup_quality = h1_structure.get("setup_quality", "C")
    is_pullback   = h1_structure.get("is_pullback", False)
    pullback_depth = h1_structure.get("pullback_depth", 0)
    active_zones  = h1.get("active_zones", [])
    entry_pattern = confluence.get("entry_pattern")
    news_check    = is_news_safe(pair)
    session_ctx   = get_session_context(pair)

    # ── Pattern conflict check ──────────────────────────────────
    pattern_direction = entry_pattern.get("direction") if entry_pattern else None
    pattern_conflict  = (
        entry_pattern is not None
        and pattern_direction not in [None, "neutral"]
        and pattern_direction != direction
    )
    if pattern_conflict:
        flags.append(
            f"❌ CONFLICT: M5 {pattern_direction} candle vs {direction} signal — "
            f"market is telling you the opposite, skip this"
        )

    # ── 1. Zone Strength (25) ───────────────────────────────────
    if active_zones:
        top_zone   = max(active_zones, key=lambda z: z["strength"])
        zone_score = round((top_zone["strength"] / 100) * 25)
    else:
        top_zone   = None
        zone_score = 0
        flags.append("⚠️ Price not at a key H1 zone — lower conviction setup")

    score_breakdown["zone"] = zone_score
    total += zone_score

    # ── 2. TF Confluence (25) ───────────────────────────────────
    confidence = confluence.get("confidence", 0)
    tf_score   = round((confidence / 3) * 25)
    score_breakdown["tf"] = tf_score
    total += tf_score

    # ── 3. Pattern (20) — 0 if conflict ─────────────────────────
    if entry_pattern and not pattern_conflict:
        bars_ago     = entry_pattern.get("bars_ago", 0)
        pattern_raw  = entry_pattern.get("strength", 50)
        candle_score = round((pattern_raw / 100) * 20)
        if bars_ago >= 3:
            candle_score = round(candle_score * 0.4)
            flags.append(f"⚠️ Pattern formed {bars_ago} bars ago — may be stale, wait for fresh one")
        elif bars_ago == 2:
            candle_score = round(candle_score * 0.7)
    else:
        candle_score = 0
        if not entry_pattern:
            flags.append("⏳ No M5 confirmation candle yet — DO NOT enter, wait")

    score_breakdown["pattern"] = candle_score
    total += candle_score

    # ── 4. Session (15) ─────────────────────────────────────────
    session_score = session_ctx["score"]
    score_breakdown["session"] = session_score
    total += session_score

    # ── 5. News (10) ────────────────────────────────────────────
    news_score = 10 if news_check["safe"] else 0
    score_breakdown["news"] = news_score
    total += news_score

    # ── Setup Quality Bonus (+15) ────────────────────────────────
    quality_bonus = 0
    if not pattern_conflict and active_zones:
        if setup_quality == "A+":
            quality_bonus = 15
        elif setup_quality == "A":
            quality_bonus = 10
        elif setup_quality == "B":
            quality_bonus = 4

        # Fibonacci sweet spot (38.2% – 61.8%)
        if is_pullback and 0.35 <= pullback_depth <= 0.65:
            quality_bonus += 5

    score_breakdown["quality_bonus"] = quality_bonus
    total += quality_bonus

    # ── FVG Bonus (+10) ─────────────────────────────────────────
    fvg_bonus = 0
    if not pattern_conflict:
        if confluence.get("has_fvg_overlap"):
            fvg_bonus = 10
        elif confluence.get("active_fvgs"):
            fvg_bonus = 4
    score_breakdown["fvg"] = fvg_bonus
    total += fvg_bonus

    # ── Penalties ────────────────────────────────────────────────
    if pattern_conflict:
        total -= 25
        score_breakdown["conflict_penalty"] = -25

    if not active_zones:
        total -= 12
        score_breakdown["no_zone_penalty"] = -12

    m5_consol = m5.get("consolidation", {})
    if m5_consol.get("consolidating"):
        total -= 15
        score_breakdown["consolidation_penalty"] = -15
        flags.append(
            f"⚠️ M5 consolidating ({m5_consol.get('range_pct','?')}x ATR) — "
            f"price chopping, wait for clear directional candle"
        )

    final_score = max(min(total, 100), 0)

    # ── Strict Grading ───────────────────────────────────────────
    has_confirmation = bool(entry_pattern) and not pattern_conflict
    has_zone         = bool(active_zones)

    if pattern_conflict:
        grade = "C"

    elif not has_confirmation and not has_zone:
        grade = "C"

    elif not has_confirmation:
        # No M5 candle = B max (setup is valid but not confirmed yet)
        grade = "B" if final_score >= 55 else "C"
        flags.append("⏳ Waiting for M5 entry candle — setup valid, not triggered yet")

    elif not has_zone:
        grade = "B" if final_score >= 60 else "C"

    elif setup_quality == "C":
        # Structure is weak — pull grade down
        if final_score >= 80:   grade = "A"
        elif final_score >= 65: grade = "B"
        else:                   grade = "C"
        flags.append("⚠️ Structure quality C — choppy market, lower your size")

    else:
        # Clean signal — grade purely on score
        if final_score >= 82:   grade = "A+"
        elif final_score >= 68: grade = "A"
        elif final_score >= 54: grade = "B"
        else:                   grade = "C"

    grade_meaning = {
        "A+": "HIGH CONFIDENCE — zone + structure + candle all aligned, strong entry",
        "A":  "GOOD SETUP — solid confluence, take if chart looks right to you",
        "B":  "WATCH ONLY — missing 1+ element, wait for more confirmation",
        "C":  "SKIP — conflicting or weak signals, not worth the risk",
    }.get(grade, "")

    result = {
        "pair":             pair,
        "score":            final_score,
        "grade":            grade,
        "grade_meaning":    grade_meaning,
        "flags":            flags,
        "breakdown":        score_breakdown,
        "pattern_conflict": pattern_conflict,
        "fvg_bonus":        fvg_bonus,
        "has_fvg_overlap":  confluence.get("has_fvg_overlap", False),
        "active_fvgs":      confluence.get("active_fvgs", []),
        "hard_blocked":     not news_check["safe"],
        "news_check":       news_check,
        "session_ctx":      session_ctx,
        "top_zone":         top_zone,
        "should_alert":     final_score >= SCORING["min_score_alert"] and news_check["safe"],
        "should_log":       final_score >= SCORING["min_score_log"],
        "direction":        direction,
        "setup_type":       confluence["setup_type"],
        "entry_pattern":    entry_pattern,
        "current_price":    confluence["current_price"],
    }

    logger.info(
        f"{pair} | {final_score}/100 {grade} | "
        f"Zone:{zone_score} TF:{tf_score} Pat:{candle_score} "
        f"Sess:{session_score} News:{news_score} Qual:{quality_bonus} | "
        f"Conflict:{pattern_conflict} Alert:{result['should_alert']}"
    )

    return result


def format_score_bar(score: int, width: int = 10) -> str:
    filled = round(score / 100 * width)
    return f"{'█' * filled}{'░' * (width - filled)} {score}/100"


def score_label(score: int) -> str:
    if score >= 82:   return "🔥 STRONG"
    elif score >= 68: return "✅ VALID"
    elif score >= 54: return "⚠️ WATCH"
    else:             return "❌ SKIP"