"""
core/liquidity.py — TP/SL source logic

Provides structure-aware SL and liquidity-based TP.
Called from filters/decision_layer.py — nothing else.

SL PRIORITY:
  1. OB edge (tightest valid anchor — same idea as entry)
  2. M15 swing high/low (same TF as typical entry trigger)
  3. H1 swing high/low (only if M15 unavailable)
  4. ATR fallback

TP PRIORITY:
  - Collect all strong levels (H1 zones strength >= 50, H1 swings)
  - Filter out levels too close (< ATR * 0.5)
  - Pick first level that gives RR >= 1.5
  - tp2 = next valid level after tp1

DEBUG LOG:
  - Prints SL anchor used and TP level selected
"""

import logging
from core.fetcher import pip_size

logger = logging.getLogger(__name__)


def get_stop_loss(entry: float, confluence: dict, direction: str, pair: str) -> tuple:
    """
    Returns (sl_price, anchor_label) — label used for debug log.

    Priority:
    1. OB edge from ICT context
    2. M15 structural swing (same TF as entry trigger)
    3. H1 structural swing (wider, only fallback)
    4. ATR-based fallback
    """
    pip    = pip_size(pair)
    buffer = 3 * pip

    ict = confluence.get("ict", {})
    ob  = ict.get("top_ob")

    # 1. OB edge — tightest SL at order block boundary
    if ob:
        if direction == "bullish" and ob.get("low") and ob["low"] < entry:
            sl = ob["low"] - buffer
            return sl, f"OB edge ({ob.get('type','OB')} low={round(ob['low'], 5)})"
        elif direction == "bearish" and ob.get("high") and ob["high"] > entry:
            sl = ob["high"] + buffer
            return sl, f"OB edge ({ob.get('type','OB')} high={round(ob['high'], 5)})"

    # 2. M15 swing — same timeframe as entry trigger
    m15_struct = confluence.get("m15", {}).get("structure", {})
    if direction == "bullish":
        m15_low = m15_struct.get("last_low")
        if m15_low and m15_low < entry:
            sl = m15_low - buffer
            return sl, f"M15 swing low ({round(m15_low, 5)})"
    else:
        m15_high = m15_struct.get("last_high")
        if m15_high and m15_high > entry:
            sl = m15_high + buffer
            return sl, f"M15 swing high ({round(m15_high, 5)})"

    # 3. H1 swing — wider fallback
    h1_struct = confluence.get("h1", {}).get("structure", {})
    if direction == "bullish":
        h1_low = h1_struct.get("last_low")
        if h1_low and h1_low < entry:
            sl = h1_low - buffer
            return sl, f"H1 swing low ({round(h1_low, 5)})"
    else:
        h1_high = h1_struct.get("last_high")
        if h1_high and h1_high > entry:
            sl = h1_high + buffer
            return sl, f"H1 swing high ({round(h1_high, 5)})"

    # 4. ATR fallback
    htf_high = h1_struct.get("last_high", entry * 1.01)
    htf_low  = h1_struct.get("last_low",  entry * 0.99)
    atr      = (htf_high - htf_low) / 20 if htf_high > htf_low else 20 * pip
    sl       = entry - atr if direction == "bullish" else entry + atr
    return sl, f"ATR fallback ({round(atr / pip, 1)} pips)"


def get_take_profit(entry: float, sl: float, confluence: dict, direction: str, pair: str, atr: float) -> tuple:
    """
    Returns (tp1, tp2, tp1_label) — labels used for debug log.

    Logic:
    - Collect H1 zones (strength >= 50) + H1 structure swings as liquidity levels
    - Filter out levels too close (< ATR * 0.5 from entry)
    - From remaining, pick first level that gives RR >= 1.5
    - tp2 = next valid level after tp1
    """
    sl_dist   = abs(entry - sl) if sl else 0
    min_dist  = atr * 0.5
    levels    = []  # list of (price, label)

    h1_struct = confluence.get("h1", {}).get("structure", {})
    h1_zones  = confluence.get("h1", {}).get("zones", [])

    # H1 structure swings — major levels
    last_high = h1_struct.get("last_high")
    last_low  = h1_struct.get("last_low")
    if last_high:
        levels.append((last_high, f"H1 swing high ({round(last_high, 5)})"))
    if last_low:
        levels.append((last_low, f"H1 swing low ({round(last_low, 5)})"))

    # H1 zones — strong levels only
    for zone in h1_zones:
        if zone.get("strength", 0) < 50:
            continue
        mid   = (zone["high"] + zone["low"]) / 2
        label = f"H1 {zone.get('type','zone')} zone ({round(mid, 5)}, str={zone.get('strength')})"
        levels.append((mid, label))

    # Filter by direction and min distance from entry
    if direction == "bullish":
        candidates = [(p, lbl) for p, lbl in levels if p > entry and (p - entry) >= min_dist]
        candidates.sort(key=lambda x: x[0])   # nearest first
    else:
        candidates = [(p, lbl) for p, lbl in levels if p < entry and (entry - p) >= min_dist]
        candidates.sort(key=lambda x: x[0], reverse=True)  # nearest first

    # Pick first level with RR >= 1.5
    tp1, tp1_label = None, None
    tp2, tp2_label = None, None

    for price, label in candidates:
        if sl_dist == 0:
            tp1, tp1_label = price, label
            break
        rr = abs(price - entry) / sl_dist
        if rr >= 1.5:
            if tp1 is None:
                tp1, tp1_label = price, label
            elif tp2 is None:
                tp2, tp2_label = price, label
                break

    # Fallback tp1 — closest valid level even if RR < 1.5
    if tp1 is None and candidates:
        tp1, tp1_label = candidates[0]
        tp1_label = f"{tp1_label} [RR<1.5 fallback]"

    # Fallback tp2 — 1.5x tp1 distance
    if tp2 is None and tp1 is not None:
        dist = abs(tp1 - entry)
        tp2  = entry + dist * 1.5 if direction == "bullish" else entry - dist * 1.5
        tp2_label = "1.5x extension"

    return tp1, tp2, tp1_label or "none"
