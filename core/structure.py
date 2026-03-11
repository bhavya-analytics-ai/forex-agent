"""
structure.py — Swing highs/lows, breakouts, S/R flips
"""

import pandas as pd
import numpy as np
import logging
from config import ZONE_CONFIG

logger = logging.getLogger(__name__)
LOOKBACK = ZONE_CONFIG["swing_lookback"]


def find_swing_highs(df: pd.DataFrame) -> pd.Series:
    """
    Identify swing highs — bars where high is highest in lookback window each side.
    Returns boolean Series.
    """
    highs = df["high"]
    is_swing_high = pd.Series(False, index=df.index)

    for i in range(LOOKBACK, len(df) - LOOKBACK):
        window = highs.iloc[i - LOOKBACK: i + LOOKBACK + 1]
        if highs.iloc[i] == window.max():
            is_swing_high.iloc[i] = True

    return is_swing_high


def find_swing_lows(df: pd.DataFrame) -> pd.Series:
    """
    Identify swing lows — bars where low is lowest in lookback window each side.
    Returns boolean Series.
    """
    lows = df["low"]
    is_swing_low = pd.Series(False, index=df.index)

    for i in range(LOOKBACK, len(df) - LOOKBACK):
        window = lows.iloc[i - LOOKBACK: i + LOOKBACK + 1]
        if lows.iloc[i] == window.min():
            is_swing_low.iloc[i] = True

    return is_swing_low


def get_swing_points(df: pd.DataFrame) -> dict:
    """
    Return all swing highs and lows with their prices and timestamps.
    """
    swing_highs_mask = find_swing_highs(df)
    swing_lows_mask  = find_swing_lows(df)

    swing_highs = df[swing_highs_mask][["high"]].rename(columns={"high": "price"})
    swing_highs["type"] = "high"

    swing_lows = df[swing_lows_mask][["low"]].rename(columns={"low": "price"})
    swing_lows["type"] = "low"

    all_swings = pd.concat([swing_highs, swing_lows]).sort_index()

    return {
        "highs": swing_highs,
        "lows":  swing_lows,
        "all":   all_swings,
    }


def detect_market_structure(df: pd.DataFrame) -> dict:
    """
    Determine if market is in uptrend, downtrend, or ranging.
    Based on sequence of swing highs and lows.
    - Uptrend:   Higher Highs + Higher Lows
    - Downtrend: Lower Highs + Lower Lows
    - Ranging:   mixed
    """
    swings = get_swing_points(df)
    highs = swings["highs"]["price"].values[-4:]  # Last 4 swing highs
    lows  = swings["lows"]["price"].values[-4:]   # Last 4 swing lows

    if len(highs) < 2 or len(lows) < 2:
        return {"trend": "unknown", "strength": 0}

    hh = all(highs[i] > highs[i-1] for i in range(1, len(highs)))
    hl = all(lows[i]  > lows[i-1]  for i in range(1, len(lows)))
    lh = all(highs[i] < highs[i-1] for i in range(1, len(highs)))
    ll = all(lows[i]  < lows[i-1]  for i in range(1, len(lows)))

    if hh and hl:
        trend = "uptrend"
        strength = 3
    elif lh and ll:
        trend = "downtrend"
        strength = 3
    elif hh or hl:
        trend = "weak_uptrend"
        strength = 1
    elif lh or ll:
        trend = "weak_downtrend"
        strength = 1
    else:
        trend = "ranging"
        strength = 0

    return {"trend": trend, "strength": strength}


def detect_breakouts(df: pd.DataFrame, zones: list) -> list:
    """
    Check if price has recently broken above/below any zone.
    A breakout = close beyond zone boundary with momentum.
    Returns list of breakout events.
    """
    breakouts = []
    recent = df.iloc[-10:]  # Last 10 candles
    current_price = df["close"].iloc[-1]

    for zone in zones:
        zone_high = zone["high"]
        zone_low  = zone["low"]
        zone_mid  = (zone_high + zone_low) / 2

        # Bullish breakout: close above zone high
        broken_up = recent[recent["close"] > zone_high]
        if not broken_up.empty:
            first_break = broken_up.index[0]
            candles_ago = len(df) - df.index.get_loc(first_break)
            breakouts.append({
                "zone":        zone,
                "direction":   "bullish",
                "break_price": zone_high,
                "break_time":  first_break,
                "candles_ago": candles_ago,
                "retested":    current_price <= zone_high * 1.001,  # Within 0.1% = retest
            })

        # Bearish breakout: close below zone low
        broken_down = recent[recent["close"] < zone_low]
        if not broken_down.empty:
            first_break = broken_down.index[0]
            candles_ago = len(df) - df.index.get_loc(first_break)
            breakouts.append({
                "zone":        zone,
                "direction":   "bearish",
                "break_price": zone_low,
                "break_time":  first_break,
                "candles_ago": candles_ago,
                "retested":    current_price >= zone_low * 0.999,
            })

    return breakouts


def detect_sr_flips(df: pd.DataFrame, zones: list) -> list:
    """
    S/R Flip: old resistance becomes support (price breaks above, retests from top)
              old support becomes resistance (price breaks below, retests from below)
    Returns list of active flips.
    """
    flips = []
    current_price = df["close"].iloc[-1]

    breakouts = detect_breakouts(df, zones)

    for bo in breakouts:
        if not bo["retested"]:
            continue

        zone = bo["zone"]

        if bo["direction"] == "bullish":
            # Old resistance flipped to support — look for long setup
            flips.append({
                "zone":      zone,
                "flip_type": "resistance_to_support",
                "bias":      "bullish",
                "level":     bo["break_price"],
                "candles_ago": bo["candles_ago"],
            })

        elif bo["direction"] == "bearish":
            # Old support flipped to resistance — look for short setup
            flips.append({
                "zone":      zone,
                "flip_type": "support_to_resistance",
                "bias":      "bearish",
                "level":     bo["break_price"],
                "candles_ago": bo["candles_ago"],
            })

    return flips