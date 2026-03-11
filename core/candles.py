"""
candles.py — Candlestick pattern detection: engulfing, pin bar, inside bar
"""

import pandas as pd
import numpy as np


def candle_body(candle: pd.Series) -> float:
    return abs(candle["close"] - candle["open"])


def candle_range(candle: pd.Series) -> float:
    return candle["high"] - candle["low"]


def upper_wick(candle: pd.Series) -> float:
    return candle["high"] - max(candle["open"], candle["close"])


def lower_wick(candle: pd.Series) -> float:
    return min(candle["open"], candle["close"]) - candle["low"]


def is_bullish(candle: pd.Series) -> bool:
    return candle["close"] > candle["open"]


def is_bearish(candle: pd.Series) -> bool:
    return candle["close"] < candle["open"]


def detect_pin_bar(candle: pd.Series, bias: str = None) -> dict:
    """
    Pin bar: small body, long wick (at least 2/3 of total range).
    bias = 'bullish' (hammer) or 'bearish' (shooting star)
    """
    body  = candle_body(candle)
    total = candle_range(candle)

    if total == 0:
        return {"detected": False}

    body_ratio = body / total

    # Body must be small (< 35% of range)
    if body_ratio > 0.35:
        return {"detected": False}

    l_wick = lower_wick(candle)
    u_wick = upper_wick(candle)

    # Bullish pin bar: long lower wick (hammer)
    if l_wick >= total * 0.6 and (bias is None or bias == "bullish"):
        return {
            "detected":  True,
            "pattern":   "pin_bar",
            "direction": "bullish",
            "strength":  round((l_wick / total) * 100),
        }

    # Bearish pin bar: long upper wick (shooting star)
    if u_wick >= total * 0.6 and (bias is None or bias == "bearish"):
        return {
            "detected":  True,
            "pattern":   "pin_bar",
            "direction": "bearish",
            "strength":  round((u_wick / total) * 100),
        }

    return {"detected": False}


def detect_engulfing(prev: pd.Series, curr: pd.Series, bias: str = None) -> dict:
    """
    Engulfing: current candle's body fully engulfs previous candle's body.
    """
    prev_body_high = max(prev["open"], prev["close"])
    prev_body_low  = min(prev["open"], prev["close"])
    curr_body_high = max(curr["open"], curr["close"])
    curr_body_low  = min(curr["open"], curr["close"])

    engulfs = (curr_body_high > prev_body_high) and (curr_body_low < prev_body_low)

    if not engulfs:
        return {"detected": False}

    # Bullish engulfing: bearish prev, bullish curr
    if is_bearish(prev) and is_bullish(curr) and (bias is None or bias == "bullish"):
        size_ratio = candle_body(curr) / max(candle_body(prev), 0.0001)
        return {
            "detected":   True,
            "pattern":    "engulfing",
            "direction":  "bullish",
            "strength":   min(round(size_ratio * 50), 100),
        }

    # Bearish engulfing: bullish prev, bearish curr
    if is_bullish(prev) and is_bearish(curr) and (bias is None or bias == "bearish"):
        size_ratio = candle_body(curr) / max(candle_body(prev), 0.0001)
        return {
            "detected":   True,
            "pattern":    "engulfing",
            "direction":  "bearish",
            "strength":   min(round(size_ratio * 50), 100),
        }

    return {"detected": False}


def detect_inside_bar(prev: pd.Series, curr: pd.Series) -> dict:
    """
    Inside bar: current candle's high/low is within previous candle's range.
    Signals consolidation and potential breakout.
    """
    inside = (curr["high"] < prev["high"]) and (curr["low"] > prev["low"])

    if not inside:
        return {"detected": False}

    return {
        "detected":  True,
        "pattern":   "inside_bar",
        "direction": "neutral",  # Needs context for bias
        "strength":  50,
    }


def detect_patterns(df: pd.DataFrame, bias: str = None) -> list:
    """
    Run all pattern detections on the last few candles.
    Returns list of detected patterns (most recent first).
    bias: 'bullish' or 'bearish' — from zone context
    """
    if len(df) < 2:
        return []

    patterns = []
    last  = df.iloc[-1]
    prev  = df.iloc[-2]

    # Check current candle for pin bar
    pin = detect_pin_bar(last, bias=bias)
    if pin["detected"]:
        patterns.append({**pin, "candle_index": -1, "time": df.index[-1]})

    # Check engulfing (prev → last)
    eng = detect_engulfing(prev, last, bias=bias)
    if eng["detected"]:
        patterns.append({**eng, "candle_index": -1, "time": df.index[-1]})

    # Check inside bar
    ib = detect_inside_bar(prev, last)
    if ib["detected"]:
        patterns.append({**ib, "candle_index": -1, "time": df.index[-1]})

    # Also check 1 candle back for patterns that just formed
    if len(df) >= 3:
        prev2 = df.iloc[-3]
        pin2  = detect_pin_bar(prev, bias=bias)
        if pin2["detected"]:
            patterns.append({**pin2, "candle_index": -2, "time": df.index[-2]})

        eng2 = detect_engulfing(prev2, prev, bias=bias)
        if eng2["detected"]:
            patterns.append({**eng2, "candle_index": -2, "time": df.index[-2]})

    return patterns