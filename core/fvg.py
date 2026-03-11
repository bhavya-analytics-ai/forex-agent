"""
fvg.py — Fair Value Gap detection
Bullish FVG: gap between candle[i-2] high and candle[i] low (price moved up too fast)
Bearish FVG: gap between candle[i-2] low and candle[i] high (price moved down too fast)
"""

import pandas as pd
import logging

logger = logging.getLogger(__name__)


def detect_fvgs(df: pd.DataFrame) -> list:
    """
    Scan all candles and return list of FVGs.
    Each FVG has: type, top, bottom, mid, filled, formed_at, size
    """
    fvgs = []

    for i in range(2, len(df)):
        c1 = df.iloc[i - 2]  # First candle
        c2 = df.iloc[i - 1]  # Middle candle (the impulse)
        c3 = df.iloc[i]      # Third candle

        # Bullish FVG: c1 high < c3 low — gap left below price
        if c1["high"] < c3["low"]:
            fvg_top    = c3["low"]
            fvg_bottom = c1["high"]
            size       = fvg_top - fvg_bottom

            if size <= 0:
                continue

            fvgs.append({
                "type":      "bullish",
                "top":       fvg_top,
                "bottom":    fvg_bottom,
                "mid":       (fvg_top + fvg_bottom) / 2,
                "size":      size,
                "formed_at": df.index[i],
                "filled":    False,
                "partially_filled": False,
            })

        # Bearish FVG: c1 low > c3 high — gap left above price
        elif c1["low"] > c3["high"]:
            fvg_top    = c1["low"]
            fvg_bottom = c3["high"]
            size       = fvg_top - fvg_bottom

            if size <= 0:
                continue

            fvgs.append({
                "type":      "bearish",
                "top":       fvg_top,
                "bottom":    fvg_bottom,
                "mid":       (fvg_top + fvg_bottom) / 2,
                "size":      size,
                "formed_at": df.index[i],
                "filled":    False,
                "partially_filled": False,
            })

    # Check fill status using candles after each FVG formed
    fvgs = _check_fill_status(df, fvgs)

    # Return only unfilled/partial FVGs, most recent first
    active = [f for f in fvgs if not f["filled"]]
    active = sorted(active, key=lambda f: f["formed_at"], reverse=True)

    logger.debug(f"Found {len(active)} active FVGs ({len(fvgs)} total)")
    return active


def _check_fill_status(df: pd.DataFrame, fvgs: list) -> list:
    """
    For each FVG, check if subsequent candles have filled it.
    Filled = price traded through the entire gap.
    Partially filled = price entered the gap but didn't close it.
    """
    for fvg in fvgs:
        formed_idx = df.index.get_loc(fvg["formed_at"])
        subsequent = df.iloc[formed_idx + 1:]

        if subsequent.empty:
            continue

        if fvg["type"] == "bullish":
            # Filled when a candle's low trades into or below the gap bottom
            full_fill    = (subsequent["low"] <= fvg["bottom"]).any()
            partial_fill = (subsequent["low"] <= fvg["top"]).any()
        else:
            # Filled when a candle's high trades into or above the gap top
            full_fill    = (subsequent["high"] >= fvg["top"]).any()
            partial_fill = (subsequent["high"] >= fvg["bottom"]).any()

        fvg["filled"]           = full_fill
        fvg["partially_filled"] = partial_fill and not full_fill

    return fvgs


def get_active_fvgs(df: pd.DataFrame) -> list:
    """Return FVGs that price is currently inside or approaching."""
    fvgs          = detect_fvgs(df)
    current_price = df["close"].iloc[-1]
    atr           = df["high"].sub(df["low"]).rolling(14).mean().iloc[-1]
    proximity     = atr * 0.5  # Within half ATR = approaching

    active = []
    for fvg in fvgs:
        in_gap     = fvg["bottom"] <= current_price <= fvg["top"]
        near_gap   = abs(current_price - fvg["mid"]) <= proximity
        if in_gap or near_gap:
            fvg["price_inside"] = in_gap
            active.append(fvg)

    return active


def fvg_zone_overlap(fvgs: list, zones: list) -> list:
    """
    Find FVGs that overlap with existing S/R or supply/demand zones.
    These are premium setups — two confluences at same price.
    Returns list of overlapping pairs.
    """
    overlaps = []

    for fvg in fvgs:
        for zone in zones:
            # Check if FVG and zone share price range
            overlap_top    = min(fvg["top"], zone["high"])
            overlap_bottom = max(fvg["bottom"], zone["low"])

            if overlap_top > overlap_bottom:
                overlaps.append({
                    "fvg":          fvg,
                    "zone":         zone,
                    "overlap_top":  overlap_top,
                    "overlap_bottom": overlap_bottom,
                    "overlap_size": overlap_top - overlap_bottom,
                })

    return overlaps