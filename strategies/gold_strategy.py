"""
strategies/gold_strategy.py — XAU_USD and XAG_USD execution strategy

ICT Sniper Sequence (strict order):
  1. Bias   — H1 trend is law
  2. Sweep  — liquidity grab at swing high/low confirms institutional intent
  3. CHoCH  — M5 structure shift AFTER sweep = reversal confirmed
  4. Entry  — FVG or OB tap after CHoCH

Entry States:
  ENTER_NOW   — full sequence confirmed + price at FVG/OB
  WAIT_RETEST — sweep + CHoCH done, waiting for FVG/OB tap
  SKIP        — sequence incomplete, conflicting, or no clear bias

Early Entry: INFO ONLY flag — never changes entry state.
Silver (XAG_USD): same logic, different ATR floor.
"""

import logging
from datetime import datetime, timezone, timedelta
from core.fetcher import pip_size

logger = logging.getLogger(__name__)

# ── CONSTANTS ─────────────────────────────────────────────────────────────────

_ATR_FLOOR = {
    "XAU_USD": 15.0,   # Gold: $15 minimum ATR
    "XAG_USD": 0.80,   # Silver: $0.80 minimum ATR
}
_ATR_CAP_MULT = 2.0    # SL never wider than ATR * 2
_ATR_SL_BUFF  = 0.3    # Buffer beyond swing/OB: ATR * 0.3
_MIN_TP_DIST  = 0.5    # TP must be at least ATR * 0.5 away
_MIN_RR       = 1.2    # Minimum RR for TP to be valid


# ── ATR HELPER ────────────────────────────────────────────────────────────────

def _get_atr(confluence: dict, pair: str) -> float:
    """Estimate ATR from H1 swing range. Floor enforced per pair."""
    structure = confluence.get("h1", {}).get("structure", {})
    last_high = structure.get("last_high", 0)
    last_low  = structure.get("last_low",  0)
    floor     = _ATR_FLOOR.get(pair, 15.0)
    if last_high > last_low:
        return max((last_high - last_low) / 20, floor)
    return floor


# ── ENTRY STATE MACHINE ───────────────────────────────────────────────────────

def _detect_sniper_sequence(confluence: dict, direction: str) -> dict:
    """
    Checks for the full ICT sniper sequence: Sweep → CHoCH → Entry zone.
    Sweep MUST be present before CHoCH is considered valid.

    Returns:
    {
        "sweep_confirmed": bool,
        "choch_confirmed": bool,
        "entry_zone":      bool,
        "entry_state":     "ENTER_NOW" | "WAIT_RETEST" | "SKIP",
        "reason":          str,
    }
    """
    ict = confluence.get("ict", {}) or {}

    # ── STEP 1: SWEEP ─────────────────────────────────────────────────────────
    has_sweep  = ict.get("has_sweep", False)
    sweep      = ict.get("recent_sweep", {}) or {}
    sweep_bias = sweep.get("bias", "")

    # Sweep must align with trade direction
    sweep_valid = has_sweep and sweep_bias == direction

    if not sweep_valid:
        return {
            "sweep_confirmed": False,
            "choch_confirmed": False,
            "entry_zone":      False,
            "entry_state":     "SKIP",
            "reason":          "No sweep — sequence not started",
        }

    # ── STEP 2: CHoCH (only valid after sweep) ────────────────────────────────
    has_choch  = ict.get("has_choch", False)
    choch      = ict.get("choch_m5") or ict.get("choch_m15") or {}
    choch_type = choch.get("type", "")

    choch_valid = has_choch and choch_type == direction

    if not choch_valid:
        return {
            "sweep_confirmed": True,
            "choch_confirmed": False,
            "entry_zone":      False,
            "entry_state":     "SKIP",
            "reason":          "Sweep confirmed — waiting for CHoCH to form",
        }

    # ── STEP 3: ENTRY ZONE (FVG or direction-matched OB) ─────────────────────
    at_fvg = confluence.get("has_fvg_overlap", False)

    at_ob = False
    if ict.get("has_ob"):
        ob = ict.get("top_ob", {}) or {}
        at_ob = ob.get("type", "") == direction

    at_entry_zone = at_fvg or at_ob

    if at_entry_zone:
        return {
            "sweep_confirmed": True,
            "choch_confirmed": True,
            "entry_zone":      True,
            "entry_state":     "ENTER_NOW",
            "reason":          "Sweep + CHoCH + FVG/OB tap — sniper entry confirmed",
        }
    else:
        return {
            "sweep_confirmed": True,
            "choch_confirmed": True,
            "entry_zone":      False,
            "entry_state":     "WAIT_RETEST",
            "reason":          "Sweep + CHoCH confirmed — wait for FVG or OB retest",
        }


# ── EARLY ENTRY DETECTOR (INFO ONLY) ─────────────────────────────────────────

def _check_early_entry(confluence: dict, direction: str, atr: float) -> str:
    """
    Detects building pressure before full sequence confirms.
    Returns a flag string if early conditions are present.
    INFO ONLY — never changes entry state or blocks/allows a trade.
    """
    h1        = confluence.get("h1", {})
    structure = h1.get("structure", {})
    ict       = confluence.get("ict", {}) or {}

    if h1.get("bias", "neutral") != direction:
        return ""

    price     = confluence.get("current_price", 0)
    last_high = structure.get("last_high", 0)
    last_low  = structure.get("last_low",  0)
    strength  = structure.get("strength", 1)
    phase     = structure.get("phase", "ranging")

    near_level = (
        (last_high and abs(price - last_high) <= atr * 0.3) or
        (last_low  and abs(price - last_low)  <= atr * 0.3)
    )
    has_sweep   = ict.get("has_sweep", False)
    good_struct = strength >= 2 and phase not in ("ranging", "deep_pullback")

    if has_sweep and near_level and good_struct:
        return "⚡ EARLY INFO — sweep done, compressing near level, CHoCH pending"
    if has_sweep and good_struct:
        return "⚡ EARLY INFO — sweep confirmed, watching for CHoCH"

    return ""


# ── SL CALCULATOR ─────────────────────────────────────────────────────────────

def _calculate_sl(confluence: dict, direction: str, price: float, atr: float) -> tuple:
    """
    SL priority:
      1. Sweep extreme (most natural ICT SL — beyond the wick that swept stops)
      2. M5 swing
      3. M15 swing
      4. Direction-matched OB edge
      5. ATR * 1.5 fallback

    Always capped at ATR * 2.
    Returns (sl_price, anchor_label)
    """
    ict        = confluence.get("ict", {}) or {}
    m5_struct  = confluence.get("m5",  {}).get("structure", {})
    m15_struct = confluence.get("m15", {}).get("structure", {})
    buf        = atr * _ATR_SL_BUFF
    sl, anchor = None, None

    # 1. Sweep extreme
    sweep   = ict.get("recent_sweep", {}) or {}
    extreme = sweep.get("extreme") or sweep.get("sweep_low") or sweep.get("sweep_high")
    if extreme and sweep.get("bias") == direction:
        if direction == "bullish":
            sl, anchor = extreme - buf, "sweep low"
        else:
            sl, anchor = extreme + buf, "sweep high"

    # 2. M5 swing
    if sl is None:
        if direction == "bullish":
            v = m5_struct.get("last_low", 0)
            if v and v < price:
                sl, anchor = v - buf, "M5 swing low"
        else:
            v = m5_struct.get("last_high", 0)
            if v and v > price:
                sl, anchor = v + buf, "M5 swing high"

    # 3. M15 swing
    if sl is None:
        if direction == "bullish":
            v = m15_struct.get("last_low", 0)
            if v and v < price:
                sl, anchor = v - buf, "M15 swing low"
        else:
            v = m15_struct.get("last_high", 0)
            if v and v > price:
                sl, anchor = v + buf, "M15 swing high"

    # 4. Direction-matched OB
    if sl is None and ict.get("has_ob"):
        ob = ict.get("top_ob", {}) or {}
        if ob.get("type") == direction:
            if direction == "bullish" and ob.get("low"):
                sl, anchor = ob["low"] - buf, "OB edge"
            elif direction == "bearish" and ob.get("high"):
                sl, anchor = ob["high"] + buf, "OB edge"

    # 5. ATR fallback
    if sl is None:
        dist   = atr * 1.5
        sl     = price - dist if direction == "bullish" else price + dist
        anchor = "ATR×1.5 fallback"

    # Cap at ATR * 2
    if abs(price - sl) > atr * _ATR_CAP_MULT:
        sl     = price - atr * _ATR_CAP_MULT if direction == "bullish" else price + atr * _ATR_CAP_MULT
        anchor += " (capped ATR×2)"

    return round(sl, 2), anchor


# ── TP CALCULATOR ─────────────────────────────────────────────────────────────

def _calculate_tp(confluence: dict, direction: str, price: float, sl: float, atr: float) -> tuple:
    """
    TP1 = nearest valid liquidity (RR >= 1.2, distance >= ATR * 0.5). Closest wins.
    TP2 = next level after TP1.
    Returns (tp1, tp2, tp1_label)
    """
    sl_dist    = abs(price - sl)
    min_dist   = atr * _MIN_TP_DIST
    h1_struct  = confluence.get("h1",  {}).get("structure",   {})
    m15_struct = confluence.get("m15", {}).get("structure",   {})
    h1_zones   = confluence.get("h1",  {}).get("active_zones", [])

    candidates = []

    if direction == "bullish":
        for lvl, lbl in [
            (m15_struct.get("last_high", 0), "M15 swing high"),
            (h1_struct.get("last_high",  0), "H1 swing high"),
        ]:
            if lvl and lvl > price and (lvl - price) >= min_dist:
                candidates.append((lvl - price, lvl, lbl))
        for z in h1_zones:
            if z.get("type") in ("resistance", "supply"):
                mid = (z["high"] + z["low"]) / 2
                if mid > price and (mid - price) >= min_dist:
                    candidates.append((mid - price, mid, "zone resistance"))
    else:
        for lvl, lbl in [
            (m15_struct.get("last_low", 0), "M15 swing low"),
            (h1_struct.get("last_low",  0), "H1 swing low"),
        ]:
            if lvl and lvl < price and (price - lvl) >= min_dist:
                candidates.append((price - lvl, lvl, lbl))
        for z in h1_zones:
            if z.get("type") in ("support", "demand"):
                mid = (z["high"] + z["low"]) / 2
                if mid < price and (price - mid) >= min_dist:
                    candidates.append((price - mid, mid, "zone support"))

    # Sort nearest first, deduplicate within ATR * 0.3
    candidates.sort(key=lambda x: x[0])
    deduped = []
    for dist, lvl, lbl in candidates:
        if deduped and abs(lvl - deduped[-1][1]) < atr * 0.3:
            continue
        deduped.append((dist, lvl, lbl))

    tp1 = tp1_label = tp2 = None
    tp1_idx = None

    for i, (dist, lvl, lbl) in enumerate(deduped):
        if sl_dist > 0 and dist / sl_dist >= _MIN_RR:
            tp1, tp1_label, tp1_idx = lvl, lbl, i
            break

    if tp1_idx is not None:
        for dist, lvl, lbl in deduped[tp1_idx + 1:]:
            if sl_dist > 0 and dist / sl_dist >= _MIN_RR:
                tp2 = lvl
                break

    # Fallbacks
    if tp1 is None:
        tp1       = price + sl_dist * 1.5 if direction == "bullish" else price - sl_dist * 1.5
        tp1_label = "1.5×SL fallback"
    if tp2 is None:
        tp2 = price + sl_dist * 2.5 if direction == "bullish" else price - sl_dist * 2.5

    return round(tp1, 2), round(tp2, 2), tp1_label


# ── KILLZONE FILTER ───────────────────────────────────────────────────────────

def _is_killzone() -> tuple:
    """
    Returns (in_killzone: bool, killzone_name: str).

    London Kill Zone : 02:00–05:00 EST  (06:00–09:00 UTC summer / 07:00–10:00 UTC winter)
    New York Kill Zone: 07:00–10:00 EST  (11:00–14:00 UTC summer / 12:00–15:00 UTC winter)

    EST offset: UTC-4 in summer (Mar–Nov), UTC-5 in winter.
    Applied ONLY to Unicorn ENTER_NOW — base gold sniper runs any session.
    """
    now_utc = datetime.now(timezone.utc)
    month   = now_utc.month
    offset  = 4 if 3 <= month <= 11 else 5          # EDT=4, EST=5

    # Convert to EST
    now_est = now_utc - timedelta(hours=offset)
    h, m    = now_est.hour, now_est.minute
    t       = h * 60 + m                             # minutes since midnight EST

    LONDON_START = 2  * 60       #  2:00 EST
    LONDON_END   = 5  * 60       #  5:00 EST
    NY_START     = 7  * 60       #  7:00 EST
    NY_END       = 10 * 60       # 10:00 EST

    if LONDON_START <= t < LONDON_END:
        return True, "London Kill Zone"
    if NY_START <= t < NY_END:
        return True, "New York Kill Zone"

    return False, ""


# ── UNICORN DETECTOR ──────────────────────────────────────────────────────────

def _detect_unicorn(df_m5, df_m1, direction: str, price: float, atr: float) -> dict:
    """
    Unicorn Model: FVG overlapping with a Breaker Block on M5/M1.

    Bullish: bullish FVG inside bullish Breaker Block (broken bearish OB = now support)
    Bearish: bearish FVG inside bearish Breaker Block (broken bullish OB = now resistance)

    M1 FVG inside M5 Breaker = valid — catches fast reversals.
    M5 candle CLOSE in direction = hard lock for ENTER_NOW. Wicks don't count.
    """
    try:
        from core.fvg import detect_fvgs
        from core.ict import find_breaker_blocks

        if df_m5 is None or len(df_m5) < 10:
            return {"detected": False}

        # FVGs: M5 first, then M1 if available (M1 FVG + M5 Breaker = valid unicorn)
        fvgs = detect_fvgs(df_m5)
        if df_m1 is not None and len(df_m1) >= 10:
            fvgs += detect_fvgs(df_m1)

        # Breaker Blocks on M5
        breakers = find_breaker_blocks(df_m5)

        # Filter to matching direction only
        fvgs     = [f for f in fvgs     if f["type"] == direction]
        breakers = [b for b in breakers if b["type"] == direction]

        if not fvgs or not breakers:
            return {"detected": False}

        # Find best overlapping pair (largest overlap wins)
        best = None
        for fvg in fvgs:
            for breaker in breakers:
                ol_top    = min(fvg["top"],    breaker["high"])
                ol_bottom = max(fvg["bottom"], breaker["low"])

                if ol_top <= ol_bottom:
                    continue  # no overlap

                ol_mid  = (ol_top + ol_bottom) / 2
                ol_size = ol_top - ol_bottom

                # Touching = price inside or within ATR*0.1 of zone
                touch_buf   = atr * 0.1
                touching    = (ol_bottom - touch_buf) <= price <= (ol_top + touch_buf)
                approaching = abs(price - ol_mid) <= atr * 0.5

                if not touching and not approaching:
                    continue

                if best is None or ol_size > best["ol_size"]:
                    best = {
                        "fvg":       fvg,
                        "breaker":   breaker,
                        "ol_top":    ol_top,
                        "ol_bottom": ol_bottom,
                        "ol_mid":    ol_mid,
                        "ol_size":   ol_size,
                        "touching":  touching,
                    }

        if best is None:
            return {"detected": False}

        # M5 hard lock — candle must CLOSE in direction, not just wick into zone
        last_m5    = df_m5.iloc[-1]
        m5_confirm = (
            last_m5["close"] > last_m5["open"] if direction == "bullish"
            else last_m5["close"] < last_m5["open"]
        )

        if best["touching"] and m5_confirm:
            entry_state = "ENTER_NOW"
            desc = f"🦄 UNICORN {direction.upper()} — FVG+Breaker overlap confirmed, M5 closed in direction"
        elif best["touching"]:
            entry_state = "WAIT_RETEST"
            desc = f"🦄 UNICORN TOUCH — price in zone, waiting M5 close {direction.upper()}"
        else:
            entry_state = "WAIT_RETEST"
            desc = f"🦄 UNICORN APPROACHING — FVG+Breaker zone at {round(best['ol_mid'], 2)}"

        return {
            "detected":       True,
            "type":           direction,
            "overlap_top":    round(best["ol_top"],    2),
            "overlap_bottom": round(best["ol_bottom"], 2),
            "overlap_mid":    round(best["ol_mid"],    2),
            "overlap_size":   best["ol_size"],
            "touching":       best["touching"],
            "m5_confirmed":   m5_confirm,
            "entry_state":    entry_state,
            "description":    desc,
        }

    except Exception as e:
        logger.debug(f"Unicorn detection error: {e}")
        return {"detected": False}


# ── MAIN ENTRY POINT ──────────────────────────────────────────────────────────

def apply_gold_strategy(scored: dict, confluence: dict, pair: str, candles: dict = None) -> dict:
    """
    Main entry point for XAU_USD and XAG_USD.

    Flow:
      1. Validate direction + price
      2. Get ATR (pair-aware floor)
      3. Run sniper sequence: Sweep → CHoCH → Entry zone
      4. If SKIP: block and return early
      5. Calculate SL/TP
      6. RR check
      7. Build max-5 flags
      8. Check early entry (info only, appended last)
      9. Return updated scored dict
    """
    direction = scored.get("direction", "none")
    price     = confluence.get("current_price", 0)

    if direction in ("none", "neutral") or not price:
        return scored

    atr = _get_atr(confluence, pair)

    # ── SNIPER SEQUENCE ───────────────────────────────────────────────────────
    sequence    = _detect_sniper_sequence(confluence, direction)
    entry_state = sequence["entry_state"]

    # ── SKIP ──────────────────────────────────────────────────────────────────
    if entry_state == "SKIP":
        early_flag = _check_early_entry(confluence, direction, atr)
        flags      = [f"🚫 GOLD SKIP — {sequence['reason']}"]
        if early_flag:
            flags.append(early_flag)
        scored.update({
            "dl_blocked":      True,
            "dl_block_reason": sequence["reason"],
            "should_alert":    False,
            "should_log":      False,
            "flags":           flags[:5],
            "entry_state":     "SKIP",
            "gold_mode":       True,
        })
        logger.info(f"{pair} | SKIP | {direction} | {sequence['reason']}")
        return scored

    # ── CALCULATE LEVELS ──────────────────────────────────────────────────────
    sl, sl_anchor       = _calculate_sl(confluence, direction, price, atr)
    tp1, tp2, tp1_label = _calculate_tp(confluence, direction, price, sl, atr)

    sl_dist  = abs(price - sl)
    pip      = pip_size(pair)
    sl_pips  = round(sl_dist / pip, 1)
    tp1_pips = round(abs(tp1 - price) / pip, 1)
    tp2_pips = round(abs(tp2 - price) / pip, 1)

    # ── RR CHECK ──────────────────────────────────────────────────────────────
    rr_val = tp1_pips / sl_pips if sl_pips > 0 else 0
    if rr_val < _MIN_RR:
        reason = f"RR {round(rr_val, 1)} < {_MIN_RR} — SL={sl_pips}p TP={tp1_pips}p"
        scored.update({
            "dl_blocked":      True,
            "dl_block_reason": reason,
            "should_alert":    False,
            "should_log":      False,
            "flags":           [f"🚫 GOLD BLOCK — {reason}"],
            "entry_state":     "SKIP",
            "gold_mode":       True,
        })
        logger.info(f"{pair} | RR BLOCK | {reason}")
        return scored

    rr1 = f"1:{round(tp1_pips / sl_pips, 1)}"
    rr2 = f"1:{round(tp2_pips / sl_pips, 1)}"

    # ── UNICORN DETECTION ─────────────────────────────────────────────────────
    df_m5 = (candles or {}).get("M5")
    df_m1 = (candles or {}).get("M1")
    unicorn = _detect_unicorn(df_m5, df_m1, direction, price, atr)

    if unicorn["detected"]:
        # Re-run Bayesian posterior with unicorn condition
        from alerts.scorer import calculate_posterior, calculate_ev, STANDARD_LIKELIHOODS, BASE_RATES
        conditions = dict(scored.get("conditions", {}))
        conditions["unicorn_model"] = True
        new_p_win = calculate_posterior("unicorn", conditions, STANDARD_LIKELIHOODS, BASE_RATES)
        new_ev    = calculate_ev(new_p_win, rr_val)
        scored["p_win"]      = new_p_win
        scored["p_win_pct"]  = f"{round(new_p_win * 100)}% (unicorn)"
        scored["ev"]         = new_ev
        scored["score"]      = round(new_p_win * 100)
        scored["setup_type"] = "🦄 UNICORN"
        scored["unicorn"]    = unicorn

        # Unicorn ENTER_NOW gated by killzone — outside London/NY = WAIT_RETEST only
        if unicorn["entry_state"] == "ENTER_NOW":
            in_kz, kz_name = _is_killzone()
            if in_kz:
                entry_state = "ENTER_NOW"
                logger.info(f"{pair} | 🦄 UNICORN ENTER_NOW | {kz_name} ✓")
            else:
                entry_state = "WAIT_RETEST"
                now_est_str = (
                    datetime.now(timezone.utc) - timedelta(hours=(4 if 3 <= datetime.now(timezone.utc).month <= 11 else 5))
                ).strftime("%H:%M EST")
                logger.info(f"{pair} | 🦄 UNICORN → WAIT_RETEST | Outside killzone ({now_est_str})")
                # Update unicorn description to reflect the downgrade
                unicorn = dict(unicorn)
                unicorn["description"] = (
                    f"🦄 UNICORN READY — outside killzone ({now_est_str}), "
                    f"wait for London (2–5am) or NY (7–10am) EST"
                )
                scored["unicorn"] = unicorn

        logger.info(f"{pair} | 🦄 UNICORN | P(win)={new_p_win} EV={new_ev} | {unicorn['description']}")

    # ── FLAGS (max 5) ─────────────────────────────────────────────────────────
    flags = []

    if unicorn["detected"]:
        flags.append(unicorn["description"])
    elif entry_state == "ENTER_NOW":
        flags.append(f"✅ ENTER NOW — {sequence['reason']}")
    else:
        flags.append(f"⏳ WAIT RETEST — {sequence['reason']}")

    flags.append(f"📍 SL: {sl} [{sl_anchor}] | TP1: {tp1} [{tp1_label}] | RR: {rr1}")

    ict   = confluence.get("ict", {}) or {}
    sweep = ict.get("recent_sweep", {}) or {}
    if sweep.get("description"):
        flags.append(sweep["description"])

    choch = ict.get("choch_m5") or ict.get("choch_m15") or {}
    if choch.get("description"):
        flags.append(choch["description"])

    early_flag = _check_early_entry(confluence, direction, atr)
    if early_flag:
        flags.append(early_flag)

    flags = flags[:5]

    # ── WRITE BACK ────────────────────────────────────────────────────────────
    scored.update({
        "dl_blocked":      False,
        "dl_block_reason": "",
        "should_alert":    entry_state == "ENTER_NOW" or (unicorn.get("detected") and unicorn.get("entry_state") == "ENTER_NOW"),
        "should_log":      True,
        "flags":           flags,
        "entry_state":     entry_state,
        "gold_mode":       True,
        "trade_levels": {
            "entry_price": round(price, 2),
            "sl_price":    round(sl,    2),
            "tp1_price":   round(tp1,   2),
            "tp2_price":   round(tp2,   2),
            "sl_pips":     sl_pips,
            "tp1_pips":    tp1_pips,
            "tp2_pips":    tp2_pips,
            "rr1":         rr1,
            "rr2":         rr2,
        },
    })

    if scored.get("grade") == "C":
        scored["grade_meaning"] = "VALID SETUP (gold) — sequence confirmed"

    logger.info(
        f"{pair} | {entry_state} | {direction} | "
        f"sweep={sequence['sweep_confirmed']} choch={sequence['choch_confirmed']} "
        f"zone={sequence['entry_zone']} | SL={sl} [{sl_anchor}] TP1={tp1} RR={rr1}"
    )

    return scored
