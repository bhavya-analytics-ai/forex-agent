"""
candles.py — Candlestick pattern detection + momentum breakout detection

Patterns: engulfing, pin bar, inside bar, doji, momentum candle
New: detect_momentum_breakout — fires on big moves regardless of killzone
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
    body  = candle_body(candle)
    total = candle_range(candle)
    if total == 0:
        return {"detected": False}

    body_ratio = body / total
    if body_ratio > 0.40:
        return {"detected": False}

    l_wick = lower_wick(candle)
    u_wick = upper_wick(candle)

    if l_wick >= total * 0.55 and l_wick > u_wick * 1.5:
        if bias is None or bias == "bullish":
            return {
                "detected":    True,
                "pattern":     "pin_bar",
                "direction":   "bullish",
                "strength":    round((l_wick / total) * 100),
                "description": f"Bullish pin bar — long lower wick ({round(l_wick/total*100)}% of range), buyers rejecting lower prices",
            }

    if u_wick >= total * 0.55 and u_wick > l_wick * 1.5:
        if bias is None or bias == "bearish":
            return {
                "detected":    True,
                "pattern":     "pin_bar",
                "direction":   "bearish",
                "strength":    round((u_wick / total) * 100),
                "description": f"Bearish pin bar — long upper wick ({round(u_wick/total*100)}% of range), sellers rejecting higher prices",
            }

    return {"detected": False}


def detect_engulfing(prev: pd.Series, curr: pd.Series, bias: str = None) -> dict:
    prev_high = max(prev["open"], prev["close"])
    prev_low  = min(prev["open"], prev["close"])
    curr_high = max(curr["open"], curr["close"])
    curr_low  = min(curr["open"], curr["close"])

    prev_body = candle_body(prev)
    curr_body = candle_body(curr)

    if prev_body == 0 or curr_body == 0:
        return {"detected": False}

    overlap     = min(curr_high, prev_high) - max(curr_low, prev_low)
    overlap_pct = overlap / prev_body if prev_body > 0 else 0
    full_engulf = (curr_high > prev_high) and (curr_low < prev_low)
    near_engulf = overlap_pct >= 0.90 and curr_body > prev_body

    if not (full_engulf or near_engulf):
        return {"detected": False}

    size_ratio = curr_body / max(prev_body, 0.0001)

    if is_bearish(prev) and is_bullish(curr):
        if bias is None or bias == "bullish":
            return {
                "detected":    True,
                "pattern":     "engulfing",
                "direction":   "bullish",
                "strength":    min(round(size_ratio * 50), 100),
                "description": f"Bullish engulfing — buyers overwhelmed sellers, candle {round(size_ratio,1)}x size of previous",
            }

    if is_bullish(prev) and is_bearish(curr):
        if bias is None or bias == "bearish":
            return {
                "detected":    True,
                "pattern":     "engulfing",
                "direction":   "bearish",
                "strength":    min(round(size_ratio * 50), 100),
                "description": f"Bearish engulfing — sellers overwhelmed buyers, candle {round(size_ratio,1)}x size of previous",
            }

    return {"detected": False}


def detect_inside_bar(prev: pd.Series, curr: pd.Series) -> dict:
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
    body  = candle_body(candle)
    total = candle_range(candle)
    if total == 0:
        return {"detected": False}
    if body / total <= 0.10:
        return {
            "detected":    True,
            "pattern":     "doji",
            "direction":   "neutral",
            "strength":    60,
            "description": "Doji — market indecision at this level, reversal possible",
        }
    return {"detected": False}


def detect_momentum_candle(candle: pd.Series, df: pd.DataFrame) -> dict:
    body     = candle_body(candle)
    total    = candle_range(candle)
    avg_body = df["high"].sub(df["low"]).rolling(10).mean().iloc[-1]

    if body < avg_body * 1.5:
        return {"detected": False}

    if total > 0 and (candle["close"] - candle["low"]) / total >= 0.70:
        return {
            "detected":    True,
            "pattern":     "momentum_candle",
            "direction":   "bullish",
            "strength":    min(round((body / avg_body) * 30), 100),
            "description": f"Bullish momentum candle — {round(body/avg_body,1)}x avg size, closing near high",
        }

    if total > 0 and (candle["high"] - candle["close"]) / total >= 0.70:
        return {
            "detected":    True,
            "pattern":     "momentum_candle",
            "direction":   "bearish",
            "strength":    min(round((body / avg_body) * 30), 100),
            "description": f"Bearish momentum candle — {round(body/avg_body,1)}x avg size, closing near low",
        }

    return {"detected": False}


def detect_momentum_breakout(df_h1: pd.DataFrame, pair: str) -> dict:
    """
    Smart momentum breakout detection.
    Fires on BIG moves regardless of killzone — these are smart money moves.

    Triggers when:
    - Last 3 H1 candles contain one that is 2.5x+ ATR in size
    - Candle closes near its high/low (not a wick — real body move)
    - Consecutive candles moving same direction = even stronger

    Returns direction, ATR ratio, pips moved, candles ago, description.
    Used to fire alerts outside killzones when something major happens.
    """
    if len(df_h1) < 20:
        return {"detected": False}

    from core.fetcher import pip_size

    atr     = df_h1["high"].sub(df_h1["low"]).rolling(14).mean().iloc[-1]
    pip     = pip_size(pair)

    if atr == 0:
        return {"detected": False}

    best_breakout = None

    # Check last 3 candles
    for i in range(1, 4):
        candle     = df_h1.iloc[-i]
        body       = candle_body(candle)
        total      = candle_range(candle)
        atr_ratio  = body / atr

        if atr_ratio < 1.5:
            continue

        if total == 0:
            continue

        # Must close near high or low (body dominates, not a wick)
        close_pct = (candle["close"] - candle["low"]) / total

        if close_pct >= 0.65:
            direction = "bullish"
        elif close_pct <= 0.35:
            direction = "bearish"
        else:
            continue  # Indecision candle — skip

        pips_moved = round(body / pip, 1)

        # Check for consecutive candles same direction (stronger signal)
        consecutive = 1
        if i == 1 and len(df_h1) >= 3:
            prev1 = df_h1.iloc[-2]
            prev2 = df_h1.iloc[-3]
            if direction == "bullish":
                if is_bullish(prev1): consecutive += 1
                if is_bullish(prev2) and consecutive == 2: consecutive += 1
            else:
                if is_bearish(prev1): consecutive += 1
                if is_bearish(prev2) and consecutive == 2: consecutive += 1

        strength = min(round(atr_ratio * 20), 100)

        # Boost strength for consecutive candles
        if consecutive >= 3:
            strength = min(strength + 20, 100)
        elif consecutive == 2:
            strength = min(strength + 10, 100)

        result = {
            "detected":     True,
            "direction":    direction,
            "atr_ratio":    round(atr_ratio, 1),
            "pips_moved":   pips_moved,
            "candles_ago":  i - 1,
            "consecutive":  consecutive,
            "strength":     strength,
            "candle_high":  float(candle["high"]),
            "candle_low":   float(candle["low"]),
            "candle_close": float(candle["close"]),
        }

        # Keep the strongest breakout
        if best_breakout is None or atr_ratio > best_breakout["atr_ratio"]:
            best_breakout = result

    if best_breakout is None:
        return {"detected": False}

    # Build description
    direction   = best_breakout["direction"]
    atr_ratio   = best_breakout["atr_ratio"]
    pips_moved  = best_breakout["pips_moved"]
    consecutive = best_breakout["consecutive"]
    bars_ago    = best_breakout["candles_ago"]

    consec_str = f" ({consecutive} consecutive candles)" if consecutive > 1 else ""
    bars_str   = f" — {bars_ago} candle ago" if bars_ago > 0 else ""

    best_breakout["description"] = (
        f"{'🔴 BEARISH' if direction == 'bearish' else '🟢 BULLISH'} momentum breakout{bars_str} — "
        f"{atr_ratio}x ATR, {pips_moved} pips{consec_str}"
    )

    return best_breakout


def detect_consolidation(df: pd.DataFrame, lookback: int = 6) -> dict:
    if len(df) < lookback:
        return {"consolidating": False, "range_pct": 0}

    recent     = df.iloc[-lookback:]
    atr        = df["high"].sub(df["low"]).rolling(14).mean().iloc[-1]
    high_range = recent["high"].max() - recent["low"].min()
    range_pct  = high_range / atr if atr > 0 else 999
    consolidating = range_pct < 1.5

    return {
        "consolidating": consolidating,
        "range_pct":     round(range_pct, 2),
        "candles":       lookback,
        "note": "Price consolidating — wait for breakout direction" if consolidating else "Price moving freely",
    }


def detect_patterns(df: pd.DataFrame, bias: str = None) -> list:
    if len(df) < 3:
        return []

    patterns    = []
    check_range = min(4, len(df) - 1)

    for i in range(1, check_range + 1):
        curr = df.iloc[-i]
        prev = df.iloc[-i - 1]

        pin = detect_pin_bar(curr, bias=bias)
        if pin["detected"]:
            patterns.append({**pin, "candle_index": -i, "time": df.index[-i], "bars_ago": i - 1})

        eng = detect_engulfing(prev, curr, bias=bias)
        if eng["detected"]:
            patterns.append({**eng, "candle_index": -i, "time": df.index[-i], "bars_ago": i - 1})

        doji = detect_doji(curr)
        if doji["detected"]:
            patterns.append({**doji, "candle_index": -i, "time": df.index[-i], "bars_ago": i - 1})

        mom = detect_momentum_candle(curr, df)
        if mom["detected"]:
            patterns.append({**mom, "candle_index": -i, "time": df.index[-i], "bars_ago": i - 1})

        if i == 1:
            ib = detect_inside_bar(prev, curr)
            if ib["detected"]:
                patterns.append({**ib, "candle_index": -i, "time": df.index[-i], "bars_ago": 0})

    patterns.sort(key=lambda p: (p["bars_ago"], -p.get("strength", 0)))

    if bias:
        patterns = [p for p in patterns if p["direction"] == bias or p["direction"] == "neutral"]

    return patterns