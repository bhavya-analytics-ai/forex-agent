"""
scorer.py — Signal scoring + complete trade plan

FIXES IN THIS VERSION:
1. ICT CONFLICT PENALTY — if ICT MSS/ChoCH says bullish but signal is
   bearish (or vice versa), that's a -30 penalty. Previously this was
   just a cosmetic flag on the dashboard. Now it actually affects score.

2. DIRECTION SANITY CHECK — if H1 trend strongly disagrees with signal
   direction, cap the grade at B maximum. No more A+ signals against trend.

3. ZONE CONFLICT FLAG — if zone type contradicts H1 trend, add warning
   to flags so trader sees it clearly.

4. SCORE CAP LOGIC — removed the possibility of 100% scores. Max realistic
   score is ~85 for a genuine A+ setup. 100% meant the scorer wasn't
   penalizing anything — now it does.
"""

import logging
from config import SCORING
from filters.news import is_news_safe
from filters.session import get_session_context
from core.fetcher import pip_size

logger  = logging.getLogger(__name__)
WEIGHTS = SCORING["weights"]


def calculate_trade_levels(confluence: dict, pair: str, direction: str, ict: dict) -> dict:
    pip   = pip_size(pair)
    h1    = confluence.get("h1", {})
    entry = confluence.get("current_price", 0)

    if not entry:
        return {}

    atr_defaults = {
        "XAU_USD": 2.0,
        "XAG_USD": 0.10,
    }
    atr = atr_defaults.get(pair, 20 * pip)

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

    if sl_price is None:
        default_sl = {"XAU_USD": 200 * pip, "XAG_USD": 200 * pip}.get(pair, 25 * pip)
        sl_price   = entry - default_sl if direction == "bullish" else entry + default_sl

    sl_dist = abs(entry - sl_price)
    sl_pips = sl_dist / pip

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

    if direction == "bullish":
        tp1_price = entry + sl_dist * 2
        tp2_price = entry + sl_dist * 3
    else:
        tp1_price = entry - sl_dist * 2
        tp2_price = entry - sl_dist * 3

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
    ict_conflict   = confluence.get("ict_conflict", False)
    zone_warnings  = confluence.get("zone_warnings", [])

    entry_pattern = confluence.get("entry_pattern")
    news_check    = is_news_safe(pair)
    session_ctx   = get_session_context(pair)

    try:
        from filters.killzones import get_killzone_context
        kz_ctx = get_killzone_context(pair)
    except Exception:
        kz_ctx = {"in_killzone": True, "pair_favored": True, "score_modifier": 1.0, "note": ""}

    # Add zone conflict warnings to flags
    for warning in zone_warnings:
        add_flag(warning)

    # Pattern conflict check
    pattern_direction = entry_pattern.get("direction") if entry_pattern else None
    pattern_conflict  = (
        entry_pattern is not None
        and pattern_direction not in [None, "neutral"]
        and pattern_direction != direction
    )
    if pattern_conflict:
        add_flag(f"❌ CONFLICT: M5 {pattern_direction} candle vs {direction} signal — skip this")

    # H1 trend vs signal direction check
    h1_trend     = h1_structure.get("trend", "ranging")
    h1_strength  = h1_structure.get("strength", 1)
    h1_direction = "bullish" if "up" in h1_trend else ("bearish" if "down" in h1_trend else "neutral")
    against_h1_trend = (
        h1_direction != "neutral"
        and direction not in ["none", "neutral"]
        and h1_direction != direction
        and h1_strength >= 2
    )
    if against_h1_trend:
        add_flag(f"⚠️ COUNTER-TREND: Signal is {direction} but H1 trend is {h1_trend} — high risk")

    # ICT conflict flag
    if ict_conflict:
        ict_dir = ict.get("ict_direction", "")
        add_flag(f"🚨 ICT CONFLICT: MSS/ChoCH says {ict_dir} but signal is {direction} — do not enter")

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
    if not pattern_conflict and active_zones and not against_h1_trend:
        if   setup_quality == "A+": quality_bonus = 15
        elif setup_quality == "A":  quality_bonus = 10
        elif setup_quality == "B":  quality_bonus = 4
        if is_pullback and 0.35 <= pullback_depth <= 0.65:
            quality_bonus += 5

    score_breakdown["quality_bonus"] = quality_bonus
    total += quality_bonus

    # 7. FVG Bonus (+10)
    fvg_bonus = 0
    if not pattern_conflict and not ict_conflict:
        if confluence.get("has_fvg_overlap"):   fvg_bonus = 10
        elif confluence.get("active_fvgs"):     fvg_bonus = 4

    score_breakdown["fvg"] = fvg_bonus
    total += fvg_bonus

    # 8. ICT Bonus (+30)
    ict_bonus = 0
    if not pattern_conflict and not ict_conflict and ict:
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
                add_flag(sweep.get("description", "💧 Liquidity sweep aligned"))
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

    # ── PENALTIES ──────────────────────────────────────────────

    # Pattern conflict
    if pattern_conflict:
        total -= 25
        score_breakdown["conflict_penalty"] = -25

    # No zone
    if not active_zones:
        total -= 12
        score_breakdown["no_zone_penalty"] = -12

    # M5 consolidating
    m5_consol = m5.get("consolidation", {})
    if m5_consol.get("consolidating"):
        total -= 15
        score_breakdown["consolidation_penalty"] = -15
        add_flag(f"⚠️ M5 consolidating — wait for directional candle")

    # FIX: ICT conflict penalty — this used to be cosmetic only
    # Now it actually tanks the score. MSS/ChoCH contradicting signal = skip.
    if ict_conflict:
        total -= 30
        score_breakdown["ict_conflict_penalty"] = -30

    # FIX: Counter-trend penalty — signal against strong H1 trend
    # A+ setups should NEVER go against a strength-3 H1 trend
    if against_h1_trend:
        penalty = 20 if h1_strength == 3 else 10
        total  -= penalty
        score_breakdown["counter_trend_penalty"] = -penalty

    final_score = max(min(total, 95), 0)  # Cap at 95 — 100% confidence doesn't exist

    kz_modifier = kz_ctx.get("score_modifier", 1.0)
    if kz_modifier < 1.0:
        final_score = round(final_score * kz_modifier)
        add_flag(kz_ctx.get("note", "Outside killzone"))

    # Grading
    has_confirmation = bool(entry_pattern) and not pattern_conflict
    has_zone         = bool(active_zones)

    # Hard overrides — these situations can never be A or A+
    if pattern_conflict or ict_conflict:
        grade = "C"
    elif against_h1_trend and h1_strength == 3:
        grade = "C"  # Never take A/A+ against a strong H1 trend
        add_flag("🚫 Strong counter-trend — grade capped at C")
    elif not has_confirmation and not has_zone:
        grade = "C"
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
    elif against_h1_trend:
        # Can trade counter-trend but max grade is B
        grade = "B" if final_score >= 54 else "C"
        add_flag("⚠️ Counter-trend setup — grade capped at B, use tight SL")
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

    trade_levels = {}
    if direction != "none" and final_score >= 40:
        trade_levels = calculate_trade_levels(confluence, pair, direction, ict)

    # Get h1/m15/m5 trend labels for dashboard
    h1_trend_label  = h1.get("structure", {}).get("trend", "—")
    m15_structure   = confluence.get("m15", {}).get("structure", {})
    m5_structure    = confluence.get("m5",  {}).get("structure", {})
    m15_trend_label = m15_structure.get("trend", "—")
    m5_trend_label  = m5_structure.get("trend",  "—")

    result = {
        "pair":             pair,
        "score":            final_score,
        "grade":            grade,
        "grade_meaning":    grade_meaning,
        "flags":            flags,
        "breakdown":        score_breakdown,
        "pattern_conflict": pattern_conflict,
        "ict_conflict":     ict_conflict,
        "against_h1_trend": against_h1_trend,
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
        "should_alert":     final_score >= SCORING["min_score_alert"] and news_check["safe"] and not ict_conflict,
        "should_log":       final_score >= SCORING["min_score_log"],
        "direction":        direction,
        "setup_type":       confluence.get("setup_type", "unknown"),
        "entry_pattern":    entry_pattern,
        "current_price":    confluence.get("current_price", 0),
        "h1_trend":         h1_trend_label,
        "m15_trend":        m15_trend_label,
        "m5_trend":         m5_trend_label,
    }

    logger.info(
        f"{pair} | {final_score}/100 {grade} | "
        f"Zone:{zone_score} TF:{tf_score} Pat:{candle_score} "
        f"Sess:{session_score} News:{news_score} Qual:{quality_bonus} "
        f"FVG:{fvg_bonus} ICT:{ict_bonus} | "
        f"Conflicts: pattern={pattern_conflict} ict={ict_conflict} counter_trend={against_h1_trend}"
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