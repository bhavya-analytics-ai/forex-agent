"""
zones.py — Zone detection with strict proximity and momentum filters.

Key fixes:
- Tighter zone proximity (price must be INSIDE zone, not 15 pips near it)
- Momentum check: price approaching zone with momentum vs drifting
- Zone freshness: recently formed zones score higher
- Deduplication: stop counting the same swing point twice
"""

import pandas as pd
import numpy as np
import logging
from core.structure import get_swing_points
from core.fetcher import pip_size
from config import ZONE_CONFIG

logger = logging.getLogger(__name__)


def merge_nearby_zones(zones: list, pair: str) -> list:
    if not zones:
        return []
    pip             = pip_size(pair)
    merge_threshold = ZONE_CONFIG["zone_merge_pips"] * pip
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
        score += 20  # S/R flips are highest quality
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
    atr    = df["high"].sub(df["low"]).rolling(14).mean().iloc[-1]
    buffer = atr * 0.25  # Tighter zone width

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

    return merge_nearby_zones(zones, pair)


def find_supply_demand_zones(df: pd.DataFrame, pair: str) -> list:
    """Supply/demand: tight consolidation → sharp impulse."""
    zones      = []
    avg_candle = df["high"].sub(df["low"]).mean()
    n_consol   = ZONE_CONFIG["supply_demand_bars"]

    for i in range(n_consol, len(df) - 1):
        window  = df.iloc[i - n_consol: i]
        w_range = window["high"].max() - window["low"].min()

        # Consolidation must be tight: < 1.5x avg candle
        if w_range > avg_candle * 1.5:
            continue

        impulse      = df.iloc[i]
        impulse_size = abs(impulse["close"] - impulse["open"])

        # Impulse must be strong: > 1.5x avg candle
        if impulse_size < avg_candle * 1.5:
            continue

        zone_type  = "demand" if impulse["close"] > impulse["open"] else "supply"
        atr        = df["high"].sub(df["low"]).rolling(14).mean().iloc[i]
        buffer     = atr * 0.15
        bars_since = len(df) - i

        zone = {
            "type": zone_type,
            "high": window["high"].max() + buffer,
            "low":  window["low"].min() - buffer,
            "mid":  (window["high"].max() + window["low"].min()) / 2,
            "touches": 1, "bars_since_touch": bars_since,
            "formed_at": df.index[i], "avg_rejection": impulse_size,
            "impulse_size": impulse_size,
        }
        zone["strength"] = score_zone(zone)
        zones.append(zone)

    return merge_nearby_zones(zones, pair)


def price_in_zone(current_price: float, zone: dict) -> bool:
    """
    Strict check: price must be INSIDE the zone boundaries.
    No pip buffer — the zone already has ATR-based width built in.
    """
    return zone["low"] <= current_price <= zone["high"]


def price_approaching_zone(current_price: float, zone: dict, pair: str, pips: int = 12) -> bool:
    """Price is approaching zone but not yet inside."""
    if price_in_zone(current_price, zone):
        return False
    pip    = pip_size(pair)
    buffer = pips * pip
    return (zone["low"] - buffer) <= current_price <= (zone["high"] + buffer)


def price_at_zone(current_price: float, zone: dict, pair: str) -> bool:
    """
    Combined: price inside zone OR within tight approach buffer.
    Used for active zone detection.
    """
    if price_in_zone(current_price, zone):
        return True
    # Small grace buffer — 5 pips for forex, $1 for gold
    pip = pip_size(pair)
    if "JPY" in pair:
        grace = 8 * pip
    elif pair == "XAU_USD":
        grace = 1.0
    elif pair == "XAG_USD":
        grace = 0.03
    else:
        grace = 5 * pip
    return (zone["low"] - grace) <= current_price <= (zone["high"] + grace)


def get_zone_momentum(df: pd.DataFrame, zone: dict) -> dict:
    """
    Is price approaching the zone with momentum or drifting in?
    Momentum approach = stronger expected reaction.
    Drift = unreliable, could easily pass through.
    """
    recent     = df.iloc[-6:]
    atr        = df["high"].sub(df["low"]).rolling(14).mean().iloc[-1]
    avg_body   = recent["high"].sub(recent["low"]).mean()
    last_close = df["close"].iloc[-1]
    prev_close = df["close"].iloc[-4]

    move_size  = abs(last_close - prev_close)
    is_fast    = move_size > atr * 0.8  # Moving more than 80% of ATR in 4 candles

    direction = "toward_zone"
    mid       = zone["mid"]
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
    sr = find_sr_zones(df, pair)
    sd = find_supply_demand_zones(df, pair)
    all_zones = sorted(sr + sd, key=lambda z: z["strength"], reverse=True)
    logger.info(f"{pair} — Found {len(all_zones)} zones ({len(sr)} S/R, {len(sd)} S/D)")
    return all_zones


def get_active_zones(df: pd.DataFrame, pair: str) -> list:
    """Zones price is currently at — strict check."""
    zones         = get_all_zones(df, pair)
    current_price = df["close"].iloc[-1]
    active        = [z for z in zones if price_at_zone(current_price, z, pair)]
    return active