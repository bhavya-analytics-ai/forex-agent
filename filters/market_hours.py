"""
filters/market_hours.py — Friday close and weekend gap risk guard

Market hours (UTC):
  Forex/metals close: Friday 22:00 UTC
  Reopen:             Sunday 22:00 UTC

Gates:
  Friday 21:00–21:30  caution    -10 pts, alerts suppressed
  Friday 21:30–22:00  hard block  no log, no alert
  Sunday 22:00–23:00  caution    -15 pts, A+ alerts only

Usage:
  from filters.market_hours import market_hours_gate
  _mh = market_hours_gate()          # uses real UTC now
  _mh = market_hours_gate(now_utc)   # inject datetime for tests

Return dict keys:
  blocked          bool  — hard block: no log, no alert
  caution          bool  — soft mode: penalties apply
  penalty_pts      int   — subtract from score (0 if clean)
  alert_suppressed bool  — force should_alert=False
  alert_min_grade  str|None — "A+" means only A+ grade may alert
  reason           str   — human-readable flag text (empty if clean)
"""

import logging
from datetime import datetime, timezone

logger = logging.getLogger(__name__)

# Weekday constants (Python datetime: Monday=0 … Sunday=6)
_FRIDAY = 4
_SUNDAY = 6


def market_hours_gate(now_utc: datetime | None = None) -> dict:
    """
    Returns market-hours risk context for the current UTC moment.
    Pass now_utc to override clock (used in tests and simulation).
    Fails safe — returns clean gate on any error.
    """
    _clean = {
        "blocked":          False,
        "caution":          False,
        "penalty_pts":      0,
        "alert_suppressed": False,
        "alert_min_grade":  None,
        "reason":           "",
    }

    try:
        if now_utc is None:
            now_utc = datetime.now(timezone.utc)

        weekday = now_utc.weekday()
        hour    = now_utc.hour
        minute  = now_utc.minute
        hhmm    = hour * 60 + minute   # minutes since midnight UTC

        # ── FRIDAY ────────────────────────────────────────────────────────────
        if weekday == _FRIDAY:

            # Hard block: 21:30–22:00 UTC
            if hhmm >= 21 * 60 + 30:
                logger.debug(
                    f"MarketHours: HARD BLOCK Friday {hour:02d}:{minute:02d} UTC"
                )
                return {**_clean,
                        "blocked": True,
                        "reason":  (
                            f"PRE-CLOSE BLOCK — market closes in <30 min "
                            f"({hour:02d}:{minute:02d} UTC)"
                        )}

            # Caution: 21:00–21:30 UTC
            if hhmm >= 21 * 60:
                logger.debug(
                    f"MarketHours: CAUTION Friday {hour:02d}:{minute:02d} UTC"
                )
                return {**_clean,
                        "caution":          True,
                        "penalty_pts":      10,
                        "alert_suppressed": True,
                        "reason":           (
                            f"NEAR CLOSE — 60 min to market close "
                            f"({hour:02d}:{minute:02d} UTC)"
                        )}

        # ── SUNDAY ────────────────────────────────────────────────────────────
        if weekday == _SUNDAY:

            # Caution: 22:00–23:00 UTC
            if 22 * 60 <= hhmm < 23 * 60:
                logger.debug(
                    f"MarketHours: SUNDAY OPEN CAUTION {hour:02d}:{minute:02d} UTC"
                )
                return {**_clean,
                        "caution":         True,
                        "penalty_pts":     15,
                        "alert_min_grade": "A+",
                        "reason":          (
                            f"SUNDAY OPEN — gap/spread risk, first hour "
                            f"({hour:02d}:{minute:02d} UTC)"
                        )}

    except Exception as e:
        logger.warning(f"MarketHours gate error: {e} — returning clean gate")

    return _clean
