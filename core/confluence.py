"""
confluence.py — Multi-timeframe confluence engine
H1 = structure anchor, M15 = confirmation, M5 = entry trigger
"""

import logging
from core.zones import get_all_zones, get_active_zones, price_at_zone
from core.structure import detect_market_structure, detect_breakouts, detect_sr_flips
from core.candles import detect_patterns, detect_consolidation
from core.fvg import detect_fvgs, get_active_fvgs, fvg_zone_overlap
from core.fetcher import pip_size

logger = logging.getLogger(__name__)


def get_approaching_zones(df, pair: str, zones: list, pip_buffer: int = 15) -> list:
    """
    Find zones price is approaching but not yet at.
    Fires early warning so trader is ready before price arrives.
    pip_buffer: how many pips away = 'approaching'
    """
    current_price = df["close"].iloc[-1]
    pip           = pip_size(pair)
    buffer        = pip_buffer * pip
    approaching   = []

    for zone in zones:
        # Already at zone — skip (handled by active_zones)
        if price_at_zone(current_price, zone, pair):
            continue

        dist_to_high = abs(current_price - zone["high"])
        dist_to_low  = abs(current_price - zone["low"])
        min_dist     = min(dist_to_high, dist_to_low)

        if min_dist <= buffer:
            pips_away = round(min_dist / pip)
            approaching.append({
                **zone,
                "pips_away":   pips_away,
                "approaching_from": "below" if current_price < zone["low"] else "above",
            })

    return sorted(approaching, key=lambda z: z["pips_away"])


def analyze_timeframe(candles: dict, pair: str, timeframe: str) -> dict:
    """Analyze a single timeframe — structure, zones, patterns, FVGs."""
    df = candles[timeframe]
    if df.empty:
        return {"bias": "neutral", "zones": [], "patterns": [], "structure": {},
                "active_zones": [], "approaching_zones": [], "consolidation": {},
                "flips": [], "fvgs": [], "fvg_overlaps": [], "current_price": 0}

    structure    = detect_market_structure(df)
    zones        = get_all_zones(df, pair)
    active_zones = get_active_zones(df, pair)
    approaching  = get_approaching_zones(df, pair, zones)
    consolidation = detect_consolidation(df)
    flips        = detect_sr_flips(df, zones)
    active_fvgs  = get_active_fvgs(df)
    fvg_overlaps = fvg_zone_overlap(active_fvgs, zones)

    # Phase-aware bias — this is the key
    bias = structure.get("bias", "neutral")
    if bias == "neutral":
        trend = structure.get("trend", "ranging")
        bias  = "bullish" if "up" in trend else ("bearish" if "down" in trend else "neutral")

    # Zone context overrides when price is AT a zone
    zone_bias = None
    if active_zones:
        top_zone = active_zones[0]
        if top_zone["type"] in ["support", "demand", "resistance_to_support"]:
            zone_bias = "bullish"
        elif top_zone["type"] in ["resistance", "supply", "support_to_resistance"]:
            zone_bias = "bearish"
        bias = zone_bias or bias

    patterns = detect_patterns(df, bias=bias)

    return {
        "bias":             bias,
        "zones":            zones,
        "active_zones":     active_zones,
        "approaching_zones": approaching,
        "consolidation":    consolidation,
        "patterns":         patterns,
        "structure":        structure,
        "flips":            flips,
        "fvgs":             active_fvgs,
        "fvg_overlaps":     fvg_overlaps,
        "current_price":    df["close"].iloc[-1],
    }


def check_confluence(candles: dict, pair: str) -> dict:
    """
    Core confluence engine — analyzes H1, M15, M5.

    Smart logic:
    - H1 is always the anchor for direction
    - M15 confirms the move is starting
    - M5 provides entry trigger (pattern)
    - Consolidation on M5 = wait, not enter
    - Zone approach = early warning, not entry
    """
    h1  = analyze_timeframe(candles, pair, "H1")
    m15 = analyze_timeframe(candles, pair, "M15")
    m5  = analyze_timeframe(candles, pair, "M5")

    biases        = [h1["bias"], m15["bias"], m5["bias"]]
    bullish_count = biases.count("bullish")
    bearish_count = biases.count("bearish")

    if bullish_count == 3:
        direction, aligned, confidence = "bullish", True, 3
        tf_reading = "H1 + M15 + M5 all bullish — full alignment, momentum entry opportunity"
    elif bearish_count == 3:
        direction, aligned, confidence = "bearish", True, 3
        tf_reading = "H1 + M15 + M5 all bearish — full alignment, momentum entry opportunity"
    elif bullish_count == 2:
        direction, aligned, confidence = "bullish", False, 2
        tf_reading = "H1 + one lower TF bullish — good timing, wait for M5 confirmation candle"
    elif bearish_count == 2:
        direction, aligned, confidence = "bearish", False, 2
        tf_reading = "H1 + one lower TF bearish — good timing, wait for M5 confirmation candle"
    else:
        # Fall back to H1 anchor
        h1_bias      = h1["structure"].get("bias", "neutral")
        h1_phase     = h1["structure"].get("phase", "")
        h1_zone_bias = None

        if h1["active_zones"]:
            top_zone = h1["active_zones"][0]
            if top_zone["type"] in ["support", "demand", "resistance_to_support"]:
                h1_zone_bias = "bullish"
            elif top_zone["type"] in ["resistance", "supply", "support_to_resistance"]:
                h1_zone_bias = "bearish"

        direction  = h1_zone_bias or h1_bias or "none"
        aligned    = False
        confidence = 1 if direction != "none" else 0

        if h1_phase == "pullback" and direction != "none":
            tf_reading = (
                f"H1 in {direction} pullback at zone — M15/M5 still in pullback momentum. "
                f"EARLY STAGE setup. Watch M5 for rejection candle before entering."
            )
        elif h1_phase == "trending" and direction != "none":
            tf_reading = (
                f"H1 trending {direction} but M15/M5 not aligned yet. "
                f"Possible late entry. Wait for M15 to confirm before acting."
            )
        elif h1_phase == "structure_break":
            tf_reading = (
                f"H1 structure break — trend possibly changing to {direction}. "
                f"HIGH RISK. Wait for M15 confirmation before any entry."
            )
        elif h1_phase == "ranging":
            tf_reading = (
                f"H1 ranging — price at zone extreme, bias {direction}. "
                f"Range trade only. Tight SL, TP at range midpoint."
            )
        else:
            tf_reading = f"Mixed signals. H1 bias {direction}. Proceed with caution, wait for alignment."

    # Consolidation check — if M5 is consolidating at zone, it's not an entry yet
    m5_consolidating = m5["consolidation"].get("consolidating", False)
    consolidation_note = ""
    if m5_consolidating:
        consolidation_note = (
            f"⚠️ M5 consolidating (range = {m5['consolidation'].get('range_pct','?')}x ATR) — "
            f"price is chopping on the zone. Wait for a clear breakout candle before entering."
        )

    # Setup type
    setup_type = "none"
    if h1["flips"] or m15["flips"]:
        setup_type = "sr_flip"
    elif h1["active_zones"] and any(z["type"] in ["supply", "demand"] for z in h1["active_zones"]):
        setup_type = "supply_demand"
    elif h1["active_zones"]:
        h1_candles = candles["H1"]
        retested   = [b for b in detect_breakouts(h1_candles, h1["zones"]) if b["retested"]]
        setup_type = "breakout_retest" if retested else "zone_tap"
    elif h1["approaching_zones"]:
        setup_type = "zone_approach"

    # Entry confirmation from M5
    entry_confirmed = bool(m5["patterns"]) and not m5_consolidating
    entry_pattern   = m5["patterns"][0] if entry_confirmed else None

    # Zone approach warning
    approaching_warning = ""
    if h1["approaching_zones"] and not h1["active_zones"]:
        closest = h1["approaching_zones"][0]
        approaching_warning = (
            f"🔜 Price approaching {closest['type']} zone at {closest['mid']:.3f} "
            f"({closest['pips_away']} pips away) — get ready"
        )

    # FVG
    has_fvg_overlap = bool(h1["fvg_overlaps"] or m15["fvg_overlaps"])
    active_fvgs     = h1["fvgs"] + m15["fvgs"] + m5["fvgs"]

    return {
        "pair":                 pair,
        "aligned":              aligned,
        "direction":            direction,
        "confidence":           confidence,
        "tf_reading":           tf_reading,
        "consolidation_note":   consolidation_note,
        "approaching_warning":  approaching_warning,
        "setup_type":           setup_type,
        "entry_confirmed":      entry_confirmed,
        "entry_pattern":        entry_pattern,
        "has_fvg_overlap":      has_fvg_overlap,
        "active_fvgs":          active_fvgs,
        "fvg_overlaps":         h1["fvg_overlaps"] + m15["fvg_overlaps"],
        "h1":                   h1,
        "m15":                  m15,
        "m5":                   m5,
        "current_price":        m5["current_price"],
    }


def is_tradeable(confluence: dict) -> bool:
    h1_zone_active = bool(confluence["h1"]["active_zones"])
    tf_agreement   = confluence["confidence"] >= 2
    entry_signal   = confluence["entry_confirmed"]
    not_consolidating = not confluence["h1"]["consolidation"].get("consolidating", False)
    return h1_zone_active and tf_agreement and entry_signal and not_consolidating