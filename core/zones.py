"""
zones.py — Zone detection with ATR-based thresholds for all pairs

KEY FIX FOR GOLD/SILVER:
- merge_nearby_zones: uses ATR * 0.3 instead of pip * 10
  Old: Gold merge = 10 × $0.1 = $1 (useless)
  New: Gold merge = ATR × 0.3 = ~$12 (correct)

- price_at_zone grace buffer: uses ATR * 0.5 instead of fixed $1
  Old: Gold grace = $1 (price never "at" zone)
  New: Gold grace = ATR × 0.5 = ~$20 (correct)

- price_approaching_zone: uses ATR * 1.5 instead of pips * pip_size
  Old: Gold approach = 12 × $0.1 = $1.20 (useless)
  New: Gold approach = ATR × 1.5 = ~$60 (correct)
"""

import pandas as pd
import numpy as np
import logging
from core.structure import get_swing_points
from core.fetcher import pip_size
from config import ZONE_CONFIG

logger = logging.getLogger(__name__)


def _get_atr(df: pd.DataFrame) -> float:
    """Get current ATR for the dataframe."""
    atr = df["high"].sub(df["low"]).rolling(14).mean().iloc[-1]
    return float(atr) if atr and atr > 0 else 0.001


def _merge_threshold(pair: str, atr: float) -> float:
    """
    ATR-based merge threshold.
    Replaces pip-based threshold which was $1 for Gold — way too tight.
    """
    return atr * 0.3


def merge_nearby_zones(zones: list, pair: str, atr: float = None) -> list:
    if not zones:
        return []

    # Need ATR for merge threshold — passed in or estimated from zone widths
    if atr is None or atr == 0:
        # Estimate from zone widths
        widths = [z.get("high", 0) - z.get("low", 0) for z in zones if z.get("high") and z.get("low")]
        atr    = sum(widths) / len(widths) / 0.25 if widths else 1.0

    merge_threshold = _merge_threshold(pair, atr)
    zones           = sorted(zones, key=lambda z: z["mid"])
    merged          = [zones[0]]

    for zone in zones[1:]:
        last = merged[-1]
        if abs(zone["mid"] - last["mid"]) <= merge_threshold:
            last["high"]     = max(last["high"], zone["high"])
            last["low"]      = min(last["low"],  zone["low"])
            last["mid"]      = (last["high"] + last["low"]) / 2
            last["touches"]  = last["touches"] + zone["touches"]
            last["strength"] = score_zone(last)
        else:
            merged.append(zone)

    return merged


def score_zone(zone: dict) -> int:
    score = 0

    # Touches (capped at 5)
    touches = min(zone.get("touches", 1), 5)
    score  += touches * 8  # Max 40

    # Recency
    bars = zone.get("bars_since_touch", 999)
    if bars < 5:
        score += 25
    elif bars < 15:
        score += 18
    elif bars < 40:
        score += 10
    elif bars < 80:
        score += 4

    # Zone type quality
    zone_type = zone.get("type", "")
    if zone_type in ["support_to_resistance", "resistance_to_support"]:
        score += 20
    elif zone_type in ["supply", "demand"]:
        score += 15
    elif zone_type in ["support", "resistance"]:
        score += 8

    # Rejection sharpness
    rejection  = zone.get("avg_rejection", 0)
    zone_width = zone.get("high", 0) - zone.get("low", 0)
    if zone_width > 0 and rejection > 0:
        ratio = rejection / zone_width
        if ratio > 3:
            score += 15
        elif ratio > 1.5:
            score += 8

    return min(score, 100)


def find_sr_zones(df: pd.DataFrame, pair: str) -> list:
    """S/R zones from swing highs/lows with deduplication."""
    swings = get_swing_points(df)
    atr    = _get_atr(df)
    buffer = atr * 0.25  # Zone width — ATR-based, correct for all pairs

    zones       = []
    seen_prices = set()

    for time, row in swings["highs"].iterrows():
        price   = row["price"]
        rounded = round(price / (atr * 0.1)) * (atr * 0.1)
        if rounded in seen_prices:
            continue
        seen_prices.add(rounded)

        zone_high = price + buffer
        zone_low  = price - buffer

        touches_mask = (df["high"] >= zone_low) & (df["high"] <= zone_high)
        touches      = int(touches_mask.sum())
        if touches < ZONE_CONFIG["min_zone_touches"]:
            continue

        touch_times = df.index[touches_mask]
        bars_since  = len(df) - df.index.get_loc(touch_times[-1])

        zone = {
            "type": "resistance", "high": zone_high, "low": zone_low,
            "mid": price, "touches": touches, "bars_since_touch": bars_since,
            "formed_at": time, "avg_rejection": atr,
        }
        zone["strength"] = score_zone(zone)
        zones.append(zone)

    seen_prices = set()
    for time, row in swings["lows"].iterrows():
        price   = row["price"]
        rounded = round(price / (atr * 0.1)) * (atr * 0.1)
        if rounded in seen_prices:
            continue
        seen_prices.add(rounded)

        zone_high = price + buffer
        zone_low  = price - buffer

        touches_mask = (df["low"] >= zone_low) & (df["low"] <= zone_high)
        touches      = int(touches_mask.sum())
        if touches < ZONE_CONFIG["min_zone_touches"]:
            continue

        touch_times = df.index[touches_mask]
        bars_since  = len(df) - df.index.get_loc(touch_times[-1])

        zone = {
            "type": "support", "high": zone_high, "low": zone_low,
            "mid": price, "touches": touches, "bars_since_touch": bars_since,
            "formed_at": time, "avg_rejection": atr,
        }
        zone["strength"] = score_zone(zone)
        zones.append(zone)

    return merge_nearby_zones(zones, pair, atr)


def find_supply_demand_zones(df: pd.DataFrame, pair: str) -> list:
    """Supply/demand: tight consolidation → sharp impulse."""
    zones      = []
    avg_candle = df["high"].sub(df["low"]).mean()
    n_consol   = ZONE_CONFIG["supply_demand_bars"]
    atr_series = df["high"].sub(df["low"]).rolling(14).mean()

    for i in range(n_consol, len(df) - 1):
        window  = df.iloc[i - n_consol: i]
        w_range = window["high"].max() - window["low"].min()

        if w_range > avg_candle * 1.5:
            continue

        impulse      = df.iloc[i]
        impulse_size = abs(impulse["close"] - impulse["open"])

        if impulse_size < avg_candle * 1.5:
            continue

        zone_type  = "demand" if impulse["close"] > impulse["open"] else "supply"
        atr        = float(atr_series.iloc[i]) if atr_series.iloc[i] > 0 else avg_candle
        buffer     = atr * 0.15
        bars_since = len(df) - i

        zone = {
            "type":         zone_type,
            "high":         window["high"].max() + buffer,
            "low":          window["low"].min() - buffer,
            "mid":          (window["high"].max() + window["low"].min()) / 2,
            "touches":      1,
            "bars_since_touch": bars_since,
            "formed_at":    df.index[i],
            "avg_rejection": impulse_size,
            "impulse_size": impulse_size,
        }
        zone["strength"] = score_zone(zone)
        zones.append(zone)

    atr = _get_atr(df)
    return merge_nearby_zones(zones, pair, atr)


def price_in_zone(current_price: float, zone: dict) -> bool:
    """Strict check: price must be INSIDE zone boundaries."""
    return zone["low"] <= current_price <= zone["high"]


def price_approaching_zone(
    current_price: float, zone: dict, pair: str, pips: int = 12, atr: float = None
) -> bool:
    """
    Price approaching zone but not yet inside.
    FIX: uses ATR-based buffer instead of pip-based.
    Old Gold buffer: 12 × $0.1 = $1.20 (never triggered)
    New Gold buffer: ATR × 1.5 = ~$60 (correct)
    """
    if price_in_zone(current_price, zone):
        return False

    if atr and atr > 0:
        buffer = atr * 1.5
    else:
        pip    = pip_size(pair)
        buffer = pips * pip

    return (zone["low"] - buffer) <= current_price <= (zone["high"] + buffer)


def price_at_zone(current_price: float, zone: dict, pair: str, atr: float = None) -> bool:
    """
    Price inside zone OR within grace buffer.
    FIX: grace buffer is now ATR-based for metals.
    Old Gold grace: $1 (price never "at" zone)
    New Gold grace: ATR × 0.5 = ~$20 (correct)
    """
    if price_in_zone(current_price, zone):
        return True

    # Grace buffer — ATR-based
    if atr and atr > 0:
        grace = atr * 0.5
    else:
        pip = pip_size(pair)
        if "JPY" in pair:
            grace = 8 * pip
        elif pair == "XAU_USD":
            grace = 2.0   # fallback $2 if no ATR
        elif pair == "XAG_USD":
            grace = 0.08  # fallback $0.08 if no ATR
        else:
            grace = 5 * pip

    return (zone["low"] - grace) <= current_price <= (zone["high"] + grace)


def get_zone_momentum(df: pd.DataFrame, zone: dict) -> dict:
    """Is price approaching with momentum or drifting?"""
    recent     = df.iloc[-6:]
    atr        = _get_atr(df)
    last_close = df["close"].iloc[-1]
    prev_close = df["close"].iloc[-4]
    move_size  = abs(last_close - prev_close)
    is_fast    = move_size > atr * 0.8

    mid       = zone["mid"]
    direction = "toward_zone"
    if last_close > prev_close and last_close > mid:
        direction = "away_from_zone"
    elif last_close < prev_close and last_close < mid:
        direction = "away_from_zone"

    return {
        "is_fast":   is_fast,
        "direction": direction,
        "move_size": move_size,
        "atr":       atr,
    }


def get_all_zones(df: pd.DataFrame, pair: str) -> list:
    sr        = find_sr_zones(df, pair)
    sd        = find_supply_demand_zones(df, pair)
    all_zones = sorted(sr + sd, key=lambda z: z["strength"], reverse=True)
    logger.info(f"{pair} — Found {len(all_zones)} zones ({len(sr)} S/R, {len(sd)} S/D)")
    return all_zones


def get_active_zones(df: pd.DataFrame, pair: str) -> list:
    """Zones price is currently at — ATR-aware check."""
    zones         = get_all_zones(df, pair)
    current_price = df["close"].iloc[-1]
    atr           = _get_atr(df)
    active        = [z for z in zones if price_at_zone(current_price, z, pair, atr)]
    return active