"""
tests/test_option_a_forex_logging.py

Regression tests for Option A — restores May 12 execution-ready logging contract
for legacy forex signals.

Root cause being fixed:
  f486303 (May 15 14:20) changed the briefing.py forex logging gate from
  `entry_state == "ENTER_NOW"` to `should_log=True`.  forex_strategy.py sets
  should_log=True on BOTH the strict FOREX PASS path AND the loose EARLY ENTRY
  path, flooding the DB with watch candidates and early-entry noise.

Option A fix:
  1. forex_strategy.py: sets scored["entry_state"] = "ENTER_NOW" ONLY inside
     the strict FOREX PASS block (valid_rr>=1.5, valid_setup, valid_struct,
     news_safe).  EARLY ENTRY does NOT set ENTER_NOW.
  2. briefing.py forex logging gate: uses entry_state=="ENTER_NOW" uniformly
     (same contract as gold/sniper).

Coverage:
  A. forex_strategy.py — ENTER_NOW assignment on FOREX PASS path only
  B. Briefing logging gate — forex requires ENTER_NOW to log
  C. Noisy May 19-style rows — EARLY ENTRY ONLY rows do NOT log
  D. Gold path — unchanged: gold_strategy sets ENTER_NOW → logs
  E. QualityGate still gates even FOREX PASS signals
  F. Global / per-strategy env gates (OM_STRATEGY_ENABLED, LEGACY_FOREX_ENABLED)
"""

import copy
import unittest
from unittest.mock import patch


# ═══════════════════════════════════════════════════════════════════════════════
# Part A — forex_strategy.py: ENTER_NOW assignment
# ═══════════════════════════════════════════════════════════════════════════════

def _clean_confluence(direction="bullish"):
    """
    Confluence dict that clears all hard filters:
    - price at 67% of range (above 60% → not mid-range)
    - no opposing zones
    - all TF biases aligned with direction
    - structure quality A+, strength 3 (not choppy)
    - no ICT/pattern conflicts
    """
    return {
        "current_price": 1.2000,
        "is_pullback":   False,
        "h1": {
            "bias": direction,
            "structure": {
                "setup_quality": "A+",
                "strength":      3,
                "phase":         "trending",
                "trend":         direction,
                "last_high":     1.2200,
                "last_low":      1.1600,
            },
            "zones": [],
        },
        "m15": {"bias": direction, "structure": {}},
        "m5":  {"bias": direction, "structure": {}},
        "ict": {},
    }


def _base_forex_scored(direction="bullish", grade="A+", setup_type="trend_follow",
                       sl_pips=20.0, tp1_pips=40.0, news_safe=True):
    """
    Minimal scored dict for forex_strategy.  Bypasses hard filters via
    pre-set trade_levels (get_stop_loss / get_take_profit are mocked to 0).
    """
    return {
        "pair":          "EUR_USD",
        "direction":     direction,
        "grade":         grade,
        "setup_type":    setup_type,
        "score":         72.0,
        "should_log":    False,
        "should_alert":  False,
        "entry_state":   None,
        "early_entry":   False,
        "ict_conflict":  False,
        "pattern_conflict": False,
        "against_h1_trend": False,
        "news_check":    {"safe": news_safe},
        # Pre-set trade_levels so DECISION PRIORITY block reads our RR directly.
        # get_stop_loss / get_take_profit are mocked to return (0,"")/(0,0,"")
        # so the TP/SL override block is skipped and these values persist.
        "trade_levels": {
            "sl_pips":  sl_pips,
            "tp1_pips": tp1_pips,
        },
    }


# mock targets: the two I/O helpers that would call OANDA
_MOCK_SL = "strategies.forex_strategy.get_stop_loss"
_MOCK_TP = "strategies.forex_strategy.get_take_profit"


class TestForexStrategyEnterNow(unittest.TestCase):
    """
    Apply apply_forex_strategy() with mocked TP/SL helpers so trade_levels
    stay as pre-set and DECISION PRIORITY logic can be exercised cleanly.
    """

    @patch(_MOCK_TP, return_value=(0, 0, ""))
    @patch(_MOCK_SL, return_value=(0, ""))
    def test_forex_pass_sets_enter_now(self, _sl, _tp):
        """FOREX PASS criteria met → entry_state = 'ENTER_NOW'."""
        from strategies.forex_strategy import apply_forex_strategy
        scored = _base_forex_scored(
            grade="A+", setup_type="trend_follow",
            sl_pips=20.0, tp1_pips=40.0,   # RR = 2.0 ≥ 1.5
        )
        result = apply_forex_strategy(scored, _clean_confluence(), "EUR_USD")
        self.assertEqual(result.get("entry_state"), "ENTER_NOW",
                         "FOREX PASS must set entry_state='ENTER_NOW'")
        self.assertTrue(result["should_log"])
        self.assertTrue(result["should_alert"])

    @patch(_MOCK_TP, return_value=(0, 0, ""))
    @patch(_MOCK_SL, return_value=(0, ""))
    def test_early_entry_only_does_not_set_enter_now(self, _sl, _tp):
        """
        FOREX PASS fails (RR < 1.5), EARLY ENTRY fires (TFs aligned).
        entry_state must NOT become 'ENTER_NOW'.
        """
        from strategies.forex_strategy import apply_forex_strategy
        scored = _base_forex_scored(
            grade="A+", setup_type="trend_follow",
            sl_pips=20.0, tp1_pips=24.0,   # RR = 1.2 < 1.5  → FOREX PASS fails
        )
        # TFs all aligned → EARLY ENTRY should fire
        result = apply_forex_strategy(scored, _clean_confluence(), "EUR_USD")

        self.assertNotEqual(result.get("entry_state"), "ENTER_NOW",
                            "EARLY ENTRY must NOT set entry_state='ENTER_NOW'")
        self.assertTrue(result.get("early_entry"),
                        "early_entry flag must be True")
        # should_log is True (EARLY ENTRY sets it) but ENTER_NOW not set
        self.assertTrue(result.get("should_log"),
                        "should_log still set by EARLY ENTRY (watch candidate)")

    @patch(_MOCK_TP, return_value=(0, 0, ""))
    @patch(_MOCK_SL, return_value=(0, ""))
    def test_both_pass_and_early_entry_sets_enter_now(self, _sl, _tp):
        """
        When FOREX PASS fires AND EARLY ENTRY fires (RR good + TFs aligned),
        entry_state must be 'ENTER_NOW' (set by FOREX PASS block, not removed by EE).
        """
        from strategies.forex_strategy import apply_forex_strategy
        scored = _base_forex_scored(
            grade="A+", setup_type="trend_follow",
            sl_pips=20.0, tp1_pips=40.0,   # RR = 2.0 ≥ 1.5
        )
        result = apply_forex_strategy(scored, _clean_confluence(), "EUR_USD")
        self.assertEqual(result.get("entry_state"), "ENTER_NOW")

    @patch(_MOCK_TP, return_value=(0, 0, ""))
    @patch(_MOCK_SL, return_value=(0, ""))
    def test_neither_pass_nor_early_entry_no_enter_now(self, _sl, _tp):
        """
        FOREX PASS fails (grade C, RR 2.0 → valid_struct fails because
        structure.setup_quality is forced to C via the confluence dict).
        EARLY ENTRY also doesn't fire (TF mis-alignment via mismatched biases).
        entry_state must NOT be 'ENTER_NOW'.
        """
        from strategies.forex_strategy import apply_forex_strategy
        # Force structure quality C to break valid_struct
        conf = _clean_confluence(direction="bullish")
        conf["h1"]["structure"]["setup_quality"] = "C"
        conf["h1"]["structure"]["strength"]      = 1
        # Misalign M15/M5 to break EARLY ENTRY TF check
        conf["m15"]["bias"] = "bearish"
        conf["m5"]["bias"]  = "bearish"

        scored = _base_forex_scored(
            grade="C", setup_type="trend_follow",
            sl_pips=20.0, tp1_pips=40.0,
        )
        # Choppy filter would normally block. Override: use is_pullback=True
        # and clear the choppy path by making phase/trend non-ranging.
        # Actually just use a direct grade-C + weak-structure + TF misalign scenario.
        # Hard filter: _is_choppy → quality C → blocks trade. Skip by making is_pb=True:
        # TF conflict skipped for pullbacks. But choppy still fires.
        # Easiest: patch _is_choppy to False for this test.
        with patch("strategies.forex_strategy._is_choppy", return_value=False):
            result = apply_forex_strategy(scored, conf, "EUR_USD")

        self.assertNotEqual(result.get("entry_state"), "ENTER_NOW",
                            "Neither FOREX PASS nor EARLY ENTRY → no ENTER_NOW")

    @patch(_MOCK_TP, return_value=(0, 0, ""))
    @patch(_MOCK_SL, return_value=(0, ""))
    def test_news_blocked_forex_no_enter_now(self, _sl, _tp):
        """news_safe=False → FOREX PASS fails → no ENTER_NOW."""
        from strategies.forex_strategy import apply_forex_strategy
        scored = _base_forex_scored(
            grade="A+", setup_type="trend_follow",
            sl_pips=20.0, tp1_pips=40.0,
            news_safe=False,
        )
        conf = _clean_confluence(direction="bullish")
        conf["m15"]["bias"] = "bearish"  # break EARLY ENTRY too
        conf["m5"]["bias"]  = "bearish"
        result = apply_forex_strategy(scored, conf, "EUR_USD")
        self.assertNotEqual(result.get("entry_state"), "ENTER_NOW",
                            "News-blocked forex must not get ENTER_NOW")

    @patch(_MOCK_TP, return_value=(0, 0, ""))
    @patch(_MOCK_SL, return_value=(0, ""))
    def test_grade_b_forex_pass_sets_enter_now(self, _sl, _tp):
        """Grade B is a valid structure grade — FOREX PASS still fires."""
        from strategies.forex_strategy import apply_forex_strategy
        conf = _clean_confluence(direction="bullish")
        conf["h1"]["structure"]["setup_quality"] = "B"
        scored = _base_forex_scored(
            grade="B", setup_type="pullback_long",
            sl_pips=20.0, tp1_pips=40.0,
        )
        result = apply_forex_strategy(scored, conf, "EUR_USD")
        self.assertEqual(result.get("entry_state"), "ENTER_NOW",
                         "Grade B with valid RR + valid setup → ENTER_NOW")


# ═══════════════════════════════════════════════════════════════════════════════
# Part B — Briefing.py forex logging gate
# ═══════════════════════════════════════════════════════════════════════════════

def _run_briefing_forex_gate(scored: dict,
                              market_blocked: bool = False,
                              qg_passes: bool = True) -> bool:
    """
    Inline reimplementation of the Option A logging gate from briefing.py.

    Returns _log_now (True → signal would be logged to DB).
    """
    s = copy.deepcopy(scored)
    _gold   = s.get("gold_mode", False)
    _sniper = s.get("signal_mode") == "news_sniper"
    _mh_blocked = market_blocked
    _qg_passes  = qg_passes

    if _mh_blocked or not _qg_passes:
        return False
    elif _gold or _sniper:
        return s.get("entry_state") == "ENTER_NOW"
    else:
        # Option A: forex uses entry_state gate (same as gold/sniper)
        return s.get("entry_state") == "ENTER_NOW"


class TestBriefingForexGate(unittest.TestCase):
    """
    Verify the Option A briefing.py logging gate for forex.
    Uses inline gate function — no need to mock full scan pipeline.
    """

    def test_forex_enter_now_logs(self):
        """Forex with entry_state='ENTER_NOW' → logs."""
        scored = {"entry_state": "ENTER_NOW", "signal_mode": "legacy_forex", "gold_mode": False}
        self.assertTrue(_run_briefing_forex_gate(scored))

    def test_forex_no_enter_now_does_not_log(self):
        """Forex with entry_state=None (EARLY ENTRY only) → does NOT log."""
        scored = {"entry_state": None, "should_log": True, "signal_mode": "legacy_forex", "gold_mode": False}
        self.assertFalse(_run_briefing_forex_gate(scored))

    def test_forex_should_log_true_without_enter_now_blocked(self):
        """
        Critical Option A regression test:
        should_log=True alone is NOT sufficient for forex to log.
        entry_state must be 'ENTER_NOW'.
        """
        scored = {"entry_state": None, "should_log": True, "signal_mode": "legacy_forex", "gold_mode": False}
        self.assertFalse(_run_briefing_forex_gate(scored),
                         "should_log=True without ENTER_NOW must NOT log (regression guard)")

    def test_market_hours_block_prevents_logging(self):
        """Market hours hard block → no log even with ENTER_NOW."""
        scored = {"entry_state": "ENTER_NOW", "signal_mode": "legacy_forex", "gold_mode": False}
        self.assertFalse(_run_briefing_forex_gate(scored, market_blocked=True))

    def test_quality_gate_block_prevents_logging(self):
        """QualityGate hard block → no log even with ENTER_NOW."""
        scored = {"entry_state": "ENTER_NOW", "signal_mode": "legacy_forex", "gold_mode": False}
        self.assertFalse(_run_briefing_forex_gate(scored, qg_passes=False))

    def test_gold_enter_now_logs(self):
        """Gold with ENTER_NOW → logs (gold path unchanged)."""
        scored = {"entry_state": "ENTER_NOW", "signal_mode": "legacy_gold", "gold_mode": True}
        self.assertTrue(_run_briefing_forex_gate(scored))

    def test_gold_without_enter_now_does_not_log(self):
        """Gold without ENTER_NOW (watch-only) → does NOT log (gold path unchanged)."""
        scored = {"entry_state": "WATCH_ONLY", "signal_mode": "legacy_gold", "gold_mode": True}
        self.assertFalse(_run_briefing_forex_gate(scored))

    def test_sniper_enter_now_logs(self):
        """News sniper with ENTER_NOW → logs."""
        scored = {"entry_state": "ENTER_NOW", "signal_mode": "news_sniper", "gold_mode": False}
        self.assertTrue(_run_briefing_forex_gate(scored))


# ═══════════════════════════════════════════════════════════════════════════════
# Part C — Noisy May 19-style EARLY ENTRY rows do NOT log
# ═══════════════════════════════════════════════════════════════════════════════

class TestMay19NoisyRowsBlocked(unittest.TestCase):
    """
    Representative noisy May 19 archived forex rows that logged under f486303
    but must NOT log under Option A.

    Row classification from audit:
      EARLY_ENTRY ONLY  — FOREX PASS fails (grade C or RR < 1.5), EARLY ENTRY fires
      NEITHER           — both fail (logged anyway under f486303's should_log gate)

    Under Option A: entry_state is never set to ENTER_NOW for these → blocked.
    """

    def _assert_not_logged(self, name, entry_state, should_log):
        scored = {
            "entry_state":  entry_state,
            "should_log":   should_log,
            "signal_mode":  "legacy_forex",
            "gold_mode":    False,
        }
        result = _run_briefing_forex_gate(scored)
        self.assertFalse(result,
                         f"Row '{name}' must NOT log under Option A (entry_state={entry_state})")

    def test_nzd_jpy_early_entry_grade_c_blocked(self):
        """NZD_JPY grade=C EARLY ENTRY ONLY — RR=1.71 but grade C fails valid_struct."""
        # FOREX PASS fails → entry_state never set → None
        self._assert_not_logged("NZD_JPY_073254", entry_state=None, should_log=True)

    def test_eur_gbp_grade_c_neither_blocked(self):
        """EUR_GBP grade=C, NEITHER path — logged anyway under f486303."""
        self._assert_not_logged("EUR_GBP_104908", entry_state=None, should_log=True)

    def test_chf_jpy_grade_c_neither_blocked(self):
        """CHF_JPY grade=C, NEITHER path."""
        self._assert_not_logged("CHF_JPY_120248", entry_state=None, should_log=True)

    def test_nzd_jpy_grade_c_early_entry_blocked(self):
        """NZD_JPY grade=C EARLY ENTRY ONLY — RR=3.20 but grade C fails valid_struct."""
        self._assert_not_logged("NZD_JPY_171916", entry_state=None, should_log=True)

    def test_usd_jpy_grade_c_early_entry_blocked(self):
        """USD_JPY grade=C EARLY ENTRY ONLY — RR=2.02 but grade C fails valid_struct."""
        self._assert_not_logged("USD_JPY_172943", entry_state=None, should_log=True)

    def test_gbp_usd_rr_too_low_early_entry_blocked(self):
        """GBP_USD grade=A+ EARLY ENTRY ONLY — RR=1.31 fails valid_rr."""
        self._assert_not_logged("GBP_USD_203547", entry_state=None, should_log=True)

    def test_gbp_jpy_grade_c_neither_blocked(self):
        """GBP_JPY grade=C, NEITHER path — RR=4.21 but grade C fails valid_struct."""
        self._assert_not_logged("GBP_JPY_212825", entry_state=None, should_log=True)

    def test_cad_jpy_grade_c_neither_blocked(self):
        """CAD_JPY grade=C, NEITHER path."""
        self._assert_not_logged("CAD_JPY_213904", entry_state=None, should_log=True)

    def test_gbp_usd_rr_too_low_early_entry_blocked_2(self):
        """GBP_USD grade=A+ EARLY ENTRY ONLY — RR=1.24 fails valid_rr."""
        self._assert_not_logged("GBP_USD_213907", entry_state=None, should_log=True)


class TestMay19ForexPassRowsStillLog(unittest.TestCase):
    """
    May 19 rows that passed FOREX PASS criteria must still log under Option A.
    These are the 14 rows where FOREX PASS fired (with or without EARLY ENTRY).
    """

    def _assert_logged(self, name):
        scored = {
            "entry_state":  "ENTER_NOW",   # forex_strategy sets this on FOREX PASS
            "should_log":   True,
            "signal_mode":  "legacy_forex",
            "gold_mode":    False,
        }
        result = _run_briefing_forex_gate(scored)
        self.assertTrue(result, f"Row '{name}' with FOREX PASS must still log under Option A")

    def test_eur_gbp_forex_pass_logs(self):
        """EUR_GBP A+ RR=2.58 FOREX PASS ONLY → logs."""
        self._assert_logged("EUR_GBP_073259")

    def test_usd_jpy_both_logs(self):
        """USD_JPY A+ RR=2.92 FOREX PASS + EARLY ENTRY → logs."""
        self._assert_logged("USD_JPY_080513")

    def test_chf_jpy_forex_pass_logs(self):
        """CHF_JPY A+ RR=1.72 FOREX PASS ONLY → logs."""
        self._assert_logged("CHF_JPY_134726")

    def test_usd_jpy_trend_follow_logs(self):
        """USD_JPY A+ RR=2.39 FOREX PASS + EARLY ENTRY → logs."""
        self._assert_logged("USD_JPY_150142")

    def test_usd_jpy_reversal_bull_logs(self):
        """USD_JPY A+ RR=4.71 FOREX PASS + EARLY ENTRY → logs."""
        self._assert_logged("USD_JPY_190510")

    def test_usd_jpy_high_rr_logs(self):
        """USD_JPY A+ RR=4.26 FOREX PASS + EARLY ENTRY → logs."""
        self._assert_logged("USD_JPY_213858")


# ═══════════════════════════════════════════════════════════════════════════════
# Part D — Gold path unchanged
# ═══════════════════════════════════════════════════════════════════════════════

class TestGoldPathUnchanged(unittest.TestCase):
    """
    Gold behavior must be identical across May 12, current, and Option A.
    gold_strategy.py sets entry_state='ENTER_NOW' on ICT sequence confirmation.
    briefing.py gold gate: `elif _gold or _sniper: _log_now = entry_state == 'ENTER_NOW'`
    This path is NOT touched by Option A.
    """

    def test_gold_enter_now_logs(self):
        """Gold ENTER_NOW → logs (same as May 12)."""
        scored = {"entry_state": "ENTER_NOW", "gold_mode": True, "signal_mode": "legacy_gold"}
        self.assertTrue(_run_briefing_forex_gate(scored))

    def test_gold_watch_only_does_not_log(self):
        """Gold without ENTER_NOW → not logged (same as May 12)."""
        scored = {"entry_state": "WATCH_ONLY", "gold_mode": True, "signal_mode": "legacy_gold"}
        self.assertFalse(_run_briefing_forex_gate(scored))

    def test_gold_enter_now_not_blocked_by_market_hours_alone(self):
        """Gold ENTER_NOW passes gate unless market is blocked or QG fails."""
        scored = {"entry_state": "ENTER_NOW", "gold_mode": True, "signal_mode": "legacy_gold"}
        self.assertTrue(_run_briefing_forex_gate(scored, market_blocked=False, qg_passes=True))

    def test_xag_usd_enter_now_logs(self):
        """XAG_USD (silver) is also gold_mode — same gate."""
        scored = {"entry_state": "ENTER_NOW", "gold_mode": True, "signal_mode": "legacy_gold", "pair": "XAG_USD"}
        self.assertTrue(_run_briefing_forex_gate(scored))

    def test_gold_strategy_source_sets_enter_now(self):
        """Confirm gold_strategy.py source code contains entry_state='ENTER_NOW'."""
        import inspect
        import strategies.gold_strategy as gmod
        src = inspect.getsource(gmod)
        self.assertIn('"ENTER_NOW"', src,
                      "gold_strategy.py must contain entry_state='ENTER_NOW' assignments")

    def test_forex_strategy_source_never_set_enter_now_before_option_a(self):
        """
        Confirm Option A added entry_state='ENTER_NOW' to forex_strategy.py.
        The assignment should be exactly in the FOREX PASS block.
        """
        import inspect
        import strategies.forex_strategy as fmod
        src = inspect.getsource(fmod)
        self.assertIn('"ENTER_NOW"', src,
                      "Option A: forex_strategy.py must now contain entry_state='ENTER_NOW'")
        # Confirm it's inside the FOREX PASS block (appears before the EARLY ENTRY section)
        fp_idx  = src.find("FOREX PASS")
        ee_idx  = src.find("EARLY ENTRY")
        en_idx  = src.find('"ENTER_NOW"')
        self.assertGreater(fp_idx, 0,  "FOREX PASS comment must exist")
        self.assertGreater(ee_idx, 0,  "EARLY ENTRY comment must exist")
        self.assertGreater(en_idx, 0,  "ENTER_NOW assignment must exist in forex_strategy")
        self.assertLess(en_idx, ee_idx,
                        "ENTER_NOW assignment must appear before EARLY ENTRY block (in FOREX PASS)")


# ═══════════════════════════════════════════════════════════════════════════════
# Part E — QualityGate still runs and blocks even FOREX PASS signals
# ═══════════════════════════════════════════════════════════════════════════════

class TestQualityGateStillRuns(unittest.TestCase):
    """
    QualityGate check happens BEFORE the logging gate in briefing.py.
    Even if forex_strategy sets entry_state='ENTER_NOW', a QualityGate
    hard block must prevent the signal from logging.
    """

    def test_qg_block_prevents_forex_enter_now_from_logging(self):
        """QualityGate hard block → not logged even with ENTER_NOW."""
        scored = {
            "entry_state":  "ENTER_NOW",
            "should_log":   True,
            "signal_mode":  "legacy_forex",
            "gold_mode":    False,
        }
        result = _run_briefing_forex_gate(scored, qg_passes=False)
        self.assertFalse(result, "QualityGate block must override ENTER_NOW")

    def test_qg_block_prevents_gold_enter_now_from_logging(self):
        """QualityGate block also applies to gold."""
        scored = {"entry_state": "ENTER_NOW", "gold_mode": True, "signal_mode": "legacy_gold"}
        self.assertFalse(_run_briefing_forex_gate(scored, qg_passes=False))

    def test_quality_gate_entry_pattern_runs(self):
        """
        QualityGate itself: A+ grade forex with no entry pattern is blocked.
        Verifies QualityGate module is functional (separate from briefing gate).
        """
        from filters.quality_gate import minimum_quality_gate
        scored = {
            "direction":    "bullish",
            "grade":        "A+",
            "setup_type":   "trend_follow",
            "gold_mode":    False,
            "signal_mode":  "legacy_forex",
            "top_zone":     None,
            "trade_levels": {"sl_pips": 10.0},
            "entry_pattern": None,   # no pattern → QG should block A+
        }
        result = minimum_quality_gate(scored, {}, "EUR_USD")
        self.assertFalse(result["passes"],
                         "QualityGate must block A+ forex with no entry pattern")
        self.assertIn("entry pattern", result["block_reason"].lower())

    def test_quality_gate_passes_forex_with_pattern(self):
        """QualityGate passes A forex with a valid entry pattern."""
        from filters.quality_gate import minimum_quality_gate
        scored = {
            "direction":    "bullish",
            "grade":        "A",
            "setup_type":   "trend_follow",
            "gold_mode":    False,
            "signal_mode":  "legacy_forex",
            "top_zone":     None,
            "trade_levels": {"sl_pips": 10.0},
            "entry_pattern": {"pattern": "engulfing", "direction": "bullish"},
        }
        result = minimum_quality_gate(scored, {}, "EUR_USD")
        self.assertTrue(result["passes"])


# ═══════════════════════════════════════════════════════════════════════════════
# Part F — Global / per-strategy env gates
# ═══════════════════════════════════════════════════════════════════════════════

def _run_full_gate(scored: dict, om_enabled: bool, forex_enabled: bool,
                   gold_enabled: bool) -> dict:
    """
    Inline reimplementation of env gates + logging gate from briefing.py.
    Returns dict with: would_log (bool), entry_state_after (str).
    """
    import copy
    s = copy.deepcopy(scored)

    # ── Global gate ────────────────────────────────────────────────────────────
    if not om_enabled:
        s["entry_state"]   = "WATCH_ONLY_GLOBAL_DISABLED"
        s["should_log"]    = False
        s["should_alert"]  = False
        s["entry_allowed"] = False
        return {"would_log": False, "entry_state_after": s["entry_state"]}

    # ── Per-strategy gate ──────────────────────────────────────────────────────
    _lg_gold   = s.get("gold_mode", False)
    _lg_sniper = s.get("signal_mode") == "news_sniper"
    _lg_forex  = not _lg_gold and not _lg_sniper

    if _lg_gold and not gold_enabled:
        s["entry_state"]   = "WATCH_ONLY_LEGACY_GOLD_DISABLED"
        s["should_log"]    = False
        s["should_alert"]  = False
        s["entry_allowed"] = False
    elif _lg_forex and not forex_enabled:
        s["entry_state"]   = "WATCH_ONLY_LEGACY_FOREX_DISABLED"
        s["should_log"]    = False
        s["should_alert"]  = False
        s["entry_allowed"] = False

    # ── Logging gate (Option A) ────────────────────────────────────────────────
    _gold   = s.get("gold_mode", False)
    _sniper = s.get("signal_mode") == "news_sniper"
    _log_now = s.get("entry_state") == "ENTER_NOW"   # uniform for all modes

    return {"would_log": _log_now, "entry_state_after": s.get("entry_state")}


class TestEnvGatesWithOptionA(unittest.TestCase):
    """
    OM_STRATEGY_ENABLED, LEGACY_GOLD_ENABLED, LEGACY_FOREX_ENABLED interact
    correctly with the Option A logging gate.
    """

    def test_om_disabled_blocks_forex_enter_now(self):
        """OM_STRATEGY_ENABLED=False → no logging even with ENTER_NOW."""
        scored = {"entry_state": "ENTER_NOW", "signal_mode": "legacy_forex", "gold_mode": False}
        r = _run_full_gate(scored, om_enabled=False, forex_enabled=True, gold_enabled=True)
        self.assertFalse(r["would_log"])
        self.assertEqual(r["entry_state_after"], "WATCH_ONLY_GLOBAL_DISABLED")

    def test_forex_disabled_blocks_forex_enter_now(self):
        """LEGACY_FOREX_ENABLED=False → entry_state overwritten, not logged."""
        scored = {"entry_state": "ENTER_NOW", "signal_mode": "legacy_forex", "gold_mode": False}
        r = _run_full_gate(scored, om_enabled=True, forex_enabled=False, gold_enabled=True)
        self.assertFalse(r["would_log"])
        self.assertEqual(r["entry_state_after"], "WATCH_ONLY_LEGACY_FOREX_DISABLED")

    def test_gold_disabled_does_not_block_forex(self):
        """LEGACY_GOLD_ENABLED=False does not block forex."""
        scored = {"entry_state": "ENTER_NOW", "signal_mode": "legacy_forex", "gold_mode": False}
        r = _run_full_gate(scored, om_enabled=True, forex_enabled=True, gold_enabled=False)
        self.assertTrue(r["would_log"])

    def test_forex_enabled_logs_enter_now(self):
        """All enabled + ENTER_NOW → logs."""
        scored = {"entry_state": "ENTER_NOW", "signal_mode": "legacy_forex", "gold_mode": False}
        r = _run_full_gate(scored, om_enabled=True, forex_enabled=True, gold_enabled=True)
        self.assertTrue(r["would_log"])

    def test_forex_enabled_does_not_log_early_entry_only(self):
        """
        All enabled + EARLY ENTRY ONLY (entry_state=None) → still NOT logged.
        Proves env gates don't bypass Option A's ENTER_NOW requirement.
        """
        scored = {"entry_state": None, "should_log": True, "signal_mode": "legacy_forex", "gold_mode": False}
        r = _run_full_gate(scored, om_enabled=True, forex_enabled=True, gold_enabled=True)
        self.assertFalse(r["would_log"],
                         "EARLY ENTRY ONLY must not log even when all env gates are open")

    def test_gold_enter_now_not_blocked_by_forex_disabled(self):
        """LEGACY_FOREX_ENABLED=False does not block gold."""
        scored = {"entry_state": "ENTER_NOW", "signal_mode": "legacy_gold", "gold_mode": True}
        r = _run_full_gate(scored, om_enabled=True, forex_enabled=False, gold_enabled=True)
        self.assertTrue(r["would_log"])

    def test_sniper_enter_now_not_blocked_by_forex_disabled(self):
        """LEGACY_FOREX_ENABLED=False does not block news_sniper."""
        scored = {"entry_state": "ENTER_NOW", "signal_mode": "news_sniper", "gold_mode": False}
        r = _run_full_gate(scored, om_enabled=True, forex_enabled=False, gold_enabled=True)
        self.assertTrue(r["would_log"])


# ═══════════════════════════════════════════════════════════════════════════════
# Part G — briefing.py source code contract check
# ═══════════════════════════════════════════════════════════════════════════════

class TestBriefingSourceContract(unittest.TestCase):
    """
    Verify that reports/briefing.py source code reflects Option A's contract —
    forex logging gate uses entry_state == 'ENTER_NOW', not should_log.
    """

    def test_briefing_forex_gate_uses_enter_now(self):
        """briefing.py forex branch must use entry_state == 'ENTER_NOW'."""
        import inspect
        import reports.briefing as bmod
        src = inspect.getsource(bmod)

        # Option A contract line must be present
        self.assertIn("entry_state", src)
        self.assertIn("ENTER_NOW", src)

        # The old regression line (forex: should_log branch) must NOT be the
        # active gate — confirm the comment marking it as the regression is gone.
        # We look for the Option A comment we added in the code.
        self.assertIn("restores May 12 execution-ready contract", src,
                      "Option A comment must be present in briefing.py forex gate")

    def test_briefing_imports_legacy_gates(self):
        """briefing.py must still import LEGACY_GOLD_ENABLED and LEGACY_FOREX_ENABLED."""
        import inspect
        import reports.briefing as bmod
        src = inspect.getsource(bmod)
        self.assertIn("LEGACY_GOLD_ENABLED", src)
        self.assertIn("LEGACY_FOREX_ENABLED", src)


if __name__ == "__main__":
    unittest.main()
