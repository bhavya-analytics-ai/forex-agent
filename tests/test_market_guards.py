"""
tests/test_market_guards.py — Production guard: session/weekend blockers

Tests for filters/market_hours.py.

Run:
  cd /Users/ompandya/Desktop/forex-agent
  python -m pytest tests/test_market_guards.py -v
"""

from datetime import datetime, timezone
import pytest
from filters.market_hours import market_hours_gate


# ─── helpers ──────────────────────────────────────────────────────────────────

def _utc(year: int, month: int, day: int, hour: int, minute: int = 0) -> datetime:
    """Build an aware UTC datetime for injecting into market_hours_gate()."""
    return datetime(year, month, day, hour, minute, 0, tzinfo=timezone.utc)


# 2024 reference calendar (confirmed by Python weekday()):
# Mon 2024-05-06, Tue 2024-05-07, Wed 2024-05-08
# Thu 2024-05-09, Fri 2024-05-10, Sat 2024-05-11, Sun 2024-05-12
_FRI = (2024, 5, 10)
_SAT = (2024, 5, 11)
_SUN = (2024, 5, 12)
_MON = (2024, 5, 6)


# ─── Saturday — hard block all day ───────────────────────────────────────────

class TestSaturdayBlock:
    def test_saturday_midnight_blocked(self):
        g = market_hours_gate(_utc(*_SAT, 0))
        assert g["blocked"]              is True
        assert g["entry_allowed"]        is False
        assert g["market_closed"]        is True
        assert g["weekend_block"]        is True
        assert g["session_block"]        is False
        assert g["blocked_reason"]       == "SATURDAY_MARKET_CLOSED"

    def test_saturday_noon_blocked(self):
        g = market_hours_gate(_utc(*_SAT, 12))
        assert g["blocked"]        is True
        assert g["entry_allowed"]  is False
        assert g["market_closed"]  is True

    def test_saturday_23_59_blocked(self):
        g = market_hours_gate(_utc(*_SAT, 23, 59))
        assert g["blocked"]        is True
        assert g["entry_allowed"]  is False

    def test_saturday_never_caution_only(self):
        """Saturday must be a hard block, not merely caution."""
        g = market_hours_gate(_utc(*_SAT, 10))
        assert g["blocked"]  is True
        assert g["caution"]  is False


# ─── Sunday pre-open — hard block until 22:00 UTC ────────────────────────────

class TestSundayPreOpenBlock:
    def test_sunday_midnight_blocked(self):
        g = market_hours_gate(_utc(*_SUN, 0))
        assert g["blocked"]        is True
        assert g["entry_allowed"]  is False
        assert g["market_closed"]  is True
        assert g["weekend_block"]  is True
        assert g["blocked_reason"] == "SUNDAY_MARKET_CLOSED"

    def test_sunday_10am_blocked(self):
        g = market_hours_gate(_utc(*_SUN, 10))
        assert g["blocked"]        is True
        assert g["entry_allowed"]  is False

    def test_sunday_21_59_still_blocked(self):
        """One minute before open is still blocked."""
        g = market_hours_gate(_utc(*_SUN, 21, 59))
        assert g["blocked"]        is True
        assert g["entry_allowed"]  is False
        assert g["market_closed"]  is True

    def test_sunday_22_00_transitions_to_caution(self):
        """At market open (22:00), block lifts — caution applies instead."""
        g = market_hours_gate(_utc(*_SUN, 22, 0))
        assert g["blocked"]              is False
        assert g["entry_allowed"]        is True
        assert g["caution"]              is True
        assert g["penalty_pts"]          == 15
        assert g["alert_min_grade"]      == "A+"
        assert g["low_liquidity_window"] is True
        assert g["blocked_reason"]       == "SUNDAY_OPEN_GAP_RISK"

    def test_sunday_22_30_still_caution(self):
        g = market_hours_gate(_utc(*_SUN, 22, 30))
        assert g["blocked"]   is False
        assert g["caution"]   is True
        assert g["entry_allowed"] is True  # caution does not block entry

    def test_sunday_23_00_clean(self):
        """After the gap-risk hour, gate is clean."""
        g = market_hours_gate(_utc(*_SUN, 23, 0))
        assert g["blocked"]   is False
        assert g["caution"]   is False
        assert g["entry_allowed"] is True
        assert g["blocked_reason"] == ""


# ─── Friday — safe hours, caution window, hard block ─────────────────────────

class TestFridayGates:
    def test_friday_morning_clean(self):
        """Friday morning is fully open."""
        g = market_hours_gate(_utc(*_FRI, 9, 0))
        assert g["blocked"]   is False
        assert g["caution"]   is False
        assert g["entry_allowed"] is True
        assert g["blocked_reason"] == ""

    def test_friday_20_59_clean(self):
        """One minute before caution window — still clean."""
        g = market_hours_gate(_utc(*_FRI, 20, 59))
        assert g["blocked"]   is False
        assert g["caution"]   is False
        assert g["entry_allowed"] is True

    def test_friday_21_00_caution(self):
        """21:00 UTC enters the near-close caution window."""
        g = market_hours_gate(_utc(*_FRI, 21, 0))
        assert g["blocked"]              is False
        assert g["caution"]              is True
        assert g["penalty_pts"]          == 10
        assert g["alert_suppressed"]     is True
        assert g["low_liquidity_window"] is True
        assert g["entry_allowed"]        is True  # caution ≠ blocked
        assert g["blocked_reason"]       == "FRIDAY_NEAR_CLOSE"

    def test_friday_21_29_still_caution(self):
        """One minute before hard block."""
        g = market_hours_gate(_utc(*_FRI, 21, 29))
        assert g["blocked"]  is False
        assert g["caution"]  is True

    def test_friday_21_30_hard_block(self):
        """21:30 UTC triggers hard block."""
        g = market_hours_gate(_utc(*_FRI, 21, 30))
        assert g["blocked"]        is True
        assert g["entry_allowed"]  is False
        assert g["session_block"]  is True
        assert g["weekend_block"]  is False
        assert g["blocked_reason"] == "FRIDAY_PRE_CLOSE"

    def test_friday_21_45_hard_block(self):
        g = market_hours_gate(_utc(*_FRI, 21, 45))
        assert g["blocked"]        is True
        assert g["entry_allowed"]  is False

    def test_friday_hard_block_not_caution(self):
        """Hard block must not also set caution=True."""
        g = market_hours_gate(_utc(*_FRI, 21, 30))
        assert g["blocked"] is True
        assert g["caution"] is False


# ─── Normal weekdays — gate should be clean ───────────────────────────────────

class TestNormalWeekdays:
    def test_monday_clean(self):
        g = market_hours_gate(_utc(*_MON, 14, 0))
        assert g["blocked"]        is False
        assert g["caution"]        is False
        assert g["entry_allowed"]  is True
        assert g["blocked_reason"] == ""

    def test_wednesday_clean(self):
        g = market_hours_gate(_utc(2024, 5, 8, 8, 0))
        assert g["blocked"]       is False
        assert g["entry_allowed"] is True


# ─── Audit fields always present ─────────────────────────────────────────────

class TestAuditFieldsAlwaysPresent:
    REQUIRED_KEYS = [
        "blocked", "caution", "penalty_pts", "alert_suppressed",
        "alert_min_grade", "reason",
        "entry_allowed", "weekend_block", "session_block",
        "market_closed", "low_liquidity_window", "blocked_reason",
    ]

    def test_all_fields_on_clean_gate(self):
        g = market_hours_gate(_utc(*_MON, 10, 0))
        for key in self.REQUIRED_KEYS:
            assert key in g, f"Missing field: {key}"

    def test_all_fields_on_saturday_block(self):
        g = market_hours_gate(_utc(*_SAT, 12, 0))
        for key in self.REQUIRED_KEYS:
            assert key in g, f"Missing field: {key}"

    def test_all_fields_on_friday_caution(self):
        g = market_hours_gate(_utc(*_FRI, 21, 15))
        for key in self.REQUIRED_KEYS:
            assert key in g, f"Missing field: {key}"


# ─── entry_allowed invariant: blocked=True → entry_allowed=False ──────────────

class TestEntryAllowedInvariant:
    """When blocked=True, entry_allowed must always be False."""
    @pytest.mark.parametrize("dt", [
        _utc(*_SAT, 0),    # Saturday midnight
        _utc(*_SAT, 12),   # Saturday noon
        _utc(*_SAT, 23),   # Saturday 23:00
        _utc(*_SUN, 0),    # Sunday midnight
        _utc(*_SUN, 10),   # Sunday 10:00
        _utc(*_SUN, 21, 59),  # Sunday 21:59
        _utc(*_FRI, 21, 30),  # Friday 21:30 hard block
        _utc(*_FRI, 21, 59),  # Friday 21:59
    ])
    def test_blocked_implies_entry_not_allowed(self, dt):
        g = market_hours_gate(dt)
        if g["blocked"]:
            assert g["entry_allowed"] is False, (
                f"entry_allowed must be False when blocked=True "
                f"(dt={dt}, reason={g['blocked_reason']})"
            )
