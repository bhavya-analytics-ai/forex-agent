"""
filters/decision_layer.py — Thin orchestrator

Routes each pair to the correct execution strategy.
All logic lives in strategies/.

  XAU_USD / XAG_USD  →  strategies/gold_strategy.py
  Everything else    →  strategies/forex_strategy.py
"""

import logging
from strategies.gold_strategy  import apply_gold_strategy
from strategies.forex_strategy import apply_forex_strategy

logger = logging.getLogger(__name__)

_GOLD_PAIRS = {"XAU_USD", "XAG_USD"}


def apply_decision_layer(scored: dict, confluence: dict, pair: str) -> dict:
    """
    Apply execution strategy for the given pair.
    Called after score_signal(), before logging/output.
    """
    if pair in _GOLD_PAIRS:
        return apply_gold_strategy(scored, confluence, pair)
    return apply_forex_strategy(scored, confluence, pair)
