"""
decision_layer.py — Hard filter layer applied AFTER scoring, BEFORE output.

Wraps existing system without touching core logic.
Blocks bad trades entirely (no score reduction — full block).
Overrides TP/SL with structure-based levels.

BLOCKS:
  - Mid-range price (40–60%) AND weak structure — skipped if strong momentum
  - Near strong opposing HTF zone (ATR * 0.5 threshold) — skipped if strong momentum
  - Timeframe conflict — skipped for pullback setups
  - Choppy structure — weak/ranging market
  - RR < 1.0 after TP/SL calculation
  - 2+ signal conflicts (trend + zone + sweep mismatches)

MOMENTUM OVERRIDE:
  - If breakout detected with atr_ratio >= 1.5 → skip mid-range and HTF zone filters
"""

import logging
from core.fetcher import pip_size
from core.liquidity import get_stop_loss, get_take_profit

logger = logging.getLogger(__name__)


# ── HELPERS ─────────────────────────────────────────────────────────────────

def _atr_estimate(htf_high: float, htf_low: float) -> float:
    """Rough ATR estimate from H1 swing range. Used when real ATR not available."""
    if htf_high <= htf_low:
        return 0.001
    return (htf_high - htf_low) / 20


def _has_strong_momentum(confluence: dict) -> bool:
    """
    True if a breakout with atr_ratio >= 1.5 was detected.
    Uses already-computed breakout data in confluence — no extra calculation.
    """
    if not confluence.get("is_breakout"):
        return False
    bo = confluence.get("breakout", {})
    return bo.get("detected", False) and bo.get("atr_ratio", 0) >= 1.5


# ── FILTER FUNCTIONS ────────────────────────────────────────────────────────

def is_mid_range(price: float, htf_high: float, htf_low: float, structure: dict) -> bool:
    """
    True if price is 40–60% of HTF range AND structure is weak.
    Strong structure (quality A/A+, strength >= 2) overrides mid-range block.
    """
    if htf_high <= htf_low or htf_high == 0:
        return False
    rng = htf_high - htf_low
    pct = (price - htf_low) / rng
    if not (0.40 <= pct <= 0.60):
        return False
    # Only block mid-range if structure is also weak
    quality  = structure.get("setup_quality", "C")
    strength = structure.get("strength", 1)
    return quality in ("C", "B") and strength <= 1


def is_near_htf_zone(price: float, zones: list, direction: str, pair: str, atr: float) -> bool:
    """
    True if a strong OPPOSING zone is within ATR * 0.5.
    Dynamic threshold — adapts to volatility instead of fixed pips.
    Bullish → checks for resistance above. Bearish → checks for support below.
    """
    thresh = atr * 0.5

    opposing_types = {
        "bullish": {"resistance", "supply", "support_to_resistance"},
        "bearish": {"support", "demand", "resistance_to_support"},
    }
    opposing = opposing_types.get(direction, set())

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


def has_timeframe_conflict(h1_bias: str, m15_bias: str, m5_bias: str) -> bool:
    """
    True if timeframes are not aligned.
    Neutral counts as non-conflicting (waiting, not opposing).
    """
    biases = [b for b in [h1_bias, m15_bias, m5_bias] if b not in ("neutral", "none", "")]
    if len(biases) < 2:
        return False
    return len(set(biases)) > 1


def is_choppy(market_structure: dict) -> bool:
    """
    True if structure is weak, ranging, or deep pullback.
    """
    quality  = market_structure.get("setup_quality", "C")
    strength = market_structure.get("strength", 1)
    phase    = market_structure.get("phase", "ranging")
    return quality == "C" or (strength == 1 and phase in ("ranging", "deep_pullback"))


def has_too_many_conflicts(scored: dict, confluence: dict) -> bool:
    """
    True if 2+ of these conflict signals are present simultaneously:
      - against_h1_trend (trend mismatch)
      - zone_conflict on H1 (zone vs trend mismatch)
      - ICT sweep bias doesn't match signal direction (sweep mismatch)
    Stacking conflicts = high noise environment = block.
    """
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


# ── GOLD MODE ────────────────────────────────────────────────────────────────

def _apply_gold_mode(scored: dict, confluence: dict) -> dict:
    """
    XAU_USD-only logic. Replaces the standard decision layer for gold.
    Called when pair == "XAU_USD". Nothing outside this function touches gold.

    Steps:
      2. Dual-lookback H1 trend (long vs short term)
      3. Zone classification (resistance/support relative to trend)
      4. Reaction vs breakout detection
      5. Trade direction validation
      6. Gold SL: M5 → M15 → OB, capped at ATR*2
      7. Gold TP: nearest liquidity with RR >= 1.2, min dist ATR*0.5
      8. Momentum override
      9. Session confidence
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
    ict       = confluence.get("ict", {}) or {}

    # ── STEP 2: DUAL LOOKBACK TREND ─────────────────────────────────────────
    # long_term  (~60 H1 candles) = H1 structure trend — 6 weighted swings
    # short_term (~30 H1 candles) = M15 structure trend — recent action proxy
    #   (M15 runs on 100 candles ≈ last 25 hrs, close enough to last 30 H1 bars)
    long_trend  = structure.get("trend", "ranging")          # H1 60-candle view
    m15_struct  = m15.get("structure", {})
    short_trend = m15_struct.get("trend", "ranging")         # M15 30-candle proxy
    phase       = structure.get("phase", "ranging")
    strength    = structure.get("strength", 1)

    long_bias  = "bullish" if "up" in long_trend  else ("bearish" if "down" in long_trend  else "neutral")
    short_bias = "bullish" if "up" in short_trend else ("bearish" if "down" in short_trend else "neutral")

    if long_bias == short_bias and long_bias != "neutral":
        trend_strength = "strong" if strength >= 2 else "weak"
    else:
        trend_strength = "pullback / transition"

    trend_agree = long_bias == short_bias

    # ── ATR ESTIMATE ─────────────────────────────────────────────────────────
    last_high = structure.get("last_high", 0)
    last_low  = structure.get("last_low",  0)
    atr       = _atr_estimate(last_high, last_low)
    atr       = max(atr, 0.50)  # Gold floor: min $0.50 ATR

    # ── STEP 3: ZONE CLASSIFICATION ──────────────────────────────────────────
    gold_zones = []
    for z in all_zones:
        mid    = (z["high"] + z["low"]) / 2
        if long_bias == "bearish":
            g_type = "resistance" if mid > price else "support"
        elif long_bias == "bullish":
            g_type = "support" if mid < price else "resistance"
        else:
            g_type = "resistance" if mid > price else "support"
        gold_zones.append({**z, "gold_type": g_type})

    # ── STEP 4: REACTION vs BREAKOUT ─────────────────────────────────────────
    is_bo = confluence.get("is_breakout", False)
    bo    = confluence.get("breakout", {}) or {}

    if is_bo and bo.get("detected"):
        atr_ratio  = bo.get("atr_ratio", 0)
        consec     = bo.get("consecutive", 1)
        # Breakout: ATR ratio >= 1.5 (was 1.8), 2+ consecutive candles
        zone_type  = "breakout" if atr_ratio >= 1.5 and consec >= 2 else "reaction"
    else:
        zone_type = "reaction"

    # ── STEP 4.5: BREAKOUT PRESSURE DETECTION ────────────────────────────────
    # Compression = M15 consolidating AND price sitting within ATR*0.3 of a key level.
    # Early breakout = compression + range expansion candle OR existing momentum.
    # Effect: upgrades zone_type so direction block (STEP 5) is bypassed.

    m15_consol    = m15.get("consolidation", {})
    consolidating = m15_consol.get("consolidating", False)

    # Level proximity — strong zone OR H1 swing high/low within ATR*0.3
    near_level      = False
    near_level_info = ""
    for z in gold_zones:
        mid = (z["high"] + z["low"]) / 2
        if abs(price - mid) <= atr * 0.3 and z.get("strength", 0) >= 50:
            near_level      = True
            near_level_info = f"{z.get('gold_type', 'zone')} @ {round(mid, 2)}"
            break
    if not near_level:
        if last_high and abs(price - last_high) <= atr * 0.3:
            near_level      = True
            near_level_info = f"H1 swing high @ {round(last_high, 2)}"
        elif last_low and abs(price - last_low) <= atr * 0.3:
            near_level      = True
            near_level_info = f"H1 swing low @ {round(last_low, 2)}"

    compression = consolidating and near_level

    # Early breakout trigger: compression + expansion candle (ATR ratio >= 1.3) OR momentum
    early_breakout    = False
    breakout_pressure = False

    if compression:
        breakout_pressure = True
        bo_atr_ratio = (confluence.get("breakout") or {}).get("atr_ratio", 0)
        early_breakout = bo_atr_ratio >= 1.3 or _has_strong_momentum(confluence)

        if early_breakout:
            zone_type = "breakout"  # full upgrade — skip all reaction filters
            scored["flags"] = scored.get("flags", []) + [
                f"⚡ EARLY BREAKOUT — consolidation at {near_level_info}, expansion fired"
            ]
        else:
            zone_type = "breakout_preparation"  # bypass reaction direction block
            scored["flags"]      = scored.get("flags", []) + [
                f"⚡ BREAKOUT PREP — compression near {near_level_info}, watch for expansion"
            ]
            scored["setup_type"] = "breakout_preparation"

    scored["breakout_pressure"] = breakout_pressure
    scored["early_breakout"]    = early_breakout
    scored["near_level"]        = near_level_info if near_level else ""

    # ── STEP 4.6: BREAKOUT ACCEPTANCE CONFIRMATION ───────────────────────────
    # After a breakout fires, check whether price is HOLDING above/below the level.
    # Uses candles_ago (how long ago the break happened) + price vs FVG/breakout level.
    # early_breakout always allows entry regardless — this check targets regular breakouts.

    breakout_confirmed = False

    if is_bo and bo.get("detected"):
        candles_ago          = bo.get("candles_ago", 0)
        bo_fvg               = bo.get("fvg") or {}
        bo_candle_high       = bo.get("candle_high", 0)
        bo_candle_low        = bo.get("candle_low",  0)
        retest_data          = confluence.get("retest") or {}

        if candles_ago >= 1:
            # At least 1 candle formed after the breakout — evaluate whether it held
            fvg_invaded = retest_data.get("in_fvg", False)

            if direction == "bullish":
                # Acceptance: price still above FVG low (or breakout candle low)
                hold_level         = bo_fvg.get("low", bo_candle_low) if bo_fvg else bo_candle_low
                breakout_confirmed = (price > hold_level) and not fvg_invaded
            else:
                # Acceptance: price still below FVG high (or breakout candle high)
                hold_level         = bo_fvg.get("high", bo_candle_high) if bo_fvg else bo_candle_high
                breakout_confirmed = (price < hold_level) and not fvg_invaded

            if breakout_confirmed:
                # ── BREAKOUT STRENGTH ─────────────────────────────────────
                _bo_atr_ratio  = bo.get("atr_ratio",    0)
                _bo_consec     = bo.get("consecutive",  1)
                breakout_strength_val = round(_bo_atr_ratio * _bo_consec, 2)

                if   breakout_strength_val >= 4.0: bo_strength_label = "HIGH"
                elif breakout_strength_val >= 2.0: bo_strength_label = "MEDIUM"
                else:                              bo_strength_label = "LOW"

                scored["breakout_strength"]       = breakout_strength_val
                scored["breakout_strength_label"] = bo_strength_label

                # ── GRADE UPGRADE ─────────────────────────────────────────
                # Full upgrade to A only if strong trend + strong candle + not mid-range
                _in_mid_range = False
                if last_high and last_low and (last_high - last_low) > 0:
                    _rng_pct      = (price - last_low) / (last_high - last_low)
                    _in_mid_range = 0.40 <= _rng_pct <= 0.60

                _full_upgrade = (
                    structure.get("strength", 1) >= 2
                    and _bo_atr_ratio >= 1.3
                    and not _in_mid_range
                )

                current_grade = scored.get("grade", "C")
                _one_up = {"C": "B", "B": "A", "A": "A", "A+": "A+"}

                if _full_upgrade:
                    new_grade     = "A"
                    new_meaning   = "BREAKOUT CONFIRMED — strong trend + strong candle, continuation entry"
                else:
                    new_grade     = _one_up.get(current_grade, current_grade)
                    new_meaning   = f"BREAKOUT CONFIRMED — upgraded {current_grade}→{new_grade} (partial conditions met)"

                if new_grade != current_grade:
                    scored["grade"]         = new_grade
                    scored["grade_meaning"] = new_meaning

                # ── ENTRY MODE BY STRENGTH ───────────────────────────────
                if bo_strength_label == "HIGH":
                    _near     = bool(scored.get("near_level"))
                    _valid_bo = breakout_confirmed or early_breakout

                    # Candle close quality: must close in top 70% (bullish) / bottom 30% (bearish)
                    _c_high  = bo.get("candle_high",  0)
                    _c_low   = bo.get("candle_low",   0)
                    _c_close = bo.get("candle_close", 0)
                    _c_range = _c_high - _c_low
                    if _c_range > 0:
                        _close_pct = (_c_close - _c_low) / _c_range
                        _strong_close = (
                            _close_pct >= 0.70 if direction == "bullish"
                            else _close_pct <= 0.30
                        )
                    else:
                        _strong_close = False

                    if _near and _valid_bo and _strong_close:
                        scored["entry_mode"]   = "immediate"
                        scored["should_alert"] = True
                        entry_mode_note = "immediate continuation entry allowed"
                    else:
                        scored["entry_mode"]   = "wait"
                        scored["should_alert"] = False
                        _fail_reasons = []
                        if not _near:         _fail_reasons.append("not near level")
                        if not _valid_bo:     _fail_reasons.append("not confirmed/early")
                        if not _strong_close: _fail_reasons.append(f"weak close ({round(_close_pct*100) if _c_range > 0 else '?'}%)")
                        entry_mode_note = f"HIGH strength but: {', '.join(_fail_reasons)} — wait"
                    scored["flags"] = scored.get("flags", []) + [
                        f"{'✅' if scored['entry_mode'] == 'immediate' else '⚠️'} "
                        f"BREAKOUT [{bo_strength_label}] — {entry_mode_note}"
                    ]

                elif bo_strength_label == "MEDIUM":
                    # Allow only if at least 1 confirmation candle already formed
                    if candles_ago >= 1:
                        scored["entry_mode"]  = "confirmed"
                        scored["should_alert"] = True
                        entry_mode_note = "1 confirmation candle present — entry valid"
                    else:
                        scored["entry_mode"]  = "wait"
                        scored["should_alert"] = False
                        entry_mode_note = "wait for 1 confirmation candle before entering"
                    scored["flags"] = scored.get("flags", []) + [
                        f"✅ BREAKOUT CONFIRMED [{bo_strength_label}] — {entry_mode_note}"
                    ]

                else:  # LOW
                    scored["entry_mode"]  = "skip"
                    scored["should_alert"] = False
                    scored["should_log"]   = True   # log it but don't alert
                    entry_mode_note = "LOW strength breakout — skip continuation trade"
                    scored["flags"] = scored.get("flags", []) + [
                        f"⚠️ BREAKOUT CONFIRMED [{bo_strength_label}] — {entry_mode_note}"
                    ]
                logger.info(
                    f"XAU_USD | BREAKOUT CONFIRMED | held={hold_level:.2f} "
                    f"strength={bo_strength_label}({breakout_strength_val}) "
                    f"grade={current_grade}→{new_grade} entry_mode={scored['entry_mode']}"
                )

            else:
                # Breakout happened but price went back — likely fakeout
                # early_breakout path still allows aggressive entry (user's intent)
                if not early_breakout:
                    scored["flags"] = scored.get("flags", []) + [
                        "⚠️ BREAKOUT UNCONFIRMED — price back inside level, possible fakeout"
                    ]
                    # Revert zone_type to reaction so direction filter kicks back in
                    if zone_type == "breakout":
                        zone_type = "reaction"
                    logger.info(f"XAU_USD | BREAKOUT FAKEOUT | price={price:.2f} hold_level={hold_level:.2f} in_fvg={fvg_invaded}")

        # candles_ago == 0: breakout candle is the LAST candle — too fresh to confirm
        # early_breakout handles this case; don't print fakeout

    elif early_breakout:
        # Compression-based early breakout — no regular breakout to evaluate
        # Treat as unconfirmed but still allow entry (aggressive mode)
        breakout_confirmed = False

    scored["breakout_confirmed"] = breakout_confirmed

    # ── STEP 4.7: ENTRY MODE LABELS ──────────────────────────────────────────
    if early_breakout and not breakout_confirmed:
        scored["flags"] = scored.get("flags", []) + [
            "⚡ EARLY ENTRY MODE — aggressive, pre-confirmation. Use smaller size."
        ]
    elif breakout_confirmed:
        scored["flags"] = scored.get("flags", []) + [
            "✅ CONTINUATION MODE — breakout accepted, full-size entry valid"
        ]

    # ── STEP 8: MOMENTUM ─────────────────────────────────────────────────────
    momentum = _has_strong_momentum(confluence)

    # ── STEP 5: TRADE DIRECTION VALIDATION ───────────────────────────────────
    # Reaction setups must trade WITH H1 trend.
    # Momentum override: strong displacement ignores mid-range and zone restrictions —
    # institutional move in progress, don't fade it.
    # Breakout also bypasses direction filter.
    if zone_type == "reaction" and not momentum and long_bias != "neutral":
        if direction != long_bias:
            reason = (
                f"Blocked (gold): reaction setup but signal={direction} "
                f"conflicts with H1 {long_bias} trend — trade WITH trend only"
            )
            logger.info(f"XAU_USD | GOLD BLOCK | {reason}")
            scored.update({
                "dl_blocked":      True,
                "dl_block_reason": reason,
                "should_alert":    False,
                "should_log":      False,
                "flags":           scored.get("flags", []) + [f"🚫 {reason}"],
            })
            return scored

    # ── STEP 1: MOMENTUM CONTEXT DETECTION ───────────────────────────────────
    # Check candle-level momentum: large candle OR 2+ strong candles same direction
    m5_struct  = m5.get("structure",  {})
    m15_struct = m15.get("structure", {})
    ob         = ict.get("top_ob",    {}) or {}

    momentum_mode = momentum  # already set by _has_strong_momentum (breakout check)
    if not momentum_mode:
        # Also check M5 candle size vs ATR
        try:
            m5_df = confluence.get("m5", {})
            # Use M5 structure ATR proxy: (last_high - last_low) / 10
            m5_high_val = m5_struct.get("last_high", 0)
            m5_low_val  = m5_struct.get("last_low",  0)
            if m5_high_val and m5_low_val:
                m5_atr_est = (m5_high_val - m5_low_val) / 10
                # Check if recent M15 breakout atr_ratio is >= 1.5 (consecutive candles)
                bo_data = confluence.get("breakout", {}) or {}
                if bo_data.get("atr_ratio", 0) >= 1.5 or bo_data.get("consecutive", 0) >= 2:
                    momentum_mode = True
        except Exception:
            pass

    sl_mode = "momentum" if momentum_mode else "normal"

    # ── GOLD STRONG MOMENTUM DETECTION ───────────────────────────────────────
    # More comprehensive than the basic breakout check.
    # Requires: M5 aligned + candle expansion + no choppy structure.
    # When True: continuation and shallow pullback entries are allowed —
    # system stops requiring deep retracement for gold.

    m5_bias_val   = m5.get("bias", "neutral")
    m5_aligned    = m5_bias_val == direction
    candle_expand = (
        bo.get("atr_ratio",    0) >= 1.5   # strong M15 impulse
        or bo.get("consecutive", 0) >= 2    # multi-candle thrust
        or momentum_mode                    # already flagged by breakout check
    )
    not_choppy_gold = (
        structure.get("strength", 1) >= 2
        and phase not in ("ranging", "deep_pullback")
    )

    strong_gold_momentum = m5_aligned and candle_expand and not_choppy_gold

    # Safety guards — cancel momentum override if conditions are dangerous
    if strong_gold_momentum:
        _overextended = (
            phase == "trending"
            and structure.get("strength", 1) >= 3
            and not near_level
            and not breakout_pressure
        )
        _hard_conflict = confluence.get("ict_conflict", False) and not momentum_mode

        if _overextended:
            strong_gold_momentum = False
            logger.info("XAU_USD | momentum override cancelled — overextended (trending, no key level nearby)")
        elif _hard_conflict:
            strong_gold_momentum = False
            logger.info("XAU_USD | momentum override cancelled — hard ICT conflict present")

    # ── STEP 2 & 3: GOLD SL (ADAPTIVE) ───────────────────────────────────────
    # Normal mode  : M5 swing → M15 swing → OB → ATR fallback (tight)
    # Momentum mode: skip M5 (too tight for fast moves) → M15 → OB → ATR*1.5
    #                + ATR*0.3 buffer on top
    sl        = None
    sl_anchor = None
    sl_buffer = atr * 0.3 if momentum_mode else atr * 0.2

    if direction == "bullish":
        m5_low  = m5_struct.get("last_low",  0)
        m15_low = m15_struct.get("last_low", 0)
        if not momentum_mode and m5_low and m5_low < price:
            sl, sl_anchor = m5_low  - sl_buffer, "M5 swing low"
        elif m15_low and m15_low < price:
            sl, sl_anchor = m15_low - sl_buffer, "M15 swing low"
        elif ob.get("low"):
            sl, sl_anchor = ob["low"] - sl_buffer, "OB edge (low)"
    else:
        m5_high  = m5_struct.get("last_high",  0)
        m15_high = m15_struct.get("last_high", 0)
        if not momentum_mode and m5_high and m5_high > price:
            sl, sl_anchor = m5_high  + sl_buffer, "M5 swing high"
        elif m15_high and m15_high > price:
            sl, sl_anchor = m15_high + sl_buffer, "M15 swing high"
        elif ob.get("high"):
            sl, sl_anchor = ob["high"] + sl_buffer, "OB edge (high)"

    if sl is None:
        fallback_dist = atr * 1.5 if momentum_mode else atr
        sl            = price - fallback_dist if direction == "bullish" else price + fallback_dist
        sl_anchor     = f"ATR×{'1.5' if momentum_mode else '1.0'} fallback"

    # Cap SL at ATR * 2
    max_sl_dist = atr * 2
    sl_dist     = abs(price - sl)
    if sl_dist > max_sl_dist:
        sl        = price - max_sl_dist if direction == "bullish" else price + max_sl_dist
        sl_dist   = max_sl_dist
        sl_anchor += " (capped ATR×2)"

    # ── STEP 7: GOLD TP ───────────────────────────────────────────────────────
    # Rules:
    #   TP1 = nearest valid liquidity (distance >= ATR*0.5, RR >= 1.2)
    #          CLOSEST always wins — far H1 swing can never beat a closer level
    #   TP2 = next level in the sorted list after TP1
    #          NOT a fixed multiplier — real structure only
    min_tp_dist = atr * 0.5
    tp1         = None
    tp1_label   = None
    tp2         = None
    tp2_label   = None

    # Collect all candidates. Sort by DISTANCE from price (ascending = nearest first).
    # Deduplication: when two levels are within ATR*0.3, keep the CLOSER one always.
    def _build_tp_candidates(dirn: str) -> list:
        """Returns list of (dist_from_price, price_level, label) sorted nearest first."""
        raw = []
        m15_s = m15.get("structure", {})

        if dirn == "bullish":
            for lvl, lbl in [
                (m15_s.get("last_high", 0),      "M15 swing high"),
                (structure.get("last_high", 0),  "H1 swing high"),
            ]:
                if lvl and lvl > price and (lvl - price) >= min_tp_dist:
                    raw.append((lvl - price, lvl, lbl))
            for z in gold_zones:
                if z.get("gold_type") == "resistance" and z.get("strength", 0) >= 55:
                    mid = (z["high"] + z["low"]) / 2
                    if mid > price and (mid - price) >= min_tp_dist:
                        raw.append((mid - price, mid, f"zone {z['type']}"))
        else:
            for lvl, lbl in [
                (m15_s.get("last_low", 0),       "M15 swing low"),
                (structure.get("last_low", 0),   "H1 swing low"),
            ]:
                if lvl and lvl < price and (price - lvl) >= min_tp_dist:
                    raw.append((price - lvl, lvl, lbl))
            for z in gold_zones:
                if z.get("gold_type") == "support" and z.get("strength", 0) >= 55:
                    mid = (z["high"] + z["low"]) / 2
                    if mid < price and (price - mid) >= min_tp_dist:
                        raw.append((price - mid, mid, f"zone {z['type']}"))

        # Sort by distance ascending — nearest first
        raw.sort(key=lambda x: x[0])

        # Deduplicate within ATR*0.3: closer level ALWAYS wins (first in list wins)
        deduped = []
        for dist, lvl, lbl in raw:
            if deduped and abs(lvl - deduped[-1][1]) < atr * 0.3:
                pass  # skip — closer level already in list
            else:
                deduped.append((dist, lvl, lbl))

        return deduped

    sorted_tps = _build_tp_candidates(direction)

    # TP1 = first candidate with RR >= 1.2
    tp1_idx = None
    for i, (dist, lvl, lbl) in enumerate(sorted_tps):
        if sl_dist > 0 and dist / sl_dist >= 1.2:
            tp1, tp1_label, tp1_idx = lvl, lbl, i
            break

    # TP2 = next candidate after TP1 with RR >= 1.2
    if tp1_idx is not None:
        for dist, lvl, lbl in sorted_tps[tp1_idx + 1:]:
            if sl_dist > 0 and dist / sl_dist >= 1.2:
                tp2, tp2_label = lvl, lbl
                break

    # Fallbacks
    if tp1 is None:
        tp1       = price + sl_dist * 1.5 if direction == "bullish" else price - sl_dist * 1.5
        tp1_label = "1.5×SL fallback"
    if tp2 is None:
        tp2       = price + sl_dist * 2.5 if direction == "bullish" else price - sl_dist * 2.5
        tp2_label = "2.5×SL fallback"

    # ── RR CHECK ─────────────────────────────────────────────────────────────
    pip      = pip_size("XAU_USD")
    sl_pips  = round(sl_dist / pip, 1)
    tp1_pips = round(abs(tp1 - price) / pip, 1)
    tp2_pips = round(abs(tp2 - price) / pip, 1)
    rr_val   = tp1_pips / sl_pips if sl_pips > 0 else 0

    if rr_val < 1.2:
        reason = f"Blocked (gold): RR={round(rr_val,1)}<1.2 — SL={sl_pips}p TP={tp1_pips}p"
        logger.info(f"XAU_USD | GOLD BLOCK | {reason}")
        scored.update({
            "dl_blocked":      True,
            "dl_block_reason": reason,
            "should_alert":    False,
            "should_log":      False,
            "flags":           scored.get("flags", []) + [f"🚫 {reason}"],
        })
        return scored

    rr1 = f"1:{round(tp1_pips / sl_pips, 1)}"
    rr2 = f"1:{round(tp2_pips / sl_pips, 1)}"

    # ── STEP 9: SESSION CONFIDENCE ───────────────────────────────────────────
    try:
        from filters.killzones import get_killzone_context
        kz    = get_killzone_context("XAU_USD")
        in_kz = kz.get("in_killzone", True)
    except Exception:
        in_kz = True

    # Outside killzone = reduce confidence, do NOT block
    if not in_kz and scored.get("grade") == "A+":
        scored["grade"]        = "A"
        scored["grade_meaning"] = scored.get("grade_meaning", "") + " | Outside killzone — reduced confidence"

    # ── GOLD MOMENTUM ENTRY RELAXATION ───────────────────────────────────────
    # When strong_gold_momentum: don't require deep retracement.
    # Allow entry on continuation candle or micro/shallow pullback.
    # Still requires structure alignment — random entries not allowed.

    entry_style = "standard"

    if strong_gold_momentum:
        is_continuation = phase in ("trending",)
        is_shallow_pb   = phase == "pullback" and structure.get("pullback_depth", 1.0) <= 0.40

        if is_continuation:
            # ── CONTINUATION CANDLE QUALITY CHECK ────────────────────────────
            # Two conditions must hold before allowing immediate entry:
            #   1. good_candle  — close in top 30% of range (buy) / bottom 30% (sell)
            #   2. not_too_far  — price is within ATR*1.5 of the nearest key level
            #      (prevents chasing a move that's already run too far from structure)

            # Candle quality from M15 breakout data (most recent strong candle)
            _boc_high  = bo.get("candle_high",  0)
            _boc_low   = bo.get("candle_low",   0)
            _boc_close = bo.get("candle_close", 0)
            _boc_range = _boc_high - _boc_low
            if _boc_range > 0:
                _close_pct  = (_boc_close - _boc_low) / _boc_range
                good_candle = _close_pct >= 0.70 if direction == "bullish" else _close_pct <= 0.30
            else:
                _close_pct  = None
                good_candle = False  # no candle data → don't allow continuation blindly

            # Distance from nearest key level (zone or swing)
            _nearest_dist = float("inf")
            for z in gold_zones:
                _nearest_dist = min(_nearest_dist, abs(price - (z["high"] + z["low"]) / 2))
            if last_high: _nearest_dist = min(_nearest_dist, abs(price - last_high))
            if last_low:  _nearest_dist = min(_nearest_dist, abs(price - last_low))
            not_too_far = _nearest_dist <= atr * 1.5

            _close_pct_str = f"{round(_close_pct * 100)}%" if _close_pct is not None else "n/a"

            if good_candle and not_too_far:
                entry_style = "momentum_continuation"
                scored["flags"] = scored.get("flags", []) + [
                    f"⚡ GOLD MOMENTUM — continuation entry allowed "
                    f"(close {_close_pct_str}, {round(_nearest_dist / atr, 1)}×ATR from level)"
                ]
            elif not good_candle:
                entry_style = "momentum_wait"
                scored["flags"] = scored.get("flags", []) + [
                    f"⚠️ GOLD MOMENTUM — weak close ({_close_pct_str}), wait for better candle"
                ]
            else:  # not_too_far failed
                entry_style = "momentum_downgrade"
                scored["flags"] = scored.get("flags", []) + [
                    f"⚠️ GOLD MOMENTUM — too far from level ({round(_nearest_dist/atr,1)}×ATR > 1.5), downgraded"
                ]
        elif is_shallow_pb:
            entry_style = "momentum_shallow_pullback"
            scored["flags"] = scored.get("flags", []) + [
                f"⚡ GOLD MOMENTUM — shallow pullback entry allowed "
                f"(depth {round(structure.get('pullback_depth', 0)*100)}%, M5 aligned)"
            ]
        else:
            entry_style = "momentum_wait"
            logger.info(f"XAU_USD | strong momentum but phase={phase} depth={structure.get('pullback_depth',0):.2f} — standard rules apply")
    else:
        # No strong momentum — check if pullback is deep enough for standard entry
        pb_depth = structure.get("pullback_depth", 0)
        if phase == "pullback" and pb_depth > 0.40:
            entry_style = "standard_pullback"
        elif phase == "trending":
            entry_style = "standard_continuation"

    scored["entry_style"] = entry_style

    # ── STEP 10: OUTPUT ───────────────────────────────────────────────────────
    logger.info(
        f"XAU_USD | GOLD PASS | {direction} | zone={zone_type} | "
        f"trend={long_trend} ({trend_strength}) | "
        f"SL={round(sl,2)} [{sl_anchor}] | TP1={round(tp1,2)} [{tp1_label}] | "
        f"RR={rr1} | momentum={momentum}"
    )

    # ── WRITE BACK ────────────────────────────────────────────────────────────
    scored["dl_blocked"]      = False
    scored["dl_block_reason"] = ""
    scored["gold_mode"]       = True
    scored["gold_zone_type"]  = zone_type
    scored["gold_trend"]      = {
        "long":     long_trend,
        "phase":    phase,
        "strength": trend_strength,
        "agree":    trend_agree,
    }
    scored["gold_momentum"]    = momentum
    scored["decision_context"] = {
        "gold_mode":          True,
        "entry_style":        entry_style,
        "strong_momentum":    strong_gold_momentum,
        "momentum_mode":      momentum_mode,
        "trend_agree":        trend_agree,
        "m5_aligned":         m5_aligned,
        "candle_expansion":   candle_expand,
        "not_choppy":         not_choppy_gold,
    }
    scored["trade_levels"]  = {
        "entry_price": round(price, 2),
        "sl_price":    round(sl,    2),
        "tp1_price":   round(tp1,   2),
        "tp2_price":   round(tp2,   2),
        "sl_pips":     sl_pips,
        "tp1_pips":    tp1_pips,
        "tp2_pips":    tp2_pips,
        "rr1":         rr1,
        "rr2":         rr2,
    }
    scored["should_alert"] = True
    scored["should_log"]   = True
    if scored.get("grade") == "C":
        scored["grade_meaning"] = "VALID SETUP (gold) — passes structure + RR"

    # ── SANITY CHECK — warn only, never block ────────────────────────────────
    _gold_sanity_check(
        scored      = scored,
        confluence  = confluence,
        price       = price,
        direction   = direction,
        sl          = sl,
        tp1         = tp1,
        sl_dist     = sl_dist,
        atr         = atr,
        long_trend  = long_trend,
        short_trend = short_trend,
        trend_strength = trend_strength,
        zone_type   = zone_type,
    )

    return scored


def _gold_sanity_check(
    scored:         dict,
    confluence:     dict,
    price:          float,
    direction:      str,
    sl:             float,
    tp1:            float,
    sl_dist:        float,
    atr:            float,
    long_trend:     str,
    short_trend:    str,
    trend_strength: str,
    zone_type:      str,
) -> None:
    """
    Post-TP/SL sanity check for XAU_USD.
    Prints trader-style warnings. Does NOT modify scored or block anything.
    """
    warnings = []

    h1       = confluence.get("h1", {})
    m5       = confluence.get("m5", {})
    ict      = confluence.get("ict", {}) or {}
    structure = h1.get("structure", {})

    last_high = structure.get("last_high", 0)
    last_low  = structure.get("last_low",  0)
    strength  = structure.get("strength",  1)
    phase     = structure.get("phase", "ranging")

    # 1. TP unrealistically far vs recent structure range
    if last_high and last_low and atr > 0:
        structure_range = last_high - last_low
        tp_dist = abs(tp1 - price)
        if structure_range > 0 and tp_dist > structure_range * 1.5:
            warnings.append("target may be unrealistic — TP beyond 1.5× current structure range")

    # 2. Move already happened — late entry
    # If price already displaced more than 2× SL distance from recent swing,
    # the bulk of the move may be done.
    if direction == "bullish" and last_low and last_low > 0:
        move_already = price - last_low
        if sl_dist > 0 and move_already > sl_dist * 4:
            warnings.append("late entry — large move already occurred, consider waiting for pullback")
    elif direction == "bearish" and last_high and last_high > 0:
        move_already = last_high - price
        if sl_dist > 0 and move_already > sl_dist * 4:
            warnings.append("late entry — large move already occurred, consider waiting for pullback")

    # 3. Price in middle of range — no clear directional edge
    if last_high and last_low and (last_high - last_low) > 0:
        range_pct = (price - last_low) / (last_high - last_low)
        if 0.40 <= range_pct <= 0.60 and zone_type not in ("breakout", "breakout_preparation"):
            warnings.append("no clear direction — price mid-range (40–60%), low probability setup")

    # 4. Weak or transitioning trend
    if trend_strength == "pullback / transition":
        if long_trend != short_trend:
            warnings.append(
                f"uncertain bias — H1 long={long_trend} vs short={short_trend} "
                f"(transition in progress)"
            )
        elif strength <= 1 or phase in ("ranging", "deep_pullback"):
            warnings.append("uncertain bias — weak/ranging structure, wait for clearer trend")

    # 5. Multiple conflicting signals
    conflict_count = 0
    direction_val  = scored.get("direction", "none")

    if scored.get("against_h1_trend"):
        conflict_count += 1
    if h1.get("zone_conflict"):
        conflict_count += 1
    sweep = ict.get("recent_sweep", {})
    if sweep and sweep.get("bias") and sweep.get("bias") != direction_val:
        conflict_count += 1
    if scored.get("ict_conflict"):
        conflict_count += 1

    if conflict_count >= 2:
        warnings.append(f"conflicting signals — {conflict_count} mismatches (trend/zone/sweep/ICT)")

    # Store warnings for dashboard/slack to pick up
    scored["gold_warnings"] = warnings if warnings else []


# ── MAIN ENTRY POINT ────────────────────────────────────────────────────────

def apply_decision_layer(scored: dict, confluence: dict, pair: str) -> dict:
    """
    Apply hard filters and TP/SL override to a scored signal.
    Called after score_signal(), before logging/output.
    """
    # ── GOLD: separate logic, no shared filters ──────────────────────────────
    if pair == "XAU_USD":
        return _apply_gold_mode(scored, confluence)

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
    htf_low  = structure.get("last_low", 0)
    atr      = _atr_estimate(htf_high, htf_low)

    strong_momentum = _has_strong_momentum(confluence)

    block_reason = None

    # ── HARD BLOCKS ─────────────────────────────────────────────────────────

    if not strong_momentum and is_mid_range(price, htf_high, htf_low, structure):
        block_reason = "Blocked: mid range — price 40–60% with weak structure, no institutional bias"

    elif not strong_momentum and is_near_htf_zone(price, all_zones, direction, pair, atr):
        block_reason = "Blocked: HTF zone — strong opposing zone within ATR*0.5, no room to run"

    elif not is_pb and has_timeframe_conflict(h1_bias, m15_bias, m5_bias):
        block_reason = "Blocked: conflict — H1/M15/M5 biases not aligned"

    elif is_choppy(structure):
        block_reason = "Blocked: choppy — weak structure (quality C or ranging, strength 1)"

    elif has_too_many_conflicts(scored, confluence):
        block_reason = "Blocked: conflicts — 2+ signal mismatches (trend + zone + sweep)"

    # ── APPLY BLOCK ─────────────────────────────────────────────────────────

    if block_reason:
        logger.info(f"{pair} | DL BLOCK | {block_reason}")
        scored["dl_blocked"]      = True
        scored["dl_block_reason"] = block_reason
        scored["should_alert"]    = False
        scored["should_log"]      = False
        scored["grade"]           = "C"
        scored["flags"]           = scored.get("flags", []) + [f"🚫 {block_reason}"]
        return scored

    # ── TP/SL OVERRIDE ──────────────────────────────────────────────────────

    scored["dl_blocked"]      = False
    scored["dl_block_reason"] = ""

    entry          = price
    sl, sl_anchor  = get_stop_loss(entry, confluence, direction, pair)
    tp1, tp2, tp1_label = get_take_profit(entry, sl, confluence, direction, pair, atr)

    if sl and tp1 and tp2:
        pip      = pip_size(pair)
        sl_dist  = abs(entry - sl)
        sl_pips  = round(sl_dist / pip, 1)
        tp1_pips = round(abs(tp1 - entry) / pip, 1)
        tp2_pips = round(abs(tp2 - entry) / pip, 1)

        # ── RR VALIDATION — hard block if RR < 1:1 ──────────────────────
        if sl_pips > 0 and tp1_pips < sl_pips:
            rr_block = f"Blocked: RR < 1 — TP1={tp1_pips}p vs SL={sl_pips}p, not worth it"
            logger.info(f"{pair} | DL BLOCK | {rr_block}")
            scored["dl_blocked"]      = True
            scored["dl_block_reason"] = rr_block
            scored["should_alert"]    = False
            scored["should_log"]      = False
            scored["grade"]           = "C"
            scored["flags"]           = scored.get("flags", []) + [f"🚫 {rr_block}"]
            return scored

        rr1      = f"1:{round(tp1_pips / sl_pips, 1)}" if sl_pips > 0 else "1:?"
        rr2      = f"1:{round(tp2_pips / sl_pips, 1)}" if sl_pips > 0 else "1:?"
        decimals = 3 if "JPY" in pair else (2 if pair == "XAU_USD" else (3 if pair == "XAG_USD" else 5))

        scored["trade_levels"] = {
            "entry_price": round(entry, decimals),
            "sl_price":    round(sl,    decimals),
            "tp1_price":   round(tp1,   decimals),
            "tp2_price":   round(tp2,   decimals),
            "sl_pips":     sl_pips,
            "tp1_pips":    tp1_pips,
            "tp2_pips":    tp2_pips,
            "rr1":         rr1,
            "rr2":         rr2,
        }
        logger.info(f"{pair} | DL TP/SL | SL={round(sl, decimals)} [{sl_anchor}] TP1={round(tp1, decimals)} [{tp1_label}] RR={rr1}")

    # ── DECISION PRIORITY OVERRIDE ───────────────────────────────────────────
    # Score does NOT block trades. After passing all hard filters + RR check,
    # a structurally valid setup is allowed regardless of grade.
    # Priority: 1) decision layer  2) RR  3) setup validity  4) score (info only)

    _VALID_SETUP_TYPES = {
        "pullback_long", "pullback_short",
        "breakout_bull", "breakout_bear", "breakout_retest",
        "reversal_bull", "reversal_bear",
        "trend_follow", "sr_flip", "zone_tap",
    }

    trade_levels  = scored.get("trade_levels", {})
    rr1_val       = 0.0
    if trade_levels.get("sl_pips", 0) > 0:
        rr1_val = trade_levels.get("tp1_pips", 0) / trade_levels["sl_pips"]

    setup_type    = scored.get("setup_type", "unknown")
    valid_rr      = rr1_val >= 1.5
    valid_setup   = setup_type in _VALID_SETUP_TYPES
    valid_struct  = structure.get("setup_quality") in ("A+", "A", "B") or structure.get("strength", 0) >= 2
    news_safe     = scored.get("news_check", {}).get("safe", True)

    if valid_rr and valid_setup and valid_struct and news_safe:
        scored["should_alert"] = True
        scored["should_log"]   = True
        # Replace "SKIP" grade meaning for low-score setups that pass DL
        if scored.get("grade") == "C":
            scored["grade_meaning"] = "VALID SETUP — lower confidence, passes structure + RR check"
        logger.info(f"{pair} | DL PASS | grade={scored.get('grade')} score={scored.get('score')} RR={round(rr1_val,1)} setup={setup_type}")
    else:
        reasons = []
        if not valid_rr:     reasons.append(f"RR={round(rr1_val,1)}<1.5")
        if not valid_setup:  reasons.append(f"setup={setup_type}")
        if not valid_struct: reasons.append(f"structure={structure.get('setup_quality','?')}")
        if not news_safe:    reasons.append("news block")
        logger.info(f"{pair} | DL NO PASS | {', '.join(reasons)}")

    # ════════════════════════════════════════════════════════════════════════
    # CONFIRMED ENTRY PATH
    # ── Handled above in "DECISION PRIORITY OVERRIDE" section ──────────────
    # Fires when: valid_rr + valid_setup + valid_struct + news_safe
    # Sets: should_alert=True, should_log=True (grade unchanged)
    # ════════════════════════════════════════════════════════════════════════

    # ════════════════════════════════════════════════════════════════════════
    # EARLY ENTRY PATH — independent, add-on only
    # Does NOT require M5 confirmation.
    # Does NOT touch confirmed entry logic above.
    # Does NOT change grade.
    # Only sets: scored["early_entry"], scored["entry_type"]
    # ════════════════════════════════════════════════════════════════════════

    _early_entry = False  # default — always written to scored at end

    # Safety: never fire early entry if hard blocked
    if not scored.get("dl_blocked"):

        # ── Conflict check (early entry path only) ───────────────────────
        no_strong_conflict = (
            not scored.get("ict_conflict", False)
            and not scored.get("pattern_conflict", False)
            and not scored.get("against_h1_trend", False)
        )

        # ── TF alignment: H1 required + M15 OR M5 ───────────────────────
        _ep_h1_bias  = h1.get("bias", "neutral")
        _ep_m15_bias = m15.get("bias", "neutral")
        _ep_m5_bias  = m5.get("bias", "neutral")
        tfs_aligned = (
            _ep_h1_bias == direction and
            (_ep_m15_bias == direction or _ep_m5_bias == direction)
        )

        # ── Structure: only block pure chop (ranging + strength 1) ──────
        _sq        = structure.get("setup_quality", "C")
        _strength  = structure.get("strength", 1)
        _phase     = structure.get("phase", "ranging")
        _trend     = structure.get("trend", "ranging")
        not_choppy = not (_trend == "ranging" and _strength == 1 and _phase == "ranging")

        # ── Location: block only truly extreme (>85% / <15%) ────────────
        _pd          = confluence.get("ict", {}).get("premium_discount", {})
        _pd_zone     = _pd.get("zone", "")
        _pd_pct      = _pd.get("pct", 0.5)
        _extreme_loc = (
            (_pd_zone == "premium"  and direction == "bullish" and _pd_pct >= 0.85) or
            (_pd_zone == "discount" and direction == "bearish" and _pd_pct <= 0.15)
        )
        _near_zone  = bool(h1.get("active_zones"))
        ok_location = _near_zone or (not _extreme_loc)  # near zone always wins

        # ── Pressure/momentum: detect building pressure, NOT confirmed ──
        # expansion_candle + consecutive are OPTIONAL, not required
        _bo_data          = confluence.get("breakout", {})
        _expansion_candle = _has_strong_momentum(confluence)                       # optional
        _hh_ll_forming    = (                                                      # real directional move only
            _phase in ("trending", "structure_break")
            and _strength >= 2
            and _trend != "ranging"
        )
        _consecutive      = _bo_data.get("consecutive", 0) >= 2                   # optional
        _soft_signals     = sum([
            _ep_m15_bias == direction,
            _ep_m5_bias  == direction,
            _strength >= 2,                                                        # strength 1 no longer counts
        ])
        has_momentum = _hh_ll_forming or (_soft_signals >= 2)

        # ── Final early pressure condition ───────────────────────────────
        # H1 is mandatory. Lower TF OR momentum is sufficient (not both required).
        _h1_match  = (_ep_h1_bias == direction)
        _ltf_or_mo = (_ep_m15_bias == direction or _ep_m5_bias == direction or has_momentum)
        early_pressure = (
            _h1_match
            and _ltf_or_mo
            and ok_location
            and no_strong_conflict
            and not_choppy
            and news_safe
        )

        # ── Fire early entry ─────────────────────────────────────────────
        if early_pressure:
            _early_entry = True
            scored["should_alert"] = True
            scored["should_log"]   = True
            scored["flags"] = scored.get("flags", []) + [
                f"⚡ EARLY ENTRY — pressure building {direction} | "
                f"TFs aligned, structure:{_sq}/{_strength}, location:{'✅' if ok_location else '⚠️'} | Risk: HIGH"
            ]
            logger.info(
                f"{pair} | EARLY ENTRY | grade={scored.get('grade')} "
                f"dir={direction} tfs={tfs_aligned} loc={'ok' if ok_location else 'extreme'} "
                f"struct={_sq}/{_strength}"
            )

    # ── Always write top-level early_entry keys (confirmed or not) ───────────
    # These are read directly by app.py — never nested
    scored["early_entry"] = _early_entry
    scored["entry_type"]  = "anticipation" if _early_entry else "confirmed"

    # ── Update decision_context ───────────────────────────────────────────────
    scored["decision_context"] = scored.get("decision_context", {})
    scored["decision_context"].update({
        "early_entry":  _early_entry,
        "entry_type":   scored["entry_type"],
        "risk_level":   "high" if _early_entry else "normal",
        "note":         "early entry — confirmation pending" if _early_entry else "",
    })

    return scored
