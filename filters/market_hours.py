"""
filters/market_hours.py — Friday close, weekend, and market-closed guard

Market hours (UTC):
  Forex/metals close: Friday 22:00 UTC
  Reopen:             Sunday 22:00 UTC

Hard blocks (ENTER_NOW forbidden, no logging):
  Saturday               all day   — market closed
  Sunday 00:00–21:59    all hours  — market closed (reopens Sunday 22:00)
  Friday 21:30–22:00    pre-close  — <30 min to close

Caution windows (soft penalties, reduced alerts):
  Friday 21:00–21:30   near-close  — -10 pts, alerts suppressed
  Sunday 22:00–22:59   open-gap    — -15 pts, A+ alerts only

Usage:
  from filters.market_hours import market_hours_gate
  _mh = market_hours_gate()          # uses real UTC now
  _mh = market_hours_gate(now_utc)   # inject datetime for tests

Return dict keys (legacy, always present):
  blocked          bool  — hard block: no log, no alert, entry_state overridden
  caution          bool  — soft mode: penalties apply
  penalty_pts      int   — subtract from score (0 if clean)
  alert_suppressed bool  — force should_alert=False
  alert_min_grade  str|None — "A+" means only A+ grade may alert
  reason           str   — human-readable flag text (empty if clean)

Audit fields (new, always present):
  entry_allowed    bool  — False when blocked=True (ENTER_NOW must be refused)
  weekend_block    bool  — True when Saturday or Sunday-pre-open caused the block
  session_block    bool  — True when Friday pre-close caused the block
  market_closed    bool  — True when market is completely closed (Sat + Sun pre-22)
  low_liquidity_window bool — True when caution applies (not a full block)
  blocked_reason   str   — machine-readable slug, empty when clean
"""

import logging
from datetime import datetime, timezone

logger = logging.getLogger(__name__)

# Weekday constants (Python datetime: Monday=0 … Sunday=6)
_FRIDAY   = 4
_SATURDAY = 5
_SUNDAY   = 6


def market_hours_gate(now_utc: datetime | None = None) -> dict:
    """
    Returns market-hours risk context for the current UTC moment.
    Pass now_utc to override clock (used in tests and simulation).
    Fails safe — returns clean gate on any error.

    GUARANTEE: when blocked=True, entry_allowed=False.
    briefing.py must override entry_state to SKIP_SESSION when blocked=True.
    """
    _clean = {
        # ── legacy ──────────────────────────────────────────────────────────
        "blocked":               False,
        "caution":               False,
        "penalty_pts":           0,
        "alert_suppressed":      False,
        "alert_min_grade":       None,
        "reason":                "",
        # ── audit ───────────────────────────────────────────────────────────
        "entry_allowed":         True,
        "weekend_block":         False,
        "session_block":         False,
        "market_closed":         False,
        "low_liquidity_window":  False,
        "blocked_reason":        "",
    }

    try:
        if now_utc is None:
            now_utc = datetime.now(timezone.utc)

        weekday = now_utc.weekday()
        hour    = now_utc.hour
        minute  = now_utc.minute
        hhmm    = hour * 60 + minute   # minutes since midnight UTC

        # ── SATURDAY — market closed all day ──────────────────────────────────
        if weekday == _SATURDAY:
            logger.debug(
                f"MarketHours: SATURDAY BLOCK {hour:02d}:{minute:02d} UTC — market closed"
            )
            return {**_clean,
                    "blocked":        True,
                    "entry_allowed":  False,
                    "weekend_block":  True,
                    "market_closed":  True,
                    "blocked_reason": "SATURDAY_MARKET_CLOSED",
                    "reason":         (
                        f"SATURDAY — market closed all day "
                        f"({hour:02d}:{minute:02d} UTC). Reopens Sunday 22:00 UTC."
                    )}

        # ── SUNDAY — market closed until 22:00 UTC ────────────────────────────
        if weekday == _SUNDAY:

            # Hard block: 00:00–21:59 UTC (market still closed from Friday)
            if hhmm < 22 * 60:
                logger.debug(
                    f"MarketHours: SUNDAY PRE-OPEN BLOCK {hour:02d}:{minute:02d} UTC"
                )
                mins_to_open = 22 * 60 - hhmm
                return {**_clean,
                        "blocked":        True,
                        "entry_allowed":  False,
                        "weekend_block":  True,
                        "market_closed":  True,
                        "blocked_reason": "SUNDAY_MARKET_CLOSED",
                        "reason":         (
                            f"SUNDAY PRE-OPEN — market closed, opens in "
                            f"{mins_to_open} min ({hour:02d}:{minute:02d} UTC)"
                        )}

            # Caution: 22:00–22:59 UTC (gap/spread risk at open)
            if 22 * 60 <= hhmm < 23 * 60:
                logger.debug(
                    f"MarketHours: SUNDAY OPEN CAUTION {hour:02d}:{minute:02d} UTC"
                )
                return {**_clean,
                        "caution":              True,
                        "penalty_pts":          15,
                        "alert_min_grade":      "A+",
                        "low_liquidity_window": True,
                        "blocked_reason":       "SUNDAY_OPEN_GAP_RISK",
                        "reason":               (
                            f"SUNDAY OPEN — gap/spread risk, first hour "
                            f"({hour:02d}:{minute:02d} UTC)"
                        )}

        # ── FRIDAY ────────────────────────────────────────────────────────────
        if weekday == _FRIDAY:

            # Hard block: 21:30–22:00 UTC (< 30 min to close)
            if hhmm >= 21 * 60 + 30:
                logger.debug(
                    f"MarketHours: HARD BLOCK Friday {hour:02d}:{minute:02d} UTC"
                )
                return {**_clean,
                        "blocked":        True,
                        "entry_allowed":  False,
                        "session_block":  True,
                        "blocked_reason": "FRIDAY_PRE_CLOSE",
                        "reason":         (
                            f"PRE-CLOSE BLOCK — market closes in <30 min "
                            f"({hour:02d}:{minute:02d} UTC)"
                        )}

            # Caution: 21:00–21:30 UTC
            if hhmm >= 21 * 60:
                logger.debug(
                    f"MarketHours: CAUTION Friday {hour:02d}:{minute:02d} UTC"
                )
                return {**_clean,
                        "caution":              True,
                        "penalty_pts":          10,
                        "alert_suppressed":     True,
                        "low_liquidity_window": True,
                        "blocked_reason":       "FRIDAY_NEAR_CLOSE",
                        "reason":               (
                            f"NEAR CLOSE — 60 min to market close "
                            f"({hour:02d}:{minute:02d} UTC)"
                        )}

    except Exception as e:
        logger.warning(f"MarketHours gate error: {e} — returning clean gate")

    return _clean
