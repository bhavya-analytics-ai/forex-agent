"""
scorer.py — Signal scoring + complete trade plan

Every signal now includes:
  entry_price  — exact entry level
  sl_price     — stop loss (above/below OB or swing)
  tp1_price    — 1:2 risk/reward (scalp)
  tp2_price    — 1:3 risk/reward (swing)
  sl_pips      — risk in pips
  tp1_pips     — reward pips TP1
  tp2_pips     — reward pips TP2
"""

import logging
from config import SCORING
from filters.news import is_news_safe
from filters.session import get_session_context
from core.fetcher import pip_size

logger  = logging.getLogger(__name__)
WEIGHTS = SCORING["weights"]


def calculate_trade_levels(confluence: dict, pair: str, direction: str, ict: dict) -> dict:
    """
    Calculate entry, SL, TP1, TP2.

    Entry  — current price at zone/OB
    SL     — below OB low (bullish) or above OB high (bearish)
             fallback: swing high/low + ATR buffer
    TP1    — 1:2 from entry
    TP2    — 1:3 from entry
    """
    pip   = pip_size(pair)
    h1    = confluence.get("h1", {})

    entry = confluence.get("current_price", 0)
    if not entry:
        return {}

    # ATR fallback per pair type
    atr_defaults = {
        "XAU_USD": 2.0,   # $2 ATR default for gold
        "XAG_USD": 0.10,  # $0.10 ATR default for silver
    }
    atr = atr_defaults.get(pair, 20 * pip)

    # --- SL ---
    sl_price = None
    top_ob   = ict.get("top_ob") if ict else None

    if top_ob:
        if direction == "bullish":
            sl_price = top_ob["low"] - atr * 0.3
        else:
            sl_price = top_ob["high"] + atr * 0.3

    if sl_price is None:
        h1_struct = h1.get("structure", {})
        if direction == "bullish":
            last_low = h1_struct.get("last_low", 0)
            if last_low:
                sl_price = last_low - atr * 0.5
        else:
            last_high = h1_struct.get("last_high", 0)
            if last_high:
                sl_price = last_high + atr * 0.5

    # Final fallback
    if sl_price is None:
        default_sl = {"XAU_USD": 200 * pip, "XAG_USD": 200 * pip}.get(pair, 25 * pip)
        sl_price   = entry - default_sl if direction == "bullish" else entry + default_sl

    # --- Sanity check SL ---
    sl_dist   = abs(entry - sl_price)
    sl_pips   = sl_dist / pip

    min_sl = {"XAU_USD": 200, "XAG_USD": 150}.get(pair, 8)
    max_sl = {"XAU_USD": 1000, "XAG_USD": 800}.get(pair, 60)

    if sl_pips < min_sl:
        sl_dist  = min_sl * pip
        sl_pips  = min_sl
        sl_price = entry - sl_dist if direction == "bullish" else entry + sl_dist

    if sl_pips > max_sl:
        sl_dist  = max_sl * pip
        sl_pips  = max_sl
        sl_price = entry - sl_dist if direction == "bullish" else entry + sl_dist

    # --- TP ---
    if direction == "bullish":
        tp1_price = entry + sl_dist * 2
        tp2_price = entry + sl_dist * 3
    else:
        tp1_price = entry - sl_dist * 2
        tp2_price = entry - sl_dist * 3

    # Decimal places per pair
    decimals = 3 if "JPY" in pair else (2 if pair == "XAU_USD" else (3 if pair == "XAG_USD" else 5))

    return {
        "entry_price": round(entry,     decimals),
        "sl_price":    round(sl_price,  decimals),
        "tp1_price":   round(tp1_price, decimals),
        "tp2_price":   round(tp2_price, decimals),
        "sl_pips":     round(sl_pips,   1),
        "tp1_pips":    round(sl_pips * 2, 1),
        "tp2_pips":    round(sl_pips * 3, 1),
        "rr1":         "1:2",
        "rr2":         "1:3",
    }


def score_signal(confluence: dict, pair: str) -> dict:
    score_breakdown = {}
    _flags_seen     = set()
    flags           = []
    total           = 0

    def add_flag(msg: str):
        if msg not in _flags_seen:
            _flags_seen.add(msg)
            flags.append(msg)

    direction      = confluence.get("direction", "none")
    h1             = confluence.get("h1", {})
    m5             = confluence.get("m5", {})
    h1_structure   = h1.get("structure", {})
    setup_quality  = h1_structure.get("setup_quality", "C")
    is_pullback    = h1_structure.get("is_pullback", False)
    pullback_depth = h1_structure.get("pullback_depth", 0)
    active_zones   = h1.get("active_zones", [])
    ict            = confluence.get("ict", {})

    entry_pattern = confluence.get("entry_pattern")
    news_check    = is_news_safe(pair)
    session_ctx   = get_session_context(pair)

    try:
        from filters.killzones import get_killzone_context
        kz_ctx = get_killzone_context(pair)
    except Exception:
        kz_ctx = {"in_killzone": True, "pair_favored": True, "score_modifier": 1.0, "note": ""}

    # Pattern conflict
    pattern_direction = entry_pattern.get("direction") if entry_pattern else None
    pattern_conflict  = (
        entry_pattern is not None
        and pattern_direction not in [None, "neutral"]
        and pattern_direction != direction
    )
    if pattern_conflict:
        add_flag(f"❌ CONFLICT: M5 {pattern_direction} candle vs {direction} signal — skip this")

    # 1. Zone (25)
    if active_zones:
        top_zone   = max(active_zones, key=lambda z: z["strength"])
        zone_score = round((top_zone["strength"] / 100) * 25)
    else:
        top_zone   = None
        zone_score = 0
        add_flag("⚠️ Price not at a key H1 zone — lower conviction")

    score_breakdown["zone"] = zone_score
    total += zone_score

    # 2. TF Confluence (25)
    confidence = confluence.get("confidence", 0)
    tf_score   = round((confidence / 3) * 25)
    score_breakdown["tf"] = tf_score
    total += tf_score

    # 3. Pattern (20)
    if entry_pattern and not pattern_conflict:
        bars_ago     = entry_pattern.get("bars_ago", 0)
        pattern_raw  = entry_pattern.get("strength", 50)
        candle_score = round((pattern_raw / 100) * 20)
        if bars_ago >= 3:
            candle_score = round(candle_score * 0.4)
            add_flag(f"⚠️ Pattern {bars_ago} bars ago — may be stale")
        elif bars_ago == 2:
            candle_score = round(candle_score * 0.7)
    else:
        candle_score = 0
        if not entry_pattern:
            add_flag("⏳ No M5 confirmation candle yet — wait")

    score_breakdown["pattern"] = candle_score
    total += candle_score

    # 4. Session (15)
    session_score = session_ctx["score"]
    score_breakdown["session"] = session_score
    total += session_score

    # 5. News (10)
    news_score = 10 if news_check["safe"] else 0
    score_breakdown["news"] = news_score
    total += news_score

    # 6. Quality Bonus (+15)
    quality_bonus = 0
    if not pattern_conflict and active_zones:
        if   setup_quality == "A+": quality_bonus = 15
        elif setup_quality == "A":  quality_bonus = 10
        elif setup_quality == "B":  quality_bonus = 4
        if is_pullback and 0.35 <= pullback_depth <= 0.65:
            quality_bonus += 5

    score_breakdown["quality_bonus"] = quality_bonus
    total += quality_bonus

    # 7. FVG Bonus (+10)
    fvg_bonus = 0
    if not pattern_conflict:
        if confluence.get("has_fvg_overlap"):   fvg_bonus = 10
        elif confluence.get("active_fvgs"):     fvg_bonus = 4

    score_breakdown["fvg"] = fvg_bonus
    total += fvg_bonus

    # 8. ICT Bonus (+30)
    ict_bonus = 0
    if not pattern_conflict and ict:
        if ict.get("has_ob"):
            ict_bonus += 8
            ob = ict.get("top_ob", {})
            add_flag(f"📦 {ob.get('type','').title()} OB: {ob.get('low',0):.5f}–{ob.get('high',0):.5f}")

        if ict.get("has_mss"):
            ict_bonus += 10
            mss = ict.get("mss_m5") or ict.get("mss_m15") or {}
            add_flag(mss.get("description", "✅ MSS confirmed"))

        if ict.get("has_choch") and not ict.get("has_mss"):
            ict_bonus += 5
            choch = ict.get("choch_m5") or ict.get("choch_m15") or {}
            add_flag(choch.get("description", "⚡ ChoCH detected"))

        if ict.get("has_sweep"):
            sweep = ict.get("recent_sweep") or {}
            if sweep.get("bias", "") == direction:
                ict_bonus += 7
                add_flag(sweep.get("description", "💧 Liquidity sweep"))
            else:
                add_flag(f"💧 Sweep bias doesn't match signal direction")

        pd      = ict.get("premium_discount", {})
        pd_zone = pd.get("zone", "")
        if (pd_zone == "discount" and direction == "bullish") or \
           (pd_zone == "premium"  and direction == "bearish"):
            ict_bonus += 5
            add_flag(pd.get("description", f"Price in {pd_zone} zone"))
        elif pd_zone in ["premium", "discount"]:
            add_flag(f"⚠️ {pd_zone.upper()} zone but signal is {direction}")

    score_breakdown["ict"] = ict_bonus
    total += ict_bonus

    # Penalties
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
        add_flag(f"⚠️ M5 consolidating — wait for directional candle")

    final_score = max(min(total, 100), 0)

    kz_modifier = kz_ctx.get("score_modifier", 1.0)
    if kz_modifier < 1.0:
        final_score = round(final_score * kz_modifier)
        add_flag(kz_ctx.get("note", "Outside killzone"))

    # Grading
    has_confirmation = bool(entry_pattern) and not pattern_conflict
    has_zone         = bool(active_zones)

    if pattern_conflict:                        grade = "C"
    elif not has_confirmation and not has_zone: grade = "C"
    elif not has_confirmation:
        grade = "B" if final_score >= 55 else "C"
        add_flag("⏳ Waiting for M5 entry candle")
    elif not has_zone:
        grade = "B" if final_score >= 60 else "C"
    elif setup_quality == "C":
        if   final_score >= 80: grade = "A"
        elif final_score >= 65: grade = "B"
        else:                   grade = "C"
        add_flag("⚠️ Structure C — choppy, lower your size")
    else:
        if   final_score >= 82: grade = "A+"
        elif final_score >= 68: grade = "A"
        elif final_score >= 54: grade = "B"
        else:                   grade = "C"

    if not kz_ctx.get("in_killzone") and grade == "A+":
        grade = "A"
        add_flag("🕐 A+ capped to A — outside killzone")

    grade_meaning = {
        "A+": "HIGH CONFIDENCE — zone + structure + candle all aligned",
        "A":  "GOOD SETUP — solid confluence, take if chart looks right",
        "B":  "WATCH ONLY — missing 1+ element, wait for confirmation",
        "C":  "SKIP — conflicting or weak signals",
    }.get(grade, "")

    # Trade levels
    trade_levels = {}
    if direction != "none" and final_score >= 40:
        trade_levels = calculate_trade_levels(confluence, pair, direction, ict)

    result = {
        "pair":             pair,
        "score":            final_score,
        "grade":            grade,
        "grade_meaning":    grade_meaning,
        "flags":            flags,
        "breakdown":        score_breakdown,
        "pattern_conflict": pattern_conflict,
        "fvg_bonus":        fvg_bonus,
        "ict_bonus":        ict_bonus,
        "has_fvg_overlap":  confluence.get("has_fvg_overlap", False),
        "active_fvgs":      confluence.get("active_fvgs", []),
        "hard_blocked":     not news_check["safe"],
        "news_check":       news_check,
        "session_ctx":      session_ctx,
        "kz_ctx":           kz_ctx,
        "top_zone":         top_zone,
        "trade_levels":     trade_levels,
        "should_alert":     final_score >= SCORING["min_score_alert"] and news_check["safe"],
        "should_log":       final_score >= SCORING["min_score_log"],
        "direction":        direction,
        "setup_type":       confluence.get("setup_type", "unknown"),
        "entry_pattern":    entry_pattern,
        "current_price":    confluence.get("current_price", 0),
    }

    logger.info(
        f"{pair} | {final_score}/100 {grade} | "
        f"Zone:{zone_score} TF:{tf_score} Pat:{candle_score} "
        f"Sess:{session_score} News:{news_score} Qual:{quality_bonus} "
        f"FVG:{fvg_bonus} ICT:{ict_bonus} | Alert:{result['should_alert']}"
    )

    return result


def format_score_bar(score: int, width: int = 10) -> str:
    filled = round(score / 100 * width)
    return f"{'█' * filled}{'░' * (width - filled)} {score}/100"


def score_label(score: int) -> str:
    if   score >= 82: return "🔥 STRONG"
    elif score >= 68: return "✅ VALID"
    elif score >= 54: return "⚠️ WATCH"
    else:             return "❌ SKIP"