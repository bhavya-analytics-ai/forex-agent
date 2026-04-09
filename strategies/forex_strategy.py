"""
strategies/forex_strategy.py — Forex pairs execution strategy

Hard filters + TP/SL override for all non-gold/silver pairs.
Called from decision_layer.py orchestrator.

Hard Filters (any one blocks the trade):
  - Mid-range (40-60%) with weak structure
  - Near strong opposing HTF zone (within ATR * 0.5)
  - Timeframe conflict (H1/M15/M5 not aligned) — skipped for pullbacks
  - Choppy structure (quality C or ranging + strength 1)
  - 2+ signal conflicts (trend + zone + sweep mismatches)
  - RR < 1.0

Momentum override: breakout ATR ratio >= 1.5 skips mid-range and HTF zone filters.
"""

import logging
from core.fetcher import pip_size
from core.liquidity import get_stop_loss, get_take_profit

logger = logging.getLogger(__name__)


# ── HELPERS ───────────────────────────────────────────────────────────────────

def _atr_estimate(htf_high: float, htf_low: float) -> float:
    if htf_high <= htf_low:
        return 0.001
    return (htf_high - htf_low) / 20


def _has_strong_momentum(confluence: dict) -> bool:
    if not confluence.get("is_breakout"):
        return False
    bo = confluence.get("breakout", {})
    return bo.get("detected", False) and bo.get("atr_ratio", 0) >= 1.5


# ── HARD FILTERS ──────────────────────────────────────────────────────────────

def _is_mid_range(price: float, htf_high: float, htf_low: float, structure: dict) -> bool:
    if htf_high <= htf_low or htf_high == 0:
        return False
    rng = htf_high - htf_low
    pct = (price - htf_low) / rng
    if not (0.40 <= pct <= 0.60):
        return False
    quality  = structure.get("setup_quality", "C")
    strength = structure.get("strength", 1)
    return quality in ("C", "B") and strength <= 1


def _is_near_htf_zone(price: float, zones: list, direction: str, atr: float) -> bool:
    thresh = atr * 0.5
    opposing = {
        "bullish": {"resistance", "supply", "support_to_resistance"},
        "bearish": {"support", "demand", "resistance_to_support"},
    }.get(direction, set())

    for zone in zones:
        if zone.get("strength", 0) < 60:
            continue
        if zone.get("type", "") not in opposing:
            continue
        mid = (zone["high"] + zone["low"]) / 2
        if direction == "bullish" and mid > price and (mid - price) <= thresh:
            return True
        if direction == "bearish" and mid < price and (price - mid) <= thresh:
            return True
    return False


def _has_timeframe_conflict(h1_bias: str, m15_bias: str, m5_bias: str) -> bool:
    biases = [b for b in [h1_bias, m15_bias, m5_bias] if b not in ("neutral", "none", "")]
    if len(biases) < 2:
        return False
    return len(set(biases)) > 1


def _is_choppy(structure: dict) -> bool:
    quality  = structure.get("setup_quality", "C")
    strength = structure.get("strength", 1)
    phase    = structure.get("phase", "ranging")
    return quality == "C" or (strength == 1 and phase in ("ranging", "deep_pullback"))


def _has_too_many_conflicts(scored: dict, confluence: dict) -> bool:
    conflicts = 0
    if scored.get("against_h1_trend"):
        conflicts += 1
    if confluence.get("h1", {}).get("zone_conflict"):
        conflicts += 1
    ict       = confluence.get("ict", {})
    sweep     = ict.get("recent_sweep", {})
    direction = scored.get("direction", "none")
    if sweep and sweep.get("bias") and sweep.get("bias") != direction:
        conflicts += 1
    return conflicts >= 2


# ── MAIN ENTRY POINT ──────────────────────────────────────────────────────────

def apply_forex_strategy(scored: dict, confluence: dict, pair: str) -> dict:
    """
    Main entry point for all non-gold/silver pairs.

    Flow:
      1. Run hard filters — any one blocks the trade
      2. Calculate TP/SL via liquidity module
      3. RR validation
      4. Decision priority override (score is info only)
      5. Early entry check
    """
    direction = scored.get("direction", "none")
    price     = confluence.get("current_price", 0)

    if direction in ("none", "neutral") or not price:
        return scored

    h1        = confluence.get("h1", {})
    m15       = confluence.get("m15", {})
    m5        = confluence.get("m5", {})
    structure = h1.get("structure", {})
    all_zones = h1.get("zones", [])
    is_pb     = confluence.get("is_pullback", False)

    h1_bias  = h1.get("bias", "neutral")
    m15_bias = m15.get("bias", "neutral")
    m5_bias  = m5.get("bias", "neutral")

    htf_high = structure.get("last_high", 0)
    htf_low  = structure.get("last_low",  0)
    atr      = _atr_estimate(htf_high, htf_low)

    strong_momentum = _has_strong_momentum(confluence)
    block_reason    = None

    # ── HARD FILTERS ──────────────────────────────────────────────────────────
    if not strong_momentum and _is_mid_range(price, htf_high, htf_low, structure):
        block_reason = "Blocked: mid-range — price 40–60% with weak structure"

    elif not strong_momentum and _is_near_htf_zone(price, all_zones, direction, atr):
        block_reason = "Blocked: HTF zone — strong opposing zone within ATR×0.5"

    elif not is_pb and _has_timeframe_conflict(h1_bias, m15_bias, m5_bias):
        block_reason = "Blocked: TF conflict — H1/M15/M5 not aligned"

    elif _is_choppy(structure):
        block_reason = "Blocked: choppy — weak structure (quality C or ranging)"

    elif _has_too_many_conflicts(scored, confluence):
        block_reason = "Blocked: 2+ conflicts — trend + zone + sweep mismatches"

    if block_reason:
        logger.info(f"{pair} | FOREX BLOCK | {block_reason}")
        scored.update({
            "dl_blocked":      True,
            "dl_block_reason": block_reason,
            "should_alert":    False,
            "should_log":      False,
            "grade":           "C",
            "flags":           (scored.get("flags", []) + [f"🚫 {block_reason}"])[:5],
        })
        return scored

    # ── TP/SL OVERRIDE ────────────────────────────────────────────────────────
    scored["dl_blocked"]      = False
    scored["dl_block_reason"] = ""

    sl, sl_anchor       = get_stop_loss(price, confluence, direction, pair)
    tp1, tp2, tp1_label = get_take_profit(price, sl, confluence, direction, pair, atr)

    if sl and tp1 and tp2:
        pip      = pip_size(pair)
        sl_dist  = abs(price - sl)
        sl_pips  = round(sl_dist / pip, 1)
        tp1_pips = round(abs(tp1 - price) / pip, 1)
        tp2_pips = round(abs(tp2 - price) / pip, 1)

        # RR hard block
        if sl_pips > 0 and tp1_pips < sl_pips:
            rr_block = f"Blocked: RR < 1 — TP={tp1_pips}p vs SL={sl_pips}p"
            logger.info(f"{pair} | FOREX BLOCK | {rr_block}")
            scored.update({
                "dl_blocked":      True,
                "dl_block_reason": rr_block,
                "should_alert":    False,
                "should_log":      False,
                "grade":           "C",
                "flags":           (scored.get("flags", []) + [f"🚫 {rr_block}"])[:5],
            })
            return scored

        decimals = 3 if "JPY" in pair else 5
        rr1 = f"1:{round(tp1_pips / sl_pips, 1)}" if sl_pips > 0 else "1:?"
        rr2 = f"1:{round(tp2_pips / sl_pips, 1)}" if sl_pips > 0 else "1:?"

        scored["trade_levels"] = {
            "entry_price": round(price,   decimals),
            "sl_price":    round(sl,      decimals),
            "tp1_price":   round(tp1,     decimals),
            "tp2_price":   round(tp2,     decimals),
            "sl_pips":     sl_pips,
            "tp1_pips":    tp1_pips,
            "tp2_pips":    tp2_pips,
            "rr1":         rr1,
            "rr2":         rr2,
        }
        logger.info(f"{pair} | DL TP/SL | SL={round(sl, decimals)} [{sl_anchor}] TP1={round(tp1, decimals)} RR={rr1}")

    # ── DECISION PRIORITY ─────────────────────────────────────────────────────
    # Score is INFO ONLY — if structure + RR valid, trade is allowed regardless of grade
    _VALID_SETUP_TYPES = {
        "pullback_long", "pullback_short",
        "breakout_bull", "breakout_bear", "breakout_retest",
        "reversal_bull", "reversal_bear",
        "trend_follow", "sr_flip", "zone_tap",
    }

    trade_levels = scored.get("trade_levels", {})
    rr1_val      = 0.0
    if trade_levels.get("sl_pips", 0) > 0:
        rr1_val = trade_levels.get("tp1_pips", 0) / trade_levels["sl_pips"]

    setup_type   = scored.get("setup_type", "unknown")
    valid_rr     = rr1_val >= 1.5
    valid_setup  = setup_type in _VALID_SETUP_TYPES
    valid_struct = structure.get("setup_quality") in ("A+", "A", "B") or structure.get("strength", 0) >= 2
    news_safe    = scored.get("news_check", {}).get("safe", True)

    if valid_rr and valid_setup and valid_struct and news_safe:
        scored["should_alert"] = True
        scored["should_log"]   = True
        if scored.get("grade") == "C":
            scored["grade_meaning"] = "VALID SETUP — passes structure + RR check"
        logger.info(f"{pair} | FOREX PASS | grade={scored.get('grade')} RR={round(rr1_val, 1)} setup={setup_type}")
    else:
        reasons = []
        if not valid_rr:     reasons.append(f"RR={round(rr1_val, 1)}<1.5")
        if not valid_setup:  reasons.append(f"setup={setup_type}")
        if not valid_struct: reasons.append(f"structure={structure.get('setup_quality', '?')}")
        if not news_safe:    reasons.append("news block")
        logger.info(f"{pair} | FOREX NO PASS | {', '.join(reasons)}")

    # ── EARLY ENTRY ───────────────────────────────────────────────────────────
    _early_entry      = False
    no_strong_conflict = (
        not scored.get("ict_conflict", False)
        and not scored.get("pattern_conflict", False)
        and not scored.get("against_h1_trend", False)
    )
    tfs_aligned = (
        h1_bias == direction and
        (m15_bias == direction or m5_bias == direction)
    )
    _sq       = structure.get("setup_quality", "C")
    _strength = structure.get("strength", 1)
    _phase    = structure.get("phase", "ranging")
    _trend    = structure.get("trend", "ranging")
    not_choppy = not (_trend == "ranging" and _strength == 1 and _phase == "ranging")

    _hh_ll_forming = _phase in ("trending", "structure_break") and _strength >= 2
    _soft_signals  = sum([m15_bias == direction, m5_bias == direction, _strength >= 2])
    has_momentum   = _hh_ll_forming or (_soft_signals >= 2)

    early_pressure = (
        h1_bias == direction
        and (m15_bias == direction or m5_bias == direction or has_momentum)
        and not_choppy
        and no_strong_conflict
        and news_safe
    )

    if early_pressure:
        _early_entry           = True
        scored["should_alert"] = True
        scored["should_log"]   = True
        flags = scored.get("flags", [])
        flags = (flags + [f"⚡ EARLY ENTRY — pressure building {direction} | struct:{_sq}/{_strength}"])[:5]
        scored["flags"] = flags

    scored["early_entry"] = _early_entry
    scored["entry_type"]  = "anticipation" if _early_entry else "confirmed"

    return scored
