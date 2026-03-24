"""
confluence.py — Multi-timeframe confluence engine

NEW IN THIS VERSION:

PULLBACK vs REVERSAL DETECTION
═══════════════════════════════
H1 trend is LAW. Only H1 MSS can change it.
M15/M5 going against H1 = pullback = ENTRY OPPORTUNITY not a reversal.

  H1 uptrend + M15/M5 bearish + NO H1 MSS = PULLBACK
  → Signal stays BULLISH
  → Note: "Pullback in progress — wait for M5 rejection, enter long"

  H1 uptrend + H1 MSS fires bearish = REVERSAL
  → Signal flips BEARISH
  → Note: "H1 MSS confirmed — trend changing"

BREAKOUT DETECTION
══════════════════
M15 impulse 2x+ ATR breaking structure → two stage alert:
  Stage 1: "BREAKOUT FIRING — get ready"
  Stage 2: "RETEST HIT — enter now"
  Aggressive: enter on M1 close in breakout direction

Only overrides H1 trend during killzones.
Outside killzones: WATCH only.

SETUP TYPES
═══════════
  pullback_long/short  — M15/M5 pullback in H1 trend, entry opportunity
  breakout_bull/bear   — M15 impulse breaks structure
  breakout_retest      — price retesting FVG/OB after breakout
  reversal_bull/bear   — H1 MSS fired, trend changing
  trend_follow         — full TF alignment
  sr_flip / zone_tap   — zone based setups
"""

import logging
from core.zones import get_all_zones, get_active_zones, price_at_zone
from core.structure import detect_market_structure, detect_breakouts, detect_sr_flips
from core.candles import detect_patterns, detect_consolidation
from core.fvg import detect_fvgs, get_active_fvgs, fvg_zone_overlap
from core.fetcher import pip_size

logger = logging.getLogger(__name__)

# H1 trend memory — only H1 MSS can change it
_h1_trend_memory = {}

# Signal stability store
_signal_lock = {}


def _get_h1_memory(pair: str) -> dict:
    return _h1_trend_memory.get(pair, {})


def _set_h1_memory(pair: str, trend: str, direction: str, price: float):
    _h1_trend_memory[pair] = {
        "trend":     trend,
        "direction": direction,
        "price":     price,
    }


def _is_signal_locked(pair: str, current_price: float) -> bool:
    lock = _signal_lock.get(pair)
    if not lock:
        return False
    pip          = pip_size(pair)
    locked_price = lock.get("entry_price", current_price)
    move_pips    = abs(current_price - locked_price) / pip
    if move_pips > 15:
        _signal_lock.pop(pair, None)
        return False
    return True


def _set_signal_lock(pair: str, direction: str, price: float):
    _signal_lock[pair] = {"direction": direction, "entry_price": price}


def get_approaching_zones(df, pair: str, zones: list, pip_buffer: int = 15) -> list:
    current_price = df["close"].iloc[-1]
    pip    = pip_size(pair)
    buffer = pip_buffer * pip
    approaching = []
    for zone in zones:
        if price_at_zone(current_price, zone, pair):
            continue
        dist_to_high = abs(current_price - zone["high"])
        dist_to_low  = abs(current_price - zone["low"])
        min_dist     = min(dist_to_high, dist_to_low)
        if min_dist <= buffer:
            pips_away = round(min_dist / pip)
            approaching.append({
                **zone,
                "pips_away":        pips_away,
                "approaching_from": "below" if current_price < zone["low"] else "above",
            })
    return sorted(approaching, key=lambda z: z["pips_away"])


def detect_m15_breakout(candles: dict, pair: str, h1_bias: str) -> dict:
    """
    Detect M15 breakout impulse that breaks structure.

    Criteria:
    1. M15 candle body 2x+ ATR
    2. Closes near high/low (real body move not a wick)
    3. Breaks recent M15 swing high or low
    4. 2+ consecutive candles = stronger signal

    Returns breakout dict with direction, FVG left behind.
    """
    df_m15 = candles.get("M15")
    if df_m15 is None or len(df_m15) < 10:
        return {"detected": False}

    atr_m15 = df_m15["high"].sub(df_m15["low"]).rolling(14).mean().iloc[-1]
    if atr_m15 == 0:
        return {"detected": False}

    best = None

    for i in range(1, 4):
        candle = df_m15.iloc[-i]
        body   = abs(candle["close"] - candle["open"])
        total  = candle["high"] - candle["low"]

        if total == 0 or body / atr_m15 < 1.8:
            continue

        close_pct = (candle["close"] - candle["low"]) / total
        if close_pct >= 0.60:
            bo_dir = "bullish"
        elif close_pct <= 0.40:
            bo_dir = "bearish"
        else:
            continue

        # Must actually break recent structure
        recent_high = df_m15["high"].iloc[-20:-i].max() if len(df_m15) > 20 else df_m15["high"].max()
        recent_low  = df_m15["low"].iloc[-20:-i].min()  if len(df_m15) > 20 else df_m15["low"].min()

        breaks = (
            (bo_dir == "bullish" and candle["close"] > recent_high) or
            (bo_dir == "bearish" and candle["close"] < recent_low)
        )
        if not breaks:
            continue

        # Check consecutive candles
        consecutive = 1
        if i == 1 and len(df_m15) >= 3:
            prev = df_m15.iloc[-2]
            if bo_dir == "bullish" and prev["close"] > prev["open"]:
                consecutive = 2
            elif bo_dir == "bearish" and prev["close"] < prev["open"]:
                consecutive = 2

        # FVG left behind
        fvg = None
        if i >= 2 and len(df_m15) > i + 1:
            prev_c = df_m15.iloc[-i - 1]
            next_c = df_m15.iloc[-i + 1] if i > 1 else candle
            if bo_dir == "bullish" and next_c["low"] > prev_c["high"]:
                fvg = {"high": next_c["low"], "low": prev_c["high"], "direction": "bullish"}
            elif bo_dir == "bearish" and next_c["high"] < prev_c["low"]:
                fvg = {"high": prev_c["low"], "low": next_c["high"], "direction": "bearish"}

        atr_ratio = round(body / atr_m15, 1)
        result = {
            "detected":     True,
            "direction":    bo_dir,
            "atr_ratio":    atr_ratio,
            "consecutive":  consecutive,
            "candles_ago":  i - 1,
            "fvg":          fvg,
            "candle_high":  float(candle["high"]),
            "candle_low":   float(candle["low"]),
            "candle_close": float(candle["close"]),
            "strength":     min(round(atr_ratio * 20 + consecutive * 10), 100),
        }

        if best is None or atr_ratio > best["atr_ratio"]:
            best = result

    return best or {"detected": False}


def detect_fvg_retest(candles: dict, pair: str, breakout: dict) -> dict:
    """Check if price has pulled back to retest the FVG left by the breakout."""
    if not breakout.get("detected") or not breakout.get("fvg"):
        return {"detected": False}

    df_m5 = candles.get("M5")
    if df_m5 is None or df_m5.empty:
        return {"detected": False}

    current_price = df_m5["close"].iloc[-1]
    fvg           = breakout["fvg"]
    pip           = pip_size(pair)
    fvg_mid       = (fvg["high"] + fvg["low"]) / 2
    distance_pips = abs(current_price - fvg_mid) / pip
    in_fvg        = fvg["low"] <= current_price <= fvg["high"]

    if in_fvg or distance_pips <= 8:
        return {
            "detected":     True,
            "in_fvg":       in_fvg,
            "fvg":          fvg,
            "distance":     round(distance_pips, 1),
            "direction":    breakout["direction"],
            "note": f"{'✅ IN FVG — enter now' if in_fvg else f'🔜 {round(distance_pips)}p from FVG'}",
        }
    return {"detected": False}


def analyze_timeframe(candles: dict, pair: str, timeframe: str) -> dict:
    df = candles.get(timeframe)
    if df is None or df.empty:
        return {
            "bias": "neutral", "zones": [], "patterns": [], "structure": {},
            "active_zones": [], "approaching_zones": [], "consolidation": {},
            "flips": [], "fvgs": [], "fvg_overlaps": [], "current_price": 0,
            "zone_conflict": False, "zone_warning": None,
        }

    structure     = detect_market_structure(df)
    zones         = get_all_zones(df, pair)
    active_zones  = get_active_zones(df, pair)
    approaching   = get_approaching_zones(df, pair, zones)
    consolidation = detect_consolidation(df)
    flips         = detect_sr_flips(df, zones)
    active_fvgs   = get_active_fvgs(df)
    fvg_overlaps  = fvg_zone_overlap(active_fvgs, zones)

    trend_bias = structure.get("bias", "neutral")
    if trend_bias == "neutral":
        trend = structure.get("trend", "ranging")
        trend_bias = "bullish" if "up" in trend else ("bearish" if "down" in trend else "neutral")

    zone_conflict = False
    zone_warning  = None

    if active_zones:
        top_zone  = active_zones[0]
        zone_type = top_zone["type"]
        if zone_type in ["support", "demand", "resistance_to_support"]:
            zone_bias = "bullish"
        elif zone_type in ["resistance", "supply", "support_to_resistance"]:
            zone_bias = "bearish"
        else:
            zone_bias = None

        if zone_bias and zone_bias != trend_bias and trend_bias != "neutral":
            zone_conflict = True
            zone_warning  = f"⚠️ Zone ({zone_type}) suggests {zone_bias} but trend is {trend_bias}"
        elif zone_bias and trend_bias == "neutral":
            trend_bias = zone_bias

    patterns = detect_patterns(df, bias=trend_bias)

    return {
        "bias":              trend_bias,
        "zones":             zones,
        "active_zones":      active_zones,
        "approaching_zones": approaching,
        "consolidation":     consolidation,
        "patterns":          patterns,
        "structure":         structure,
        "flips":             flips,
        "fvgs":              active_fvgs,
        "fvg_overlaps":      fvg_overlaps,
        "current_price":     df["close"].iloc[-1],
        "zone_conflict":     zone_conflict,
        "zone_warning":      zone_warning,
    }


def check_confluence(candles: dict, pair: str) -> dict:
    """
    Core confluence engine.

    THE RULE:
    H1 trend = LAW. Only H1 MSS can change it.
    M15/M5 against H1 = pullback = entry opportunity.
    M15 impulse + MSS = breakout = new move.
    """
    h1  = analyze_timeframe(candles, pair, "H1")
    m15 = analyze_timeframe(candles, pair, "M15")
    m5  = analyze_timeframe(candles, pair, "M5")

    current_price = m5["current_price"] or h1["current_price"]

    # ICT context
    ict_context  = {}
    ict_direction = None
    h1_mss_fired = False
    h1_mss_type  = None

    try:
        from core.ict import get_ict_context
        ict_context   = get_ict_context(candles["H1"], candles["M15"], candles["M5"])
        ict_direction = ict_context.get("ict_direction")
        mss_h1        = ict_context.get("mss_h1", {})
        h1_mss_fired  = mss_h1.get("detected", False)
        h1_mss_type   = mss_h1.get("type")
    except Exception as e:
        logger.warning(f"ICT context failed: {e}")

    # ── STEP 1: H1 TREND (the law) ──────────────────────────────
    h1_structure = h1["structure"]
    h1_trend     = h1_structure.get("trend", "ranging")
    h1_bias      = h1["bias"]
    h1_strength  = h1_structure.get("strength", 1)

    if h1_mss_fired and h1_mss_type:
        h1_bias = h1_mss_type
        _set_h1_memory(pair, h1_trend, h1_bias, current_price)
        logger.info(f"{pair} H1 MSS {h1_mss_type} — trend updated")
    elif h1_strength >= 2 and h1_bias != "neutral":
        _set_h1_memory(pair, h1_trend, h1_bias, current_price)
    else:
        memory = _get_h1_memory(pair)
        if memory and h1_bias == "neutral":
            h1_bias = memory.get("direction", h1_bias)

    # ── STEP 2: BREAKOUT CHECK ───────────────────────────────────
    breakout    = detect_m15_breakout(candles, pair, h1_bias)
    retest      = {"detected": False}
    is_breakout = False
    is_retest   = False

    if breakout["detected"]:
        retest = detect_fvg_retest(candles, pair, breakout)
        try:
            from filters.killzones import get_active_killzone
            in_kz = get_active_killzone().get("active", False)
        except Exception:
            in_kz = True

        same_as_h1 = breakout["direction"] == h1_bias
        if in_kz or same_as_h1:
            is_breakout = True
            is_retest   = retest["detected"]

    # ── STEP 3: PULLBACK CHECK ───────────────────────────────────
    m15_bias = m15["bias"]
    m5_bias  = m5["bias"]

    m15_against = m15_bias != h1_bias and h1_bias != "neutral" and m15_bias != "neutral"
    m5_against  = m5_bias  != h1_bias and h1_bias != "neutral" and m5_bias  != "neutral"
    is_pullback = (m15_against or m5_against) and not is_breakout

    # ── STEP 4: FINAL DIRECTION + SIGNAL TYPE ────────────────────
    direction   = h1_bias
    confidence  = 1
    aligned     = False
    tf_reading  = ""
    signal_type = "trend_follow"
    setup_type  = "none"

    if h1_mss_fired and h1_mss_type:
        # H1 MSS — highest priority, trend officially changing
        direction   = h1_mss_type
        confidence  = 3
        aligned     = True
        signal_type = f"reversal_{direction}"
        setup_type  = f"reversal_{'bull' if direction == 'bullish' else 'bear'}"
        tf_reading  = (
            f"🔄 H1 MSS {direction.upper()} CONFIRMED — trend officially changing. "
            f"High conviction reversal. Enter on M5 confirmation."
        )

    elif is_breakout:
        bo_dir      = breakout["direction"]
        direction   = bo_dir
        confidence  = 2 if is_retest else 1
        aligned     = is_retest
        signal_type = "breakout"

        if is_retest:
            setup_type = "breakout_retest"
            tf_reading = (
                f"⚡ BREAKOUT RETEST — {bo_dir.upper()} {breakout['atr_ratio']}x ATR impulse, "
                f"price retesting FVG. {retest.get('note', '')} "
                f"SL below {'FVG low' if bo_dir == 'bullish' else 'FVG high'}."
            )
        else:
            setup_type = f"breakout_{'bull' if bo_dir == 'bullish' else 'bear'}"
            tf_reading = (
                f"🚀 BREAKOUT FIRING — {bo_dir.upper()} {breakout['atr_ratio']}x ATR "
                f"breaking structure. Stage 1. Watch for FVG retest OR enter aggressive on M1 close."
            )

    elif is_pullback:
        # M15/M5 pulling back inside H1 trend — KEEP H1 DIRECTION
        direction   = h1_bias
        confidence  = 2
        aligned     = False
        signal_type = f"pullback_{'long' if h1_bias == 'bullish' else 'short'}"
        setup_type  = signal_type
        pb_dir      = "bearish" if h1_bias == "bullish" else "bullish"
        tf_reading  = (
            f"📉 PULLBACK in H1 {h1_bias.upper()} trend — "
            f"M15/M5 temporarily {pb_dir} (normal retracement, NOT a reversal). "
            f"Wait for M5 rejection candle → enter {h1_bias}. "
            f"This is your entry opportunity."
        )

    else:
        # Weighted vote
        bull_v = (2 if h1_bias=="bullish" else 0) + (1 if m15_bias=="bullish" else 0) + (1 if m5_bias=="bullish" else 0)
        bear_v = (2 if h1_bias=="bearish" else 0) + (1 if m15_bias=="bearish" else 0) + (1 if m5_bias=="bearish" else 0)

        if bull_v >= 3:
            direction, aligned, confidence = "bullish", bull_v==4, min(bull_v,3)
            tf_reading = "✅ Full bullish alignment"
            setup_type = "trend_follow"
        elif bear_v >= 3:
            direction, aligned, confidence = "bearish", bear_v==4, min(bear_v,3)
            tf_reading = "✅ Full bearish alignment"
            setup_type = "trend_follow"
        elif bull_v == 2 and h1_bias == "bullish":
            direction, aligned, confidence = "bullish", False, 2
            tf_reading = "H1 bullish, partial alignment — wait for M5"
        elif bear_v == 2 and h1_bias == "bearish":
            direction, aligned, confidence = "bearish", False, 2
            tf_reading = "H1 bearish, partial alignment — wait for M5"
        else:
            direction  = h1_bias if h1_bias != "neutral" else "none"
            confidence = 1 if direction != "none" else 0
            tf_reading = f"Mixed — H1 {direction}. Wait for alignment."

    # ICT conflict — skip during pullbacks (expected to have opposite lower TF ICT)
    ict_conflict = False
    if not is_pullback and ict_direction and direction not in ["none","neutral"]:
        if ict_direction != direction:
            ict_conflict = True

    # Zone warnings
    zone_warnings = []
    if h1.get("zone_conflict") and h1.get("zone_warning"):
        zone_warnings.append(h1["zone_warning"])

    # Signal stability — don't flip unless H1 MSS fired
    if _is_signal_locked(pair, current_price) and not h1_mss_fired:
        locked     = _signal_lock.get(pair, {})
        locked_dir = locked.get("direction", direction)
        if locked_dir != direction:
            logger.info(f"{pair} locked at {locked_dir}, ignoring flip to {direction}")
            direction = locked_dir

    if direction not in ["none","neutral"] and confidence >= 2:
        _set_signal_lock(pair, direction, current_price)

    # Setup type fallback
    if setup_type == "none":
        if h1["flips"] or m15["flips"]:
            setup_type = "sr_flip"
        elif h1["active_zones"]:
            setup_type = "zone_tap"
        elif h1["approaching_zones"]:
            setup_type = "zone_approach"

    m5_consolidating   = m5["consolidation"].get("consolidating", False)
    consolidation_note = "⚠️ M5 consolidating — wait for breakout" if m5_consolidating else ""
    entry_confirmed    = bool(m5["patterns"]) and not m5_consolidating
    entry_pattern      = m5["patterns"][0] if entry_confirmed else None

    approaching_warning = ""
    if h1["approaching_zones"] and not h1["active_zones"]:
        c = h1["approaching_zones"][0]
        approaching_warning = f"🔜 Approaching {c['type']} zone at {c['mid']:.5f} ({c['pips_away']}p away)"

    has_fvg_overlap = bool(h1["fvg_overlaps"] or m15["fvg_overlaps"])
    active_fvgs     = h1["fvgs"] + m15["fvgs"] + m5["fvgs"]

    return {
        "pair":                pair,
        "aligned":             aligned,
        "direction":           direction,
        "confidence":          confidence,
        "tf_reading":          tf_reading,
        "signal_type":         signal_type,
        "setup_type":          setup_type,
        "is_pullback":         is_pullback,
        "is_breakout":         is_breakout,
        "is_retest":           is_retest,
        "breakout":            breakout,
        "retest":              retest,
        "h1_mss_fired":        h1_mss_fired,
        "h1_mss_type":         h1_mss_type,
        "consolidation_note":  consolidation_note,
        "approaching_warning": approaching_warning,
        "entry_confirmed":     entry_confirmed,
        "entry_pattern":       entry_pattern,
        "has_fvg_overlap":     has_fvg_overlap,
        "active_fvgs":         active_fvgs,
        "fvg_overlaps":        h1["fvg_overlaps"] + m15["fvg_overlaps"],
        "h1":                  h1,
        "m15":                 m15,
        "m5":                  m5,
        "ict":                 ict_context,
        "ict_conflict":        ict_conflict,
        "zone_warnings":       zone_warnings,
        "current_price":       current_price,
    }


def is_tradeable(confluence: dict) -> bool:
    h1_zone_active    = bool(confluence["h1"]["active_zones"])
    tf_agreement      = confluence["confidence"] >= 2
    entry_signal      = confluence["entry_confirmed"]
    not_consolidating = not confluence["h1"]["consolidation"].get("consolidating", False)
    return h1_zone_active and tf_agreement and entry_signal and not_consolidating