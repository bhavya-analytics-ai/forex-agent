"""
strategies/om_gold_scalp.py — OM Gold Scalp strategy (XAU_USD only)

Runs in parallel with legacy gold and legacy forex strategies.
Self-contained — no shared code with other strategy files.
Only shared imports: logging, config, and candle math defined below.

Architecture:
  1H  → zone map + bias layer (htf_range, htf_magnet, zone_state)
  15M → setup location + context (decision_zone, setup classification)
  5M  → trigger + execution (entry_state, trade levels, audit fields)

State machine (progressive, per scan cycle):
  SKIP_CHOP           — inside HTF range or chop
  WAIT_REACTION       — boundary event or sweep printing
  WAIT_RECLAIM        — price below/above S/R, push back expected
  WAIT_HOLD           — reclaim body close printed, waiting for hold bar
  ENTER_LONG_ALLOWED  / ENTER_SHORT_ALLOWED → entry_state = ENTER_NOW
  SKIP_CHASE          — direction correct but entry too far from zone

v1 setup categories (5 of 10):
  sweep_reclaim_long              — sweep + reclaim + bullish displacement
  sweep_reclaim_short             — mirror short
  failed_reclaim_continuation     — reclaim fails → continuation
  range_breakdown_bearish         — range low breaks + retest holds + follow-through
  range_fake_breakout_no_trade    — breakout returns inside → block both directions

Thresholds (all configurable via OM_SCALP_* env vars in future):
  max_sl_pts          = 20    SL > 20 pts → SKIP sl_too_wide
  sl_buffer_pts       = 2     sweep extreme + 2 pts
  max_chase_pts       = 25    entry > 25 pts from zone → SKIP_CHASE
  tp1_min_pts         = 15
  tp1_max_pts         = 25
  min_rr              = 1.5
  sweep_min_wick_pts  = 1.5   minimum wick beyond level to count as sweep
  sweep_max_bars_ago  = 20    sweep must be within last 20 M5 bars
  displace_min_mult   = 1.5   displacement body >= 1.5× average body
"""

import logging
from config import OM_GOLD_SCALP_ENABLED

logger = logging.getLogger(__name__)

# ── STRATEGY METADATA ─────────────────────────────────────────────────────────
STRATEGY_META = {
    "signal_mode":          "om_gold_scalp",
    "allowed_symbols":      {"XAU_USD"},
    "required_timeframes":  ["H1", "M15", "M5"],
    "can_run_watch_only":   True,
    "can_emit_live_signal": True,   # runtime gate: OM_GOLD_SCALP_ENABLED in config
}
# ─────────────────────────────────────────────────────────────────────────────

# ── THRESHOLDS ────────────────────────────────────────────────────────────────
MAX_SL_PTS         = 20.0
SL_BUFFER_PTS      = 2.0
MAX_CHASE_PTS      = 25.0
TP1_MIN_PTS        = 15.0
TP1_MAX_PTS        = 25.0
MIN_RR             = 1.5
SWEEP_MIN_WICK_PTS = 1.5
SWEEP_MAX_BARS_AGO = 20
DISPLACE_MIN_MULT  = 1.5
RANGE_FLAT_THRESH      = 8.0    # H1 range < this → htf_range_active candidate
MIN_MOMENTUM_REQUIRED  = 50.0   # momentum_score must reach this before ENTER_NOW is allowed
# ─────────────────────────────────────────────────────────────────────────────


# ── CANDLE HELPERS ────────────────────────────────────────────────────────────

def _body(c):
    return abs(c["close"] - c["open"])


def _range(c):
    return c["high"] - c["low"]


def _avg_body(candles, n=10):
    recent = candles[-n:] if len(candles) >= n else candles
    bodies = [_body(c) for c in recent]
    return sum(bodies) / len(bodies) if bodies else 0.01


def _is_bullish(c):
    return c["close"] > c["open"]


def _is_bearish(c):
    return c["close"] < c["open"]


# ── 1H ANALYSIS — zone map + bias ────────────────────────────────────────────

def _analyse_h1(h1_candles, h1_trend):
    """
    Returns:
      htf_range_active  bool
      range_boundary_high float
      range_boundary_low  float
      htf_magnet          float  (nearest opposing level)
      zone_state          str
    """
    if not h1_candles or len(h1_candles) < 10:
        return {
            "htf_range_active":    False,
            "range_boundary_high": 0.0,
            "range_boundary_low":  0.0,
            "htf_magnet":          0.0,
            "zone_state":          "unknown",
        }

    recent = h1_candles[-40:]
    highs  = [c["high"]  for c in recent]
    lows   = [c["low"]   for c in recent]
    closes = [c["close"] for c in recent]

    swing_high = max(highs)
    swing_low  = min(lows)
    price      = closes[-1]
    h_range    = swing_high - swing_low

    # HTF range detection:
    #   - "chop" trend label always → range active
    #   - Clear directional trend (bearish/bullish) → trust the label, NOT range width
    #   - Unknown/neutral trend AND small range → range active
    _directional = {
        "bullish", "bearish", "uptrend", "downtrend",
        "weak_bullish", "weak_bearish", "weak_uptrend", "weak_downtrend",
    }
    if h1_trend == "chop":
        htf_range_active = True
    elif h1_trend in _directional:
        htf_range_active = False   # trust the trend label
    else:
        htf_range_active = h_range < RANGE_FLAT_THRESH

    # Zone state
    if htf_range_active:
        zone_state = "inside_range_chop"
    elif price > swing_high - 2:
        zone_state = "rejecting_resistance"
    elif price < swing_low + 2:
        zone_state = "holding_support"
    elif h1_trend == "bearish":
        zone_state = "below_zone"
    elif h1_trend == "bullish":
        zone_state = "above_zone"
    else:
        zone_state = "decision_chop"

    return {
        "htf_range_active":    htf_range_active,
        "range_boundary_high": swing_high,
        "range_boundary_low":  swing_low,
        "htf_magnet":          swing_low if h1_trend == "bearish" else swing_high,
        "zone_state":          zone_state,
    }


# ── 5M ANALYSIS — sweep / reclaim / displacement detection ───────────────────

def _detect_sweep(m5_candles, direction="bearish"):
    """
    Detect a liquidity sweep in the last SWEEP_MAX_BARS_AGO bars.
    direction="bearish" → sweep wick goes DOWN (bearish sweep, bullish reversal setup).
    direction="bullish" → sweep wick goes UP   (bullish sweep, bearish reversal setup).

    A sweep bar:
      - wick extends beyond the PRIOR swing extreme (bars before it) by >= SWEEP_MIN_WICK_PTS
      - body closes back toward the other side by >= SWEEP_MIN_WICK_PTS

    Rolling prior approach: for each candidate bar at index i, the reference
    extreme is computed from bars[:i] only — never including the candidate itself.

    Returns dict with:
      detected        bool
      sweep_low/high  float  (the extreme wick tip)
      bars_ago        int    (1 = bar immediately before current)
    """
    _no_sweep = {
        "detected": False, "sweep_low": 0.0, "sweep_high": 0.0, "bars_ago": 999,
        "sweep_reference_level": 0.0, "sweep_distance_pts": 0.0,
    }

    if len(m5_candles) < 5:
        return _no_sweep

    # Exclude the current (last) bar — scan the prior SWEEP_MAX_BARS_AGO bars.
    window = m5_candles[-(SWEEP_MAX_BARS_AGO + 1):-1]
    n = len(window)
    if n < 2:
        return _no_sweep

    if direction == "bearish":
        # Iterate newest → oldest; for each bar compare to minimum of all bars before it.
        for i in range(n - 1, 0, -1):
            c = window[i]
            prior_swing_low = min(b["low"] for b in window[:i])
            if (c["low"] < prior_swing_low - SWEEP_MIN_WICK_PTS
                    and c["close"] > c["low"] + SWEEP_MIN_WICK_PTS):
                return {
                    "detected":              True,
                    "sweep_low":             c["low"],
                    "sweep_high":            c["high"],
                    "bars_ago":              n - i,
                    "sweep_reference_level": round(prior_swing_low, 3),
                    "sweep_distance_pts":    round(prior_swing_low - c["low"], 2),
                }
    else:  # bullish sweep
        for i in range(n - 1, 0, -1):
            c = window[i]
            prior_swing_high = max(b["high"] for b in window[:i])
            if (c["high"] > prior_swing_high + SWEEP_MIN_WICK_PTS
                    and c["close"] < c["high"] - SWEEP_MIN_WICK_PTS):
                return {
                    "detected":              True,
                    "sweep_low":             c["low"],
                    "sweep_high":            c["high"],
                    "bars_ago":              n - i,
                    "sweep_reference_level": round(prior_swing_high, 3),
                    "sweep_distance_pts":    round(c["high"] - prior_swing_high, 2),
                }

    return _no_sweep


def _detect_reclaim(m5_candles, level, direction="bullish"):
    """
    Check the last 1-3 bars for a reclaim of `level`.
    direction="bullish" → body close above level = bullish reclaim confirmed.
    direction="bearish" → body close below level = bearish reclaim (failed bullish reclaim).

    Returns:
      reclaim_confirmed  bool
      reclaim_failed     bool  (wick crossed, body closed back through)
      hold_bar           bool  (bar after reclaim holds above/below level)
    """
    _no_reclaim = {
        "reclaim_confirmed": False, "reclaim_failed": False, "hold_bar": False,
        "reclaim_distance_pts": 0.0,
    }

    if len(m5_candles) < 3:
        return _no_reclaim

    last3 = m5_candles[-3:]

    if direction == "bullish":
        reclaim_bar = next(
            (c for c in reversed(last3) if c["close"] > level),
            None
        )
        if reclaim_bar is None:
            return _no_reclaim

        idx = last3.index(reclaim_bar)
        hold_bar = idx < len(last3) - 1 and last3[idx + 1]["close"] > level
        reclaim_distance_pts = round(reclaim_bar["close"] - level, 2)
        return {
            "reclaim_confirmed":    True,
            "reclaim_failed":       False,
            "hold_bar":             hold_bar,
            "reclaim_distance_pts": reclaim_distance_pts,
        }

    else:  # bearish: wick above, body closes back below = failed reclaim
        for c in reversed(last3):
            if c["high"] > level and c["close"] < level:
                return {
                    "reclaim_confirmed":    False,
                    "reclaim_failed":       True,
                    "hold_bar":             False,
                    "reclaim_distance_pts": round(level - c["close"], 2),
                }
        return _no_reclaim


def _detect_displacement(m5_candles, direction="bullish", avg_body=None):
    """
    Displacement = last 1-2 bars contain a body >= DISPLACE_MIN_MULT × avg_body
    in the given direction.

    Returns dict:
      detected              bool
      displacement_body_pts float  (largest qualifying body, or 0.0 if none)
      avg_body_pts          float
      displacement_ratio    float  (body / avg_body, or 0.0 if none)
    """
    _no_disp = {"detected": False, "displacement_body_pts": 0.0,
                "avg_body_pts": 0.0, "displacement_ratio": 0.0}

    if not m5_candles:
        return _no_disp
    if avg_body is None:
        avg_body = _avg_body(m5_candles[:-2]) if len(m5_candles) > 2 else 1.0
    if avg_body < 0.01:
        avg_body = 0.01

    for c in reversed(m5_candles[-2:]):
        b = _body(c)
        if b >= DISPLACE_MIN_MULT * avg_body:
            if direction == "bullish" and _is_bullish(c):
                return {
                    "detected":              True,
                    "displacement_body_pts": round(b, 3),
                    "avg_body_pts":          round(avg_body, 3),
                    "displacement_ratio":    round(b / avg_body, 2),
                    "fail_reason":           "",
                }
            if direction == "bearish" and _is_bearish(c):
                return {
                    "detected":              True,
                    "displacement_body_pts": round(b, 3),
                    "avg_body_pts":          round(avg_body, 3),
                    "displacement_ratio":    round(b / avg_body, 2),
                    "fail_reason":           "",
                }

    # Not detected — surface what actually failed for audit/rejection reason.
    # max_b is the largest body in the last 2 bars (any direction) so we can
    # distinguish: body was big enough but wrong direction vs body too small.
    max_b = max((_body(c) for c in m5_candles[-2:]), default=0.0)
    ratio = round(max_b / avg_body, 2) if avg_body > 0 else 0.0
    # fail_reason: "direction_mismatch" when ratio >= threshold but bar points
    # the wrong way; "ratio_below_threshold" when body is simply too small.
    fail_reason = (
        "direction_mismatch" if ratio >= DISPLACE_MIN_MULT else "ratio_below_threshold"
    )
    return {
        "detected":              False,
        "displacement_body_pts": round(max_b, 3),
        "avg_body_pts":          round(avg_body, 3),
        "displacement_ratio":    ratio,
        "fail_reason":           fail_reason,
    }


# ── RANGE BREAKDOWN DETECTION ────────────────────────────────────────────────

def _detect_range_breakdown(m5_candles, range_low):
    """
    Path: range_low_broken → retest_held_below → follow_through → ENTER_NOW short.

    Returns dict with each gate flag.
    """
    if len(m5_candles) < 5 or range_low <= 0:
        return {
            "range_low_broken":        False,
            "range_retest_held_below": False,
            "bearish_follow_through":  False,
        }

    # Look for body close below range_low in the last 5 bars
    breakdown_idx = None
    for i, c in enumerate(m5_candles[-5:]):
        if c["close"] < range_low:
            breakdown_idx = i
            break

    if breakdown_idx is None:
        return {
            "range_low_broken":        False,
            "range_retest_held_below": False,
            "bearish_follow_through":  False,
        }

    remaining = m5_candles[-5:][breakdown_idx + 1:]
    if not remaining:
        return {
            "range_low_broken":        True,
            "range_retest_held_below": False,
            "bearish_follow_through":  False,
        }

    # Retest: a bar wicks toward range_low but body closes below
    retest_held = any(
        c["high"] >= range_low - 2 and c["close"] < range_low
        for c in remaining
    )

    # Follow-through: after retest, a bar closes lower
    follow_through = False
    if retest_held and len(remaining) >= 2:
        follow_through = remaining[-1]["close"] < remaining[0]["close"]

    return {
        "range_low_broken":        True,
        "range_retest_held_below": retest_held,
        "bearish_follow_through":  follow_through,
    }


def _detect_range_breakout(m5_candles, range_high):
    """
    Bullish mirror of _detect_range_breakdown.

    Path: range_high_broken → retest_held_above → bullish_follow_through → ENTER_NOW long.

    Looks for body close ABOVE range_high in last 5 bars, then retest bar
    wicks down toward range_high but body holds above, then follow-through
    bar closes higher.

    Returns dict with each gate flag.
    """
    if len(m5_candles) < 5 or range_high <= 0:
        return {
            "range_high_broken":       False,
            "range_retest_held_above": False,
            "bullish_follow_through":  False,
        }

    # Look for body close above range_high in the last 5 bars
    breakout_idx = None
    for i, c in enumerate(m5_candles[-5:]):
        if c["close"] > range_high:
            breakout_idx = i
            break

    if breakout_idx is None:
        return {
            "range_high_broken":       False,
            "range_retest_held_above": False,
            "bullish_follow_through":  False,
        }

    remaining = m5_candles[-5:][breakout_idx + 1:]
    if not remaining:
        return {
            "range_high_broken":       True,
            "range_retest_held_above": False,
            "bullish_follow_through":  False,
        }

    # Retest: a bar wicks toward range_high but body closes above
    retest_held = any(
        c["low"] <= range_high + 2 and c["close"] > range_high
        for c in remaining
    )

    # Follow-through: after retest, a bar closes higher
    follow_through = False
    if retest_held and len(remaining) >= 2:
        follow_through = remaining[-1]["close"] > remaining[0]["close"]

    return {
        "range_high_broken":       True,
        "range_retest_held_above": retest_held,
        "bullish_follow_through":  follow_through,
    }


def _detect_fake_breakout(m5_candles, range_high):
    """
    Fake breakout: body closes above range_high, then body closes back below range_high
    within 1-2 bars.
    """
    if len(m5_candles) < 4 or range_high <= 0:
        return False

    last4 = m5_candles[-4:]
    for i, c in enumerate(last4[:-1]):
        if c["close"] > range_high:
            # Check if any subsequent bar reclaims back below
            for c2 in last4[i + 1:]:
                if c2["close"] < range_high:
                    return True
    return False


# ── TRADE LEVEL CALCULATION ──────────────────────────────────────────────────

def _calc_trade_levels(entry_price, sl_extreme, direction, htf_magnet=0.0):
    """
    SL  = sl_extreme + SL_BUFFER_PTS (on the far side of the sweep)
    TP1 = entry + TP1_MIN_PTS (target TP1_MIN → TP1_MAX, capped by htf_magnet if reasonable)
    TP2 = entry + TP1_MAX_PTS (or htf_magnet if within range)

    Returns None if SL > MAX_SL_PTS.
    All values in price points (XAU_USD pts = 1.0 = $1).
    """
    if direction == "bullish":
        sl_price = sl_extreme - SL_BUFFER_PTS
        sl_pts   = entry_price - sl_price
        tp1_price = entry_price + max(TP1_MIN_PTS, sl_pts * MIN_RR)
        tp1_price = min(tp1_price, entry_price + TP1_MAX_PTS)
        tp2_price = entry_price + TP1_MAX_PTS
    else:
        sl_price = sl_extreme + SL_BUFFER_PTS
        sl_pts   = sl_price - entry_price
        tp1_price = entry_price - max(TP1_MIN_PTS, sl_pts * MIN_RR)
        tp1_price = max(tp1_price, entry_price - TP1_MAX_PTS)
        tp2_price = entry_price - TP1_MAX_PTS

    if sl_pts > MAX_SL_PTS:
        return None  # caller treats as sl_too_wide; use _compute_sl_raw to surface values

    tp1_pts = abs(tp1_price - entry_price)
    sl_pips = round(sl_pts * 100)   # 1 pt = 100 pips for XAU (pip_size 0.01)
    tp1_pips = round(tp1_pts * 100)
    rr = round(tp1_pts / sl_pts, 2) if sl_pts > 0 else 0.0

    return {
        "entry_price": round(entry_price, 3),
        "sl_price":    round(sl_price, 3),
        "tp1_price":   round(tp1_price, 3),
        "tp2_price":   round(tp2_price, 3),
        "sl_pips":     sl_pips,
        "tp1_pips":    tp1_pips,
        "sl_pts":      round(sl_pts, 2),
        "tp1_pts":     round(tp1_pts, 2),
        "rr":          rr,
    }


# ── RAW SL COMPUTATION (no gate) ─────────────────────────────────────────────

def _compute_sl_raw(entry_price: float, sl_extreme: float, direction: str):
    """
    Compute sl_price and sl_pts using the same formula as _calc_trade_levels
    but WITHOUT the MAX_SL_PTS gate.

    Used exclusively at sl_too_wide rejection sites so the output dict always
    carries numeric sl_price_candidate and sl_pts even when SL is rejected.
    This is debug/audit only — does NOT change any entry decision.

    Returns: (sl_price: float, sl_pts: float)  — both rounded, sl_pts >= 0.
    """
    if direction == "bullish":
        sl_price = sl_extreme - SL_BUFFER_PTS
        sl_pts   = entry_price - sl_price
    else:
        sl_price = sl_extreme + SL_BUFFER_PTS
        sl_pts   = sl_price - entry_price
    return round(sl_price, 3), round(max(0.0, sl_pts), 2)


# ── MOMENTUM SCORE ────────────────────────────────────────────────────────────

def _momentum_score(m5_candles, direction, confluence):
    """
    0–100 score. Four components (PROPOSED weights from spec):
      M5 pressure (trend alignment): 35 pts
      Displacement strength:         25 pts
      M15 alignment:                 25 pts
      Unused (future M1):            15 pts  → defaulted to 7 (partial)
    """
    score = 0
    m5_trend  = confluence.get("m5",  {}).get("structure", {}).get("trend", "")
    m15_trend = confluence.get("m15", {}).get("structure", {}).get("trend", "")

    # M5 pressure
    if direction == "bullish" and m5_trend in ("uptrend", "bullish"):
        score += 35
    elif direction == "bearish" and m5_trend in ("downtrend", "bearish"):
        score += 35
    elif m5_trend in ("weak_uptrend", "weak_bullish") and direction == "bullish":
        score += 20
    elif m5_trend in ("weak_downtrend", "weak_bearish") and direction == "bearish":
        score += 20

    # Displacement strength
    avg = _avg_body(m5_candles)
    last2 = m5_candles[-2:] if len(m5_candles) >= 2 else m5_candles
    max_body = max((_body(c) for c in last2), default=0)
    if avg > 0:
        ratio = max_body / avg
        if ratio >= 3.0:
            score += 25
        elif ratio >= 2.0:
            score += 18
        elif ratio >= 1.5:
            score += 10

    # M15 alignment
    if direction == "bullish" and m15_trend in ("uptrend", "bullish"):
        score += 25
    elif direction == "bearish" and m15_trend in ("downtrend", "bearish"):
        score += 25
    elif m15_trend in ("weak_uptrend", "weak_bullish") and direction == "bullish":
        score += 12
    elif m15_trend in ("weak_downtrend", "weak_bearish") and direction == "bearish":
        score += 12

    # Partial M1 placeholder
    score += 7

    return min(100, max(0, score))


# ── EMPTY AUDIT TEMPLATE ─────────────────────────────────────────────────────

def _base_audit():
    """Return an audit dict with all required fields set to safe defaults."""
    return {
        # Identity
        "signal_mode":    "om_gold_scalp",
        "setup_type":     "no_setup",
        "direction":      "",
        "entry_state":    "SKIP",
        "entry_allowed":  False,
        "should_log":     False,
        "should_alert":   False,
        "skip_reason":    "no_setup",
        # Context trends (from confluence, set in run())
        "h1_trend":       "",
        "m15_trend":      "",
        "m5_trend":       "",
        # Branch evaluation tracking
        "evaluated_branches":     [],
        "active_branch":          "",
        "rejection_stage":        "",
        "rejection_reason":       "",
        "setup_candidates_found": 0,
        # Zone / range
        "htf_range_active":     False,
        "range_boundary_high":  0.0,
        "range_boundary_low":   0.0,
        "no_trade_zone":        False,
        "inside_range_chop":    False,
        "zone_state":           "unknown",
        # Sweep (summary)
        "sweep_detected":       False,
        "sweep_candidate":      False,   # kept for back-compat
        "double_sweep":         False,
        "swept_side":           "",
        "sweep_alone_no_entry": False,
        # Sweep (detail)
        "sweep_low":             0.0,
        "sweep_high":            0.0,
        "sweep_bars_ago":        999,
        "sweep_reference_level": 0.0,
        "sweep_distance_pts":    0.0,
        # Reclaim (summary)
        "reclaim_candidate":    False,
        "reclaim_confirmed":    False,
        "reclaim_failed":       False,
        "reclaim_direction":    "",
        # Reclaim (detail)
        "reclaim_level":        0.0,
        "hold_bar":             False,
        "reclaim_distance_pts": 0.0,
        # Displacement (summary)
        "bullish_displacement": False,
        "bearish_displacement_after_failed_reclaim": False,
        "follow_through_confirmed":                  False,
        # Displacement (detail)
        "displacement_body_pts": 0.0,
        "avg_body_pts":          0.0,
        "displacement_ratio":    0.0,
        # Range breakdown (bearish)
        "range_low_broken":        False,
        "range_retest_held_below": False,
        "bearish_follow_through":  False,
        # Range breakout (bullish)
        "range_high_broken":       False,
        "range_retest_held_above": False,
        "bullish_follow_through":  False,
        # Fake breakout
        "breakout_failed":             False,
        "reclaim_back_inside_range":   False,
        "avoid_long_reason":           "",
        "avoid_short_reason":          "",
        # Entry quality
        "entry_quality":         "low",
        "momentum_score":        0,
        "min_momentum_required": MIN_MOMENTUM_REQUIRED,
        "momentum_gate_passed":  False,
        "scanner_state_flow":    "init",
        # Entry / SL candidates (populated when evaluated, even if SKIP)
        "entry_price_candidate": None,
        "sl_anchor":             None,
        "sl_price_candidate":    None,
        "sl_gate_passed":        False,
        "max_sl_pts":            MAX_SL_PTS,
        # Trade levels (populated on ENTER_NOW only)
        "entry_price": None,
        "sl_price":    None,
        "tp1_price":   None,
        "tp2_price":   None,
        "sl_pips":     0,
        "tp1_pips":    0,
        "sl_pts":      0.0,
        "tp1_pts":     0.0,
        "rr":          0.0,
    }


# ── MAIN ENTRY POINT ─────────────────────────────────────────────────────────

def run(scored: dict, confluence: dict, pair: str, candles: dict) -> dict:
    """
    Full OM Gold Scalp scan for one pair.

    Returns a scored dict with all audit fields + entry_state.
    Never raises — all errors return SKIP with skip_reason="internal_error".

    Watch-only gate: if OM_GOLD_SCALP_ENABLED=false, should_log and
    should_alert are forced False regardless of entry_state.
    """
    out = _base_audit()
    out.update({k: v for k, v in scored.items() if k not in out})

    try:
        # ── PAIR GUARD ────────────────────────────────────────────────────────
        if pair not in STRATEGY_META["allowed_symbols"]:
            out["entry_state"]        = "SKIP"
            out["skip_reason"]        = "pair_not_supported"
            out["rejection_stage"]    = "pair_guard"
            out["rejection_reason"]   = f"{pair} not in allowed_symbols"
            out["scanner_state_flow"] = f"pair_guard: {pair} not in allowed_symbols"
            _apply_watch_only_gate(out)
            return out

        # ── EXTRACT CANDLES ───────────────────────────────────────────────────
        h1_candles  = confluence.get("h1",  {}).get("candles") or candles.get("H1",  [])
        m15_candles = confluence.get("m15", {}).get("candles") or candles.get("M15", [])
        m5_candles  = confluence.get("m5",  {}).get("candles") or candles.get("M5",  [])
        h1_trend    = confluence.get("h1",  {}).get("structure", {}).get("trend", "chop")
        m15_trend   = confluence.get("m15", {}).get("structure", {}).get("trend", "")
        m5_trend    = confluence.get("m5",  {}).get("structure", {}).get("trend", "")

        # Expose trend context in output (for debug/dashboard visibility)
        out["h1_trend"]  = h1_trend
        out["m15_trend"] = m15_trend
        out["m5_trend"]  = m5_trend

        # ── 1H ANALYSIS ───────────────────────────────────────────────────────
        h1 = _analyse_h1(h1_candles, h1_trend)
        out.update(h1)

        # ── GATE 1: HTF range chop ────────────────────────────────────────────
        _branches = []
        if h1["htf_range_active"]:
            _branches.append("htf_range")
            out["evaluated_branches"]     = _branches
            out["active_branch"]          = "htf_range"
            out["setup_candidates_found"] = 1
            range_high = h1["range_boundary_high"]
            range_low  = h1["range_boundary_low"]
            out["inside_range_chop"] = True
            out["no_trade_zone"]     = True

            # Check for fake breakout first
            if _detect_fake_breakout(m5_candles, range_high):
                out["breakout_failed"]           = True
                out["reclaim_back_inside_range"] = True
                out["entry_state"]               = "SKIP_INSIDE_RANGE"
                out["skip_reason"]               = "fake_breakout_no_trade"
                out["avoid_long_reason"]         = "failed_breakout_back_inside_range"
                out["avoid_short_reason"]        = "still_inside_range_until_low_break_hold"
                out["setup_type"]                = "range_fake_breakout_no_trade"
                out["scanner_state_flow"]        = "range_active → fake_breakout_detected → SKIP_INSIDE_RANGE"
                out["rejection_stage"]           = "fake_breakout_check"
                out["rejection_reason"]          = "fake_breakout_no_trade"
                _apply_watch_only_gate(out)
                return out

            # Check for range breakdown (bearish)
            bd = _detect_range_breakdown(m5_candles, range_low)
            out.update(bd)
            if bd["range_low_broken"] and bd["range_retest_held_below"] and bd["bearish_follow_through"]:
                # Valid breakdown — proceed to entry
                entry_price = m5_candles[-1]["close"] if m5_candles else 0.0
                sl_extreme  = range_low + 1.0  # retest resistance level
                # Record entry/SL candidates for debug visibility
                out["entry_price_candidate"] = round(entry_price, 3)
                out["sl_anchor"]             = round(sl_extreme, 3)
                levels = _calc_trade_levels(entry_price, sl_extreme, "bearish",
                                            htf_magnet=h1["htf_magnet"])
                if levels is not None:
                    out["sl_price_candidate"] = levels["sl_price"]
                if levels is None:
                    _raw_sl_price, _raw_sl_pts = _compute_sl_raw(entry_price, sl_extreme, "bearish")
                    out["sl_price_candidate"] = _raw_sl_price
                    out["sl_pts"]             = _raw_sl_pts
                    out["sl_gate_passed"]     = False
                    out["rejection_stage"]    = "sl_check"
                    out["rejection_reason"]   = f"sl_pts={_raw_sl_pts} > max={MAX_SL_PTS}"
                    out["skip_reason"]        = "sl_too_wide"
                    out["scanner_state_flow"] = "range_breakdown → sl_too_wide"
                    _apply_watch_only_gate(out)
                    return out
                out["sl_gate_passed"] = True

                entry_dist = abs(entry_price - range_low)
                if entry_dist > MAX_CHASE_PTS:
                    out["entry_state"]     = "SKIP_CHASE"
                    out["skip_reason"]     = "chase_distance"
                    out["rejection_stage"] = "chase_check"
                    out["rejection_reason"] = "chase_distance"
                    out["scanner_state_flow"] = "range_breakdown → chase_distance"
                    _apply_watch_only_gate(out)
                    return out

                # ── MOMENTUM GATE ─────────────────────────────────────────────
                mom = _momentum_score(m5_candles, "bearish", confluence)
                out["momentum_score"]        = mom
                out["min_momentum_required"] = MIN_MOMENTUM_REQUIRED

                # H1 opposing hard skip (h1_trend="chop" here normally; guard for edge cases)
                if (h1_trend in ("bullish", "uptrend", "weak_bullish", "weak_uptrend")
                        and mom < 35):
                    out["entry_state"]          = "SKIP"
                    out["skip_reason"]          = "opposing_h1_low_momentum"
                    out["momentum_gate_passed"] = False
                    out["rejection_stage"]      = "momentum_gate"
                    out["rejection_reason"]     = "opposing_h1_low_momentum"
                    out["scanner_state_flow"]   = (
                        "range_active → range_low_broken → retest_held → follow_through"
                        " → opposing_h1_low_momentum → SKIP"
                    )
                    _apply_watch_only_gate(out)
                    return out

                if mom < MIN_MOMENTUM_REQUIRED:
                    out["entry_state"]          = "WAIT_MOMENTUM"
                    out["skip_reason"]          = "low_momentum"
                    out["momentum_gate_passed"] = False
                    out["rejection_stage"]      = "momentum_gate"
                    out["rejection_reason"]     = f"momentum={mom} < {MIN_MOMENTUM_REQUIRED}"
                    out["scanner_state_flow"]   = (
                        "range_active → range_low_broken → retest_held → follow_through"
                        " → low_momentum → WAIT_MOMENTUM"
                    )
                    _apply_watch_only_gate(out)
                    return out

                out["momentum_gate_passed"] = True
                out.update(levels)
                out["entry_state"]        = "ENTER_NOW"
                out["direction"]          = "bearish"
                out["setup_type"]         = "range_breakdown_bearish"
                out["entry_allowed"]      = True
                out["should_log"]         = True
                out["should_alert"]       = True
                out["entry_quality"]      = "high"
                out["skip_reason"]        = ""
                out["scanner_state_flow"] = (
                    "range_active → range_low_broken → retest_held → follow_through → ENTER_NOW short"
                )
                _apply_watch_only_gate(out)
                return out

            # Check for range breakout (bullish)
            bo = _detect_range_breakout(m5_candles, range_high)
            out.update(bo)
            if bo["range_high_broken"] and bo["range_retest_held_above"] and bo["bullish_follow_through"]:
                # Valid breakout — proceed to entry
                entry_price = m5_candles[-1]["close"] if m5_candles else 0.0
                sl_extreme  = range_high - 1.0  # retest support level
                # Record entry/SL candidates for debug visibility
                out["entry_price_candidate"] = round(entry_price, 3)
                out["sl_anchor"]             = round(sl_extreme, 3)
                levels = _calc_trade_levels(entry_price, sl_extreme, "bullish",
                                            htf_magnet=h1["htf_magnet"])
                if levels is not None:
                    out["sl_price_candidate"] = levels["sl_price"]
                if levels is None:
                    _raw_sl_price, _raw_sl_pts = _compute_sl_raw(entry_price, sl_extreme, "bullish")
                    out["sl_price_candidate"] = _raw_sl_price
                    out["sl_pts"]             = _raw_sl_pts
                    out["sl_gate_passed"]     = False
                    out["rejection_stage"]    = "sl_check"
                    out["rejection_reason"]   = f"sl_pts={_raw_sl_pts} > max={MAX_SL_PTS}"
                    out["skip_reason"]        = "sl_too_wide"
                    out["scanner_state_flow"] = "range_breakout → sl_too_wide"
                    _apply_watch_only_gate(out)
                    return out
                out["sl_gate_passed"] = True
                out["setup_type"]     = "range_breakout_bullish"
                out["direction"]      = "bullish"

                entry_dist = abs(entry_price - range_high)
                if entry_dist > MAX_CHASE_PTS:
                    out["entry_state"]        = "SKIP_CHASE"
                    out["skip_reason"]        = "chase_distance"
                    out["rejection_stage"]    = "chase_check"
                    out["rejection_reason"]   = "chase_distance"
                    out["scanner_state_flow"] = "range_breakout → chase_distance"
                    _apply_watch_only_gate(out)
                    return out

                # ── MOMENTUM GATE ─────────────────────────────────────────────
                mom = _momentum_score(m5_candles, "bullish", confluence)
                out["momentum_score"]        = mom
                out["min_momentum_required"] = MIN_MOMENTUM_REQUIRED

                # H1 opposing hard skip
                if (h1_trend in ("bearish", "downtrend", "weak_bearish", "weak_downtrend")
                        and mom < 35):
                    out["entry_state"]          = "SKIP"
                    out["skip_reason"]          = "opposing_h1_low_momentum"
                    out["momentum_gate_passed"] = False
                    out["rejection_stage"]      = "momentum_gate"
                    out["rejection_reason"]     = "opposing_h1_low_momentum"
                    out["scanner_state_flow"]   = (
                        "range_active → range_high_broken → retest_held → follow_through"
                        " → opposing_h1_low_momentum → SKIP"
                    )
                    _apply_watch_only_gate(out)
                    return out

                if mom < MIN_MOMENTUM_REQUIRED:
                    out["entry_state"]          = "WAIT_MOMENTUM"
                    out["skip_reason"]          = "low_momentum"
                    out["momentum_gate_passed"] = False
                    out["rejection_stage"]      = "momentum_gate"
                    out["rejection_reason"]     = f"momentum={mom} < {MIN_MOMENTUM_REQUIRED}"
                    out["scanner_state_flow"]   = (
                        "range_active → range_high_broken → retest_held → follow_through"
                        " → low_momentum → WAIT_MOMENTUM"
                    )
                    _apply_watch_only_gate(out)
                    return out

                out["momentum_gate_passed"] = True
                out.update(levels)
                out["entry_state"]        = "ENTER_NOW"
                out["direction"]          = "bullish"
                out["setup_type"]         = "range_breakout_bullish"
                out["entry_allowed"]      = True
                out["should_log"]         = True
                out["should_alert"]       = True
                out["entry_quality"]      = "high"
                out["skip_reason"]        = ""
                out["scanner_state_flow"] = (
                    "range_active → range_high_broken → retest_held → follow_through → ENTER_NOW long"
                )
                _apply_watch_only_gate(out)
                return out

            # Still inside range, no breakdown or breakout confirmed
            out["setup_type"]        = "htf_range_no_trade"
            out["entry_state"]       = "SKIP"
            out["skip_reason"]       = "inside_range_chop"
            out["rejection_stage"]   = "range_breakdown_check"
            out["rejection_reason"]  = "no_breakdown_confirmed"
            out["scanner_state_flow"] = "range_active → no_breakdown → SKIP_CHOP"
            _apply_watch_only_gate(out)
            return out

        # ── GATE 2: Sweep + reclaim long (bullish reversal) ──────────────────
        _branches.append("bearish_sweep_reclaim_long")
        sweep_bear = _detect_sweep(m5_candles, direction="bearish")
        out["sweep_candidate"]       = sweep_bear["detected"]
        out["sweep_detected"]        = sweep_bear["detected"]
        out["swept_side"]            = "bearish" if sweep_bear["detected"] else ""
        out["sweep_low"]             = sweep_bear["sweep_low"]
        out["sweep_high"]            = sweep_bear["sweep_high"]
        out["sweep_bars_ago"]        = sweep_bear["bars_ago"]
        out["sweep_reference_level"] = sweep_bear["sweep_reference_level"]
        out["sweep_distance_pts"]    = sweep_bear["sweep_distance_pts"]

        if sweep_bear["detected"]:
            out["active_branch"]          = "bearish_sweep_reclaim_long"
            out["setup_candidates_found"] = out["setup_candidates_found"] + 1
            sweep_extreme = sweep_bear["sweep_low"]
            entry_price_candidate = m5_candles[-1]["close"] if m5_candles else 0.0
            out["entry_price_candidate"] = round(entry_price_candidate, 3)
            out["sl_anchor"]             = round(sweep_extreme, 3)

            # Chase check first — if price has run too far from zone, no point computing SL
            entry_dist_pre = abs(entry_price_candidate - sweep_extreme)
            if entry_dist_pre > MAX_CHASE_PTS:
                out["entry_state"]     = "SKIP_CHASE"
                out["skip_reason"]     = "chase_distance"
                out["rejection_stage"] = "chase_check"
                out["rejection_reason"] = "chase_distance"
                out["scanner_state_flow"] = "sweep_detected → chase_distance → SKIP_CHASE"
                out["evaluated_branches"] = _branches
                _apply_watch_only_gate(out)
                return out

            # SL check
            levels = _calc_trade_levels(
                entry_price_candidate, sweep_extreme, "bullish", h1["htf_magnet"]
            )
            if levels is not None:
                out["sl_price_candidate"] = levels["sl_price"]

            if levels is None:
                _raw_sl_price, _raw_sl_pts = _compute_sl_raw(
                    entry_price_candidate, sweep_extreme, "bullish"
                )
                out["sl_price_candidate"] = _raw_sl_price
                out["sl_pts"]             = _raw_sl_pts
                out["sl_gate_passed"]     = False
                out["entry_state"]        = "SKIP"
                out["skip_reason"]        = "sl_too_wide"
                out["rejection_stage"]    = "sl_check"
                out["rejection_reason"]   = f"sl_pts={_raw_sl_pts} > max={MAX_SL_PTS}"
                out["scanner_state_flow"] = "sweep_detected → sl_too_wide → SKIP"
                out["evaluated_branches"] = _branches
                _apply_watch_only_gate(out)
                return out
            out["sl_gate_passed"] = True

            # Check reclaim
            reclaim_level = sweep_bear["sweep_low"] + SWEEP_MIN_WICK_PTS
            rec = _detect_reclaim(m5_candles, reclaim_level, direction="bullish")
            out.update({
                "reclaim_candidate":    True,
                "reclaim_confirmed":    rec["reclaim_confirmed"],
                "reclaim_direction":    "bullish",
                "reclaim_level":        round(reclaim_level, 3),
                "hold_bar":             rec["hold_bar"],
                "reclaim_distance_pts": rec["reclaim_distance_pts"],
            })

            if not rec["reclaim_confirmed"]:
                out["entry_state"]          = "WAIT_REACTION"
                out["sweep_alone_no_entry"] = True
                out["skip_reason"]          = ""
                out["rejection_stage"]      = "reclaim_check"
                out["rejection_reason"]     = "reclaim_not_confirmed"
                out["scanner_state_flow"]   = "sweep_detected → awaiting_reclaim → WAIT_REACTION"
                out["evaluated_branches"]   = _branches
                _apply_watch_only_gate(out)
                return out

            # Reclaim confirmed — check displacement
            avg = _avg_body(m5_candles)
            disp = _detect_displacement(m5_candles, "bullish", avg)
            out["bullish_displacement"]  = disp["detected"]
            out["displacement_body_pts"] = disp["displacement_body_pts"]
            out["avg_body_pts"]          = disp["avg_body_pts"]
            out["displacement_ratio"]    = disp["displacement_ratio"]

            if not disp["detected"]:
                _fail = disp.get("fail_reason", "ratio_below_threshold")
                if _fail == "direction_mismatch":
                    _disp_rej = (
                        f"displacement_ratio={disp['displacement_ratio']} >= {DISPLACE_MIN_MULT}"
                        f" but bar is not bullish (direction_mismatch)"
                    )
                else:
                    _disp_rej = (
                        f"displacement_ratio={disp['displacement_ratio']} < {DISPLACE_MIN_MULT}"
                    )
                out["entry_state"]     = "WAIT_HOLD"
                out["skip_reason"]     = ""
                out["rejection_stage"] = "displacement_check"
                out["rejection_reason"] = _disp_rej
                out["scanner_state_flow"] = "sweep_detected → reclaim_confirmed → awaiting_displacement → WAIT_HOLD"
                out["evaluated_branches"] = _branches
                _apply_watch_only_gate(out)
                return out

            # ── MOMENTUM GATE ─────────────────────────────────────────────────
            mom = _momentum_score(m5_candles, "bullish", confluence)
            out["momentum_score"]        = mom
            out["min_momentum_required"] = MIN_MOMENTUM_REQUIRED

            # H1 opposing hard skip: H1 directional against bullish entry + low momentum
            if (h1_trend in ("bearish", "downtrend", "weak_bearish", "weak_downtrend")
                    and mom < 35):
                out["entry_state"]          = "SKIP"
                out["skip_reason"]          = "opposing_h1_low_momentum"
                out["momentum_gate_passed"] = False
                out["rejection_stage"]      = "momentum_gate"
                out["rejection_reason"]     = f"opposing_h1({h1_trend})_momentum={mom}"
                out["scanner_state_flow"]   = (
                    "sweep_detected → reclaim_confirmed → displacement"
                    " → opposing_h1_low_momentum → SKIP"
                )
                out["evaluated_branches"]   = _branches
                _apply_watch_only_gate(out)
                return out

            if mom < MIN_MOMENTUM_REQUIRED:
                out["entry_state"]          = "WAIT_MOMENTUM"
                out["skip_reason"]          = "low_momentum"
                out["momentum_gate_passed"] = False
                out["rejection_stage"]      = "momentum_gate"
                out["rejection_reason"]     = f"momentum={mom} < {MIN_MOMENTUM_REQUIRED}"
                out["scanner_state_flow"]   = (
                    "sweep_detected → reclaim_confirmed → displacement"
                    " → low_momentum → WAIT_MOMENTUM"
                )
                out["evaluated_branches"]   = _branches
                _apply_watch_only_gate(out)
                return out

            # All gates passed — ENTER_NOW long
            out["momentum_gate_passed"]   = True
            out["evaluated_branches"]     = _branches
            out.update(levels)
            out["entry_state"]        = "ENTER_NOW"
            out["direction"]          = "bullish"
            out["setup_type"]         = "sweep_reclaim_long"
            out["entry_allowed"]      = True
            out["should_log"]         = True
            out["should_alert"]       = True
            out["entry_quality"]      = "high"
            out["skip_reason"]        = ""
            out["scanner_state_flow"] = (
                "sweep_detected → reclaim_confirmed → displacement → ENTER_NOW long"
            )
            _apply_watch_only_gate(out)
            return out

        # ── GATE 3: Failed reclaim → continuation short ───────────────────────
        _branches.append("bullish_sweep_failed_reclaim_short")
        sweep_bull = _detect_sweep(m5_candles, direction="bullish")
        if sweep_bull["detected"]:
            out["sweep_candidate"]       = True
            out["sweep_detected"]        = True
            out["swept_side"]            = "bullish"
            out["sweep_low"]             = sweep_bull["sweep_low"]
            out["sweep_high"]            = sweep_bull["sweep_high"]
            out["sweep_bars_ago"]        = sweep_bull["bars_ago"]
            out["sweep_reference_level"] = sweep_bull["sweep_reference_level"]
            out["sweep_distance_pts"]    = sweep_bull["sweep_distance_pts"]
            out["active_branch"]         = "bullish_sweep_failed_reclaim_short"
            out["setup_candidates_found"] = out["setup_candidates_found"] + 1

            sr_level = sweep_bull["sweep_high"] - SWEEP_MIN_WICK_PTS
            rec_fail = _detect_reclaim(m5_candles, sr_level, direction="bearish")
            out["reclaim_failed"]       = rec_fail["reclaim_failed"]
            out["reclaim_level"]        = round(sr_level, 3)
            out["reclaim_distance_pts"] = rec_fail["reclaim_distance_pts"]

            if rec_fail["reclaim_failed"]:
                # ── PATH A: failed_reclaim_continuation ──────────────────────
                # At least one of the last 3 bars pushed above sr_level and closed
                # back below — an explicit reclaim attempt that failed.
                avg_b = _avg_body(m5_candles)
                disp = _detect_displacement(m5_candles, "bearish", avg_b)
                out["bearish_displacement_after_failed_reclaim"] = disp["detected"]
                out["displacement_body_pts"] = disp["displacement_body_pts"]
                out["avg_body_pts"]          = disp["avg_body_pts"]
                out["displacement_ratio"]    = disp["displacement_ratio"]

                if disp["detected"]:
                    entry_price = m5_candles[-1]["close"] if m5_candles else 0.0
                    sl_extreme  = sweep_bull["sweep_high"]
                    out["entry_price_candidate"] = round(entry_price, 3)
                    out["sl_anchor"]             = round(sl_extreme, 3)
                    levels = _calc_trade_levels(entry_price, sl_extreme, "bearish",
                                                h1["htf_magnet"])
                    if levels is not None:
                        out["sl_price_candidate"] = levels["sl_price"]

                    if levels is None:
                        _raw_sl_price, _raw_sl_pts = _compute_sl_raw(
                            entry_price, sl_extreme, "bearish"
                        )
                        out["sl_price_candidate"] = _raw_sl_price
                        out["sl_pts"]             = _raw_sl_pts
                        out["sl_gate_passed"]     = False
                        out["skip_reason"]        = "sl_too_wide"
                        out["rejection_stage"]    = "sl_check"
                        out["rejection_reason"]   = f"sl_pts={_raw_sl_pts} > max={MAX_SL_PTS}"
                        out["scanner_state_flow"] = "failed_reclaim → sl_too_wide"
                        out["evaluated_branches"] = _branches
                        _apply_watch_only_gate(out)
                        return out
                    out["sl_gate_passed"] = True

                    entry_dist = abs(entry_price - sl_extreme)
                    if entry_dist > MAX_CHASE_PTS:
                        out["entry_state"]     = "SKIP_CHASE"
                        out["skip_reason"]     = "chase_distance"
                        out["rejection_stage"] = "chase_check"
                        out["rejection_reason"] = "chase_distance"
                        out["scanner_state_flow"] = "failed_reclaim → chase_distance → SKIP_CHASE"
                        out["evaluated_branches"] = _branches
                        _apply_watch_only_gate(out)
                        return out

                    # ── MOMENTUM GATE ─────────────────────────────────────────
                    mom = _momentum_score(m5_candles, "bearish", confluence)
                    out["momentum_score"]        = mom
                    out["min_momentum_required"] = MIN_MOMENTUM_REQUIRED

                    # H1 opposing hard skip: H1 directional against bearish entry + low momentum
                    if (h1_trend in ("bullish", "uptrend", "weak_bullish", "weak_uptrend")
                            and mom < 35):
                        out["entry_state"]          = "SKIP"
                        out["skip_reason"]          = "opposing_h1_low_momentum"
                        out["momentum_gate_passed"] = False
                        out["rejection_stage"]      = "momentum_gate"
                        out["rejection_reason"]     = f"opposing_h1({h1_trend})_momentum={mom}"
                        out["scanner_state_flow"]   = (
                            "bullish_sweep → reclaim_failed → bearish_displacement"
                            " → opposing_h1_low_momentum → SKIP"
                        )
                        out["evaluated_branches"]   = _branches
                        _apply_watch_only_gate(out)
                        return out

                    if mom < MIN_MOMENTUM_REQUIRED:
                        out["entry_state"]          = "WAIT_MOMENTUM"
                        out["skip_reason"]          = "low_momentum"
                        out["momentum_gate_passed"] = False
                        out["rejection_stage"]      = "momentum_gate"
                        out["rejection_reason"]     = f"momentum={mom} < {MIN_MOMENTUM_REQUIRED}"
                        out["scanner_state_flow"]   = (
                            "bullish_sweep → reclaim_failed → bearish_displacement"
                            " → low_momentum → WAIT_MOMENTUM"
                        )
                        out["evaluated_branches"]   = _branches
                        _apply_watch_only_gate(out)
                        return out

                    out["momentum_gate_passed"]   = True
                    out["evaluated_branches"]     = _branches
                    out.update(levels)
                    out["entry_state"]        = "ENTER_NOW"
                    out["direction"]          = "bearish"
                    out["setup_type"]         = "failed_reclaim_continuation"
                    out["entry_allowed"]      = True
                    out["should_log"]         = True
                    out["should_alert"]       = True
                    out["entry_quality"]      = "high"
                    out["skip_reason"]        = ""
                    out["scanner_state_flow"] = (
                        "bullish_sweep → reclaim_failed → bearish_displacement → ENTER_NOW short"
                    )
                    _apply_watch_only_gate(out)
                    return out

                # Bearish displacement not confirmed yet
                _fail3 = disp.get("fail_reason", "ratio_below_threshold")
                if _fail3 == "direction_mismatch":
                    _disp_rej3 = (
                        f"displacement_ratio={disp['displacement_ratio']} >= {DISPLACE_MIN_MULT}"
                        f" but bar is not bearish (direction_mismatch)"
                    )
                else:
                    _disp_rej3 = (
                        f"displacement_ratio={disp['displacement_ratio']} < {DISPLACE_MIN_MULT}"
                    )
                out["rejection_stage"]  = "displacement_check"
                out["rejection_reason"] = _disp_rej3
                # Falls through to WAIT_REACTION below

            else:
                # ── PATH B: sweep_reclaim_short ───────────────────────────────
                # Bullish sweep is in the detection window (last 20 bars) but none
                # of the last 3 bars pushed above sr_level. No explicit reclaim
                # attempt observed — the market simply rolled over after the sweep.
                # Check for immediate bearish displacement: if present this is a
                # clean sweep-and-reject short (sweep_reclaim_short), distinct from
                # failed_reclaim_continuation which requires a separate reclaim bar.
                avg_b = _avg_body(m5_candles)
                disp  = _detect_displacement(m5_candles, "bearish", avg_b)
                out["bearish_displacement_after_failed_reclaim"] = disp["detected"]
                out["displacement_body_pts"] = disp["displacement_body_pts"]
                out["avg_body_pts"]          = disp["avg_body_pts"]
                out["displacement_ratio"]    = disp["displacement_ratio"]

                if disp["detected"]:
                    entry_price = m5_candles[-1]["close"] if m5_candles else 0.0
                    sl_extreme  = sweep_bull["sweep_high"]
                    out["entry_price_candidate"] = round(entry_price, 3)
                    out["sl_anchor"]             = round(sl_extreme, 3)
                    levels = _calc_trade_levels(entry_price, sl_extreme, "bearish",
                                                h1["htf_magnet"])
                    if levels is not None:
                        out["sl_price_candidate"] = levels["sl_price"]

                    if levels is None:
                        _raw_sl_price, _raw_sl_pts = _compute_sl_raw(
                            entry_price, sl_extreme, "bearish"
                        )
                        out["sl_price_candidate"] = _raw_sl_price
                        out["sl_pts"]             = _raw_sl_pts
                        out["sl_gate_passed"]     = False
                        out["skip_reason"]        = "sl_too_wide"
                        out["rejection_stage"]    = "sl_check"
                        out["rejection_reason"]   = f"sl_pts={_raw_sl_pts} > max={MAX_SL_PTS}"
                        out["scanner_state_flow"] = "bullish_sweep → direct_rejection → sl_too_wide"
                        out["evaluated_branches"] = _branches
                        _apply_watch_only_gate(out)
                        return out
                    out["sl_gate_passed"] = True

                    entry_dist = abs(entry_price - sl_extreme)
                    if entry_dist > MAX_CHASE_PTS:
                        out["entry_state"]      = "SKIP_CHASE"
                        out["skip_reason"]      = "chase_distance"
                        out["rejection_stage"]  = "chase_check"
                        out["rejection_reason"] = "chase_distance"
                        out["scanner_state_flow"] = (
                            "bullish_sweep → direct_rejection → chase_distance → SKIP_CHASE"
                        )
                        out["evaluated_branches"] = _branches
                        _apply_watch_only_gate(out)
                        return out

                    # ── MOMENTUM GATE ─────────────────────────────────────────
                    mom = _momentum_score(m5_candles, "bearish", confluence)
                    out["momentum_score"]        = mom
                    out["min_momentum_required"] = MIN_MOMENTUM_REQUIRED

                    if (h1_trend in ("bullish", "uptrend", "weak_bullish", "weak_uptrend")
                            and mom < 35):
                        out["entry_state"]          = "SKIP"
                        out["skip_reason"]          = "opposing_h1_low_momentum"
                        out["momentum_gate_passed"] = False
                        out["rejection_stage"]      = "momentum_gate"
                        out["rejection_reason"]     = f"opposing_h1({h1_trend})_momentum={mom}"
                        out["scanner_state_flow"]   = (
                            "bullish_sweep → direct_rejection → bearish_displacement"
                            " → opposing_h1_low_momentum → SKIP"
                        )
                        out["evaluated_branches"] = _branches
                        _apply_watch_only_gate(out)
                        return out

                    if mom < MIN_MOMENTUM_REQUIRED:
                        out["entry_state"]          = "WAIT_MOMENTUM"
                        out["skip_reason"]          = "low_momentum"
                        out["momentum_gate_passed"] = False
                        out["rejection_stage"]      = "momentum_gate"
                        out["rejection_reason"]     = f"momentum={mom} < {MIN_MOMENTUM_REQUIRED}"
                        out["scanner_state_flow"]   = (
                            "bullish_sweep → direct_rejection → bearish_displacement"
                            " → low_momentum → WAIT_MOMENTUM"
                        )
                        out["evaluated_branches"] = _branches
                        _apply_watch_only_gate(out)
                        return out

                    out["momentum_gate_passed"] = True
                    out["evaluated_branches"]   = _branches
                    out.update(levels)
                    out["entry_state"]        = "ENTER_NOW"
                    out["direction"]          = "bearish"
                    out["setup_type"]         = "sweep_reclaim_short"
                    out["entry_allowed"]      = True
                    out["should_log"]         = True
                    out["should_alert"]       = True
                    out["entry_quality"]      = "high"
                    out["skip_reason"]        = ""
                    out["scanner_state_flow"] = (
                        "bullish_sweep → direct_rejection → bearish_displacement → ENTER_NOW short"
                    )
                    _apply_watch_only_gate(out)
                    return out

                # Displacement not confirmed yet — set rejection reason
                _fail_b = disp.get("fail_reason", "ratio_below_threshold")
                if _fail_b == "direction_mismatch":
                    _disp_rej_b = (
                        f"displacement_ratio={disp['displacement_ratio']} >= {DISPLACE_MIN_MULT}"
                        f" but bar is not bearish (direction_mismatch)"
                    )
                else:
                    _disp_rej_b = (
                        f"displacement_ratio={disp['displacement_ratio']} < {DISPLACE_MIN_MULT}"
                    )
                out["rejection_stage"]  = "displacement_check"
                out["rejection_reason"] = _disp_rej_b
                # Falls through to WAIT_HOLD below

            # Sweep detected but no actionable outcome yet.
            # Path A (rec_fail=True, no displacement): WAIT_REACTION — failed reclaim
            #   confirmed, waiting for displacement bar.
            # Path B (rec_fail=False, no displacement): WAIT_HOLD — sweep seen, no
            #   reclaim attempt observed, waiting for rejection/displacement to form.
            if rec_fail["reclaim_failed"]:
                out["entry_state"]        = "WAIT_REACTION"
                out["scanner_state_flow"] = (
                    "bullish_sweep_detected → awaiting_reclaim_outcome → WAIT_REACTION"
                )
            else:
                out["entry_state"]        = "WAIT_HOLD"
                out["scanner_state_flow"] = (
                    "bullish_sweep_detected → awaiting_rejection_displacement → WAIT_HOLD"
                )
            out["skip_reason"]        = ""
            out["evaluated_branches"] = _branches
            _apply_watch_only_gate(out)
            return out

        # ── FALLTHROUGH: no setup ─────────────────────────────────────────────
        out["entry_state"]        = "SKIP"
        out["skip_reason"]        = "no_setup"
        out["rejection_stage"]    = "all_gates"
        out["rejection_reason"]   = "no_sweep_detected_no_range_event"
        out["evaluated_branches"] = _branches
        out["scanner_state_flow"] = "no_sweep_no_range_event → SKIP"
        _apply_watch_only_gate(out)
        return out

    except Exception as exc:
        logger.exception(f"om_gold_scalp.run error for {pair}: {exc}")
        out["entry_state"]        = "SKIP"
        out["skip_reason"]        = "internal_error"
        out["rejection_stage"]    = "internal_error"
        out["rejection_reason"]   = str(exc)
        out["scanner_state_flow"] = f"internal_error: {exc}"
        _apply_watch_only_gate(out)
        return out


# ── SKIP CLASSIFICATION CONSISTENCY GUARD ────────────────────────────────────

def _enforce_skip_consistency(out: dict) -> None:
    """
    Invariant: skip_reason="sl_too_wide" is ONLY valid when ALL of:
      - entry_price_candidate is not None   (a real candidate was found)
      - sl_price_candidate is not None      (SL was computed before rejection)
      - sl_pts is numeric and > 0           (the actual pts that exceeded the gate)

    If any precondition is missing the caller set sl_too_wide incorrectly
    (no real setup existed). Reclassify to no_setup so the debug panel
    never shows an inconsistent state.

    Called as the first step of _apply_watch_only_gate so it fires on every
    return path without requiring individual call sites to remember.
    """
    if out.get("skip_reason") != "sl_too_wide":
        return

    has_entry   = out.get("entry_price_candidate") is not None
    has_sl_cand = out.get("sl_price_candidate")    is not None
    has_sl_pts  = isinstance(out.get("sl_pts"), (int, float)) and out.get("sl_pts", 0) > 0

    if not (has_entry and has_sl_cand and has_sl_pts):
        out["skip_reason"]        = "no_setup"
        out["rejection_stage"]    = "setup_detection"
        out["rejection_reason"]   = "no_valid_candidate"
        out["scanner_state_flow"] = "no_sweep_no_range_event → SKIP"


# ── WATCH-ONLY GATE ───────────────────────────────────────────────────────────

def _apply_watch_only_gate(out: dict) -> None:
    """
    Mutate `out` in place.
    1. Enforce skip classification consistency (sl_too_wide preconditions).
    2. If OM_GOLD_SCALP_ENABLED is false, suppress should_log and should_alert
       but preserve all audit fields.
    """
    _enforce_skip_consistency(out)   # invariant check on every return path
    if not OM_GOLD_SCALP_ENABLED:
        out["should_log"]   = False
        out["should_alert"] = False
