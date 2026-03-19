"""
candles.py — Candlestick pattern detection
Patterns: engulfing, pin bar, inside bar, doji, momentum candle
Key fix: looser thresholds, check last 5 candles not just 2
"""

import pandas as pd
import numpy as np


def candle_body(c): return abs(c["close"] - c["open"])
def candle_range(c): return c["high"] - c["low"]
def upper_wick(c): return c["high"] - max(c["open"], c["close"])
def lower_wick(c): return min(c["open"], c["close"]) - c["low"]
def is_bullish(c): return c["close"] > c["open"]
def is_bearish(c): return c["close"] < c["open"]


def detect_pin_bar(candle: pd.Series, bias: str = None) -> dict:
    """
    Pin bar: small body with long wick.
    Loosened threshold: body < 40% of range, wick >= 55% of range.
    """
    body  = candle_body(candle)
    total = candle_range(candle)
    if total == 0:
        return {"detected": False}

    body_ratio = body / total
    if body_ratio > 0.40:  # loosened from 0.35
        return {"detected": False}

    l_wick = lower_wick(candle)
    u_wick = upper_wick(candle)

    # Bullish pin bar (hammer): long lower wick
    if l_wick >= total * 0.55 and l_wick > u_wick * 1.5:
        if bias is None or bias == "bullish":
            return {
                "detected":  True,
                "pattern":   "pin_bar",
                "direction": "bullish",
                "strength":  round((l_wick / total) * 100),
                "description": f"Bullish pin bar — long lower wick ({round(l_wick/total*100)}% of range), buyers rejecting lower prices",
            }

    # Bearish pin bar (shooting star): long upper wick
    if u_wick >= total * 0.55 and u_wick > l_wick * 1.5:
        if bias is None or bias == "bearish":
            return {
                "detected":  True,
                "pattern":   "pin_bar",
                "direction": "bearish",
                "strength":  round((u_wick / total) * 100),
                "description": f"Bearish pin bar — long upper wick ({round(u_wick/total*100)}% of range), sellers rejecting higher prices",
            }

    return {"detected": False}


def detect_engulfing(prev: pd.Series, curr: pd.Series, bias: str = None) -> dict:
    """
    Engulfing: current body fully covers previous body.
    Also catches near-engulfing (90% overlap) which is equally valid.
    """
    prev_high = max(prev["open"], prev["close"])
    prev_low  = min(prev["open"], prev["close"])
    curr_high = max(curr["open"], curr["close"])
    curr_low  = min(curr["open"], curr["close"])

    prev_body = candle_body(prev)
    curr_body = candle_body(curr)

    if prev_body == 0 or curr_body == 0:
        return {"detected": False}

    # Full engulf or near-engulf (curr covers 90%+ of prev body)
    overlap = min(curr_high, prev_high) - max(curr_low, prev_low)
    overlap_pct = overlap / prev_body if prev_body > 0 else 0

    full_engulf = (curr_high > prev_high) and (curr_low < prev_low)
    near_engulf = overlap_pct >= 0.90 and curr_body > prev_body

    if not (full_engulf or near_engulf):
        return {"detected": False}

    size_ratio = curr_body / max(prev_body, 0.0001)

    # Bullish engulfing
    if is_bearish(prev) and is_bullish(curr):
        if bias is None or bias == "bullish":
            return {
                "detected":   True,
                "pattern":    "engulfing",
                "direction":  "bullish",
                "strength":   min(round(size_ratio * 50), 100),
                "description": f"Bullish engulfing — buyers overwhelmed sellers, candle {round(size_ratio,1)}x size of previous",
            }

    # Bearish engulfing
    if is_bullish(prev) and is_bearish(curr):
        if bias is None or bias == "bearish":
            return {
                "detected":   True,
                "pattern":    "engulfing",
                "direction":  "bearish",
                "strength":   min(round(size_ratio * 50), 100),
                "description": f"Bearish engulfing — sellers overwhelmed buyers, candle {round(size_ratio,1)}x size of previous",
            }

    return {"detected": False}


def detect_inside_bar(prev: pd.Series, curr: pd.Series) -> dict:
    """Inside bar: consolidation before breakout."""
    inside = (curr["high"] <= prev["high"]) and (curr["low"] >= prev["low"])
    if not inside:
        return {"detected": False}
    return {
        "detected":    True,
        "pattern":     "inside_bar",
        "direction":   "neutral",
        "strength":    50,
        "description": "Inside bar — consolidation, watch for breakout direction",
    }


def detect_doji(candle: pd.Series) -> dict:
    """
    Doji: open ≈ close, indecision candle at a zone = potential reversal.
    """
    body  = candle_body(candle)
    total = candle_range(candle)
    if total == 0:
        return {"detected": False}

    if body / total <= 0.10:  # body is less than 10% of range
        return {
            "detected":    True,
            "pattern":     "doji",
            "direction":   "neutral",
            "strength":    60,
            "description": "Doji — market indecision at this level, reversal possible",
        }
    return {"detected": False}


def detect_momentum_candle(candle: pd.Series, df: pd.DataFrame) -> dict:
    """
    Momentum candle: large body (>1.5x avg) closing near its high/low.
    Signals strong directional move — confirms breakout or continuation.
    """
    body     = candle_body(candle)
    total    = candle_range(candle)
    avg_body = df["high"].sub(df["low"]).rolling(10).mean().iloc[-1]

    if body < avg_body * 1.5:
        return {"detected": False}

    # Close near high = bullish momentum
    if total > 0 and (candle["close"] - candle["low"]) / total >= 0.70:
        return {
            "detected":    True,
            "pattern":     "momentum_candle",
            "direction":   "bullish",
            "strength":    min(round((body / avg_body) * 30), 100),
            "description": f"Bullish momentum candle — {round(body/avg_body,1)}x avg size, closing near high",
        }

    # Close near low = bearish momentum
    if total > 0 and (candle["high"] - candle["close"]) / total >= 0.70:
        return {
            "detected":    True,
            "pattern":     "momentum_candle",
            "direction":   "bearish",
            "strength":    min(round((body / avg_body) * 30), 100),
            "description": f"Bearish momentum candle — {round(body/avg_body,1)}x avg size, closing near low",
        }

    return {"detected": False}


def detect_consolidation(df: pd.DataFrame, lookback: int = 6) -> dict:
    """
    Detect if price is currently consolidating (ranging) on a zone.
    Consolidation = last N candles have tight range relative to ATR.
    This is important — consolidating at a zone is NOT an entry signal.
    """
    if len(df) < lookback:
        return {"consolidating": False, "range_pct": 0}

    recent     = df.iloc[-lookback:]
    atr        = df["high"].sub(df["low"]).rolling(14).mean().iloc[-1]
    high_range = recent["high"].max() - recent["low"].min()
    range_pct  = high_range / atr if atr > 0 else 999

    # Consolidating if range of last 6 candles < 1.5x ATR
    consolidating = range_pct < 1.5

    return {
        "consolidating": consolidating,
        "range_pct":     round(range_pct, 2),
        "candles":       lookback,
        "note":          "Price consolidating — wait for breakout direction" if consolidating else "Price moving freely",
    }


def detect_patterns(df: pd.DataFrame, bias: str = None) -> list:
    """
    Run all pattern detections on the last 5 candles.
    Returns list of detected patterns sorted by recency and strength.
    """
    if len(df) < 3:
        return []

    patterns = []

    # Check last 4 candles for patterns
    check_range = min(4, len(df) - 1)

    for i in range(1, check_range + 1):
        curr = df.iloc[-i]
        prev = df.iloc[-i - 1]

        # Pin bar on current candle
        pin = detect_pin_bar(curr, bias=bias)
        if pin["detected"]:
            patterns.append({**pin, "candle_index": -i, "time": df.index[-i], "bars_ago": i - 1})

        # Engulfing (prev → curr)
        eng = detect_engulfing(prev, curr, bias=bias)
        if eng["detected"]:
            patterns.append({**eng, "candle_index": -i, "time": df.index[-i], "bars_ago": i - 1})

        # Doji
        doji = detect_doji(curr)
        if doji["detected"]:
            patterns.append({**doji, "candle_index": -i, "time": df.index[-i], "bars_ago": i - 1})

        # Momentum candle
        mom = detect_momentum_candle(curr, df)
        if mom["detected"]:
            patterns.append({**mom, "candle_index": -i, "time": df.index[-i], "bars_ago": i - 1})

        # Inside bar (only check most recent)
        if i == 1:
            ib = detect_inside_bar(prev, curr)
            if ib["detected"]:
                patterns.append({**ib, "candle_index": -i, "time": df.index[-i], "bars_ago": 0})

    # Sort: most recent first, then by strength
    patterns.sort(key=lambda p: (p["bars_ago"], -p.get("strength", 0)))

    # Filter to bias if provided — keep neutral patterns too
    if bias:
        patterns = [p for p in patterns if p["direction"] == bias or p["direction"] == "neutral"]

    return patterns