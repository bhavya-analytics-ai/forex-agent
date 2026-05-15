"""
strategies/news_sniper.py — News Sniper Mode (strict silo)

ONLY runs when NEWS_MODE is active.
Dual-timeframe: M5 liquidity sweep → M1 CHoCH entry trigger.
Logic never bleeds into standard mode.

ICT News Sequence (dual-TF):
  1. High-impact news fires
  2. M5 candle wicks through a swing high/low (institutional stop hunt), closes back inside
  3. M5 sweep confirmed = liquidity grab complete, reversal bias set
  4. M1 CHoCH fires in reversal direction = entry confirmed
  5. SL = M5 sweep extreme + buffer, TP = nearest opposing liquidity

H1 Marubozu Hard Block:
  If last completed H1 candle is a strong Marubozu (body >= 80% range) in the
  OPPOSITE direction of the reversal — a standard post-spike M1 CHoCH is NOT
  enough. Requires a Trend Reversal CHoCH (M1 close breaks a PRE-SPIKE swing
  high/low, not just the mini post-spike reaction). Prevents buying into a
  dominant H1 sell candle on a micro bounce.

Entry States:
  ENTER_NOW   — M5 sweep + M1 CHoCH confirmed (standard or reversal CHoCH)
  WAIT_RETEST — M5 sweep confirmed, waiting for M1 CHoCH
  SKIP        — no sweep, bias mismatch, H1 block not cleared, or RR too low
"""

import logging
import pandas as pd
from core.fetcher import pip_size
from alerts.scorer import NEWS_LIKELIHOODS, BASE_RATES, calculate_posterior, calculate_ev

logger = logging.getLogger(__name__)

# ── CONSTANTS ─────────────────────────────────────────────────────────────────

_SPIKE_ATR_MULT      = 1.5    # kept for reference / future M1 spike confirmation
_WICK_PCT_MIN        = 0.30   # minimum wick fraction to qualify as sweep
_M1_LOOKBACK         = 10     # post-spike M1 CHoCH lookback
_M5_LOOKBACK_SWINGS  = 20     # bars to define M5 swing high/low
_M5_SWEEP_WINDOW     = 5      # last N M5 candles checked for sweep
_H1_MARUBOZU_BODY    = 0.80   # body/range ratio to qualify as Marubozu
_SL_BUFFER_MULT      = 0.20   # SL buffer beyond sweep extreme
_MIN_RR              = 1.5    # news sniper minimum RR

# CHoCH candle quality gates
_CHOCH_MAX_WICK_PCT       = 0.70   # reject trigger candle if wick >= 70% of range (no body commitment)
_CHOCH_DISPLACEMENT_MULT  = 1.2    # trigger candle body must be >= 1.2x avg body of prior 5 candles
_CHOCH_BODY_REF_CANDLES   = 5      # how many candles before the trigger to measure avg body


# ── M5 LIQUIDITY SWEEP DETECTOR ──────────────────────────────────────────────

def _detect_m5_sweep(df_m5: pd.DataFrame) -> dict:
    """
    Gate 1: M5 liquidity sweep — wick through a swing high/low, close back inside.
    Institutional stop hunt. M1 CHoCH only armed after this fires.

    Returns:
    {
        "detected":      bool,
        "direction":     "up" | "down",    # direction of the wick
        "reversal_bias": "bullish" | "bearish",
        "sweep_extreme": float,            # wick tip → SL anchor
        "swept_level":   float,            # swing level that was swept
        "bars_ago":      int,
    }
    """
    if df_m5 is None or len(df_m5) < _M5_LOOKBACK_SWINGS + _M5_SWEEP_WINDOW:
        return {"detected": False}

    # Define swing from the lookback window (exclude the recent sweep window)
    lookback   = df_m5.iloc[-(_M5_LOOKBACK_SWINGS + _M5_SWEEP_WINDOW):-_M5_SWEEP_WINDOW]
    swing_high = float(lookback["high"].max())
    swing_low  = float(lookback["low"].min())

    weak_sweep_found = False  # track whether a candle went through the level but failed wick gate

    for i in range(1, _M5_SWEEP_WINDOW + 1):
        c            = df_m5.iloc[-i]
        candle_range = float(c["high"]) - float(c["low"])

        # Bearish sweep: wicked above swing high, closed back below it
        if c["high"] > swing_high and c["close"] < swing_high:
            wick_frac = (float(c["high"]) - swing_high) / candle_range if candle_range > 0 else 0.0
            if wick_frac < _WICK_PCT_MIN:
                logger.debug(
                    f"[sweep] bearish wick at bars_ago={i-1} rejected: "
                    f"wick_frac={round(wick_frac, 3)} < _WICK_PCT_MIN={_WICK_PCT_MIN}"
                )
                weak_sweep_found = True
                continue  # keep looking — an older candle may have a stronger wick
            return {
                "detected":          True,
                "direction":         "up",
                "reversal_bias":     "bearish",
                "sweep_extreme":     float(c["high"]),
                "swept_level":       round(swing_high, 5),
                "sweep_candle_close": float(c["close"]),
                "bars_ago":          i - 1,
                "wick_frac":         round(wick_frac, 3),
            }

        # Bullish sweep: wicked below swing low, closed back above it
        if c["low"] < swing_low and c["close"] > swing_low:
            wick_frac = (swing_low - float(c["low"])) / candle_range if candle_range > 0 else 0.0
            if wick_frac < _WICK_PCT_MIN:
                logger.debug(
                    f"[sweep] bullish wick at bars_ago={i-1} rejected: "
                    f"wick_frac={round(wick_frac, 3)} < _WICK_PCT_MIN={_WICK_PCT_MIN}"
                )
                weak_sweep_found = True
                continue  # keep looking — an older candle may have a stronger wick
            return {
                "detected":          True,
                "direction":         "down",
                "reversal_bias":     "bullish",
                "sweep_extreme":     float(c["low"]),
                "swept_level":       round(swing_low, 5),
                "sweep_candle_close": float(c["close"]),
                "bars_ago":          i - 1,
                "wick_frac":         round(wick_frac, 3),
            }

    # Nothing qualified in the last _M5_SWEEP_WINDOW candles.
    # reject_reason distinguishes: nothing touched the level vs touched but wick too small.
    reject_reason = "sweep_too_weak" if weak_sweep_found else "no_sweep_in_window"
    return {"detected": False, "reject_reason": reject_reason}


# ── H1 MARUBOZU DETECTOR ─────────────────────────────────────────────────────

def _detect_h1_marubozu(df_h1: pd.DataFrame) -> dict:
    """
    Checks if the last COMPLETED H1 candle is a strong Marubozu.
    Marubozu = body >= 80% of total H-L range (dominant directional conviction).
    Used to escalate CHoCH requirement — must break PRE-SPIKE swing, not just
    mini post-spike reaction.

    Returns: {"detected": bool, "direction": "bullish"|"bearish", "body_pct": float}
    """
    if df_h1 is None or len(df_h1) < 2:
        return {"detected": False}

    c = df_h1.iloc[-2]   # last completed candle (not current forming)
    total_range = c["high"] - c["low"]
    if total_range == 0:
        return {"detected": False}

    body     = abs(c["close"] - c["open"])
    body_pct = body / total_range

    if body_pct < _H1_MARUBOZU_BODY:
        return {"detected": False}

    direction = "bullish" if c["close"] > c["open"] else "bearish"
    return {
        "detected":  True,
        "direction": direction,
        "body_pct":  round(body_pct, 2),
    }


# ── CHoCH CANDLE QUALITY VALIDATOR ───────────────────────────────────────────

def _validate_choch_candle(df_m1: pd.DataFrame) -> dict:
    """
    Two-gate quality check on the trigger candle (df_m1.iloc[-1]).

    Gate 1 — Wick rejection:
        If the trigger candle is >= 70% wick (< 30% body), it has no directional
        commitment. A shooting star closing 1 pip above a swing high is noise.
        Reject it.

    Gate 2 — Displacement:
        The trigger candle body must be >= 1.2x the average body of the prior
        N candles. A micro doji poke barely above the level is not a CHoCH —
        it's a false break. We want to see institutional displacement.

    Returns:
    {
        "passed":       bool,
        "reject_reason": str | None,  # "wick_dominated" | "no_displacement" | None
        "body":         float,
        "wick_pct":     float,
        "avg_body":     float,
        "displacement_ratio": float,
    }
    """
    trigger = df_m1.iloc[-1]
    body    = abs(float(trigger["close"]) - float(trigger["open"]))
    rng     = float(trigger["high"]) - float(trigger["low"])

    wick_pct = (rng - body) / rng if rng > 0 else 1.0

    # Gate 1: wick rejection
    if wick_pct >= _CHOCH_MAX_WICK_PCT:
        return {
            "passed":             False,
            "reject_reason":      "wick_dominated",
            "body":               round(body, 5),
            "wick_pct":           round(wick_pct, 3),
            "avg_body":           None,
            "displacement_ratio": None,
        }

    # Gate 2: displacement — compare to prior N candles
    ref_slice = df_m1.iloc[-(1 + _CHOCH_BODY_REF_CANDLES):-1]
    avg_body  = 0.0
    disp_ratio = 0.0

    if len(ref_slice) >= 2:
        avg_body   = float(ref_slice.apply(
            lambda r: abs(r["close"] - r["open"]), axis=1
        ).mean())
        disp_ratio = body / avg_body if avg_body > 0 else 0.0

        if avg_body > 0 and disp_ratio < _CHOCH_DISPLACEMENT_MULT:
            return {
                "passed":             False,
                "reject_reason":      "no_displacement",
                "body":               round(body, 5),
                "wick_pct":           round(wick_pct, 3),
                "avg_body":           round(avg_body, 5),
                "displacement_ratio": round(disp_ratio, 2),
            }

    return {
        "passed":             True,
        "reject_reason":      None,
        "body":               round(body, 5),
        "wick_pct":           round(wick_pct, 3),
        "avg_body":           round(avg_body, 5),
        "displacement_ratio": round(disp_ratio, 2),
    }


# ── M1 CHoCH DETECTOR ────────────────────────────────────────────────────────

def _detect_m1_choch(
    df_m1: pd.DataFrame,
    reversal_bias: str,
    spike_bars_ago: int,
    strict: bool = False,
) -> dict:
    """
    Detects M1 Change of Character AFTER an M5 sweep.

    strict=False (standard): M1 closes above/below a post-spike mini swing.
        Used when H1 context is neutral or H1 bias agrees with trade direction.

    strict=True (Trend Reversal CHoCH): M1 must close beyond a PRE-SPIKE swing
        high/low — not just the bounce after the sweep. Requires meaningful
        structure shift against the dominant H1 Marubozu candle.

    Both paths run through _validate_choch_candle():
      - Wick >= 70% of candle range → rejected (no body commitment)
      - Body < 1.2x avg of prior 5 candle bodies → rejected (no displacement)

    Returns:
    {
        "detected":          bool,
        "reject_reason":     str | None,   # why it failed quality check
        "type":              "bullish" | "bearish",
        "level":             float,
        "is_reversal_choch": bool,
        "body":              float,
        "wick_pct":          float,
        "displacement_ratio": float,
        "description":       str,
    }
    """
    if df_m1 is None or len(df_m1) < max(_M1_LOOKBACK, spike_bars_ago + 3):
        return {"detected": False}

    if strict:
        # Pre-spike swing: candles well before the sweep event
        pre_window = min(len(df_m1), 25)
        pre_end    = max(spike_bars_ago, 1)
        pre_spike  = df_m1.iloc[-pre_window:-pre_end]
        if len(pre_spike) < 3:
            return {"detected": False}

        last_close = float(df_m1.iloc[-1]["close"])

        level_broken = False
        choch_type   = None
        level_val    = None

        if reversal_bias == "bullish":
            pre_swing_high = float(pre_spike["high"].max())
            if last_close > pre_swing_high:
                level_broken = True
                choch_type   = "bullish"
                level_val    = pre_swing_high

        elif reversal_bias == "bearish":
            pre_swing_low = float(pre_spike["low"].min())
            if last_close < pre_swing_low:
                level_broken = True
                choch_type   = "bearish"
                level_val    = pre_swing_low

        if not level_broken:
            return {"detected": False}

        # Quality gates
        qc = _validate_choch_candle(df_m1)
        if not qc["passed"]:
            logger.info(
                f"[choch] strict {choch_type} level broken but candle rejected: "
                f"{qc['reject_reason']} | wick={qc['wick_pct']} disp={qc['displacement_ratio']}"
            )
            return {"detected": False, "reject_reason": qc["reject_reason"], **qc}

        desc_prefix = "⚡ M1 TREND REVERSAL CHoCH"
        level_word  = "above" if choch_type == "bullish" else "below"
        return {
            "detected":           True,
            "reject_reason":      None,
            "type":               choch_type,
            "level":              round(level_val, 5),
            "bars_ago":           0,
            "is_reversal_choch":  True,
            "body":               qc["body"],
            "wick_pct":           qc["wick_pct"],
            "displacement_ratio": qc["displacement_ratio"],
            "description": (
                f"{desc_prefix} {choch_type.upper()} — "
                f"closed {level_word} pre-sweep swing {round(level_val, 5)} | "
                f"body {round(qc['body']/0.01):.0f}p, wick {int(qc['wick_pct']*100)}%, "
                f"disp {qc['displacement_ratio']}x"
            ),
        }

    # ── STANDARD CHoCH (post-spike mini swing) ────────────────────────────────
    post_spike = df_m1.iloc[-(spike_bars_ago + 1):]
    if len(post_spike) < 3:
        return {"detected": False}

    level_broken = False
    choch_type   = None
    level_val    = None

    if reversal_bias == "bullish":
        recent_high = float(post_spike["high"].iloc[:-1].max())
        last_close  = float(post_spike["close"].iloc[-1])
        if last_close > recent_high:
            level_broken = True
            choch_type   = "bullish"
            level_val    = recent_high

    elif reversal_bias == "bearish":
        recent_low = float(post_spike["low"].iloc[:-1].min())
        last_close = float(post_spike["close"].iloc[-1])
        if last_close < recent_low:
            level_broken = True
            choch_type   = "bearish"
            level_val    = recent_low

    if not level_broken:
        return {"detected": False}

    # Quality gates
    qc = _validate_choch_candle(df_m1)
    if not qc["passed"]:
        logger.info(
            f"[choch] standard {choch_type} level broken but candle rejected: "
            f"{qc['reject_reason']} | wick={qc['wick_pct']} disp={qc['displacement_ratio']}"
        )
        return {"detected": False, "reject_reason": qc["reject_reason"], **qc}

    level_word = "above" if choch_type == "bullish" else "below"
    return {
        "detected":           True,
        "reject_reason":      None,
        "type":               choch_type,
        "level":              round(level_val, 5),
        "bars_ago":           0,
        "is_reversal_choch":  False,
        "body":               qc["body"],
        "wick_pct":           qc["wick_pct"],
        "displacement_ratio": qc["displacement_ratio"],
        "description": (
            f"⚡ M1 CHoCH {choch_type.upper()} — "
            f"closed {level_word} {round(level_val, 5)} after sweep | "
            f"body {round(qc['body']/0.01):.0f}p, wick {int(qc['wick_pct']*100)}%, "
            f"disp {qc['displacement_ratio']}x"
        ),
    }


# ── NEWS SNIPER LEVELS ────────────────────────────────────────────────────────

def _calculate_sniper_levels(
    price: float,
    direction: str,
    spike: dict,
    confluence: dict,
    pair: str,
) -> dict:
    """
    SL = sweep extreme + small buffer (stops are AT the wick tip).
    TP = nearest opposing swing/zone with RR >= 1.5.
    """
    spike_extreme = spike.get("spike_extreme", 0)
    pip           = pip_size(pair)

    spike_range = abs(spike.get("spike_body_end", price) - spike_extreme)
    sl_buffer   = spike_range * _SL_BUFFER_MULT

    if direction == "bullish":
        sl = spike_extreme - sl_buffer
    else:
        sl = spike_extreme + sl_buffer

    sl_dist  = abs(price - sl)
    sl_pips  = round(sl_dist / pip, 1) if pip > 0 else 0

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
        # Use _MIN_RR + small buffer so rr_val never fails the boundary check due to float precision
        tp1 = price + sl_dist * (_MIN_RR + 0.05) if direction == "bullish" else price - sl_dist * (_MIN_RR + 0.05)

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

    Gate sequence:
      1. M5 liquidity sweep (institutional stop hunt)
      2. H1 Marubozu check → escalates CHoCH requirement if H1 is dominant counter-trend
      3. M1 CHoCH — standard (post-spike mini swing) OR strict (pre-sweep swing break)

    Args:
        scored:     output from score_signal() with NEWS_LIKELIHOODS
        confluence: full confluence dict
        pair:       trading pair
        candles:    raw candle dict — must contain M5, M1, H1

    Returns updated scored dict.
    """
    price = confluence.get("current_price", 0)
    if not price:
        return scored

    df_m5 = candles.get("M5")
    df_m1 = candles.get("M1")
    df_h1 = candles.get("H1")

    direction = scored.get("direction", "none")

    # ── GATE 1: M5 LIQUIDITY SWEEP ────────────────────────────────────────────
    m5_sweep = _detect_m5_sweep(df_m5)

    if not m5_sweep.get("detected"):
        reject_reason = m5_sweep.get("reject_reason", "no_sweep_in_window")
        if reject_reason == "sweep_too_weak":
            flag = "🚫 NEWS SNIPER — M5 wick through level but too small (< 30% of candle range), not an institutional sweep"
            block_reason = "News sniper: M5 wick detected but wick_frac < _WICK_PCT_MIN — sweep too weak"
        else:
            flag = "🚫 NEWS SNIPER — no M5 sweep in last 5 bars, waiting for institutional liquidity grab"
            block_reason = "News sniper: no M5 liquidity sweep detected in window"
        scored.update({
            "dl_blocked":      True,
            "dl_block_reason": block_reason,
            "should_alert":    False,
            "entry_state":     "SKIP",
            "flags":           [flag],
        })
        logger.info(f"{pair} | NEWS SNIPER | SKIP | {reject_reason}")
        return scored

    reversal_bias = m5_sweep["reversal_bias"]

    # M5 sweep reversal bias must match intended trade direction
    if reversal_bias != direction:
        scored.update({
            "dl_blocked":      True,
            "dl_block_reason": f"News sniper: M5 sweep bias {reversal_bias} ≠ signal {direction}",
            "should_alert":    False,
            "entry_state":     "SKIP",
            "flags":           [f"🚫 NEWS SNIPER — M5 sweep {reversal_bias.upper()} but signal is {direction.upper()}"],
        })
        return scored

    # ── GATE 2: H1 MARUBOZU CHECK ─────────────────────────────────────────────
    h1_marub       = _detect_h1_marubozu(df_h1)
    require_strict = False
    h1_block_note  = ""

    if h1_marub.get("detected") and h1_marub["direction"] != reversal_bias:
        # H1 last candle is a strong Marubozu AGAINST our reversal direction.
        # Standard post-sweep M1 CHoCH is not enough — must break a pre-sweep swing.
        require_strict = True
        h1_block_note  = (
            f"H1 {h1_marub['direction'].upper()} Marubozu ({int(h1_marub['body_pct']*100)}% body) "
            f"→ Trend Reversal CHoCH required"
        )
        logger.info(f"{pair} | NEWS SNIPER | {h1_block_note}")

    # ── GATE 3: M1 CHoCH (standard or strict) ─────────────────────────────────
    # M5 bars_ago ≠ M1 bars. Convert: each M5 bar = 5 M1 bars.
    # Minimum 5 M1 bars lookback so post_spike slice always has >= 3 rows.
    m1_lookback = max((m5_sweep.get("bars_ago", 0) + 1) * 5, 5)
    choch = _detect_m1_choch(
        df_m1,
        reversal_bias,
        m1_lookback,
        strict=require_strict,
    )

    if not choch.get("detected"):
        # Compose wait message
        wait_flags = [
            f"✅ M5 SWEEP {m5_sweep['direction'].upper()} confirmed — swept {m5_sweep['swept_level']}",
        ]
        if require_strict:
            wait_flags.append(
                f"🛑 H1 BLOCK — {h1_block_note}"
            )
            wait_flags.append(
                f"⏳ WAIT — need Trend Reversal CHoCH {reversal_bias.upper()} (pre-sweep swing break)"
            )
        else:
            wait_flags.append(
                f"⏳ WAIT — watching for M1 CHoCH {reversal_bias.upper()} entry trigger"
            )

        scored.update({
            "dl_blocked":   False,
            "should_alert": False,
            "should_log":   True,
            "entry_state":  "WAIT_RETEST",
            "flags":        wait_flags[:5],
        })
        logger.info(
            f"{pair} | NEWS SNIPER | M5 sweep ok, "
            f"{'strict CHoCH' if require_strict else 'standard CHoCH'} not yet"
        )
        return scored

    # ── FULL SEQUENCE CONFIRMED → ENTER NOW ───────────────────────────────────
    spike_proxy = {
        "spike_extreme":  m5_sweep["sweep_extreme"],
        "spike_body_end": m5_sweep["sweep_candle_close"],  # actual M5 sweep candle close, not current price
    }
    levels = _calculate_sniper_levels(price, direction, spike_proxy, confluence, pair)

    if levels["rr_val"] < _MIN_RR:
        scored.update({
            "dl_blocked":      True,
            "dl_block_reason": f"News sniper RR {round(levels['rr_val'], 1)} < {_MIN_RR}",
            "should_alert":    False,
            "entry_state":     "SKIP",
            "flags":           [f"🚫 NEWS SNIPER — RR {round(levels['rr_val'], 1)} too low"],
        })
        return scored

    # Bayesian
    conditions = {
        "news_spike_detected": True,
        "wick_sweep":          True,
        "m1_choch":            True,
        "fvg_overlap":         confluence.get("has_fvg_overlap", False),
        "h1_aligned":          confluence.get("h1", {}).get("bias") == direction,
        "ict_conflict":        confluence.get("ict_conflict", False),
        "news_safe":           False,  # inverted — we WANT news in this mode
    }
    p_win = calculate_posterior("sweep_choch_fvg", conditions, NEWS_LIKELIHOODS)
    ev    = calculate_ev(p_win, levels["rr_val"])

    choch_label = "TREND REVERSAL CHoCH" if choch.get("is_reversal_choch") else "M1 CHoCH"
    flags = [
        f"✅ NEWS SNIPER ENTER NOW — M5 sweep + {choch_label} confirmed",
        f"💥 M5 Swept {m5_sweep['swept_level']} ({m5_sweep['direction'].upper()} wick) — {reversal_bias.upper()} reversal",
        choch.get("description", f"⚡ {choch_label} confirmed"),
        f"📍 SL: {levels['sl_price']} (sweep extreme) | TP1: {levels['tp1_price']} | RR: {levels['rr1']}",
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
        "m5_sweep":        m5_sweep,
        "m1_choch":        choch,
        "h1_marubozu":     h1_marub if h1_marub.get("detected") else None,
        "gold_mode":       pair in ("XAU_USD", "XAG_USD"),
    })

    logger.info(
        f"{pair} | NEWS SNIPER ENTER | {direction} | "
        f"M5 swept={m5_sweep['swept_level']} "
        f"choch={'reversal' if choch.get('is_reversal_choch') else 'standard'} "
        f"RR={levels['rr1']} P(win)={p_win}"
    )

    return scored
