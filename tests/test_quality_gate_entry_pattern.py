"""
tests/test_quality_gate_entry_pattern.py

Regression tests for the entry_pattern dict bug in filters/quality_gate.py.

Root cause: scored["entry_pattern"] is a dict produced by core/confluence.py
  entry_pattern = m5["patterns"][0]  → {"pattern": "pin_bar", "direction": "bullish", ...}

quality_gate.py line 75 previously did:
  entry_pat = (scored.get("entry_pattern") or "").strip()

A non-empty dict is truthy, so `or ""` returns the dict → .strip() → AttributeError.

Fix: extract _ep.get("pattern") when _ep is a dict.
"""

import unittest
from filters.quality_gate import minimum_quality_gate


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _base_scored(**overrides):
    """Minimal scored dict that won't hit other gates."""
    d = {
        "direction":      "bullish",
        "grade":          "A",
        "setup_type":     "pullback",
        "gold_mode":      False,
        "signal_mode":    "legacy_forex",
        "top_zone":       None,
        "trade_levels":   {"sl_pips": 10.0},
        "entry_pattern":  None,
    }
    d.update(overrides)
    return d


def _base_confluence():
    return {}


# ---------------------------------------------------------------------------
# Tests — entry_pattern as dict (the bug case)
# ---------------------------------------------------------------------------

class TestEntryPatternDict(unittest.TestCase):
    """entry_pattern is a dict — must NOT raise AttributeError."""

    def test_dict_entry_pattern_does_not_raise(self):
        """Core regression: dict entry_pattern must not throw."""
        scored = _base_scored(entry_pattern={"pattern": "pin_bar", "direction": "bullish"})
        # Must not raise — was previously crashing here
        result = minimum_quality_gate(scored, _base_confluence(), "EUR_USD")
        self.assertIsInstance(result, dict)
        self.assertIn("passes", result)

    def test_dict_entry_pattern_passes_gate(self):
        """Grade A with a valid dict pattern should pass the entry pattern gate."""
        scored = _base_scored(
            grade="A",
            entry_pattern={"pattern": "engulfing", "direction": "bullish"},
        )
        result = minimum_quality_gate(scored, _base_confluence(), "EUR_USD")
        self.assertTrue(result["passes"])

    def test_dict_entry_pattern_blocked_when_empty_name(self):
        """Dict with empty pattern name is treated as no pattern → block A+ grade."""
        scored = _base_scored(
            grade="A+",
            entry_pattern={"pattern": "", "direction": "bullish"},
        )
        result = minimum_quality_gate(scored, _base_confluence(), "EUR_USD")
        self.assertFalse(result["passes"])
        self.assertIn("entry pattern", result["block_reason"].lower())

    def test_dict_entry_pattern_missing_key(self):
        """Dict with no 'pattern' key treats as no pattern (falls back to '')."""
        scored = _base_scored(
            grade="A+",
            entry_pattern={"direction": "bullish"},  # no "pattern" key
        )
        result = minimum_quality_gate(scored, _base_confluence(), "EUR_USD")
        self.assertFalse(result["passes"])  # A+ with no pattern → block

    def test_various_dict_patterns_recognised(self):
        """All known pattern names extracted correctly from dict form."""
        known_patterns = ["pin_bar", "engulfing", "doji", "inside_bar", "momentum_candle"]
        for pname in known_patterns:
            with self.subTest(pattern=pname):
                scored = _base_scored(
                    grade="A",
                    entry_pattern={"pattern": pname, "direction": "bullish"},
                )
                result = minimum_quality_gate(scored, _base_confluence(), "EUR_USD")
                self.assertTrue(result["passes"],
                                f"Pattern '{pname}' should pass gate but got: {result}")


# ---------------------------------------------------------------------------
# Tests — entry_pattern as string (legacy / plain-string callers)
# ---------------------------------------------------------------------------

class TestEntryPatternString(unittest.TestCase):
    """entry_pattern is a plain string — must work as before."""

    def test_string_entry_pattern_passes(self):
        scored = _base_scored(grade="A", entry_pattern="pin_bar")
        result = minimum_quality_gate(scored, _base_confluence(), "EUR_USD")
        self.assertTrue(result["passes"])

    def test_empty_string_blocks_a_plus(self):
        scored = _base_scored(grade="A+", entry_pattern="")
        result = minimum_quality_gate(scored, _base_confluence(), "EUR_USD")
        self.assertFalse(result["passes"])

    def test_none_entry_pattern_blocks_a_plus(self):
        scored = _base_scored(grade="A+", entry_pattern=None)
        result = minimum_quality_gate(scored, _base_confluence(), "EUR_USD")
        self.assertFalse(result["passes"])

    def test_none_entry_pattern_warns_b_grade(self):
        scored = _base_scored(grade="B", entry_pattern=None)
        result = minimum_quality_gate(scored, _base_confluence(), "EUR_USD")
        self.assertTrue(result["passes"])  # B grade not blocked
        self.assertTrue(any("NO PATTERN" in f for f in result["flags"]))


# ---------------------------------------------------------------------------
# Tests — gate does not throw (fail-open must NOT mask the fix)
# ---------------------------------------------------------------------------

class TestNoFailOpen(unittest.TestCase):
    """After fix, the gate must not rely on fail-open for entry_pattern."""

    def test_result_is_not_fail_open_marker(self):
        """
        Before the fix, the gate always hit the except block for dict input,
        returning passes=True (fail-open) with no block_reason and no flags.
        After fix, a clean A+ with no pattern should return passes=False via
        normal logic — not from fail-open.
        """
        scored = _base_scored(grade="A+", entry_pattern={"pattern": "", "direction": "bullish"})
        result = minimum_quality_gate(scored, _base_confluence(), "EUR_USD")
        # Proper block: passes=False with a meaningful block_reason
        self.assertFalse(result["passes"])
        self.assertNotEqual(result["block_reason"], "")

    def test_dict_with_valid_pattern_not_fail_open(self):
        """Valid dict pattern should pass with empty block_reason — not fail-open."""
        scored = _base_scored(grade="A", entry_pattern={"pattern": "pin_bar", "direction": "bullish"})
        result = minimum_quality_gate(scored, _base_confluence(), "EUR_USD")
        self.assertTrue(result["passes"])
        self.assertEqual(result["block_reason"], "")

    def test_gold_mode_exempt_from_pattern_gate(self):
        """Gold mode is exempt from entry pattern check.
        Use sl_pips=200 to clear the minimum SL gate for XAU_USD (min=150)."""
        scored = _base_scored(
            grade="A+",
            gold_mode=True,
            trade_levels={"sl_pips": 200.0},  # clears XAU_USD min SL gate
            entry_pattern={"pattern": "", "direction": "bullish"},
        )
        result = minimum_quality_gate(scored, _base_confluence(), "XAU_USD")
        self.assertTrue(result["passes"])

    def test_news_sniper_exempt_from_pattern_gate(self):
        """News sniper is exempt — should pass even with no entry_pattern dict."""
        scored = _base_scored(
            grade="A+",
            signal_mode="news_sniper",
            entry_pattern=None,
        )
        result = minimum_quality_gate(scored, _base_confluence(), "EUR_USD")
        self.assertTrue(result["passes"])


if __name__ == "__main__":
    unittest.main()
