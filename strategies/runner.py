"""
strategies/runner.py — Multi-strategy runner for parallel strategy execution.

Candles and confluence are fetched once upstream (briefing.py).
This module runs all strategies eligible for a pair BEYOND the primary
legacy result and returns them as independent candidate dicts.

Two-gate live control (both must be True for DB writes / Slack alerts):
  Gate 1 (global):      OM_STRATEGY_ENABLED  — master on/off for ALL strategies
  Gate 2 (per-strategy): OM_GOLD_SCALP_ENABLED — individual strategy flag

In watch-only mode (any gate False):
  - Strategy state machines run and produce full audit output.
  - should_log=False and should_alert=False enforced before returning.
  - Zero DB writes. Zero Slack calls. No Railway env changes needed.

Isolation contract:
  - Each extra candidate is an independent dict — never shares references
    with the primary scored dict.
  - Primary `scored` is NEVER modified by this module.
  - Each candidate carries its own signal_mode (e.g. "om_gold_scalp").
  - Legacy and OM candidates are fully independent and cannot overwrite each other.
"""

import logging
from config import OM_STRATEGY_ENABLED

logger = logging.getLogger(__name__)


def run_extra_strategies(
    scored: dict, confluence: dict, pair: str, candles: dict
) -> list:
    """
    Run all extra strategies eligible for this pair beyond the primary legacy result.

    Args:
        scored:     Primary legacy scored dict (read-only reference — NOT modified).
        confluence: Shared confluence dict from check_confluence().
        pair:       e.g. "XAU_USD"
        candles:    Raw candle dict from fetch_all_timeframes() (fallback only;
                    om_gold_scalp reads candles from confluence first).

    Returns:
        List of extra candidate dicts. May be empty. Each has its own signal_mode,
        should_log, should_alert, entry_state, and full audit fields.
    """
    extras = []

    om = _run_om_gold_scalp(scored, confluence, pair, candles)
    if om is not None:
        extras.append(om)

    return extras


def _run_om_gold_scalp(
    primary_scored: dict,
    confluence: dict,
    pair: str,
    candles: dict,
) -> "dict | None":
    """
    Run om_gold_scalp as an independent parallel strategy.

    Returns a result dict if the pair is eligible, None otherwise.

    Gate enforcement:
      - Gate 2 (OM_GOLD_SCALP_ENABLED): enforced inside om_gold_scalp.run()
        via _apply_watch_only_gate().
      - Gate 1 (OM_STRATEGY_ENABLED):  enforced here on top — overrides even
        if OM_GOLD_SCALP_ENABLED is True.
    """
    try:
        from strategies.om_gold_scalp import run as om_run, STRATEGY_META
    except ImportError:
        logger.debug("om_gold_scalp not importable — skipping")
        return None

    # Pair eligibility check (XAU_USD only for v1)
    if pair not in STRATEGY_META["allowed_symbols"]:
        return None

    try:
        # Build a minimal independent base — do NOT pass primary_scored directly.
        # OM reads its own state machine; we only borrow score/grade for display.
        base = {
            "pair":  pair,
            "score": primary_scored.get("score", 0),
            "grade": primary_scored.get("grade", "C"),
        }

        om_result = om_run(base, confluence, pair, candles)

        # Gate 1: global master applied on top of per-strategy gate (Gate 2)
        if not OM_STRATEGY_ENABLED:
            om_result["should_log"]   = False
            om_result["should_alert"] = False

        return om_result

    except Exception as exc:
        logger.warning(f"om_gold_scalp runner error for {pair}: {exc}")
        return None
