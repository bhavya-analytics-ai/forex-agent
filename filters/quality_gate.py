"""
filters/quality_gate.py — Minimum signal quality checks

Applied in reports/briefing.py after strategy + market_hours gate,
before the logging gate. Never modifies scoring, strategy, or confluence.

Checks (in order):
  1. Entry pattern gate  — forex only (gold/sniper exempt)
  2. Zone-direction conflict gate — all paths
  3. Minimum SL gate    — all paths

Grade C metal ENTER_NOW alert suppression is handled directly in
briefing.py (it is alert-only, not a logging block).

Return dict:
  passes:       bool  — False → block logging entirely
  block_reason: str   — human-readable reason (empty if passes)
  penalty_pts:  int   — subtract from score (weak-zone conflict only)
  flags:        list  — additional ⚠️ warning flags to append
"""

import logging

logger = logging.getLogger(__name__)

# Zone types that oppose each trade direction
_OPPOSING = {
    "bullish": {"resistance", "supply"},
    "bearish": {"support",    "demand"},
}

# Setup types that signal a zone reclaim/flip — bypass zone conflict check
_ZONE_BYPASS_SETUPS = {"sr_flip", "zone_tap"}

# Minimum SL thresholds in pips (pip_size-relative, per pair)
#   XAU_USD pip=0.01  → 150 pips = $1.50 minimum distance
#   XAG_USD pip=0.001 → 200 pips = $0.20 minimum distance
#   Forex/JPY        → 5 pips
_MIN_SL_PIPS: dict[str, float] = {
    "XAU_USD": 150.0,
    "XAG_USD": 200.0,
}
_MIN_SL_DEFAULT = 5.0


def _result(passes=True, block_reason="", penalty_pts=0, flags=None) -> dict:
    return {
        "passes":       passes,
        "block_reason": block_reason,
        "penalty_pts":  penalty_pts,
        "flags":        flags or [],
    }


def minimum_quality_gate(scored: dict, confluence: dict, pair: str) -> dict:
    """
    Run all minimum quality checks in order.
    First hard block encountered is returned immediately.
    Penalties and flags are accumulated across all soft checks.

    Fails open — returns passes=True on any unexpected error so a bug
    in the gate never silently kills valid signals.
    """
    try:
        direction   = scored.get("direction", "")
        grade       = scored.get("grade", "C")
        setup_type  = scored.get("setup_type", "")
        gold_mode   = scored.get("gold_mode", False)
        is_sniper   = (scored.get("signal_mode") or "") == "news_sniper"
        top_zone    = scored.get("top_zone") or {}
        zone_type   = (top_zone.get("type") or "").strip()
        zone_str    = float(top_zone.get("strength") or 0)
        trade_lvls  = scored.get("trade_levels") or {}
        sl_pips     = float(trade_lvls.get("sl_pips") or 0)
        entry_pat   = (scored.get("entry_pattern") or "").strip()

        extra_flags: list[str] = []
        penalty = 0

        # ── 1. ENTRY PATTERN GATE ─────────────────────────────────────────────
        # Gold and news-sniper are exempt — their ICT sequence IS the pattern.
        if not gold_mode and not is_sniper:
            if not entry_pat:
                if grade in ("A+", "A"):
                    logger.info(
                        f"QualityGate BLOCK {pair}: no entry pattern, grade={grade}"
                    )
                    return _result(
                        passes=False,
                        block_reason=(
                            f"No entry pattern — grade {grade} forex requires "
                            f"candle confirmation"
                        ),
                    )
                elif grade == "B":
                    extra_flags.append("⚠️ NO PATTERN — structural entry only")

        # ── 2. ZONE-DIRECTION CONFLICT GATE ───────────────────────────────────
        if direction and zone_type:
            opposing   = _OPPOSING.get(direction, set())
            is_conflict = zone_type in opposing
            is_bypass   = (
                scored.get("zone_flip", False)
                or setup_type in _ZONE_BYPASS_SETUPS
            )

            if is_conflict and not is_bypass:
                if zone_str >= 40:
                    logger.info(
                        f"QualityGate BLOCK {pair}: {direction} into "
                        f"{zone_type} str={int(zone_str)}"
                    )
                    return _result(
                        passes=False,
                        block_reason=(
                            f"Zone conflict — {direction} into {zone_type} "
                            f"(str={int(zone_str)})"
                        ),
                    )
                else:
                    # Weak zone — penalty only
                    penalty += 8
                    extra_flags.append(
                        f"⚠️ WEAK ZONE CONFLICT — {direction} into "
                        f"{zone_type} (str={int(zone_str)})"
                    )
                    logger.debug(
                        f"QualityGate penalty {pair}: weak zone conflict "
                        f"{direction}/{zone_type} str={int(zone_str)} → −8 pts"
                    )

        # ── 3. MINIMUM SL GATE ────────────────────────────────────────────────
        # Only fires when a SL was actually calculated (sl_pips > 0).
        if sl_pips > 0:
            min_sl = _MIN_SL_PIPS.get(pair, _MIN_SL_DEFAULT)
            if sl_pips < min_sl:
                logger.info(
                    f"QualityGate BLOCK {pair}: sl_pips={sl_pips} < min={min_sl}"
                )
                return _result(
                    passes=False,
                    block_reason=(
                        f"SL too tight — {sl_pips}p below minimum "
                        f"{min_sl}p for {pair}"
                    ),
                )

        return _result(penalty_pts=penalty, flags=extra_flags)

    except Exception as e:
        logger.warning(
            f"QualityGate error for {pair}: {e} — failing open (signal allowed)"
        )
        return _result()
