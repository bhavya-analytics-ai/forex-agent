"""
tests/test_multi_strategy_runner.py — Unit tests for parallel strategy runner.

Verifies:
  - XAU_USD scan produces OM Gold Scalp extra candidate
  - signal_mode is preserved on each candidate
  - OM is watch-only (should_log=False, should_alert=False) with switches off
  - Primary scored dict is never modified by the runner
  - Legacy and OM candidates are fully independent (no overwrite)
  - Non-XAU pairs do not produce OM candidates
  - Global kill switch (OM_STRATEGY_ENABLED=False) suppresses OM even if
    OM_GOLD_SCALP_ENABLED=True

No OANDA API calls. No DB writes. No Slack. Pure unit tests.
"""

import pytest


# ---------------------------------------------------------------------------
# Candle + confluence helpers (reuse from test_om_gold_scalp layout)
# ---------------------------------------------------------------------------

def _flat_candles(price=2300.0, n=30):
    return [
        {"open": price, "high": price + 2, "low": price - 2, "close": price, "volume": 1000.0}
        for _ in range(n)
    ]


def _make_confluence(h1_trend="bearish", m15_trend="bearish", m5_trend="bearish"):
    def _wrap(trend):
        return {"candles": _flat_candles(), "structure": {"trend": trend}}

    return {
        "h1":  _wrap(h1_trend),
        "m15": _wrap(m15_trend),
        "m5":  _wrap(m5_trend),
        "approaching_warning": "",
    }


def _make_scored(pair="XAU_USD", signal_mode="legacy_gold"):
    return {
        "pair":         pair,
        "score":        72.0,
        "grade":        "A",
        "direction":    "bearish",
        "signal_mode":  signal_mode,
        "entry_state":  "WAIT_OM_RULES",
        "should_log":   False,
        "should_alert": False,
    }


def _make_candles():
    """Minimal candle dict matching fetch_all_timeframes() key structure."""
    return {
        "H1":  _flat_candles(),
        "M15": _flat_candles(),
        "M5":  _flat_candles(),
        "M1":  _flat_candles(),
    }


# ---------------------------------------------------------------------------
# Import helper
# ---------------------------------------------------------------------------

def _import_runner():
    try:
        from strategies import runner
        return runner
    except ImportError:
        pytest.skip("strategies/runner.py does not exist yet")


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

class TestRunnerXauProducesOmCandidate:
    """XAU_USD scan must produce at least one om_gold_scalp extra candidate."""

    def test_xau_returns_om_extra(self, monkeypatch):
        import config
        monkeypatch.setattr(config, "OM_STRATEGY_ENABLED",  False)
        monkeypatch.setattr(config, "OM_GOLD_SCALP_ENABLED", False)

        runner = _import_runner()
        scored     = _make_scored("XAU_USD", "legacy_gold")
        confluence = _make_confluence()
        candles    = _make_candles()

        extras = runner.run_extra_strategies(scored, confluence, "XAU_USD", candles)

        assert isinstance(extras, list)
        assert len(extras) >= 1
        om = next((e for e in extras if e.get("signal_mode") == "om_gold_scalp"), None)
        assert om is not None, "Expected om_gold_scalp candidate in extras"

    def test_om_candidate_is_dict(self, monkeypatch):
        import config
        monkeypatch.setattr(config, "OM_STRATEGY_ENABLED",  False)
        monkeypatch.setattr(config, "OM_GOLD_SCALP_ENABLED", False)

        runner = _import_runner()
        extras = runner.run_extra_strategies(
            _make_scored("XAU_USD"), _make_confluence(), "XAU_USD", _make_candles()
        )
        om = next((e for e in extras if e.get("signal_mode") == "om_gold_scalp"), None)
        assert isinstance(om, dict)


class TestNonXauNoOm:
    """Non-XAU pairs must NOT produce om_gold_scalp candidates."""

    @pytest.mark.parametrize("pair", ["EUR_USD", "GBP_JPY", "XAG_USD", "USD_JPY"])
    def test_non_xau_no_om_candidate(self, monkeypatch, pair):
        import config
        monkeypatch.setattr(config, "OM_STRATEGY_ENABLED",  False)
        monkeypatch.setattr(config, "OM_GOLD_SCALP_ENABLED", False)

        runner = _import_runner()
        extras = runner.run_extra_strategies(
            _make_scored(pair), _make_confluence(), pair, _make_candles()
        )
        om_extras = [e for e in extras if e.get("signal_mode") == "om_gold_scalp"]
        assert len(om_extras) == 0, f"OM candidate must not appear for {pair}"


class TestSignalModePreserved:
    """signal_mode on each candidate must be correct and independent."""

    def test_om_candidate_has_correct_signal_mode(self, monkeypatch):
        import config
        monkeypatch.setattr(config, "OM_STRATEGY_ENABLED",  False)
        monkeypatch.setattr(config, "OM_GOLD_SCALP_ENABLED", False)

        runner = _import_runner()
        extras = runner.run_extra_strategies(
            _make_scored("XAU_USD", "legacy_gold"), _make_confluence(), "XAU_USD", _make_candles()
        )
        om = next(e for e in extras if e.get("signal_mode") == "om_gold_scalp")
        assert om["signal_mode"] == "om_gold_scalp"

    def test_primary_signal_mode_unchanged(self, monkeypatch):
        """Primary scored dict must not be modified by the runner."""
        import config
        monkeypatch.setattr(config, "OM_STRATEGY_ENABLED",  False)
        monkeypatch.setattr(config, "OM_GOLD_SCALP_ENABLED", False)

        runner = _import_runner()
        scored = _make_scored("XAU_USD", "legacy_gold")
        runner.run_extra_strategies(scored, _make_confluence(), "XAU_USD", _make_candles())

        assert scored["signal_mode"] == "legacy_gold", \
            "runner must not mutate primary scored dict"


class TestWatchOnlyGate:
    """With all switches off, OM must have should_log=False and should_alert=False."""

    def test_both_gates_off_suppresses_log_alert(self, monkeypatch):
        import config
        monkeypatch.setattr(config, "OM_STRATEGY_ENABLED",  False)
        monkeypatch.setattr(config, "OM_GOLD_SCALP_ENABLED", False)

        runner = _import_runner()
        extras = runner.run_extra_strategies(
            _make_scored("XAU_USD"), _make_confluence(), "XAU_USD", _make_candles()
        )
        om = next(e for e in extras if e.get("signal_mode") == "om_gold_scalp")
        assert om["should_log"]   is False
        assert om["should_alert"] is False

    def test_global_gate_off_overrides_per_strategy_on(self, monkeypatch):
        """OM_STRATEGY_ENABLED=False must suppress even when OM_GOLD_SCALP_ENABLED=True."""
        import config
        monkeypatch.setattr(config, "OM_STRATEGY_ENABLED",   False)  # global OFF
        monkeypatch.setattr(config, "OM_GOLD_SCALP_ENABLED", True)   # per-strategy ON

        runner = _import_runner()
        extras = runner.run_extra_strategies(
            _make_scored("XAU_USD"), _make_confluence(), "XAU_USD", _make_candles()
        )
        om = next(e for e in extras if e.get("signal_mode") == "om_gold_scalp")
        assert om["should_log"]   is False, "global gate must override per-strategy"
        assert om["should_alert"] is False, "global gate must override per-strategy"

    def test_per_strategy_gate_off_suppresses(self, monkeypatch):
        """OM_GOLD_SCALP_ENABLED=False must suppress even if global gate is on."""
        import config
        monkeypatch.setattr(config, "OM_STRATEGY_ENABLED",   True)   # global ON
        monkeypatch.setattr(config, "OM_GOLD_SCALP_ENABLED", False)  # per-strategy OFF

        runner = _import_runner()
        extras = runner.run_extra_strategies(
            _make_scored("XAU_USD"), _make_confluence(), "XAU_USD", _make_candles()
        )
        om = next(e for e in extras if e.get("signal_mode") == "om_gold_scalp")
        assert om["should_log"]   is False
        assert om["should_alert"] is False


class TestLegacyOmIsolation:
    """Legacy and OM candidates must be completely independent."""

    def test_om_does_not_overwrite_primary(self, monkeypatch):
        import config
        monkeypatch.setattr(config, "OM_STRATEGY_ENABLED",  False)
        monkeypatch.setattr(config, "OM_GOLD_SCALP_ENABLED", False)

        runner = _import_runner()
        scored = _make_scored("XAU_USD", "legacy_gold")
        orig   = scored.copy()

        runner.run_extra_strategies(scored, _make_confluence(), "XAU_USD", _make_candles())

        for key in orig:
            assert scored[key] == orig[key], \
                f"runner mutated primary scored['{key}']: {orig[key]} → {scored[key]}"

    def test_separate_candidate_objects(self, monkeypatch):
        """Extra candidates must be different dict objects from primary."""
        import config
        monkeypatch.setattr(config, "OM_STRATEGY_ENABLED",  False)
        monkeypatch.setattr(config, "OM_GOLD_SCALP_ENABLED", False)

        runner = _import_runner()
        scored = _make_scored("XAU_USD", "legacy_gold")
        extras = runner.run_extra_strategies(scored, _make_confluence(), "XAU_USD", _make_candles())

        for cand in extras:
            assert cand is not scored, "extra candidate must be a new dict, not the primary"


class TestRequiredAuditFields:
    """OM extra candidates must have the standard audit fields."""

    REQUIRED = [
        "signal_mode", "entry_state", "direction", "setup_type",
        "should_log", "should_alert", "entry_allowed", "skip_reason",
        "momentum_score", "scanner_state_flow",
    ]

    def test_om_candidate_has_audit_fields(self, monkeypatch):
        import config
        monkeypatch.setattr(config, "OM_STRATEGY_ENABLED",  False)
        monkeypatch.setattr(config, "OM_GOLD_SCALP_ENABLED", False)

        runner = _import_runner()
        extras = runner.run_extra_strategies(
            _make_scored("XAU_USD"), _make_confluence(), "XAU_USD", _make_candles()
        )
        om = next(e for e in extras if e.get("signal_mode") == "om_gold_scalp")
        missing = [f for f in self.REQUIRED if f not in om]
        assert not missing, f"OM extra candidate missing audit fields: {missing}"
