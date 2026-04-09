"""
structure.py — Market structure analysis

Uses adaptive lookback per timeframe:
- H1:  lookback=10 bars each side
- M15: lookback=6
- M5:  lookback=4
- M1:  lookback=3

BUG FIXES:
1. Strict 3-candle rule — candle must be higher/lower than 3 bars EACH side
2. Last 4 clean swings only for trend vote (not 6)
3. Last 2 swings weighted 2x — recent structure matters more
"""

import pandas as pd
import numpy as np
import logging
from config import ZONE_CONFIG

logger = logging.getLogger(__name__)


def get_lookback_for_tf(df: pd.DataFrame) -> int:
    """
    Adaptive lookback based on candle count.
    H1 (200 candles) → 5
    M15 (100 candles) → 4
    M5 (60 candles)  → 3
    M1 (60 candles)  → 2

    Reduced from 10/6/4/3 — previous values were too strict,
    causing recent swings (last 10 bars) to be invisible to the system.
    """
    n = len(df)
    if n >= 150:
        return 5
    elif n >= 80:
        return 4
    elif n >= 50:
        return 3
    else:
        return 2


def find_swing_highs(df: pd.DataFrame) -> pd.Series:
    """
    Strict swing high: candle high must be strictly greater than
    ALL candles within lookback on BOTH sides (3-candle minimum each side).
    No ties allowed — must be the undisputed highest point.
    """
    lb     = get_lookback_for_tf(df)
    highs  = df["high"]
    result = pd.Series(False, index=df.index)

    for i in range(lb, len(df) - lb):
        pivot = highs.iloc[i]

        # Must be strictly greater than all bars on left AND right
        left_ok  = all(pivot > highs.iloc[j] for j in range(i - lb, i))
        right_ok = all(pivot > highs.iloc[j] for j in range(i + 1, i + lb + 1))

        if left_ok and right_ok:
            result.iloc[i] = True

    return result


def find_swing_lows(df: pd.DataFrame) -> pd.Series:
    """
    Strict swing low: candle low must be strictly less than
    ALL candles within lookback on BOTH sides.
    """
    lb     = get_lookback_for_tf(df)
    lows   = df["low"]
    result = pd.Series(False, index=df.index)

    for i in range(lb, len(df) - lb):
        pivot = lows.iloc[i]

        left_ok  = all(pivot < lows.iloc[j] for j in range(i - lb, i))
        right_ok = all(pivot < lows.iloc[j] for j in range(i + 1, i + lb + 1))

        if left_ok and right_ok:
            result.iloc[i] = True

    return result


def get_swing_points(df: pd.DataFrame) -> dict:
    sh         = df[find_swing_highs(df)][["high"]].rename(columns={"high": "price"})
    sh["type"] = "high"
    sl         = df[find_swing_lows(df)][["low"]].rename(columns={"low": "price"})
    sl["type"] = "low"
    return {
        "highs": sh,
        "lows":  sl,
        "all":   pd.concat([sh, sl]).sort_index(),
    }


def detect_dominant_trend(df: pd.DataFrame) -> dict:
    """
    Trend from last 4 swing highs and 4 swing lows.
    Last 2 swings counted 2x (recency weighting).

    Uptrend:   weighted 66%+ higher highs AND higher lows
    Downtrend: weighted 66%+ lower highs AND lower lows
    Weak:      50%+ one side
    Ranging:   mixed
    """
    swings = get_swing_points(df)

    # Use last 6 clean swings only
    highs = swings["highs"]["price"].values[-6:]
    lows  = swings["lows"]["price"].values[-6:]

    if len(highs) < 2 or len(lows) < 2:
        return {
            "trend":     "ranging",
            "strength":  1,
            "last_high": float(df["high"].max()),
            "last_low":  float(df["low"].min()),
            "prev_high": float(df["high"].max()),
            "prev_low":  float(df["low"].min()),
        }

    def weighted_vote(values, direction="up"):
        """
        Compare consecutive pairs. Last pair counts 2x.
        direction='up'  → count how many are rising
        direction='down'→ count how many are falling
        """
        total_weight  = 0
        winning_weight = 0

        for i in range(1, len(values)):
            # Last comparison (most recent) gets weight 2, older get weight 1
            weight = 2 if i == len(values) - 1 else 1
            total_weight += weight

            if direction == "up" and values[i] > values[i - 1]:
                winning_weight += weight
            elif direction == "down" and values[i] < values[i - 1]:
                winning_weight += weight

        return winning_weight / total_weight if total_weight > 0 else 0

    hh_pct = weighted_vote(highs, "up")    # Higher highs
    lh_pct = weighted_vote(highs, "down")  # Lower highs
    hl_pct = weighted_vote(lows,  "up")    # Higher lows
    ll_pct = weighted_vote(lows,  "down")  # Lower lows

    if hh_pct >= 0.66 and hl_pct >= 0.66:
        trend, strength = "uptrend", 3
    elif lh_pct >= 0.66 and ll_pct >= 0.66:
        trend, strength = "downtrend", 3
    elif hh_pct >= 0.50 and hl_pct >= 0.50:
        trend, strength = "weak_uptrend", 2
    elif lh_pct >= 0.50 and ll_pct >= 0.50:
        trend, strength = "weak_downtrend", 2
    else:
        trend, strength = "ranging", 1

    return {
        "trend":     trend,
        "strength":  strength,
        "last_high": float(highs[-1]),
        "last_low":  float(lows[-1]),
        "prev_high": float(highs[-2]) if len(highs) >= 2 else float(highs[-1]),
        "prev_low":  float(lows[-2])  if len(lows)  >= 2 else float(lows[-1]),
    }


def detect_current_phase(df: pd.DataFrame, dominant: dict) -> dict:
    """
    What is price doing RIGHT NOW vs the dominant trend?

    Uptrend + below last high  → pullback (look for longs)
    Downtrend + above last low → pullback (look for shorts)
    Broke last swing low in uptrend   → structure break
    Broke last swing high in downtrend → structure break
    """
    trend         = dominant.get("trend", "ranging")
    last_high     = dominant.get("last_high")
    last_low      = dominant.get("last_low")
    prev_high     = dominant.get("prev_high", last_high)
    prev_low      = dominant.get("prev_low",  last_low)
    current_price = df["close"].iloc[-1]
    atr           = df["high"].sub(df["low"]).rolling(14).mean().iloc[-1]

    if last_high is None or last_low is None or atr == 0:
        return {
            "phase":         "ranging",
            "bias":          "neutral",
            "pullback_depth": 0.5,
            "current_price": current_price,
            "last_high":     float(df["high"].max()),
            "last_low":      float(df["low"].min()),
        }

    pullback_depth = 0.5

    if "up" in trend:
        trend_range = last_high - (prev_low or last_low)

        if current_price < last_low - atr * 0.5:
            phase, bias = "structure_break", "bearish"
        elif current_price >= last_high - atr * 0.5:
            phase, bias = "trending", "bullish"
        else:
            if trend_range > 0:
                pullback_depth = (last_high - current_price) / trend_range
                pullback_depth = max(0.0, min(pullback_depth, 1.0))
            phase = "deep_pullback" if pullback_depth > 0.72 else "pullback"
            bias  = "neutral" if pullback_depth > 0.72 else "bullish"

    elif "down" in trend:
        trend_range = (prev_high or last_high) - last_low

        if current_price > last_high + atr * 0.5:
            phase, bias = "structure_break", "bullish"
        elif current_price <= last_low + atr * 0.5:
            phase, bias = "trending", "bearish"
        else:
            if trend_range > 0:
                pullback_depth = (current_price - last_low) / trend_range
                pullback_depth = max(0.0, min(pullback_depth, 1.0))
            phase = "deep_pullback" if pullback_depth > 0.72 else "pullback"
            bias  = "neutral" if pullback_depth > 0.72 else "bearish"

    else:
        atr_val = atr if atr > 0 else 0.001
        if current_price >= last_high - atr_val * 0.5:
            phase, bias = "ranging", "bearish"
        elif current_price <= last_low + atr_val * 0.5:
            phase, bias = "ranging", "bullish"
        else:
            phase, bias = "ranging", "neutral"

    return {
        "phase":          phase,
        "bias":           bias,
        "pullback_depth": round(pullback_depth, 2),
        "last_high":      last_high,
        "last_low":       last_low,
        "current_price":  current_price,
    }


def detect_market_structure(df: pd.DataFrame) -> dict:
    """
    Full structure: dominant trend + current phase → setup quality.

    A+: pullback in strong trend (strength 3), 30–65% Fib retracement
    A:  pullback in strong trend (any depth) OR momentum in strong trend
    B:  weak trend pullback, structure break watch, range extreme
    C:  deep pullback, neutral ranging, unknown
    """
    dominant = detect_dominant_trend(df)
    phase    = detect_current_phase(df, dominant)

    trend    = dominant["trend"]
    strength = dominant["strength"]
    ph       = phase["phase"]
    bias     = phase["bias"]
    depth    = phase["pullback_depth"]

    ideal_fib = 0.30 <= depth <= 0.65

    if   ph == "pullback" and strength == 3 and ideal_fib: quality = "A+"
    elif ph == "pullback" and strength == 3:               quality = "A"
    elif ph == "pullback" and strength == 2:               quality = "A"
    elif ph == "trending" and strength == 3:               quality = "A"
    elif ph == "trending" and strength == 2:               quality = "B"
    elif ph == "ranging"  and bias != "neutral":           quality = "B"
    elif ph == "structure_break":                          quality = "B"
    elif ph == "deep_pullback":                            quality = "C"
    else:                                                  quality = "C"

    return {
        "trend":          trend,
        "phase":          ph,
        "bias":           bias,
        "strength":       strength,
        "is_pullback":    ph == "pullback",
        "pullback_depth": depth,
        "setup_quality":  quality,
        "last_high":      phase["last_high"],
        "last_low":       phase["last_low"],
    }


def detect_breakouts(df: pd.DataFrame, zones: list) -> list:
    breakouts     = []
    recent        = df.iloc[-10:]
    current_price = df["close"].iloc[-1]

    for zone in zones:
        broken_up = recent[recent["close"] > zone["high"]]
        if not broken_up.empty:
            idx = broken_up.index[0]
            breakouts.append({
                "zone":        zone,
                "direction":   "bullish",
                "break_price": zone["high"],
                "break_time":  idx,
                "candles_ago": len(df) - df.index.get_loc(idx),
                "retested":    current_price <= zone["high"] * 1.002,
            })

        broken_down = recent[recent["close"] < zone["low"]]
        if not broken_down.empty:
            idx = broken_down.index[0]
            breakouts.append({
                "zone":        zone,
                "direction":   "bearish",
                "break_price": zone["low"],
                "break_time":  idx,
                "candles_ago": len(df) - df.index.get_loc(idx),
                "retested":    current_price >= zone["low"] * 0.998,
            })

    return breakouts


def detect_sr_flips(df: pd.DataFrame, zones: list) -> list:
    flips = []
    for bo in detect_breakouts(df, zones):
        if not bo["retested"]:
            continue
        flip_type = (
            "resistance_to_support" if bo["direction"] == "bullish"
            else "support_to_resistance"
        )
        flips.append({
            "zone":       bo["zone"],
            "flip_type":  flip_type,
            "bias":       "bullish" if bo["direction"] == "bullish" else "bearish",
            "level":      bo["break_price"],
            "candles_ago": bo["candles_ago"],
        })
    return flips