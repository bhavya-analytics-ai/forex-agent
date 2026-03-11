"""
confluence.py — Check if 1H + 15M + 5M all align on a setup
"""

import logging
from core.zones import get_all_zones, get_active_zones, price_at_zone
from core.structure import detect_market_structure, detect_breakouts, detect_sr_flips
from core.candles import detect_patterns
from core.fvg import detect_fvgs, get_active_fvgs, fvg_zone_overlap

logger = logging.getLogger(__name__)


def analyze_timeframe(df: dict, pair: str, timeframe: str) -> dict:
    """
    Analyze a single timeframe.
    Returns: bias, active_zones, patterns, structure
    """
    candles = df[timeframe]
    if candles.empty:
        return {"bias": "neutral", "zones": [], "patterns": [], "structure": {}}

    # Market structure on this TF
    structure = detect_market_structure(candles)

    # All zones on this TF
    zones = get_all_zones(candles, pair)

    # Zones price is currently tapping
    active_zones = get_active_zones(candles, pair)

    # Determine bias from structure
    trend = structure.get("trend", "ranging")
    if "up" in trend:
        bias = "bullish"
    elif "down" in trend:
        bias = "bearish"
    else:
        bias = "neutral"

    # Candle patterns — use bias from active zone if available
    zone_bias = None
    if active_zones:
        top_zone = active_zones[0]
        if top_zone["type"] in ["support", "demand", "resistance_to_support"]:
            zone_bias = "bullish"
        elif top_zone["type"] in ["resistance", "supply", "support_to_resistance"]:
            zone_bias = "bearish"

    patterns = detect_patterns(candles, bias=zone_bias or bias)

    # S/R flips
    flips = detect_sr_flips(candles, zones)

    # FVG detection
    active_fvgs  = get_active_fvgs(candles)
    fvg_overlaps = fvg_zone_overlap(active_fvgs, zones)

    return {
        "bias":         bias,
        "zones":        zones,
        "active_zones": active_zones,
        "patterns":     patterns,
        "structure":    structure,
        "flips":        flips,
        "fvgs":         active_fvgs,
        "fvg_overlaps": fvg_overlaps,
        "current_price": candles["close"].iloc[-1],
    }


def check_confluence(candles: dict, pair: str) -> dict:
    """
    Core confluence engine.
    Analyzes H1, M15, M5 and checks if they all agree on direction.

    Returns:
        aligned:    True/False — all TFs agree
        direction:  bullish / bearish / none
        h1:         H1 analysis
        m15:        M15 analysis
        m5:         M5 analysis
        setup_type: breakout_retest / supply_demand / sr_flip / zone_tap
        confidence: 0-3 (how many TFs agree)
    """
    h1  = analyze_timeframe(candles, pair, "H1")
    m15 = analyze_timeframe(candles, pair, "M15")
    m5  = analyze_timeframe(candles, pair, "M5")

    biases = [h1["bias"], m15["bias"], m5["bias"]]

    # Count agreement
    bullish_count = biases.count("bullish")
    bearish_count = biases.count("bearish")

    if bullish_count == 3:
        direction  = "bullish"
        aligned    = True
        confidence = 3
    elif bearish_count == 3:
        direction  = "bearish"
        aligned    = True
        confidence = 3
    elif bullish_count == 2:
        direction  = "bullish"
        aligned    = False
        confidence = 2
    elif bearish_count == 2:
        direction  = "bearish"
        aligned    = False
        confidence = 2
    else:
        direction  = "none"
        aligned    = False
        confidence = 0

    # Determine setup type
    setup_type = "none"
    if h1["flips"] or m15["flips"]:
        setup_type = "sr_flip"
    elif h1["active_zones"] and any(
        z["type"] in ["supply", "demand"] for z in h1["active_zones"]
    ):
        setup_type = "supply_demand"
    elif h1["active_zones"]:
        # Check if it's a breakout retest
        h1_candles = candles["H1"]
        breakouts = detect_breakouts(h1_candles, h1["zones"])
        retested = [b for b in breakouts if b["retested"]]
        if retested:
            setup_type = "breakout_retest"
        else:
            setup_type = "zone_tap"

    # Entry confirmation: does M5 have a pattern?
    entry_confirmed = bool(m5["patterns"])
    entry_pattern   = m5["patterns"][0] if entry_confirmed else None

    # FVG summary across timeframes
    has_fvg_overlap = bool(h1["fvg_overlaps"] or m15["fvg_overlaps"])
    active_fvgs     = h1["fvgs"] + m15["fvgs"] + m5["fvgs"]

    return {
        "pair":             pair,
        "aligned":          aligned,
        "direction":        direction,
        "confidence":       confidence,
        "setup_type":       setup_type,
        "entry_confirmed":  entry_confirmed,
        "entry_pattern":    entry_pattern,
        "has_fvg_overlap":  has_fvg_overlap,
        "active_fvgs":      active_fvgs,
        "fvg_overlaps":     h1["fvg_overlaps"] + m15["fvg_overlaps"],
        "h1":               h1,
        "m15":              m15,
        "m5":               m5,
        "current_price":    m5["current_price"],
    }


def is_tradeable(confluence: dict) -> bool:
    """
    Final check: is this setup worth alerting?
    Requires:
    - H1 zone active (the anchor)
    - At least 2/3 TF agreement
    - M5 confirmation pattern
    """
    h1_zone_active = bool(confluence["h1"]["active_zones"])
    tf_agreement   = confluence["confidence"] >= 2
    entry_signal   = confluence["entry_confirmed"]

    return h1_zone_active and tf_agreement and entry_signal