"""
core/ict.py — ICT / Smart Money Concepts

Concepts implemented:
  1. Order Blocks (OB)       — last bearish candle before bullish impulse (and vice versa)
  2. Breaker Blocks          — order blocks that got broken, now act as opposing zone
  3. Liquidity Sweeps        — wick above swing high closes back below = sweep
  4. MSS (Market Structure Shift) — price breaks last Lower High in downtrend = bullish flip
  5. ChoCH (Change of Character)  — first break of any short-term high, precedes MSS
  6. Premium / Discount Zones     — 50% of swing range = equilibrium
                                    above = premium (sell bias)
                                    below = discount (buy bias)
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
    """
    Bullish OB: last bearish candle before a strong bullish impulse move.
    Bearish OB: last bullish candle before a strong bearish impulse move.

    Impulse = next candle body is >= 1.5x average candle size AND
              moves decisively away from the OB candle.

    Returns list of OBs sorted most recent first.
    """
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

        # Bullish OB: bearish candle followed by strong bullish impulse
        if (
            candle["close"] < candle["open"]          # bearish candle
            and next_candle["close"] > next_candle["open"]  # bullish next
            and next_body >= avg * 1.5                # strong impulse
            and next_candle["close"] > candle["high"] # closes above OB high
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

        # Bearish OB: bullish candle followed by strong bearish impulse
        elif (
            candle["close"] > candle["open"]           # bullish candle
            and next_candle["close"] < next_candle["open"]  # bearish next
            and next_body >= avg * 1.5                 # strong impulse
            and next_candle["close"] < candle["low"]   # closes below OB low
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

    # Check which OBs have been broken (price traded through them)
    obs = _mark_broken_obs(df, obs)

    # Return unbroken OBs only, most recent first
    active = [ob for ob in obs if not ob["broken"]]
    active.sort(key=lambda x: x["formed_at"], reverse=True)

    logger.debug(f"Found {len(active)} active OBs ({len(obs)} total)")
    return active


def _mark_broken_obs(df: pd.DataFrame, obs: list) -> list:
    """Mark OBs where price has since traded through the body."""
    for ob in obs:
        try:
            formed_loc  = df.index.get_loc(ob["formed_at"])
            subsequent  = df.iloc[formed_loc + 2:]   # skip impulse candle

            if subsequent.empty:
                continue

            if ob["type"] == "bullish":
                # Broken if price closes below the OB low
                ob["broken"] = bool((subsequent["close"] < ob["low"]).any())
            else:
                # Broken if price closes above the OB high
                ob["broken"] = bool((subsequent["close"] > ob["high"]).any())
        except Exception:
            continue

    return obs


# ─────────────────────────────────────────────────────────────
# 2. BREAKER BLOCKS
# ─────────────────────────────────────────────────────────────

def find_breaker_blocks(df: pd.DataFrame) -> list:
    """
    Breaker Block = an Order Block that got broken through.
    Now it flips polarity and acts as resistance (was support) or support (was resistance).

    Bullish OB gets broken → becomes bearish breaker (resistance)
    Bearish OB gets broken → becomes bullish breaker (support)
    """
    all_obs  = find_order_blocks.__wrapped__(df) if hasattr(find_order_blocks, "__wrapped__") else _find_all_obs(df)
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
            "timeframe":     ob["timeframe"],
            "note":          f"Broken {ob['type']} OB — now acts as {breaker_type} zone",
        })

    breakers.sort(key=lambda x: x["formed_at"], reverse=True)
    return breakers


def _find_all_obs(df: pd.DataFrame) -> list:
    """Internal: find ALL OBs including broken ones."""
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
    """
    Liquidity Sweep:
      Buy-side sweep:  wick above a swing high, candle CLOSES back below it
      Sell-side sweep: wick below a swing low,  candle CLOSES back above it

    This is a classic smart money move — take out stops above highs/below lows
    then reverse. A sweep is a strong reversal signal.
    """
    swings  = get_swing_points(df)
    sweeps  = []
    atr     = df["high"].sub(df["low"]).rolling(14).mean()

    # Check recent candles for sweeps
    lookback = min(30, len(df) - 1)

    for i in range(len(df) - lookback, len(df)):
        candle    = df.iloc[i]
        candle_atr = atr.iloc[i]

        if candle_atr == 0:
            continue

        # Buy-side sweep: wick above swing high, close back below
        for _, swing_row in swings["highs"].iterrows():
            swing_price = swing_row["price"]

            if swing_price <= df["high"].iloc[:i].max() * 0.999:
                # Only check recent swing highs (within lookback)
                pass

            wick_above   = candle["high"] > swing_price
            close_below  = candle["close"] < swing_price
            wick_size    = candle["high"] - max(candle["open"], candle["close"])
            meaningful   = wick_size >= candle_atr * 0.3  # wick must be meaningful

            if wick_above and close_below and meaningful:
                sweeps.append({
                    "type":         "buy_side",
                    "swept_level":  swing_price,
                    "candle_high":  candle["high"],
                    "candle_close": candle["close"],
                    "wick_size":    wick_size,
                    "time":         df.index[i],
                    "bars_ago":     len(df) - i - 1,
                    "bias":         "bearish",  # sweep buy stops = bearish
                    "description":  f"Buy-side liquidity swept @ {swing_price:.5f} — bearish reversal signal",
                })
                break  # one sweep per candle is enough

        # Sell-side sweep: wick below swing low, close back above
        for _, swing_row in swings["lows"].iterrows():
            swing_price = swing_row["price"]

            wick_below   = candle["low"] < swing_price
            close_above  = candle["close"] > swing_price
            wick_size    = min(candle["open"], candle["close"]) - candle["low"]
            meaningful   = wick_size >= candle_atr * 0.3

            if wick_below and close_above and meaningful:
                sweeps.append({
                    "type":         "sell_side",
                    "swept_level":  swing_price,
                    "candle_low":   candle["low"],
                    "candle_close": candle["close"],
                    "wick_size":    wick_size,
                    "time":         df.index[i],
                    "bars_ago":     len(df) - i - 1,
                    "bias":         "bullish",  # sweep sell stops = bullish
                    "description":  f"Sell-side liquidity swept @ {swing_price:.5f} — bullish reversal signal",
                })
                break

    # Most recent sweeps first, only sweeps from last 10 bars are actionable
    sweeps = [s for s in sweeps if s["bars_ago"] <= 10]
    sweeps.sort(key=lambda x: x["bars_ago"])
    return sweeps


# ─────────────────────────────────────────────────────────────
# 4. MSS — Market Structure Shift
# ─────────────────────────────────────────────────────────────

def detect_mss(df: pd.DataFrame) -> dict:
    """
    MSS (Market Structure Shift):
      Bullish MSS: in a downtrend, price breaks above the LAST Lower High
                   with a full candle close above it
      Bearish MSS: in an uptrend, price breaks below the LAST Higher Low
                   with a full candle close below it

    MSS = trend is officially changing. Strong signal.
    """
    swings        = get_swing_points(df)
    current_price = df["close"].iloc[-1]
    last_close    = df["close"].iloc[-1]
    prev_close    = df["close"].iloc[-2]

    highs = swings["highs"]["price"].values
    lows  = swings["lows"]["price"].values

    result = {
        "detected":  False,
        "type":      None,
        "level":     None,
        "bars_ago":  None,
        "description": "",
    }

    if len(highs) < 2 or len(lows) < 2:
        return result

    # Bullish MSS: closed above last swing high (breaks lower high in downtrend)
    last_high = highs[-1]
    if last_close > last_high and prev_close <= last_high:
        # Fresh break — happened on last closed candle
        result.update({
            "detected":    True,
            "type":        "bullish",
            "level":       last_high,
            "bars_ago":    0,
            "description": f"🔵 Bullish MSS — broke above {last_high:.5f}, trend shifting UP",
        })
        return result

    # Bearish MSS: closed below last swing low (breaks higher low in uptrend)
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

    # Check last 5 candles for recent MSS
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
    ChoCH (Change of Character):
      The FIRST break of a short-term swing high/low that precedes MSS.
      Less confirmed than MSS but fires earlier.

      In downtrend: first candle that closes above any recent swing high
      In uptrend:   first candle that closes below any recent swing low

    ChoCH = early warning. MSS = confirmation.
    """
    swings     = get_swing_points(df)
    last_close = df["close"].iloc[-1]

    # Use short-term swings — last 5 swing points
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

    # Bullish ChoCH: close above any recent swing high
    for i, level in enumerate(reversed(recent_highs)):
        if last_close > level:
            result.update({
                "detected":    True,
                "type":        "bullish",
                "level":       level,
                "bars_ago":    0,
                "description": f"⚡ Bullish ChoCH — broke short-term high @ {level:.5f} (precedes MSS)",
            })
            return result

    # Bearish ChoCH: close below any recent swing low
    for i, level in enumerate(reversed(recent_lows)):
        if last_close < level:
            result.update({
                "detected":    True,
                "type":        "bearish",
                "level":       level,
                "bars_ago":    0,
                "description": f"⚡ Bearish ChoCH — broke short-term low @ {level:.5f} (precedes MSS)",
            })
            return result

    return result


# ─────────────────────────────────────────────────────────────
# 6. PREMIUM / DISCOUNT ZONES
# ─────────────────────────────────────────────────────────────

def get_premium_discount(df: pd.DataFrame) -> dict:
    """
    Premium / Discount based on the current swing range.

    Equilibrium = 50% of the range between last swing high and swing low
    Discount    = below 50% → buy bias (price is cheap)
    Premium     = above 50% → sell bias (price is expensive)

    Trading rule:
      Buy in discount (0%–40% of range)
      Sell in premium (60%–100% of range)
      Avoid equilibrium zone (40%–60%) — less edge
    """
    swings = get_swing_points(df)
    highs  = swings["highs"]["price"].values
    lows   = swings["lows"]["price"].values

    if len(highs) == 0 or len(lows) == 0:
        return {
            "zone":          "unknown",
            "pct":           0.5,
            "equilibrium":   0,
            "swing_high":    0,
            "swing_low":     0,
            "description":   "Not enough swing data",
        }

    swing_high    = float(highs[-1])
    swing_low     = float(lows[-1])
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

    pct           = (current_price - swing_low) / swing_range
    pct           = max(0.0, min(pct, 1.0))
    equilibrium   = (swing_high + swing_low) / 2

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
    """
    Run full ICT analysis across all timeframes.
    Returns a single dict used by confluence engine and scorer.
    """
    try:
        # H1 — structure-level ICT
        obs_h1        = find_order_blocks(df_h1)
        breakers_h1   = find_breaker_blocks(df_h1)
        pd_h1         = get_premium_discount(df_h1)
        mss_h1        = detect_mss(df_h1)

        # M15 — confirmation-level ICT
        obs_m15       = find_order_blocks(df_m15)
        sweeps_m15    = find_liquidity_sweeps(df_m15)
        mss_m15       = detect_mss(df_m15)
        choch_m15     = detect_choch(df_m15)

        # M5 — entry-level ICT
        obs_m5        = find_order_blocks(df_m5)
        sweeps_m5     = find_liquidity_sweeps(df_m5)
        mss_m5        = detect_mss(df_m5)
        choch_m5      = detect_choch(df_m5)

        # Most relevant OB for signal (closest to current price on M15)
        current_price = df_m5["close"].iloc[-1]
        nearby_obs    = [
            ob for ob in obs_m15
            if ob["low"] <= current_price <= ob["high"]
               or abs(current_price - ob["mid"]) / max(ob["mid"], 0.001) < 0.005
        ]
        top_ob = nearby_obs[0] if nearby_obs else (obs_m15[0] if obs_m15 else None)

        # Recent sweep (within 5 bars)
        recent_sweep = next(
            (s for s in (sweeps_m5 + sweeps_m15) if s["bars_ago"] <= 5),
            None
        )

        return {
            # Order blocks
            "obs_h1":      obs_h1,
            "obs_m15":     obs_m15,
            "obs_m5":      obs_m5,
            "top_ob":      top_ob,

            # Breakers
            "breakers_h1": breakers_h1,

            # Sweeps
            "sweeps_m15":  sweeps_m15,
            "sweeps_m5":   sweeps_m5,
            "recent_sweep": recent_sweep,

            # MSS
            "mss_h1":      mss_h1,
            "mss_m15":     mss_m15,
            "mss_m5":      mss_m5,

            # ChoCH
            "choch_m15":   choch_m15,
            "choch_m5":    choch_m5,

            # Premium/Discount
            "premium_discount": pd_h1,

            # Quick flags for scorer
            "has_ob":           bool(top_ob),
            "has_sweep":        bool(recent_sweep),
            "has_mss":          mss_m5["detected"] or mss_m15["detected"],
            "has_choch":        choch_m5["detected"] or choch_m15["detected"],
            "in_premium":       pd_h1["zone"] == "premium",
            "in_discount":      pd_h1["zone"] == "discount",
            "mss_direction":    mss_m5.get("type") or mss_m15.get("type"),
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
            "mss_direction": None,
        }


# ─────────────────────────────────────────────────────────────
# HELPERS
# ─────────────────────────────────────────────────────────────

def _guess_tf(df: pd.DataFrame) -> str:
    """Guess timeframe from candle count."""
    n = len(df)
    if n >= 150:  return "H1"
    if n >= 80:   return "M15"
    if n >= 50:   return "M5"
    return "M1"


def format_ict_summary(ict: dict) -> str:
    """One-line ICT summary for alert output."""
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
            parts.append(f"Swept {sweep['type'].replace('_',' ')} @ {sweep['swept_level']:.5f}")

    if ict.get("top_ob"):
        ob = ict["top_ob"]
        parts.append(f"{ob['type'].title()} OB {ob['low']:.5f}–{ob['high']:.5f}")

    return " | ".join(parts) if parts else "No ICT context"