"""
core/ict.py — ICT / Smart Money Concepts

FIXES IN THIS VERSION:
1. ChoCH — was firing on EVERY candle because it just checked if price
   was above any recent high. Now correctly checks if price JUST broke
   a level (prev close was below, current close is above). Real ChoCH only.

2. Premium/Discount — was using highs[-1] and lows[-1] independently,
   which could be from completely different swing legs. Now uses the most
   recent PAIRED swing high and low from the same price leg. Gold at 4466
   is not "premium" relative to a range from 6 months ago.

3. MSS — added mss_direction to return dict so confluence.py can use it
   to influence final direction decision.
"""

import pandas as pd
import numpy as np
import logging
from core.structure import get_swing_points

logger = logging.getLogger(__name__)


# ─────────────────────────────────────────────────────────────
# 1. ORDER BLOCKS
# ─────────────────────────────────────────────────────────────

def find_order_blocks(df: pd.DataFrame) -> list:
    avg_body = df["high"].sub(df["low"]).rolling(10).mean()
    obs      = []

    for i in range(1, len(df) - 1):
        candle      = df.iloc[i]
        next_candle = df.iloc[i + 1]
        body        = abs(candle["close"] - candle["open"])
        next_body   = abs(next_candle["close"] - next_candle["open"])
        avg         = avg_body.iloc[i]

        if avg == 0:
            continue

        if (
            candle["close"] < candle["open"]
            and next_candle["close"] > next_candle["open"]
            and next_body >= avg * 1.5
            and next_candle["close"] > candle["high"]
        ):
            obs.append({
                "type":       "bullish",
                "high":       candle["high"],
                "low":        candle["low"],
                "mid":        (candle["high"] + candle["low"]) / 2,
                "formed_at":  df.index[i],
                "body_high":  max(candle["open"], candle["close"]),
                "body_low":   min(candle["open"], candle["close"]),
                "broken":     False,
                "timeframe":  _guess_tf(df),
            })

        elif (
            candle["close"] > candle["open"]
            and next_candle["close"] < next_candle["open"]
            and next_body >= avg * 1.5
            and next_candle["close"] < candle["low"]
        ):
            obs.append({
                "type":       "bearish",
                "high":       candle["high"],
                "low":        candle["low"],
                "mid":        (candle["high"] + candle["low"]) / 2,
                "formed_at":  df.index[i],
                "body_high":  max(candle["open"], candle["close"]),
                "body_low":   min(candle["open"], candle["close"]),
                "broken":     False,
                "timeframe":  _guess_tf(df),
            })

    obs = _mark_broken_obs(df, obs)
    active = [ob for ob in obs if not ob["broken"]]
    active.sort(key=lambda x: x["formed_at"], reverse=True)
    return active


def _mark_broken_obs(df: pd.DataFrame, obs: list) -> list:
    for ob in obs:
        try:
            formed_loc = df.index.get_loc(ob["formed_at"])
            subsequent = df.iloc[formed_loc + 2:]
            if subsequent.empty:
                continue
            if ob["type"] == "bullish":
                ob["broken"] = bool((subsequent["close"] < ob["low"]).any())
            else:
                ob["broken"] = bool((subsequent["close"] > ob["high"]).any())
        except Exception:
            continue
    return obs


# ─────────────────────────────────────────────────────────────
# 2. BREAKER BLOCKS
# ─────────────────────────────────────────────────────────────

def find_breaker_blocks(df: pd.DataFrame) -> list:
    all_obs  = _find_all_obs(df)
    breakers = []

    for ob in all_obs:
        if not ob["broken"]:
            continue
        breaker_type = "bearish" if ob["type"] == "bullish" else "bullish"
        breakers.append({
            "type":          breaker_type,
            "original_type": ob["type"],
            "high":          ob["high"],
            "low":           ob["low"],
            "mid":           ob["mid"],
            "formed_at":     ob["formed_at"],
            "timeframe":     ob.get("timeframe", ""),
            "note":          f"Broken {ob['type']} OB — now acts as {breaker_type} zone",
        })

    breakers.sort(key=lambda x: x["formed_at"], reverse=True)
    return breakers


def _find_all_obs(df: pd.DataFrame) -> list:
    avg_body = df["high"].sub(df["low"]).rolling(10).mean()
    obs      = []

    for i in range(1, len(df) - 1):
        candle      = df.iloc[i]
        next_candle = df.iloc[i + 1]
        next_body   = abs(next_candle["close"] - next_candle["open"])
        avg         = avg_body.iloc[i]

        if avg == 0:
            continue

        if (
            candle["close"] < candle["open"]
            and next_candle["close"] > next_candle["open"]
            and next_body >= avg * 1.5
            and next_candle["close"] > candle["high"]
        ):
            obs.append({
                "type": "bullish", "high": candle["high"], "low": candle["low"],
                "mid": (candle["high"] + candle["low"]) / 2,
                "formed_at": df.index[i], "broken": False,
                "timeframe": _guess_tf(df),
            })
        elif (
            candle["close"] > candle["open"]
            and next_candle["close"] < next_candle["open"]
            and next_body >= avg * 1.5
            and next_candle["close"] < candle["low"]
        ):
            obs.append({
                "type": "bearish", "high": candle["high"], "low": candle["low"],
                "mid": (candle["high"] + candle["low"]) / 2,
                "formed_at": df.index[i], "broken": False,
                "timeframe": _guess_tf(df),
            })

    return _mark_broken_obs(df, obs)


# ─────────────────────────────────────────────────────────────
# 3. LIQUIDITY SWEEPS
# ─────────────────────────────────────────────────────────────

def find_liquidity_sweeps(df: pd.DataFrame) -> list:
    swings   = get_swing_points(df)
    sweeps   = []
    atr      = df["high"].sub(df["low"]).rolling(14).mean()
    lookback = min(30, len(df) - 1)

    for i in range(len(df) - lookback, len(df)):
        candle     = df.iloc[i]
        candle_atr = atr.iloc[i]

        if candle_atr == 0:
            continue

        for _, swing_row in swings["highs"].iterrows():
            swing_price = swing_row["price"]
            wick_above  = candle["high"] > swing_price
            close_below = candle["close"] < swing_price
            wick_size   = candle["high"] - max(candle["open"], candle["close"])
            meaningful  = wick_size >= candle_atr * 0.3

            if wick_above and close_below and meaningful:
                sweeps.append({
                    "type":         "buy_side",
                    "swept_level":  swing_price,
                    "candle_high":  candle["high"],
                    "candle_close": candle["close"],
                    "wick_size":    wick_size,
                    "time":         df.index[i],
                    "bars_ago":     len(df) - i - 1,
                    "bias":         "bearish",
                    "description":  f"Buy-side liquidity swept @ {swing_price:.5f} — bearish reversal signal",
                })
                break

        for _, swing_row in swings["lows"].iterrows():
            swing_price = swing_row["price"]
            wick_below  = candle["low"] < swing_price
            close_above = candle["close"] > swing_price
            wick_size   = min(candle["open"], candle["close"]) - candle["low"]
            meaningful  = wick_size >= candle_atr * 0.3

            if wick_below and close_above and meaningful:
                sweeps.append({
                    "type":         "sell_side",
                    "swept_level":  swing_price,
                    "candle_low":   candle["low"],
                    "candle_close": candle["close"],
                    "wick_size":    wick_size,
                    "time":         df.index[i],
                    "bars_ago":     len(df) - i - 1,
                    "bias":         "bullish",
                    "description":  f"Sell-side liquidity swept @ {swing_price:.5f} — bullish reversal signal",
                })
                break

    sweeps = [s for s in sweeps if s["bars_ago"] <= 10]
    sweeps.sort(key=lambda x: x["bars_ago"])
    return sweeps


# ─────────────────────────────────────────────────────────────
# 4. MSS — Market Structure Shift
# ─────────────────────────────────────────────────────────────

def detect_mss(df: pd.DataFrame) -> dict:
    swings     = get_swing_points(df)
    last_close = df["close"].iloc[-1]
    prev_close = df["close"].iloc[-2]

    highs = swings["highs"]["price"].values
    lows  = swings["lows"]["price"].values

    result = {
        "detected":    False,
        "type":        None,
        "level":       None,
        "bars_ago":    None,
        "description": "",
    }

    if len(highs) < 2 or len(lows) < 2:
        return result

    last_high = highs[-1]
    if last_close > last_high and prev_close <= last_high:
        result.update({
            "detected":    True,
            "type":        "bullish",
            "level":       last_high,
            "bars_ago":    0,
            "description": f"🔵 Bullish MSS — broke above {last_high:.5f}, trend shifting UP",
        })
        return result

    last_low = lows[-1]
    if last_close < last_low and prev_close >= last_low:
        result.update({
            "detected":    True,
            "type":        "bearish",
            "level":       last_low,
            "bars_ago":    0,
            "description": f"🔴 Bearish MSS — broke below {last_low:.5f}, trend shifting DOWN",
        })
        return result

    for i in range(2, min(6, len(df))):
        close_i      = df["close"].iloc[-i]
        close_before = df["close"].iloc[-i - 1]

        if close_i > last_high and close_before <= last_high:
            result.update({
                "detected":    True,
                "type":        "bullish",
                "level":       last_high,
                "bars_ago":    i - 1,
                "description": f"🔵 Bullish MSS {i-1} bars ago — broke {last_high:.5f}",
            })
            return result

        if close_i < last_low and close_before >= last_low:
            result.update({
                "detected":    True,
                "type":        "bearish",
                "level":       last_low,
                "bars_ago":    i - 1,
                "description": f"🔴 Bearish MSS {i-1} bars ago — broke {last_low:.5f}",
            })
            return result

    return result


# ─────────────────────────────────────────────────────────────
# 5. ChoCH — Change of Character
# ─────────────────────────────────────────────────────────────

def detect_choch(df: pd.DataFrame) -> dict:
    """
    FIX: Previous version fired ChoCH if last_close > ANY recent high.
    That's almost always true and means nothing.

    Correct ChoCH: price must have been BELOW the level on the previous
    candle and CLOSE ABOVE it on the current candle. A fresh break only.
    We check the last 3 candles for a recent fresh break.
    """
    swings     = get_swing_points(df)
    last_close = df["close"].iloc[-1]
    prev_close = df["close"].iloc[-2] if len(df) >= 2 else last_close

    recent_highs = swings["highs"]["price"].values[-5:]
    recent_lows  = swings["lows"]["price"].values[-5:]

    result = {
        "detected":    False,
        "type":        None,
        "level":       None,
        "bars_ago":    None,
        "description": "",
    }

    if len(recent_highs) == 0 or len(recent_lows) == 0:
        return result

    # Bullish ChoCH: current close ABOVE level AND previous close was BELOW it
    # = fresh break, not just "price is above some high"
    for level in reversed(recent_highs):
        if last_close > level and prev_close <= level:
            result.update({
                "detected":    True,
                "type":        "bullish",
                "level":       level,
                "bars_ago":    0,
                "description": f"⚡ Bullish ChoCH — just broke short-term high @ {level:.5f}",
            })
            return result

    # Check 2-3 bars back for recent ChoCH
    for lookback in range(2, min(4, len(df))):
        close_now  = df["close"].iloc[-lookback]
        close_prev = df["close"].iloc[-lookback - 1]

        for level in reversed(recent_highs):
            if close_now > level and close_prev <= level:
                result.update({
                    "detected":    True,
                    "type":        "bullish",
                    "level":       level,
                    "bars_ago":    lookback - 1,
                    "description": f"⚡ Bullish ChoCH {lookback-1}b ago — broke {level:.5f}",
                })
                return result

        for level in reversed(recent_lows):
            if close_now < level and close_prev >= level:
                result.update({
                    "detected":    True,
                    "type":        "bearish",
                    "level":       level,
                    "bars_ago":    lookback - 1,
                    "description": f"⚡ Bearish ChoCH {lookback-1}b ago — broke {level:.5f}",
                })
                return result

    # Bearish ChoCH: current close BELOW level AND previous close was ABOVE it
    for level in reversed(recent_lows):
        if last_close < level and prev_close >= level:
            result.update({
                "detected":    True,
                "type":        "bearish",
                "level":       level,
                "bars_ago":    0,
                "description": f"⚡ Bearish ChoCH — just broke short-term low @ {level:.5f}",
            })
            return result

    return result


# ─────────────────────────────────────────────────────────────
# 6. PREMIUM / DISCOUNT ZONES
# ─────────────────────────────────────────────────────────────

def get_premium_discount(df: pd.DataFrame) -> dict:
    """
    FIX: Previous version used highs[-1] and lows[-1] independently.
    These could be from completely different swing legs — e.g. last high
    from 3 weeks ago, last low from yesterday. The range was meaningless.

    Now: find the most recent COMPLETE swing leg — either:
    - Last swing high → last swing low (if high came after low = bearish leg)
    - Last swing low → last swing high (if low came after high = bullish leg)

    This gives the CURRENT range price is trading in, not some random range.
    Critical for gold which has moved into entirely new price territory.
    """
    swings = get_swing_points(df)
    highs  = swings["highs"]
    lows   = swings["lows"]

    if highs.empty or lows.empty:
        return {
            "zone":        "unknown",
            "pct":         0.5,
            "equilibrium": 0,
            "swing_high":  0,
            "swing_low":   0,
            "description": "Not enough swing data",
        }

    # Get the most recent swing high and low WITH their timestamps
    last_high_time  = highs.index[-1]
    last_high_price = float(highs["price"].values[-1])
    last_low_time   = lows.index[-1]
    last_low_price  = float(lows["price"].values[-1])

    # Use whichever came LATER as the anchor, pair with the most recent opposite
    # This finds the current active swing range
    if last_high_time > last_low_time:
        # Most recent event was a swing high — find the swing low BEFORE it
        lows_before = lows[lows.index < last_high_time]
        if lows_before.empty:
            swing_low = last_low_price
        else:
            swing_low = float(lows_before["price"].values[-1])
        swing_high = last_high_price
    else:
        # Most recent event was a swing low — find the swing high BEFORE it
        highs_before = highs[highs.index < last_low_time]
        if highs_before.empty:
            swing_high = last_high_price
        else:
            swing_high = float(highs_before["price"].values[-1])
        swing_low = last_low_price

    swing_range   = swing_high - swing_low
    current_price = df["close"].iloc[-1]

    if swing_range <= 0:
        return {
            "zone":        "ranging",
            "pct":         0.5,
            "equilibrium": (swing_high + swing_low) / 2,
            "swing_high":  swing_high,
            "swing_low":   swing_low,
            "description": "Range too tight — no premium/discount context",
        }

    pct         = (current_price - swing_low) / swing_range
    pct         = max(0.0, min(pct, 1.0))
    equilibrium = (swing_high + swing_low) / 2

    if pct >= 0.60:
        zone        = "premium"
        bias        = "bearish"
        description = f"📈 PREMIUM zone ({round(pct*100)}% of range) — price expensive, sell bias"
    elif pct <= 0.40:
        zone        = "discount"
        bias        = "bullish"
        description = f"📉 DISCOUNT zone ({round(pct*100)}% of range) — price cheap, buy bias"
    else:
        zone        = "equilibrium"
        bias        = "neutral"
        description = f"⚖️ EQUILIBRIUM ({round(pct*100)}% of range) — avoid, wait for extension"

    return {
        "zone":        zone,
        "bias":        bias,
        "pct":         round(pct, 3),
        "equilibrium": equilibrium,
        "swing_high":  swing_high,
        "swing_low":   swing_low,
        "description": description,
    }


# ─────────────────────────────────────────────────────────────
# COMBINED ICT ANALYSIS
# ─────────────────────────────────────────────────────────────

def get_ict_context(df_h1: pd.DataFrame, df_m15: pd.DataFrame, df_m5: pd.DataFrame) -> dict:
    try:
        obs_h1      = find_order_blocks(df_h1)
        breakers_h1 = find_breaker_blocks(df_h1)
        pd_h1       = get_premium_discount(df_h1)
        mss_h1      = detect_mss(df_h1)

        obs_m15   = find_order_blocks(df_m15)
        sweeps_m15 = find_liquidity_sweeps(df_m15)
        mss_m15   = detect_mss(df_m15)
        choch_m15 = detect_choch(df_m15)

        obs_m5    = find_order_blocks(df_m5)
        sweeps_m5 = find_liquidity_sweeps(df_m5)
        mss_m5    = detect_mss(df_m5)
        choch_m5  = detect_choch(df_m5)

        current_price = df_m5["close"].iloc[-1]
        nearby_obs    = [
            ob for ob in obs_m15
            if ob["low"] <= current_price <= ob["high"]
               or abs(current_price - ob["mid"]) / max(ob["mid"], 0.001) < 0.005
        ]
        top_ob = nearby_obs[0] if nearby_obs else (obs_m15[0] if obs_m15 else None)

        recent_sweep = next(
            (s for s in (sweeps_m5 + sweeps_m15) if s["bars_ago"] <= 5),
            None
        )

        # Determine ICT-based direction signal
        # MSS is the strongest signal — if MSS fired, that's the direction
        # ChoCH is secondary — earlier warning
        ict_direction = None
        if mss_m5["detected"]:
            ict_direction = mss_m5["type"]
        elif mss_m15["detected"]:
            ict_direction = mss_m15["type"]
        elif mss_h1["detected"]:
            ict_direction = mss_h1["type"]
        elif choch_m5["detected"]:
            ict_direction = choch_m5["type"]
        elif choch_m15["detected"]:
            ict_direction = choch_m15["type"]

        return {
            "obs_h1":      obs_h1,
            "obs_m15":     obs_m15,
            "obs_m5":      obs_m5,
            "top_ob":      top_ob,
            "breakers_h1": breakers_h1,
            "sweeps_m15":  sweeps_m15,
            "sweeps_m5":   sweeps_m5,
            "recent_sweep": recent_sweep,
            "mss_h1":      mss_h1,
            "mss_m15":     mss_m15,
            "mss_m5":      mss_m5,
            "choch_m15":   choch_m15,
            "choch_m5":    choch_m5,
            "premium_discount": pd_h1,
            "has_ob":      bool(top_ob),
            "has_sweep":   bool(recent_sweep),
            "has_mss":     mss_m5["detected"] or mss_m15["detected"],
            "has_choch":   choch_m5["detected"] or choch_m15["detected"],
            "in_premium":  pd_h1["zone"] == "premium",
            "in_discount": pd_h1["zone"] == "discount",
            "mss_direction":  mss_m5.get("type") or mss_m15.get("type"),
            "ict_direction":  ict_direction,  # NEW: clean single direction signal from ICT
        }

    except Exception as e:
        logger.error(f"ICT analysis error: {e}", exc_info=True)
        return {
            "obs_h1": [], "obs_m15": [], "obs_m5": [], "top_ob": None,
            "breakers_h1": [], "sweeps_m15": [], "sweeps_m5": [],
            "recent_sweep": None, "mss_h1": {"detected": False},
            "mss_m15": {"detected": False}, "mss_m5": {"detected": False},
            "choch_m15": {"detected": False}, "choch_m5": {"detected": False},
            "premium_discount": {"zone": "unknown", "pct": 0.5},
            "has_ob": False, "has_sweep": False, "has_mss": False,
            "has_choch": False, "in_premium": False, "in_discount": False,
            "mss_direction": None, "ict_direction": None,
        }


# ─────────────────────────────────────────────────────────────
# HELPERS
# ─────────────────────────────────────────────────────────────

def _guess_tf(df: pd.DataFrame) -> str:
    n = len(df)
    if n >= 150: return "H1"
    if n >= 80:  return "M15"
    if n >= 50:  return "M5"
    return "M1"


def format_ict_summary(ict: dict) -> str:
    parts = []

    pd_zone = ict.get("premium_discount", {})
    if pd_zone.get("zone") == "premium":
        parts.append(f"📈 PREMIUM ({round(pd_zone.get('pct',0)*100)}%)")
    elif pd_zone.get("zone") == "discount":
        parts.append(f"📉 DISCOUNT ({round(pd_zone.get('pct',0)*100)}%)")

    if ict.get("has_mss"):
        mss = ict.get("mss_m5") or ict.get("mss_m15")
        if mss and mss.get("detected"):
            parts.append(f"MSS {mss['type'].upper()}")

    if ict.get("has_choch"):
        choch = ict.get("choch_m5") or ict.get("choch_m15")
        if choch and choch.get("detected"):
            parts.append(f"ChoCH {choch['type'].upper()}")

    if ict.get("has_sweep"):
        sweep = ict.get("recent_sweep")
        if sweep:
            parts.append(f"Swept {sweep['type'].replace('_',' ')}")

    if ict.get("top_ob"):
        ob = ict["top_ob"]
        parts.append(f"{ob['type'].title()} OB")

    return " | ".join(parts) if parts else "No ICT context"