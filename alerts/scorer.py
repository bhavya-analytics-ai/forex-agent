"""
alerts/scorer.py — Hybrid Bayesian Scorer

PRIMARY OUTPUT: P(win) + EV
FALLBACK:       Grade (A+/A/B/C) for human readability

HOW IT WORKS:
  1. Determine setup type from confluence
  2. Pull base rate for that setup type
  3. Run calculate_posterior() — Bayesian update per condition
  4. Calculate EV = P(win) * RR - (1 - P(win)) * 1
  5. Derive grade from P(win) thresholds
  6. Auto-switch to data-backed rates at 50+ labeled signals

MODE AWARENESS:
  Normal mode    → STANDARD_LIKELIHOODS
  News sniper    → NEWS_LIKELIHOODS (passed in from mode_manager)
  The function never knows which mode — it just uses whatever table is passed.
"""

import csv
import logging
import os
from pathlib import Path

from filters.news    import is_news_safe
from filters.session import get_session_context
from core.fetcher    import pip_size

logger = logging.getLogger(__name__)

# ── BASE RATES ────────────────────────────────────────────────────────────────
# Estimated from ICT research. Replaced by real data at 50+ signals.

BASE_RATES = {
    "sweep_choch_fvg":   0.62,   # Full sniper: sweep + CHoCH + FVG/OB tap
    "breakout_retest":   0.55,   # Breakout confirmed + FVG retest
    "pullback_trend":    0.58,   # Clean pullback in strong H1 trend
    "trend_follow":      0.52,   # Full TF alignment
    "breakout_stage1":   0.42,   # Breakout stage 1, no retest yet
    "reversal":          0.50,   # H1 MSS confirmed reversal
    "ranging_weak":      0.35,   # Choppy / weak structure
    "default":           0.45,   # Unknown setup type
}

# ── STANDARD LIKELIHOODS ─────────────────────────────────────────────────────
# Each condition updates P(win) up or down.
# "yes" = condition present, "no" = condition absent.

STANDARD_LIKELIHOODS = {
    "h1_aligned":        {"yes": 1.30, "no": 0.70},
    "m15_aligned":       {"yes": 1.15, "no": 0.88},
    "m5_confirmation":   {"yes": 1.30, "no": 0.75},
    "at_ob":             {"yes": 1.40, "no": 0.85},
    "fvg_overlap":       {"yes": 1.35, "no": 0.90},
    "sweep_present":     {"yes": 1.30, "no": 0.80},
    "choch_present":     {"yes": 1.25, "no": 0.82},
    "in_killzone":       {"yes": 1.20, "no": 0.85},
    "news_safe":         {"yes": 1.10, "no": 0.40},
    "ict_conflict":      {"yes": 0.30, "no": 1.00},
    "pattern_conflict":  {"yes": 0.40, "no": 1.00},
    "against_h1_trend":  {"yes": 0.60, "no": 1.00},
    "choppy":            {"yes": 0.55, "no": 1.00},
    "m5_consolidating":  {"yes": 0.70, "no": 1.00},
}

# ── NEWS LIKELIHOODS ──────────────────────────────────────────────────────────
# Aggressive weights for news sniper mode.
# Built for speed: wick sweeps + M1 CHoCH after news spike.
# ONLY applied when NEWS_MODE is active — never bleeds into standard mode.

NEWS_LIKELIHOODS = {
    "news_spike_detected": {"yes": 2.10, "no": 0.20},  # spike = institutional intent
    "wick_sweep":          {"yes": 1.90, "no": 0.30},  # wick took stops = high conviction
    "m1_choch":            {"yes": 1.80, "no": 0.40},  # M1 CHoCH after spike = entry
    "fvg_overlap":         {"yes": 1.50, "no": 0.70},
    "h1_aligned":          {"yes": 1.20, "no": 0.80},  # less strict in news mode
    "m5_confirmation":     {"yes": 1.10, "no": 0.90},  # not required in news mode
    "ict_conflict":        {"yes": 0.20, "no": 1.00},  # still blocks hard conflicts
    "news_safe":           {"yes": 0.10, "no": 1.00},  # inverted — news mode WANTS news
    "in_killzone":         {"yes": 1.10, "no": 0.95},  # less important in news mode
}


# ── BAYESIAN CORE ─────────────────────────────────────────────────────────────

def calculate_posterior(setup_type: str, conditions: dict, likelihoods: dict, base_rates: dict = None) -> float:
    """
    Bayesian probability update.

    Starts with base rate for setup type.
    Each condition present/absent multiplies P(win) by its likelihood ratio.
    Result normalized to [0.01, 0.99].

    Args:
        setup_type:  key into base_rates dict
        conditions:  {condition_name: True/False}
        likelihoods: STANDARD_LIKELIHOODS or NEWS_LIKELIHOODS
        base_rates:  override base rates (used when data-backed)

    Returns:
        float: P(win) between 0.01 and 0.99
    """
    rates = base_rates or BASE_RATES
    prior = rates.get(setup_type, rates["default"])
    p     = prior

    for condition, present in conditions.items():
        if condition not in likelihoods:
            continue
        key = "yes" if present else "no"
        p  *= likelihoods[condition][key]

    return round(min(max(p, 0.01), 0.99), 3)


def calculate_ev(p_win: float, rr: float) -> float:
    """
    Expected Value = P(win) * RR - P(loss) * 1
    Positive EV = edge exists. Only take trades where EV > 0.20.
    """
    return round(p_win * rr - (1 - p_win) * 1, 3)


# ── DATA-BACKED BASE RATES ────────────────────────────────────────────────────

_SIGNALS_CSV = Path(__file__).parent.parent / "logs" / "signals.csv"
_MIN_SIGNALS  = 50   # threshold to switch from estimated to data-backed


def _load_data_backed_rates() -> tuple:
    """
    Load real win rates from signals.csv if enough labeled data exists.
    Returns (rates_dict, n_signals, is_data_backed)
    """
    if not _SIGNALS_CSV.exists():
        return BASE_RATES, 0, False

    try:
        labeled = []
        with open(_SIGNALS_CSV, "r") as f:
            reader = csv.DictReader(f)
            for row in reader:
                if row.get("outcome") in ("WIN", "LOSS"):
                    labeled.append(row)

        if len(labeled) < _MIN_SIGNALS:
            return BASE_RATES, len(labeled), False

        # Calculate win rate per setup type
        from collections import defaultdict
        wins   = defaultdict(int)
        totals = defaultdict(int)

        for row in labeled:
            st = row.get("setup_type", "default")
            totals[st] += 1
            if row["outcome"] == "WIN":
                wins[st] += 1

        data_rates = dict(BASE_RATES)  # start from estimated
        for st, total in totals.items():
            if total >= 10:  # only update if enough samples per type
                data_rates[st] = round(wins[st] / total, 3)

        return data_rates, len(labeled), True

    except Exception as e:
        logger.warning(f"Could not load data-backed rates: {e}")
        return BASE_RATES, 0, False


# ── SETUP TYPE MAPPER ─────────────────────────────────────────────────────────

def _map_setup_type(confluence: dict, scored_setup: str) -> str:
    """Map confluence setup type to base rate key."""
    ict        = confluence.get("ict", {}) or {}
    has_sweep  = ict.get("has_sweep", False)
    has_choch  = ict.get("has_choch", False)
    has_fvg    = confluence.get("has_fvg_overlap", False)
    is_pb      = confluence.get("is_pullback", False)
    is_bo      = confluence.get("is_breakout", False)
    is_retest  = confluence.get("is_retest", False)
    h1_mss     = confluence.get("h1_mss_fired", False)

    if has_sweep and has_choch and has_fvg:
        return "sweep_choch_fvg"
    if h1_mss:
        return "reversal"
    if is_bo and is_retest:
        return "breakout_retest"
    if is_pb:
        return "pullback_trend"
    if is_bo:
        return "breakout_stage1"
    if scored_setup == "trend_follow":
        return "trend_follow"
    return "default"


# ── GRADE FROM PROBABILITY ────────────────────────────────────────────────────

def _grade_from_p(p_win: float, ev: float, is_data_backed: bool) -> tuple:
    """
    Derive human-readable grade from P(win) and EV.
    Grade is secondary — P(win) + EV are primary.
    """
    if   p_win >= 0.62 and ev >= 0.25: grade = "A+"
    elif p_win >= 0.55 and ev >= 0.15: grade = "A"
    elif p_win >= 0.48 and ev >= 0.05: grade = "B"
    else:                               grade = "C"

    suffix = f"(n={is_data_backed})" if isinstance(is_data_backed, int) else ("data" if is_data_backed else "est")
    meaning = {
        "A+": "HIGH CONFIDENCE — strong edge, take if chart agrees",
        "A":  "GOOD SETUP — solid probability, standard size",
        "B":  "WATCH — marginal edge, reduce size or wait",
        "C":  "SKIP — negative or near-zero EV",
    }.get(grade, "")

    return grade, meaning, suffix


# ── CONDITION EXTRACTOR ───────────────────────────────────────────────────────

def _extract_conditions(confluence: dict, pair: str) -> dict:
    """Extract all scoreable conditions from confluence dict."""
    h1          = confluence.get("h1", {})
    m15         = confluence.get("m15", {})
    m5          = confluence.get("m5", {})
    ict         = confluence.get("ict", {}) or {}
    direction   = confluence.get("direction", "none")
    news_check  = is_news_safe(pair)
    session_ctx = get_session_context(pair)

    try:
        from filters.killzones import get_killzone_context
        kz_ctx = get_killzone_context(pair)
    except Exception:
        kz_ctx = {"in_killzone": True}

    h1_bias  = h1.get("bias", "neutral")
    m15_bias = m15.get("bias", "neutral")
    structure = h1.get("structure", {})

    entry_pattern  = m5.get("patterns", [])
    entry_pattern  = entry_pattern[0] if entry_pattern else None
    pattern_conflict = (
        entry_pattern is not None
        and entry_pattern.get("direction") not in [None, "neutral"]
        and entry_pattern.get("direction") != direction
    )

    m5_consol = m5.get("consolidation", {}).get("consolidating", False)
    choppy    = (
        structure.get("setup_quality") == "C"
        or (structure.get("strength", 1) == 1 and structure.get("phase") in ("ranging", "deep_pullback"))
    )

    ob_present = False
    if ict.get("has_ob"):
        ob = ict.get("top_ob", {}) or {}
        ob_present = ob.get("type") == direction

    return {
        "h1_aligned":       h1_bias == direction,
        "m15_aligned":      m15_bias == direction,
        "m5_confirmation":  bool(entry_pattern) and not pattern_conflict,
        "at_ob":            ob_present,
        "fvg_overlap":      confluence.get("has_fvg_overlap", False),
        "sweep_present":    ict.get("has_sweep", False),
        "choch_present":    ict.get("has_choch", False),
        "in_killzone":      kz_ctx.get("in_killzone", True),
        "news_safe":        news_check.get("safe", True),
        "ict_conflict":     confluence.get("ict_conflict", False),
        "pattern_conflict": pattern_conflict,
        "against_h1_trend": confluence.get("against_h1_trend", False),
        "choppy":           choppy,
        "m5_consolidating": m5_consol,
    }


# ── MAIN SCORER ───────────────────────────────────────────────────────────────

def score_signal(confluence: dict, pair: str, likelihoods: dict = None) -> dict:
    """
    Score a signal using Bayesian probability.

    Args:
        confluence:  full confluence dict from check_confluence()
        pair:        trading pair
        likelihoods: override likelihood table (for news sniper mode)
                     defaults to STANDARD_LIKELIHOODS

    Returns full scored dict with P(win), EV, grade, flags, trade_levels.
    """
    if likelihoods is None:
        likelihoods = STANDARD_LIKELIHOODS

    direction   = confluence.get("direction", "none")
    setup_type  = confluence.get("setup_type", "unknown")
    ict         = confluence.get("ict", {}) or {}
    news_check  = is_news_safe(pair)
    session_ctx = get_session_context(pair)

    # ── BASE RATES: estimated vs data-backed ──────────────────────────────────
    base_rates, n_labeled, is_data_backed = _load_data_backed_rates()
    mode_label = f"n={n_labeled}" if is_data_backed else "estimated"

    # ── SETUP TYPE ────────────────────────────────────────────────────────────
    bayes_setup = _map_setup_type(confluence, setup_type)

    # ── CONDITIONS ────────────────────────────────────────────────────────────
    conditions = _extract_conditions(confluence, pair)

    # ── POSTERIOR ─────────────────────────────────────────────────────────────
    p_win = calculate_posterior(bayes_setup, conditions, likelihoods, base_rates)

    # ── RR for EV ─────────────────────────────────────────────────────────────
    # Use 2.0 as default RR until decision layer sets real levels
    rr    = 2.0
    ev    = calculate_ev(p_win, rr)

    # ── GRADE ─────────────────────────────────────────────────────────────────
    grade, grade_meaning, data_suffix = _grade_from_p(p_win, ev, is_data_backed if is_data_backed else mode_label)

    # ── FLAGS (max 5, priority ordered) ───────────────────────────────────────
    flags      = []
    _seen      = set()

    def add_flag(msg: str):
        if msg not in _seen and len(flags) < 5:
            _seen.add(msg)
            flags.append(msg)

    # Signal type flags — most important first
    if confluence.get("h1_mss_fired"):
        add_flag(f"🔄 H1 MSS — trend reversing {direction.upper()}")

    if confluence.get("is_pullback"):
        add_flag(f"📉 PULLBACK in H1 {direction.upper()} — wait for M5 rejection")

    if confluence.get("is_breakout") and confluence.get("breakout", {}).get("detected"):
        bo = confluence["breakout"]
        if confluence.get("is_retest"):
            add_flag(f"⚡ BREAKOUT RETEST — {bo.get('atr_ratio', 0)}×ATR, enter {direction}")
        else:
            add_flag(f"🚀 BREAKOUT — {bo.get('atr_ratio', 0)}×ATR, watch for retest")

    # Conflict flags
    if confluence.get("ict_conflict"):
        add_flag(f"🚨 ICT CONFLICT — MSS/CHoCH vs signal direction, skip")

    if conditions.get("pattern_conflict"):
        add_flag(f"❌ PATTERN CONFLICT — M5 candle opposes signal direction")

    # ICT context flags
    if ict.get("has_sweep") and ict.get("recent_sweep", {}).get("description"):
        add_flag(ict["recent_sweep"]["description"])

    if ict.get("has_ob") and not conditions.get("ict_conflict"):
        ob = ict.get("top_ob", {}) or {}
        add_flag(f"📦 OB {ob.get('type','').title()}: {ob.get('low',0):.2f}–{ob.get('high',0):.2f}")

    if not news_check.get("safe"):
        add_flag(f"📰 NEWS BLOCK — {news_check.get('reason', '')}")
    elif news_check.get("caution"):
        add_flag(f"⚠️ NEWS CAUTION — {news_check.get('reason', '')}")

    # ── TRADE LEVELS (basic, overridden by decision layer) ───────────────────
    trade_levels = {}
    entry        = confluence.get("current_price", 0)
    pip          = pip_size(pair)

    if entry and direction != "none":
        atr_defaults = {"XAU_USD": 20.0, "XAG_USD": 1.0}
        atr          = atr_defaults.get(pair, 20 * pip)
        sl_dist      = atr
        sl           = entry - sl_dist if direction == "bullish" else entry + sl_dist
        tp1          = entry + sl_dist * 2 if direction == "bullish" else entry - sl_dist * 2
        tp2          = entry + sl_dist * 3 if direction == "bullish" else entry - sl_dist * 3
        sl_pips      = round(sl_dist / pip, 1)
        decimals     = 3 if "JPY" in pair else (2 if "XAU" in pair else 5)

        trade_levels = {
            "entry_price": round(entry, decimals),
            "sl_price":    round(sl,   decimals),
            "tp1_price":   round(tp1,  decimals),
            "tp2_price":   round(tp2,  decimals),
            "sl_pips":     sl_pips,
            "tp1_pips":    round(sl_pips * 2, 1),
            "tp2_pips":    round(sl_pips * 3, 1),
            "rr1":         "1:2",
            "rr2":         "1:3",
        }

        # Update EV with real RR once levels exist
        rr = 2.0
        ev = calculate_ev(p_win, rr)

    # ── TREND LABELS ──────────────────────────────────────────────────────────
    h1_trend_label  = confluence.get("h1", {}).get("structure", {}).get("trend", "—")
    m15_trend_label = confluence.get("m15", {}).get("structure", {}).get("trend", "—")
    m5_trend_label  = confluence.get("m5",  {}).get("structure", {}).get("trend", "—")

    # ── ALERT THRESHOLDS ──────────────────────────────────────────────────────
    should_alert = (
        p_win >= 0.55
        and ev >= 0.15
        and news_check.get("safe", True)
        and not confluence.get("ict_conflict", False)
    )

    result = {
        "pair":             pair,
        "p_win":            p_win,
        "p_win_pct":        f"{round(p_win * 100)}% ({mode_label})",
        "ev":               ev,
        "ev_label":         f"EV: {'+' if ev >= 0 else ''}{ev}",
        "grade":            grade,
        "grade_meaning":    grade_meaning,
        "bayes_setup":      bayes_setup,
        "conditions":       conditions,
        "flags":            flags,
        "score":            round(p_win * 100),   # kept for dashboard compatibility
        "direction":        direction,
        "setup_type":       setup_type,
        "entry_pattern":    confluence.get("entry_pattern"),
        "current_price":    entry,
        "h1_trend":         h1_trend_label,
        "m15_trend":        m15_trend_label,
        "m5_trend":         m5_trend_label,
        "trade_levels":     trade_levels,
        "top_zone":         confluence.get("h1", {}).get("active_zones", [None])[0] if confluence.get("h1", {}).get("active_zones") else None,
        "ict_conflict":     confluence.get("ict_conflict", False),
        "against_h1_trend": conditions.get("against_h1_trend", False),
        "pattern_conflict": conditions.get("pattern_conflict", False),
        "hard_blocked":     not news_check.get("safe", True),
        "news_check":       news_check,
        "session_ctx":      session_ctx,
        "has_fvg_overlap":  confluence.get("has_fvg_overlap", False),
        "active_fvgs":      confluence.get("active_fvgs", []),
        "should_alert":     should_alert,
        "should_log":       p_win >= 0.45,
        "breakdown":        conditions,   # kept for dashboard compatibility
    }

    logger.info(
        f"{pair} | P(win)={p_win} EV={ev} {grade} | "
        f"setup={bayes_setup} mode={mode_label} | "
        f"sweep={conditions.get('sweep_present')} choch={conditions.get('choch_present')} "
        f"ob={conditions.get('at_ob')} fvg={conditions.get('fvg_overlap')}"
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
