"""
strategies/news_sniper.py — News Sniper Mode (strict silo)

ONLY runs when NEWS_MODE is active.
Uses M1 candles only for CHoCH and wick sweep detection.
Logic never bleeds into standard mode.

ICT News Sequence:
  1. High-impact news fires → big spike candle (1.5x+ ATR)
  2. Spike wicks above swing high or below swing low (liquidity grab)
  3. Closes back inside range = stops taken, institutional reversal incoming
  4. M1 CHoCH fires in opposite direction = entry confirmed
  5. SL = spike extreme + buffer, TP = nearest opposing liquidity

Entry States (same 3 as gold_strategy, consistent across system):
  ENTER_NOW   — spike + wick sweep + M1 CHoCH all confirmed
  WAIT_RETEST — spike + sweep confirmed, waiting for M1 CHoCH
  SKIP        — no spike, no sweep, or conflicting signals
"""

import logging
import pandas as pd
from core.fetcher import pip_size
from alerts.scorer import NEWS_LIKELIHOODS, BASE_RATES, calculate_posterior, calculate_ev

logger = logging.getLogger(__name__)

# ── CONSTANTS ─────────────────────────────────────────────────────────────────

_SPIKE_ATR_MULT  = 1.5    # candle must be 1.5x ATR to qualify as news spike
_WICK_PCT_MIN    = 0.30   # wick must be 30%+ of candle range to be a real sweep
_M1_LOOKBACK     = 10     # how many M1 candles to look back for CHoCH
_SL_BUFFER_MULT  = 0.20   # SL buffer beyond spike extreme as fraction of spike range
_MIN_RR          = 1.5    # news sniper minimum RR (higher than standard 1.2)


# ── M1 SPIKE DETECTOR ────────────────────────────────────────────────────────

def _detect_news_spike(df_m1: pd.DataFrame) -> dict:
    """
    Detects a news spike candle on M1.
    Spike = candle range >= 1.5x ATR + wick-heavy (not a clean body move).

    Returns:
    {
        "detected":        bool,
        "direction":       "up" | "down",   # which way did it spike
        "reversal_bias":   "bullish" | "bearish",
        "spike_extreme":   float,            # wick tip (SL anchor)
        "spike_body_end":  float,            # close of spike candle
        "atr_ratio":       float,
        "bars_ago":        int,
    }
    """
    if df_m1 is None or len(df_m1) < 15:
        return {"detected": False}

    atr = df_m1["high"].sub(df_m1["low"]).rolling(14).mean().iloc[-1]
    if atr == 0:
        return {"detected": False}

    # Check last 5 M1 candles for a spike
    for i in range(1, 6):
        candle      = df_m1.iloc[-i]
        candle_range = candle["high"] - candle["low"]

        if candle_range < atr * _SPIKE_ATR_MULT:
            continue

        body     = abs(candle["close"] - candle["open"])
        wick_pct = (candle_range - body) / candle_range if candle_range > 0 else 0

        if wick_pct < _WICK_PCT_MIN:
            continue   # clean body move, not a spike/sweep

        upper_wick = candle["high"] - max(candle["open"], candle["close"])
        lower_wick = min(candle["open"], candle["close"]) - candle["low"]

        if upper_wick > lower_wick:
            return {
                "detected":       True,
                "direction":      "up",
                "reversal_bias":  "bearish",   # spiked up = expect reversal down
                "spike_extreme":  float(candle["high"]),
                "spike_body_end": float(min(candle["open"], candle["close"])),
                "atr_ratio":      round(candle_range / atr, 1),
                "bars_ago":       i - 1,
            }
        else:
            return {
                "detected":       True,
                "direction":      "down",
                "reversal_bias":  "bullish",   # spiked down = expect reversal up
                "spike_extreme":  float(candle["low"]),
                "spike_body_end": float(max(candle["open"], candle["close"])),
                "atr_ratio":      round(candle_range / atr, 1),
                "bars_ago":       i - 1,
            }

    return {"detected": False}


# ── M1 CHoCH DETECTOR ────────────────────────────────────────────────────────

def _detect_m1_choch(df_m1: pd.DataFrame, reversal_bias: str, spike_bars_ago: int) -> dict:
    """
    Detects M1 Change of Character AFTER a spike.
    Only looks at candles formed AFTER the spike (not before).

    Bullish CHoCH: after bearish spike, M1 closes above a recent M1 swing high
    Bearish CHoCH: after bullish spike, M1 closes below a recent M1 swing low

    Returns:
    {
        "detected": bool,
        "type":     "bullish" | "bearish",
        "level":    float,
        "bars_ago": int,
    }
    """
    if df_m1 is None or len(df_m1) < _M1_LOOKBACK + spike_bars_ago:
        return {"detected": False}

    # Only evaluate candles after the spike
    post_spike = df_m1.iloc[-(spike_bars_ago + 1):]
    if len(post_spike) < 3:
        return {"detected": False}

    if reversal_bias == "bullish":
        # Look for M1 close above recent swing high (in post-spike candles)
        recent_high = post_spike["high"].iloc[:-1].max()
        last_close  = post_spike["close"].iloc[-1]
        if last_close > recent_high:
            return {
                "detected": True,
                "type":     "bullish",
                "level":    round(float(recent_high), 2),
                "bars_ago": 0,
                "description": f"⚡ M1 CHoCH BULLISH — closed above {round(recent_high, 2)} after spike",
            }

    elif reversal_bias == "bearish":
        # Look for M1 close below recent swing low (in post-spike candles)
        recent_low = post_spike["low"].iloc[:-1].min()
        last_close = post_spike["close"].iloc[-1]
        if last_close < recent_low:
            return {
                "detected": True,
                "type":     "bearish",
                "level":    round(float(recent_low), 2),
                "bars_ago": 0,
                "description": f"⚡ M1 CHoCH BEARISH — closed below {round(recent_low, 2)} after spike",
            }

    return {"detected": False}


# ── NEWS SNIPER LEVELS ────────────────────────────────────────────────────────

def _calculate_sniper_levels(
    price: float,
    direction: str,
    spike: dict,
    confluence: dict,
    pair: str,
) -> dict:
    """
    SL = spike extreme + small buffer (institutional stops are AT the extreme)
    TP = nearest opposing swing/zone with RR >= 1.5
    """
    spike_extreme = spike.get("spike_extreme", 0)
    pip           = pip_size(pair)

    # SL: just beyond the spike extreme
    spike_range = abs(spike.get("spike_body_end", price) - spike_extreme)
    sl_buffer   = spike_range * _SL_BUFFER_MULT

    if direction == "bullish":
        sl = spike_extreme - sl_buffer
    else:
        sl = spike_extreme + sl_buffer

    sl_dist  = abs(price - sl)
    sl_pips  = round(sl_dist / pip, 1) if pip > 0 else 0

    # TP: nearest swing in direction
    h1_struct  = confluence.get("h1",  {}).get("structure", {})
    m15_struct = confluence.get("m15", {}).get("structure", {})

    tp1 = tp2 = None

    if direction == "bullish":
        for lvl in [m15_struct.get("last_high", 0), h1_struct.get("last_high", 0)]:
            if lvl and lvl > price and (lvl - price) >= sl_dist * _MIN_RR:
                tp1 = lvl
                break
    else:
        for lvl in [m15_struct.get("last_low", 0), h1_struct.get("last_low", 0)]:
            if lvl and lvl < price and (price - lvl) >= sl_dist * _MIN_RR:
                tp1 = lvl
                break

    if tp1 is None:
        tp1 = price + sl_dist * _MIN_RR if direction == "bullish" else price - sl_dist * _MIN_RR

    tp2 = price + sl_dist * 2.5 if direction == "bullish" else price - sl_dist * 2.5

    tp1_pips = round(abs(tp1 - price) / pip, 1) if pip > 0 else 0
    tp2_pips = round(abs(tp2 - price) / pip, 1) if pip > 0 else 0
    decimals = 2 if "XAU" in pair else (3 if "JPY" in pair else 5)

    rr_val = tp1_pips / sl_pips if sl_pips > 0 else 0

    return {
        "entry_price": round(price, decimals),
        "sl_price":    round(sl,   decimals),
        "tp1_price":   round(tp1,  decimals),
        "tp2_price":   round(tp2,  decimals),
        "sl_pips":     sl_pips,
        "tp1_pips":    tp1_pips,
        "tp2_pips":    tp2_pips,
        "rr1":         f"1:{round(rr_val, 1)}",
        "rr2":         f"1:{round(tp2_pips / sl_pips, 1)}" if sl_pips > 0 else "1:?",
        "rr_val":      rr_val,
    }


# ── MAIN ENTRY POINT ──────────────────────────────────────────────────────────

def apply_news_sniper(scored: dict, confluence: dict, pair: str, candles: dict) -> dict:
    """
    Main entry point for news sniper mode.
    Called from mode_manager when NEWS_MODE is active.

    Args:
        scored:     output from score_signal() with NEWS_LIKELIHOODS already applied
        confluence: full confluence dict
        pair:       trading pair
        candles:    raw candle dict including M1

    Returns updated scored dict with news sniper entry state and levels.
    """
    price = confluence.get("current_price", 0)
    if not price:
        return scored

    df_m1 = candles.get("M1")

    # ── SPIKE DETECTION ───────────────────────────────────────────────────────
    spike = _detect_news_spike(df_m1)

    if not spike.get("detected"):
        scored.update({
            "dl_blocked":      True,
            "dl_block_reason": "News sniper: no spike detected on M1",
            "should_alert":    False,
            "entry_state":     "SKIP",
            "flags":           ["🚫 NEWS SNIPER — no M1 spike detected, waiting"],
        })
        logger.info(f"{pair} | NEWS SNIPER | no spike")
        return scored

    reversal_bias = spike["reversal_bias"]
    direction     = scored.get("direction", "none")

    # Spike reversal bias must match intended trade direction
    if reversal_bias != direction:
        scored.update({
            "dl_blocked":      True,
            "dl_block_reason": f"News sniper: spike bias {reversal_bias} ≠ signal {direction}",
            "should_alert":    False,
            "entry_state":     "SKIP",
            "flags":           [f"🚫 NEWS SNIPER — spike {reversal_bias.upper()} but signal is {direction.upper()}"],
        })
        return scored

    # ── M1 CHoCH DETECTION ────────────────────────────────────────────────────
    choch = _detect_m1_choch(df_m1, reversal_bias, spike.get("bars_ago", 0))

    if not choch.get("detected"):
        # Spike confirmed, waiting for CHoCH
        scored.update({
            "dl_blocked":      False,
            "should_alert":    False,
            "should_log":      True,
            "entry_state":     "WAIT_RETEST",
            "flags": [
                f"⚡ NEWS SPIKE {spike['direction'].upper()} — {spike['atr_ratio']}×ATR, "
                f"reversal bias {reversal_bias.upper()}",
                f"⏳ WAIT — watching for M1 CHoCH {reversal_bias.upper()} to confirm entry",
            ][:5],
        })
        logger.info(f"{pair} | NEWS SNIPER | spike={spike['atr_ratio']}x, waiting CHoCH")
        return scored

    # ── FULL SEQUENCE CONFIRMED ───────────────────────────────────────────────
    levels = _calculate_sniper_levels(price, direction, spike, confluence, pair)

    if levels["rr_val"] < _MIN_RR:
        scored.update({
            "dl_blocked":      True,
            "dl_block_reason": f"News sniper RR {round(levels['rr_val'], 1)} < {_MIN_RR}",
            "should_alert":    False,
            "entry_state":     "SKIP",
            "flags":           [f"🚫 NEWS SNIPER — RR {round(levels['rr_val'], 1)} too low"],
        })
        return scored

    # Bayesian probability for news setup
    conditions = {
        "news_spike_detected": True,
        "wick_sweep":          True,
        "m1_choch":            True,
        "fvg_overlap":         confluence.get("has_fvg_overlap", False),
        "h1_aligned":          confluence.get("h1", {}).get("bias") == direction,
        "ict_conflict":        confluence.get("ict_conflict", False),
        "news_safe":           False,   # inverted in news mode — we WANT news
    }
    p_win = calculate_posterior("sweep_choch_fvg", conditions, NEWS_LIKELIHOODS)
    ev    = calculate_ev(p_win, levels["rr_val"])

    flags = [
        f"✅ NEWS SNIPER ENTER NOW — spike + M1 CHoCH confirmed",
        f"💥 Spike {spike['direction'].upper()} {spike['atr_ratio']}×ATR — {reversal_bias.upper()} reversal",
        choch.get("description", "⚡ M1 CHoCH confirmed"),
        f"📍 SL: {levels['sl_price']} (spike extreme) | TP1: {levels['tp1_price']} | RR: {levels['rr1']}",
        f"P(win): {round(p_win*100)}% | EV: {'+' if ev>=0 else ''}{ev}",
    ]

    scored.update({
        "dl_blocked":      False,
        "dl_block_reason": "",
        "should_alert":    True,
        "should_log":      True,
        "entry_state":     "ENTER_NOW",
        "p_win":           p_win,
        "p_win_pct":       f"{round(p_win*100)}% (news)",
        "ev":              ev,
        "flags":           flags[:5],
        "trade_levels":    levels,
        "news_spike":      spike,
        "m1_choch":        choch,
        "gold_mode":       pair in ("XAU_USD", "XAG_USD"),
    })

    logger.info(
        f"{pair} | NEWS SNIPER ENTER | {direction} | "
        f"spike={spike['atr_ratio']}x choch={choch['type']} "
        f"RR={levels['rr1']} P(win)={p_win}"
    )

    return scored
