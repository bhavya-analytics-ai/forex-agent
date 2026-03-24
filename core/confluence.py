"""
confluence.py — Multi-timeframe confluence engine

FIXES IN THIS VERSION:

1. ZONE OVERRIDE REMOVED
   Old: if price is at a resistance zone → bias = bearish (always)
        This completely ignored the H1 trend. A resistance zone during
        a massive uptrend would flip everything to bearish. WRONG.
   New: Zone type is a CONFIRMATION signal only. If H1 says uptrend and
        price hits resistance, that's flagged as a WARNING, not a direction
        flip. Zone can only confirm the existing trend, never override it.

2. H1 IS THE BOSS — WEIGHTED VOTE
   Old: H1, M15, M5 all had equal votes (1 each). 2 lower TFs could
        override H1 trend easily.
   New: H1 counts as 2 votes. M15 = 1 vote. M5 = 1 vote.
        So H1 bullish + M15 bearish + M5 bearish = 2 bull vs 2 bear = neutral
        H1 bullish + M15 bullish + M5 bearish = 3 bull vs 1 bear = bullish
        H1 must be overridden by BOTH lower TFs to flip direction.

3. ICT MSS/ChoCH WIRED INTO DIRECTION
   Old: ICT direction was calculated but never used to set direction.
        MSS bullish would show on dashboard but direction stayed bearish.
   New: ICT direction acts as a tiebreaker. If H1 and lower TFs are split,
        ICT MSS/ChoCH direction breaks the tie.
        If ICT strongly disagrees with direction (MSS bullish but signal
        is bearish), a conflict flag is raised for scorer to penalize.

4. SIGNAL STABILITY — 10 PIP LOCK
   Once a signal fires, store the entry price. Don't re-evaluate direction
   until price moves more than 10 pips away. Stops the 30s flip chaos.
"""

import logging
from core.zones import get_all_zones, get_active_zones, price_at_zone
from core.structure import detect_market_structure, detect_breakouts, detect_sr_flips
from core.candles import detect_patterns, detect_consolidation
from core.fvg import detect_fvgs, get_active_fvgs, fvg_zone_overlap
from core.fetcher import pip_size

logger = logging.getLogger(__name__)

# Signal stability store — prevents 30s flipping
# { pair: { "direction": str, "entry_price": float, "lock_pips": int } }
_signal_lock = {}


def _is_signal_locked(pair: str, current_price: float) -> bool:
    """
    Returns True if the current signal is locked and price hasn't moved
    enough to invalidate it. Prevents flip-flopping every 30 seconds.
    """
    lock = _signal_lock.get(pair)
    if not lock:
        return False

    pip    = pip_size(pair)
    locked_price = lock.get("entry_price", current_price)
    move_pips    = abs(current_price - locked_price) / pip

    # Unlock if price moved more than 10 pips from lock point
    if move_pips > 10:
        _signal_lock.pop(pair, None)
        return False

    return True


def _set_signal_lock(pair: str, direction: str, price: float):
    """Lock a signal at the current price to prevent flipping."""
    _signal_lock[pair] = {
        "direction":   direction,
        "entry_price": price,
        "lock_pips":   10,
    }


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


def analyze_timeframe(candles: dict, pair: str, timeframe: str) -> dict:
    """Analyze a single timeframe — structure, zones, patterns, FVGs."""
    df = candles.get(timeframe)
    if df is None or df.empty:
        return {
            "bias": "neutral", "zones": [], "patterns": [], "structure": {},
            "active_zones": [], "approaching_zones": [], "consolidation": {},
            "flips": [], "fvgs": [], "fvg_overlaps": [], "current_price": 0,
            "zone_conflict": False,
        }

    structure    = detect_market_structure(df)
    zones        = get_all_zones(df, pair)
    active_zones = get_active_zones(df, pair)
    approaching  = get_approaching_zones(df, pair, zones)
    consolidation = detect_consolidation(df)
    flips        = detect_sr_flips(df, zones)
    active_fvgs  = get_active_fvgs(df)
    fvg_overlaps = fvg_zone_overlap(active_fvgs, zones)

    # Step 1: Get the real trend bias from structure
    # This is the ground truth — what is price actually doing?
    trend_bias = structure.get("bias", "neutral")
    if trend_bias == "neutral":
        trend = structure.get("trend", "ranging")
        trend_bias = "bullish" if "up" in trend else ("bearish" if "down" in trend else "neutral")

    # Step 2: Check if price is at a zone
    zone_conflict = False
    zone_warning  = None

    if active_zones:
        top_zone  = active_zones[0]
        zone_type = top_zone["type"]

        # Determine what bias the zone SUGGESTS
        if zone_type in ["support", "demand", "resistance_to_support"]:
            zone_suggested_bias = "bullish"
        elif zone_type in ["resistance", "supply", "support_to_resistance"]:
            zone_suggested_bias = "bearish"
        else:
            zone_suggested_bias = None

        # FIX: Zone only CONFIRMS the trend, never overrides it
        # If zone agrees with trend → great, confirmation
        # If zone disagrees with trend → WARNING flag, but keep trend bias
        if zone_suggested_bias and zone_suggested_bias != trend_bias and trend_bias != "neutral":
            zone_conflict = True
            zone_warning  = (
                f"⚠️ Zone type ({zone_type}) suggests {zone_suggested_bias} "
                f"but H1 trend is {trend_bias} — zone is being tested, "
                f"watch for rejection or breakout"
            )
        # Only use zone bias if trend is neutral/ranging (no clear trend to follow)
        elif zone_suggested_bias and trend_bias == "neutral":
            trend_bias = zone_suggested_bias

    bias = trend_bias
    patterns = detect_patterns(df, bias=bias)

    return {
        "bias":              bias,
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
    Core confluence engine — analyzes H1, M15, M5.

    H1  = direction anchor (counts as 2 votes)
    M15 = confirmation (1 vote)
    M5  = entry trigger (1 vote)
    ICT = tiebreaker + conflict detector
    """
    h1  = analyze_timeframe(candles, pair, "H1")
    m15 = analyze_timeframe(candles, pair, "M15")
    m5  = analyze_timeframe(candles, pair, "M5")

    current_price = m5["current_price"] or h1["current_price"]

    # ICT context first — we need it for tiebreaking
    ict_context   = {}
    ict_direction = None
    try:
        from core.ict import get_ict_context
        ict_context   = get_ict_context(candles["H1"], candles["M15"], candles["M5"])
        ict_direction = ict_context.get("ict_direction")  # MSS/ChoCH based direction
    except Exception as e:
        logger.warning(f"ICT context failed: {e}")

    # WEIGHTED VOTE: H1 = 2 votes, M15 = 1, M5 = 1 (total 4 votes)
    h1_bias  = h1["bias"]
    m15_bias = m15["bias"]
    m5_bias  = m5["bias"]

    bullish_votes = (
        (2 if h1_bias  == "bullish" else 0) +
        (1 if m15_bias == "bullish" else 0) +
        (1 if m5_bias  == "bullish" else 0)
    )
    bearish_votes = (
        (2 if h1_bias  == "bearish" else 0) +
        (1 if m15_bias == "bearish" else 0) +
        (1 if m5_bias  == "bearish" else 0)
    )

    # Determine direction and confidence
    if bullish_votes >= 3 and bearish_votes == 0:
        direction, aligned, confidence = "bullish", True, 3
        tf_reading = "H1 + M15 + M5 all bullish — full alignment"

    elif bearish_votes >= 3 and bullish_votes == 0:
        direction, aligned, confidence = "bearish", True, 3
        tf_reading = "H1 + M15 + M5 all bearish — full alignment"

    elif bullish_votes >= 3:
        direction, aligned, confidence = "bullish", True, 3
        tf_reading = "Strong bullish — H1 leading, lower TFs partially aligned"

    elif bearish_votes >= 3:
        direction, aligned, confidence = "bearish", True, 3
        tf_reading = "Strong bearish — H1 leading, lower TFs partially aligned"

    elif bullish_votes == 2 and h1_bias == "bullish":
        # H1 bullish + one other = solid
        direction, aligned, confidence = "bullish", False, 2
        tf_reading = "H1 bullish confirmed — wait for M5 entry candle"

    elif bearish_votes == 2 and h1_bias == "bearish":
        direction, aligned, confidence = "bearish", False, 2
        tf_reading = "H1 bearish confirmed — wait for M5 entry candle"

    elif bullish_votes == bearish_votes:
        # TRUE TIE — use ICT direction as tiebreaker
        if ict_direction == "bullish":
            direction, aligned, confidence = "bullish", False, 1
            tf_reading = "Mixed TFs — ICT MSS/ChoCH bullish breaks the tie"
        elif ict_direction == "bearish":
            direction, aligned, confidence = "bearish", False, 1
            tf_reading = "Mixed TFs — ICT MSS/ChoCH bearish breaks the tie"
        else:
            # H1 anchor when truly no signal
            h1_phase = h1["structure"].get("phase", "")
            direction  = h1_bias if h1_bias != "neutral" else "none"
            aligned    = False
            confidence = 1 if direction != "none" else 0
            tf_reading = f"Mixed signals — using H1 anchor ({direction}). Wait for alignment."

    else:
        # H1 is the boss — use it
        direction  = h1_bias if h1_bias != "neutral" else "none"
        aligned    = False
        confidence = 1 if direction != "none" else 0
        h1_phase   = h1["structure"].get("phase", "")

        if h1_phase == "pullback" and direction != "none":
            tf_reading = (
                f"H1 in {direction} pullback — lower TFs still in pullback momentum. "
                f"EARLY STAGE. Wait for M5 rejection candle."
            )
        elif h1_phase == "trending":
            tf_reading = f"H1 trending {direction} — M15/M5 not aligned yet. Wait for M15."
        elif h1_phase == "structure_break":
            tf_reading = f"H1 structure break toward {direction}. HIGH RISK. Wait for M15."
        else:
            tf_reading = f"Mixed signals. H1 bias {direction}. Wait for alignment."

    # ICT CONFLICT CHECK
    # If ICT says one thing and our direction says another — that's important
    ict_conflict = False
    if ict_direction and direction not in ["none", "neutral"]:
        if ict_direction != direction:
            ict_conflict = True
            logger.warning(
                f"{pair} ICT CONFLICT: signal={direction} but ICT MSS/ChoCH={ict_direction}"
            )

    # Zone conflict warnings from H1
    zone_warnings = []
    if h1.get("zone_conflict") and h1.get("zone_warning"):
        zone_warnings.append(h1["zone_warning"])

    # Signal stability check — don't flip if price hasn't moved enough
    if _is_signal_locked(pair, current_price):
        locked = _signal_lock.get(pair, {})
        locked_dir = locked.get("direction", direction)
        if locked_dir != direction:
            logger.info(f"{pair} signal locked at {locked_dir}, ignoring flip to {direction}")
            direction = locked_dir

    # Lock new valid signals
    if direction not in ["none", "neutral"] and confidence >= 2:
        _set_signal_lock(pair, direction, current_price)

    # Consolidation check
    m5_consolidating   = m5["consolidation"].get("consolidating", False)
    consolidation_note = ""
    if m5_consolidating:
        consolidation_note = (
            f"⚠️ M5 consolidating — price chopping. Wait for directional breakout candle."
        )

    # Setup type
    setup_type = "none"
    if h1["flips"] or m15["flips"]:
        setup_type = "sr_flip"
    elif h1["active_zones"] and any(
        z["type"] in ["supply", "demand"] for z in h1["active_zones"]
    ):
        setup_type = "supply_demand"
    elif h1["active_zones"]:
        h1_candles = candles["H1"]
        retested   = [b for b in detect_breakouts(h1_candles, h1["zones"]) if b["retested"]]
        setup_type = "breakout_retest" if retested else "zone_tap"
    elif h1["approaching_zones"]:
        setup_type = "zone_approach"

    entry_confirmed = bool(m5["patterns"]) and not m5_consolidating
    entry_pattern   = m5["patterns"][0] if entry_confirmed else None

    approaching_warning = ""
    if h1["approaching_zones"] and not h1["active_zones"]:
        closest = h1["approaching_zones"][0]
        approaching_warning = (
            f"🔜 Price approaching {closest['type']} zone at {closest['mid']:.5f} "
            f"({closest['pips_away']} pips away) — get ready"
        )

    has_fvg_overlap = bool(h1["fvg_overlaps"] or m15["fvg_overlaps"])
    active_fvgs     = h1["fvgs"] + m15["fvgs"] + m5["fvgs"]

    return {
        "pair":                pair,
        "aligned":             aligned,
        "direction":           direction,
        "confidence":          confidence,
        "tf_reading":          tf_reading,
        "consolidation_note":  consolidation_note,
        "approaching_warning": approaching_warning,
        "setup_type":          setup_type,
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