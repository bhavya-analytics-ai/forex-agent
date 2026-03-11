"""
zones.py — S/R zone detection, supply/demand zones, zone strength scoring
"""

import pandas as pd
import numpy as np
import logging
from core.structure import get_swing_points
from core.fetcher import pip_size
from config import ZONE_CONFIG

logger = logging.getLogger(__name__)


def merge_nearby_zones(zones: list, pair: str) -> list:
    """
    Merge zones that are within pip threshold of each other.
    Avoids cluttering chart with duplicate levels.
    """
    if not zones:
        return []

    pip = pip_size(pair)
    merge_threshold = ZONE_CONFIG["zone_merge_pips"] * pip
    zones = sorted(zones, key=lambda z: z["mid"])
    merged = [zones[0]]

    for zone in zones[1:]:
        last = merged[-1]
        if abs(zone["mid"] - last["mid"]) <= merge_threshold:
            # Merge: expand boundaries, combine touches
            last["high"]    = max(last["high"], zone["high"])
            last["low"]     = min(last["low"],  zone["low"])
            last["mid"]     = (last["high"] + last["low"]) / 2
            last["touches"] = last["touches"] + zone["touches"]
            last["strength"] = score_zone(last)
        else:
            merged.append(zone)

    return merged


def score_zone(zone: dict) -> int:
    """
    Score a zone from 0–100 based on:
    - Number of touches (respect = validity)
    - Sharpness of rejections
    - Recency of last touch
    - Zone type (supply/demand weighted higher)
    """
    score = 0

    # Touches — more touches = stronger zone (cap at 5)
    touches = min(zone.get("touches", 1), 5)
    score += touches * 10  # Max 50

    # Recency — penalize old zones
    bars_since = zone.get("bars_since_touch", 999)
    if bars_since < 10:
        score += 20
    elif bars_since < 30:
        score += 12
    elif bars_since < 60:
        score += 5

    # Zone type bonus
    if zone.get("type") in ["supply", "demand"]:
        score += 15  # Supply/demand zones are higher quality
    elif zone.get("type") in ["resistance_to_support", "support_to_resistance"]:
        score += 20  # S/R flips are highest quality

    # Rejection sharpness (avg rejection size relative to zone width)
    rejection = zone.get("avg_rejection", 0)
    zone_width = zone.get("high", 0) - zone.get("low", 0)
    if zone_width > 0 and rejection > 0:
        ratio = rejection / zone_width
        if ratio > 2:
            score += 15
        elif ratio > 1:
            score += 8

    return min(score, 100)


def find_sr_zones(df: pd.DataFrame, pair: str) -> list:
    """
    Detect S/R zones from swing highs and lows.
    Groups nearby swing points into zones with width = ATR-based buffer.
    """
    swings = get_swing_points(df)
    pip    = pip_size(pair)
    atr    = df["high"].sub(df["low"]).rolling(14).mean().iloc[-1]
    buffer = atr * 0.3  # Zone width = 30% of ATR

    zones = []

    # Resistance zones from swing highs
    for time, row in swings["highs"].iterrows():
        price = row["price"]
        zone_high = price + buffer
        zone_low  = price - buffer

        # Count how many times price touched this zone
        touches_mask = (
            (df["high"] >= zone_low) &
            (df["high"] <= zone_high)
        )
        touches = touches_mask.sum()

        if touches < ZONE_CONFIG["min_zone_touches"]:
            continue

        # Bars since last touch
        touch_times = df.index[touches_mask]
        bars_since  = len(df) - df.index.get_loc(touch_times[-1]) if len(touch_times) > 0 else 999

        zone = {
            "type":            "resistance",
            "high":            zone_high,
            "low":             zone_low,
            "mid":             price,
            "touches":         int(touches),
            "bars_since_touch": bars_since,
            "formed_at":       time,
            "avg_rejection":   atr,
        }
        zone["strength"] = score_zone(zone)
        zones.append(zone)

    # Support zones from swing lows
    for time, row in swings["lows"].iterrows():
        price = row["price"]
        zone_high = price + buffer
        zone_low  = price - buffer

        touches_mask = (
            (df["low"] >= zone_low) &
            (df["low"] <= zone_high)
        )
        touches = touches_mask.sum()

        if touches < ZONE_CONFIG["min_zone_touches"]:
            continue

        touch_times = df.index[touches_mask]
        bars_since  = len(df) - df.index.get_loc(touch_times[-1]) if len(touch_times) > 0 else 999

        zone = {
            "type":            "support",
            "high":            zone_high,
            "low":             zone_low,
            "mid":             price,
            "touches":         int(touches),
            "bars_since_touch": bars_since,
            "formed_at":       time,
            "avg_rejection":   atr,
        }
        zone["strength"] = score_zone(zone)
        zones.append(zone)

    return merge_nearby_zones(zones, pair)


def find_supply_demand_zones(df: pd.DataFrame, pair: str) -> list:
    """
    Supply/Demand zones: consolidation (tight range) followed by a big impulse move.
    - Demand: tight range → sharp move UP  → zone where move started (buy pressure)
    - Supply: tight range → sharp move DOWN → zone where move started (sell pressure)
    """
    zones = []
    avg_candle = df["high"].sub(df["low"]).mean()
    big_move   = avg_candle * ZONE_CONFIG["big_move_multiplier"]
    n_consol   = ZONE_CONFIG["supply_demand_bars"]

    for i in range(n_consol, len(df) - 1):
        # Consolidation window
        window = df.iloc[i - n_consol: i]
        w_high = window["high"].max()
        w_low  = window["low"].min()
        w_range = w_high - w_low

        # Tight consolidation = range less than 1x avg candle
        if w_range > avg_candle:
            continue

        # Next candle = impulse?
        impulse = df.iloc[i]
        impulse_size = abs(impulse["close"] - impulse["open"])

        if impulse_size < big_move:
            continue

        zone_type = "demand" if impulse["close"] > impulse["open"] else "supply"

        bars_since = len(df) - i

        zone = {
            "type":             zone_type,
            "high":             w_high,
            "low":              w_low,
            "mid":              (w_high + w_low) / 2,
            "touches":          1,
            "bars_since_touch": bars_since,
            "formed_at":        df.index[i],
            "avg_rejection":    impulse_size,
            "impulse_size":     impulse_size,
        }
        zone["strength"] = score_zone(zone)
        zones.append(zone)

    return merge_nearby_zones(zones, pair)


def get_all_zones(df: pd.DataFrame, pair: str) -> list:
    """
    Combine S/R zones and supply/demand zones.
    Sort by strength descending.
    """
    sr_zones = find_sr_zones(df, pair)
    sd_zones = find_supply_demand_zones(df, pair)
    all_zones = sr_zones + sd_zones

    # Sort by strength
    all_zones = sorted(all_zones, key=lambda z: z["strength"], reverse=True)

    logger.info(f"{pair} — Found {len(all_zones)} zones ({len(sr_zones)} S/R, {len(sd_zones)} S/D)")
    return all_zones


def price_at_zone(current_price: float, zone: dict, pair: str) -> bool:
    """
    Check if current price is tapping (within) a zone.
    """
    pip    = pip_size(pair)
    buffer = 5 * pip  # 5 pip buffer outside zone edges

    return (zone["low"] - buffer) <= current_price <= (zone["high"] + buffer)


def get_active_zones(df: pd.DataFrame, pair: str) -> list:
    """
    Return only zones that price is currently tapping.
    """
    zones = get_all_zones(df, pair)
    current_price = df["close"].iloc[-1]
    return [z for z in zones if price_at_zone(current_price, z, pair)]