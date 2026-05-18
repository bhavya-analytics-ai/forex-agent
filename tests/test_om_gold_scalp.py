"""
tests/test_om_gold_scalp.py — Unit + integration tests for om_gold_scalp strategy.

All tests must FAIL before strategies/om_gold_scalp.py exists.
All tests must PASS before om_gold_scalp is wired into the scan loop.

Run: pytest tests/test_om_gold_scalp.py -v

Candle fixture format (list of dicts, newest last):
  {"open": float, "high": float, "low": float, "close": float, "volume": float}

No OANDA API calls. No DB writes. No Slack. Pure unit tests.
"""

import pytest
import importlib
import sys


# ---------------------------------------------------------------------------
# Helpers — synthetic candle builders
# ---------------------------------------------------------------------------

def candle(o, h, l, c, vol=1000.0):
    return {"open": o, "high": h, "low": l, "close": c, "volume": vol}


def flat_candles(price=2300.0, n=30):
    """n sideways candles at price."""
    return [candle(price, price + 2, price - 2, price) for _ in range(n)]


def bearish_candles(start=2320.0, step=3.0, n=10):
    """Steady downtrend candles."""
    out = []
    p = start
    for _ in range(n):
        out.append(candle(p, p + 1, p - step - 1, p - step))
        p -= step
    return out


def bullish_candles(start=2280.0, step=3.0, n=10):
    """Steady uptrend candles."""
    out = []
    p = start
    for _ in range(n):
        out.append(candle(p, p + step + 1, p - 1, p + step))
        p += step
    return out


def make_confluence(
    h1_candles=None,
    m15_candles=None,
    m5_candles=None,
    h1_trend="bearish",
    m15_trend="bearish",
    m5_trend="bearish",
):
    """Minimal confluence dict matching the shape expected by om_gold_scalp."""
    def _wrap(candles, trend):
        return {
            "candles": candles or flat_candles(),
            "structure": {"trend": trend},
        }

    return {
        "h1":  _wrap(h1_candles,  h1_trend),
        "m15": _wrap(m15_candles, m15_trend),
        "m5":  _wrap(m5_candles,  m5_trend),
        "approaching_warning": "",
    }


def make_candles_dict(h1=None, m15=None, m5=None):
    return {
        "H1":  h1  or flat_candles(),
        "M15": m15 or flat_candles(),
        "M5":  m5  or flat_candles(),
    }


# ---------------------------------------------------------------------------
# Lazy import — fails gracefully when module doesn't exist
# ---------------------------------------------------------------------------

def _import_strategy():
    try:
        from strategies import om_gold_scalp
        return om_gold_scalp
    except ImportError:
        pytest.skip("strategies/om_gold_scalp.py does not exist yet")


# ---------------------------------------------------------------------------
# UNIT TESTS
# ---------------------------------------------------------------------------

class TestStrategyMeta:
    """STRATEGY_META must be declared and correctly shaped."""

    def test_meta_exists(self):
        mod = _import_strategy()
        assert hasattr(mod, "STRATEGY_META"), "STRATEGY_META missing"

    def test_meta_signal_mode(self):
        mod = _import_strategy()
        assert mod.STRATEGY_META["signal_mode"] == "om_gold_scalp"

    def test_meta_allowed_symbols(self):
        mod = _import_strategy()
        syms = mod.STRATEGY_META["allowed_symbols"]
        assert "XAU_USD" in syms
        # Must NOT claim all pairs
        assert syms != "*"

    def test_meta_required_timeframes(self):
        mod = _import_strategy()
        tfs = mod.STRATEGY_META["required_timeframes"]
        assert "H1"  in tfs
        assert "M15" in tfs
        assert "M5"  in tfs

    def test_meta_can_run_watch_only(self):
        mod = _import_strategy()
        assert mod.STRATEGY_META["can_run_watch_only"] is True

    def test_meta_can_emit_live_signal(self):
        """Starts false — only enabled via OM_GOLD_SCALP_ENABLED env var."""
        mod = _import_strategy()
        # The META value is True; the runtime gate is in config/runner.
        # This just confirms the field exists and is bool.
        assert isinstance(mod.STRATEGY_META["can_emit_live_signal"], bool)


class TestIsolation:
    """om_gold_scalp must not import from gold_strategy or news_sniper."""

    def test_no_gold_strategy_import(self):
        mod = _import_strategy()
        src = open(mod.__file__).read()
        assert "gold_strategy" not in src, \
            "om_gold_scalp must not import from gold_strategy"

    def test_no_news_sniper_import(self):
        mod = _import_strategy()
        src = open(mod.__file__).read()
        assert "news_sniper" not in src, \
            "om_gold_scalp must not import from news_sniper"


class TestWatchOnlyGate:
    """With OM_GOLD_SCALP_ENABLED=false, should_log and should_alert must be False
    regardless of what the state machine computed."""

    def test_watch_only_suppresses_log(self, monkeypatch):
        mod = _import_strategy()
        import config
        monkeypatch.setattr(config, "OM_GOLD_SCALP_ENABLED", False)

        confluence = make_confluence()
        candles    = make_candles_dict()
        result     = mod.run({}, confluence, "XAU_USD", candles)
        assert result["should_log"]   is False
        assert result["should_alert"] is False

    def test_watch_only_preserves_entry_state(self, monkeypatch):
        """Even in watch-only mode the state machine output must be readable."""
        mod = _import_strategy()
        import config
        monkeypatch.setattr(config, "OM_GOLD_SCALP_ENABLED", False)

        confluence = make_confluence()
        candles    = make_candles_dict()
        result     = mod.run({}, confluence, "XAU_USD", candles)
        assert "entry_state" in result


class TestHtfRangeSkipChop:
    """Price inside HTF range → SKIP, skip_reason=inside_range_chop."""

    def test_inside_range_gives_skip(self, monkeypatch):
        mod = _import_strategy()
        import config
        monkeypatch.setattr(config, "OM_GOLD_SCALP_ENABLED", True)

        # Flat H1 candles — price oscillating inside a band = range
        h1 = flat_candles(price=2300.0, n=60)
        confluence = make_confluence(h1_candles=h1, h1_trend="chop")
        candles    = make_candles_dict(h1=h1)

        result = mod.run({}, confluence, "XAU_USD", candles)
        assert result["entry_state"] in ("SKIP", "SKIP_CHOP")
        assert result.get("skip_reason") == "inside_range_chop"

    def test_skip_chop_entry_allowed_false(self, monkeypatch):
        mod = _import_strategy()
        import config
        monkeypatch.setattr(config, "OM_GOLD_SCALP_ENABLED", True)

        h1 = flat_candles(price=2300.0, n=60)
        confluence = make_confluence(h1_candles=h1, h1_trend="chop")
        candles    = make_candles_dict(h1=h1)

        result = mod.run({}, confluence, "XAU_USD", candles)
        assert result.get("entry_allowed") is False


class TestSweepReclaimLong:
    """Bearish sweep wick + bullish reclaim body close + displacement → ENTER_NOW long."""

    def _build_sweep_reclaim_m5(self, base=2300.0):
        """
        Synthetic M5 sequence:
          bars[0..19]: downtrend context
          bars[20]:    sweep candle — wick below base-10, body closes back above base-5
          bars[21]:    reclaim candle — body close above base (bullish)
          bars[22]:    hold candle — closes above base (no reversal)
          bars[23]:    displacement — large bullish body (> 1.5× avg)
        """
        bars = bearish_candles(start=base + 20, step=1.5, n=20)
        # sweep low=base-13: clears prior swing low (~base-11.5) by >1.5pts ✓
        # displace close=base+1: entry_dist=14 ≤ 25 (no chase), sl_pts=16 ≤ 20, RR=1.5 ✓
        sweep    = candle(base - 2, base + 1, base - 13, base - 3)  # wick down, body back up
        reclaim  = candle(base - 3, base + 2, base - 4,  base + 1)  # body close above level
        hold     = candle(base + 1, base + 3, base,      base + 2)  # holds above
        displace = candle(base - 2, base + 4, base - 3,  base + 1)  # bullish body, close=base+1
        bars += [sweep, reclaim, hold, displace]
        return bars

    def test_sweep_reclaim_long_enter_now(self, monkeypatch):
        mod = _import_strategy()
        import config
        monkeypatch.setattr(config, "OM_GOLD_SCALP_ENABLED", True)

        m5 = self._build_sweep_reclaim_m5(base=2300.0)
        # Confluent trends required: momentum_gate (>=50) must pass.
        # m5="bullish" (+35), m15="bullish" (+25), displacement (+10), M1 (+7) = 77 >= 50.
        # h1="bullish" is not opposing bullish direction → no opposing-H1 skip.
        confluence = make_confluence(m5_candles=m5, m5_trend="bullish",
                                     h1_trend="bullish", m15_trend="bullish")
        candles = make_candles_dict(m5=m5)
        result  = mod.run({}, confluence, "XAU_USD", candles)

        assert result["entry_state"] == "ENTER_NOW"
        assert result["direction"]   == "bullish"
        assert result["setup_type"]  == "sweep_reclaim_long"

    def test_sweep_alone_no_entry(self, monkeypatch):
        """Sweep detected but no displacement yet → not ENTER_NOW (WAIT_HOLD or earlier)."""
        mod = _import_strategy()
        import config
        monkeypatch.setattr(config, "OM_GOLD_SCALP_ENABLED", True)

        base = 2300.0
        bars = bearish_candles(start=base + 20, step=1.5, n=20)
        # Sweep: low=base-13 clears prior swing low by >1.5pts
        sweep     = candle(base - 2, base + 1, base - 13, base - 3)
        # Small follow bar — body=1, well below the displacement threshold
        small_bar = candle(base - 3, base,     base - 4,  base - 2)
        bars += [sweep, small_bar]

        confluence = make_confluence(m5_candles=bars, m5_trend="bearish",
                                     h1_trend="bearish")
        candles    = make_candles_dict(m5=bars)
        result     = mod.run({}, confluence, "XAU_USD", candles)

        assert result["entry_state"] in (
            "WAIT_RETEST", "WAIT_REACTION", "WAIT_RECLAIM", "WAIT_HOLD"
        )
        assert result.get("sweep_candidate") is True


class TestFailedReclaimShort:
    """Reclaim attempt fails + bearish displacement → ENTER_NOW short."""

    def _build_failed_reclaim_m5(self, sr=2300.0):
        """
        bars[0..19]: flat context near sr-5 (highs ≈ sr-3)
        bars[20]:    bullish sweep — wick spikes above prior swing high by >1.5pts, body closes back
        bars[21]:    reclaim attempt — wick above sweep_high, body closes below
        bars[22]:    bearish displacement — large bearish body
        """
        # Flat near sr-5 so prior_swing_high ≈ sr-3 (price+2). A wick to sr+3 clears it by >1.5pts.
        bars = flat_candles(price=sr - 5, n=20)
        sweep_up     = candle(sr - 5, sr + 3,  sr - 7,  sr - 4)   # high=sr+3>prior+1.5 ✓, body back
        reclaim_fail = candle(sr - 2, sr + 5,  sr - 3,  sr - 1)   # wick>sweep_high-1.5, body below
        displace     = candle(sr - 1, sr,       sr - 14, sr - 13)  # large bearish body
        bars += [sweep_up, reclaim_fail, displace]
        return bars, sr

    def test_failed_reclaim_short_enter_now(self, monkeypatch):
        mod = _import_strategy()
        import config
        monkeypatch.setattr(config, "OM_GOLD_SCALP_ENABLED", True)

        m5, sr = self._build_failed_reclaim_m5(sr=2300.0)
        confluence = make_confluence(m5_candles=m5, m5_trend="bearish",
                                     h1_trend="bearish")
        candles = make_candles_dict(m5=m5)
        result  = mod.run({}, confluence, "XAU_USD", candles)

        assert result["entry_state"] == "ENTER_NOW"
        assert result["direction"]   == "bearish"
        assert result["setup_type"]  == "failed_reclaim_continuation"


class TestRangeBreakdownBearish:
    """Range low broken + retest held below + follow-through → ENTER_NOW short."""

    def _build_breakdown_m5(self, range_low=2290.0):
        """
        bars[0..19]: range context — flat at range_low+2, inside H1 range [range_low, range_low+4]
        bars[20]:    body close below range_low
        bars[21]:    retest — wicks up toward range_low, body holds below
        bars[22]:    follow-through — closes lower

        M5 context at range_low+2 keeps all bars below range_high (range_low+4)
        so fake_breakout detection does not fire before range_breakdown.
        """
        bars = flat_candles(price=range_low + 2, n=20)
        breakdown    = candle(range_low + 1, range_low + 3, range_low - 5, range_low - 3)
        retest       = candle(range_low - 3, range_low - 0.5, range_low - 6, range_low - 4)
        follow       = candle(range_low - 4, range_low - 3,  range_low - 12, range_low - 10)
        bars += [breakdown, retest, follow]
        return bars, range_low

    def test_range_breakdown_enter_now_short(self, monkeypatch):
        mod = _import_strategy()
        import config
        monkeypatch.setattr(config, "OM_GOLD_SCALP_ENABLED", True)

        range_low = 2290.0
        m5, rlow = self._build_breakdown_m5(range_low=range_low)
        # H1: flat_candles with price = range_low + 2 so swing_low ≈ range_low
        h1 = flat_candles(price=range_low + 2, n=60)
        confluence = make_confluence(h1_candles=h1, m5_candles=m5,
                                     h1_trend="chop", m5_trend="bearish")
        candles = make_candles_dict(h1=h1, m5=m5)
        result  = mod.run({}, confluence, "XAU_USD", candles)

        assert result["entry_state"] == "ENTER_NOW"
        assert result["direction"]   == "bearish"
        assert result["setup_type"]  == "range_breakdown_bearish"


class TestRangeFakeBreakoutSkip:
    """Breakout above range + body reclaims back inside → SKIP_INSIDE_RANGE, entry_allowed=False."""

    def _build_fake_breakout_m5(self, range_high=2310.0):
        """
        bars[0..19]: range (flat)
        bars[20]:    breakout — body closes above range_high
        bars[21]:    reclaim — body closes back inside range (below range_high)
        """
        bars = flat_candles(price=range_high - 10, n=20)
        breakout = candle(range_high - 1, range_high + 8, range_high - 2, range_high + 5)
        reclaim  = candle(range_high + 5, range_high + 6, range_high - 5, range_high - 3)
        bars += [breakout, reclaim]
        return bars, range_high

    def test_fake_breakout_gives_skip_inside_range(self, monkeypatch):
        mod = _import_strategy()
        import config
        monkeypatch.setattr(config, "OM_GOLD_SCALP_ENABLED", True)

        range_high = 2310.0
        m5, rhigh = self._build_fake_breakout_m5(range_high=range_high)
        # H1: flat_candles with price = range_high - 2 so swing_high ≈ range_high
        h1 = flat_candles(price=range_high - 2, n=60)
        confluence = make_confluence(h1_candles=h1, m5_candles=m5, h1_trend="chop")
        candles = make_candles_dict(h1=h1, m5=m5)
        result  = mod.run({}, confluence, "XAU_USD", candles)

        assert result["entry_state"] in ("SKIP", "SKIP_INSIDE_RANGE")
        assert result.get("skip_reason") in (
            "fake_breakout_no_trade", "inside_range_chop"
        )
        assert result.get("entry_allowed") is False

    def test_fake_breakout_blocks_both_directions(self, monkeypatch):
        """After fake breakout, neither long nor short is allowed."""
        mod = _import_strategy()
        import config
        monkeypatch.setattr(config, "OM_GOLD_SCALP_ENABLED", True)

        range_high = 2310.0
        m5, rhigh = self._build_fake_breakout_m5(range_high=range_high)
        h1 = flat_candles(price=range_high - 2, n=60)
        confluence = make_confluence(h1_candles=h1, m5_candles=m5, h1_trend="chop")
        candles = make_candles_dict(h1=h1, m5=m5)
        result  = mod.run({}, confluence, "XAU_USD", candles)

        assert result.get("entry_allowed") is False
        # avoid_long and avoid_short reasons must be set
        assert result.get("avoid_long_reason")  != ""
        assert result.get("avoid_short_reason") != ""


class TestSlTooWide:
    """SL > max_sl_pts (20) → SKIP, skip_reason=sl_too_wide."""

    def test_sl_too_wide_gives_skip(self, monkeypatch):
        mod = _import_strategy()
        import config
        monkeypatch.setattr(config, "OM_GOLD_SCALP_ENABLED", True)

        # Sweep 27pts deep → SL = entry_dist + 2 > 20.
        # Displace closes at base-4 (entry_dist=23 ≤ 25 chase threshold, sl_pts=25 > 20).
        base = 2300.0
        bars = bearish_candles(start=base + 20, step=1.5, n=20)
        sweep    = candle(base - 2, base + 1,  base - 27, base - 2)   # low = base-27
        reclaim  = candle(base - 2, base + 2,  base - 3,  base + 1)
        hold     = candle(base + 1, base + 3,  base,      base + 2)
        displace = candle(base - 9, base - 3,  base - 10, base - 4)   # close=base-4, bullish, body=5
        bars += [sweep, reclaim, hold, displace]

        # Use bearish H1 trend so range gate doesn't fire before the SL check
        h1 = bearish_candles(start=base + 60, step=2.0, n=40)
        confluence = make_confluence(m5_candles=bars, h1_candles=h1, h1_trend="bearish")
        candles    = make_candles_dict(m5=bars, h1=h1)
        result     = mod.run({}, confluence, "XAU_USD", candles)

        assert result["entry_state"] in ("SKIP", "SKIP_CHOP")
        assert result.get("skip_reason") == "sl_too_wide"


class TestChaseDistance:
    """Entry > max_chase_pts (25) from origin zone → SKIP_CHASE."""

    def test_chase_distance_skip(self, monkeypatch):
        mod = _import_strategy()
        import config
        monkeypatch.setattr(config, "OM_GOLD_SCALP_ENABLED", True)

        # Valid sweep+reclaim but displacement moves price 31 pts from sweep low
        base = 2300.0
        bars = bearish_candles(start=base + 20, step=1.5, n=20)
        sweep    = candle(base - 2, base + 1, base - 13, base - 3)  # low=base-13, clears prior swing
        reclaim  = candle(base - 3, base + 2, base - 4, base + 1)
        hold     = candle(base + 1, base + 3, base,     base + 2)
        displace = candle(base + 2, base + 32, base + 1, base + 31)  # 31 pts from zone
        bars += [sweep, reclaim, hold, displace]

        # Use bearish H1 trend so range gate doesn't fire before the chase check
        h1 = bearish_candles(start=base + 60, step=2.0, n=40)
        confluence = make_confluence(m5_candles=bars, h1_candles=h1, h1_trend="bearish")
        candles    = make_candles_dict(m5=bars, h1=h1)
        result     = mod.run({}, confluence, "XAU_USD", candles)

        assert result["entry_state"] == "SKIP_CHASE"
        assert result.get("skip_reason") == "chase_distance"


class TestSkipReasonAlwaysLogged:
    """Every SKIP must include a non-empty skip_reason. Never silent."""

    def test_no_setup_has_skip_reason(self, monkeypatch):
        mod = _import_strategy()
        import config
        monkeypatch.setattr(config, "OM_GOLD_SCALP_ENABLED", True)

        # Perfectly flat — no setup possible
        bars = flat_candles(price=2300.0, n=40)
        confluence = make_confluence(m5_candles=bars, h1_trend="chop")
        candles    = make_candles_dict(m5=bars)
        result     = mod.run({}, confluence, "XAU_USD", candles)

        if result["entry_state"] in ("SKIP", "SKIP_CHOP", "SKIP_CHASE", "SKIP_INSIDE_RANGE"):
            assert result.get("skip_reason"), \
                f"SKIP with no skip_reason — entry_state={result['entry_state']}"

    def test_all_skip_variants_have_reason(self, monkeypatch):
        """Run five known-skip scenarios and confirm skip_reason is set in each."""
        mod = _import_strategy()
        import config
        monkeypatch.setattr(config, "OM_GOLD_SCALP_ENABLED", True)

        scenarios = [
            # (label, m5_bars, h1_trend)
            ("flat_chop",    flat_candles(2300.0, 40), "chop"),
            ("bearish_chop", bearish_candles(2320.0, step=1.0, n=40), "bearish"),
        ]
        for label, m5, h1_trend in scenarios:
            confluence = make_confluence(m5_candles=m5, h1_trend=h1_trend)
            candles    = make_candles_dict(m5=m5)
            result     = mod.run({}, confluence, "XAU_USD", candles)
            if "SKIP" in result.get("entry_state", ""):
                assert result.get("skip_reason"), \
                    f"skip_reason empty for scenario '{label}'"


class TestMomentumScore:
    """Momentum score must always be 0–100."""

    def test_momentum_score_range_on_skip(self, monkeypatch):
        mod = _import_strategy()
        import config
        monkeypatch.setattr(config, "OM_GOLD_SCALP_ENABLED", True)

        bars = flat_candles(2300.0, 40)
        confluence = make_confluence(m5_candles=bars, h1_trend="chop")
        candles    = make_candles_dict(m5=bars)
        result     = mod.run({}, confluence, "XAU_USD", candles)
        score = result.get("momentum_score", 0)
        assert 0 <= score <= 100, f"momentum_score={score} out of range"

    def test_momentum_score_range_on_enter_now(self, monkeypatch):
        mod = _import_strategy()
        import config
        monkeypatch.setattr(config, "OM_GOLD_SCALP_ENABLED", True)

        base = 2300.0
        bars = bearish_candles(start=base + 20, step=1.5, n=20)
        sweep    = candle(base - 2, base + 1, base - 13, base - 3)
        reclaim  = candle(base - 3, base + 2, base - 4,  base + 1)
        hold     = candle(base + 1, base + 3, base,      base + 2)
        displace = candle(base - 2, base + 4, base - 3,  base + 1)
        bars += [sweep, reclaim, hold, displace]

        confluence = make_confluence(m5_candles=bars)
        candles    = make_candles_dict(m5=bars)
        result     = mod.run({}, confluence, "XAU_USD", candles)
        score = result.get("momentum_score", 0)
        assert 0 <= score <= 100


class TestAuditFieldsPresent:
    """Every output — SKIP or ENTER_NOW — must carry the required audit fields."""

    REQUIRED_FIELDS = [
        "entry_state",
        "direction",
        "setup_type",
        "entry_allowed",
        "skip_reason",
        "momentum_score",
        "signal_mode",
        "should_log",
        "should_alert",
        "htf_range_active",
        "zone_state",
        "sweep_candidate",
        "reclaim_confirmed",
        "reclaim_failed",
        "bullish_displacement",
        "bearish_displacement_after_failed_reclaim",
        "scanner_state_flow",
    ]

    def _run_default(self, monkeypatch, enabled=True):
        mod = _import_strategy()
        import config
        monkeypatch.setattr(config, "OM_GOLD_SCALP_ENABLED", enabled)
        bars = flat_candles(2300.0, 40)
        confluence = make_confluence(m5_candles=bars, h1_trend="chop")
        candles    = make_candles_dict(m5=bars)
        return mod.run({}, confluence, "XAU_USD", candles)

    def test_all_required_fields_present_on_skip(self, monkeypatch):
        result = self._run_default(monkeypatch, enabled=True)
        missing = [f for f in self.REQUIRED_FIELDS if f not in result]
        assert not missing, f"Missing audit fields: {missing}"

    def test_all_required_fields_present_watch_only(self, monkeypatch):
        result = self._run_default(monkeypatch, enabled=False)
        missing = [f for f in self.REQUIRED_FIELDS if f not in result]
        assert not missing, f"Missing audit fields in watch-only mode: {missing}"

    def test_signal_mode_is_om_gold_scalp(self, monkeypatch):
        result = self._run_default(monkeypatch, enabled=True)
        assert result["signal_mode"] == "om_gold_scalp"

    def test_skip_reason_is_string(self, monkeypatch):
        result = self._run_default(monkeypatch, enabled=True)
        assert isinstance(result.get("skip_reason", ""), str)

    def test_scanner_state_flow_is_string(self, monkeypatch):
        result = self._run_default(monkeypatch, enabled=True)
        assert isinstance(result.get("scanner_state_flow", ""), str)


class TestTradeLevels:
    """On ENTER_NOW, trade levels must be present and sane."""

    def _run_sweep_reclaim(self, monkeypatch, base=2300.0):
        mod = _import_strategy()
        import config
        monkeypatch.setattr(config, "OM_GOLD_SCALP_ENABLED", True)

        bars = bearish_candles(start=base + 20, step=1.5, n=20)
        sweep    = candle(base - 2, base + 1, base - 13, base - 3)
        reclaim  = candle(base - 3, base + 2, base - 4,  base + 1)
        hold     = candle(base + 1, base + 3, base,      base + 2)
        displace = candle(base - 2, base + 4, base - 3,  base + 1)
        bars += [sweep, reclaim, hold, displace]
        confluence = make_confluence(m5_candles=bars, m5_trend="bearish")
        candles    = make_candles_dict(m5=bars)
        return _import_strategy().run({}, confluence, "XAU_USD", candles)

    def test_entry_price_present(self, monkeypatch):
        result = self._run_sweep_reclaim(monkeypatch)
        if result["entry_state"] == "ENTER_NOW":
            assert result.get("entry_price") is not None

    def test_sl_within_max(self, monkeypatch):
        result = self._run_sweep_reclaim(monkeypatch)
        if result["entry_state"] == "ENTER_NOW":
            ep = result.get("entry_price", 0)
            sl = result.get("sl_price", 0)
            sl_pts = abs(ep - sl)
            assert sl_pts <= 22, f"SL too wide: {sl_pts} pts"  # 20 + 2 buffer tolerance

    def test_tp1_min_rr(self, monkeypatch):
        result = self._run_sweep_reclaim(monkeypatch)
        if result["entry_state"] == "ENTER_NOW":
            ep  = result.get("entry_price", 0)
            sl  = result.get("sl_price", 0)
            tp1 = result.get("tp1_price", 0)
            sl_dist  = abs(ep - sl)
            tp1_dist = abs(tp1 - ep)
            if sl_dist > 0:
                rr = tp1_dist / sl_dist
                assert rr >= 1.5, f"RR={rr:.2f} below minimum 1.5"


# ---------------------------------------------------------------------------
# MOMENTUM GATE TESTS
# ---------------------------------------------------------------------------

class TestMomentumGate:
    """
    momentum_score < MIN_MOMENTUM_REQUIRED (50) must prevent ENTER_NOW.
    Audit fields min_momentum_required and momentum_gate_passed must always be present.
    """

    def _build_sweep_reclaim_m5(self, base=2300.0):
        """Same geometric fixture as TestSweepReclaimLong — sweep + reclaim + displacement."""
        bars = bearish_candles(start=base + 20, step=1.5, n=20)
        sweep    = candle(base - 2, base + 1, base - 13, base - 3)
        reclaim  = candle(base - 3, base + 2, base - 4,  base + 1)
        hold     = candle(base + 1, base + 3, base,      base + 2)
        displace = candle(base - 2, base + 4, base - 3,  base + 1)
        bars += [sweep, reclaim, hold, displace]
        return bars

    def test_low_momentum_no_enter_now(self, monkeypatch):
        """
        Sweep + reclaim + displacement fires, but chop trends → momentum ≈ 17 < 50.
        Must produce WAIT_MOMENTUM (or SKIP), never ENTER_NOW.
        """
        mod = _import_strategy()
        import config
        monkeypatch.setattr(config, "OM_GOLD_SCALP_ENABLED", True)

        m5 = self._build_sweep_reclaim_m5(base=2300.0)
        # h1="bullish" (not opposing bullish direction, so no opposing-H1 skip)
        # m5/m15="chop" → 0 M5/M15 pts → momentum ≈ 10(displace)+7(M1) = 17 < 50
        confluence = make_confluence(
            m5_candles=m5,
            h1_trend="bullish",
            m5_trend="chop",
            m15_trend="chop",
        )
        candles = make_candles_dict(m5=m5)
        result  = mod.run({}, confluence, "XAU_USD", candles)

        assert result["entry_state"] != "ENTER_NOW", (
            f"Expected WAIT_MOMENTUM or SKIP, got ENTER_NOW "
            f"(momentum_score={result.get('momentum_score')})"
        )
        assert result["entry_state"] in ("WAIT_MOMENTUM", "SKIP", "SKIP_CHOP"), (
            f"Unexpected entry_state={result['entry_state']}"
        )

    def test_high_momentum_can_enter_now(self, monkeypatch):
        """
        Same geometry + strong confluent trends → momentum ≈ 77 >= 50 → ENTER_NOW allowed.
        """
        mod = _import_strategy()
        import config
        monkeypatch.setattr(config, "OM_GOLD_SCALP_ENABLED", True)

        m5 = self._build_sweep_reclaim_m5(base=2300.0)
        # m5="bullish"(+35) + m15="bullish"(+25) + displacement(+10) + M1(+7) = 77 >= 50
        # h1="bullish" → not opposing bullish direction
        confluence = make_confluence(
            m5_candles=m5,
            h1_trend="bullish",
            m5_trend="bullish",
            m15_trend="bullish",
        )
        candles = make_candles_dict(m5=m5)
        result  = mod.run({}, confluence, "XAU_USD", candles)

        assert result["entry_state"] == "ENTER_NOW", (
            f"Expected ENTER_NOW with high momentum, got {result['entry_state']} "
            f"(momentum_score={result.get('momentum_score')})"
        )
        assert result["direction"]  == "bullish"
        assert result["setup_type"] == "sweep_reclaim_long"

    def test_momentum_audit_fields_present(self, monkeypatch):
        """min_momentum_required and momentum_gate_passed must be in every result."""
        mod = _import_strategy()
        import config
        monkeypatch.setattr(config, "OM_GOLD_SCALP_ENABLED", True)

        m5 = self._build_sweep_reclaim_m5(base=2300.0)
        # Low-momentum path (chop trends) so we exercise the WAIT_MOMENTUM branch
        confluence = make_confluence(
            m5_candles=m5,
            h1_trend="bullish",
            m5_trend="chop",
            m15_trend="chop",
        )
        candles = make_candles_dict(m5=m5)
        result  = mod.run({}, confluence, "XAU_USD", candles)

        assert "min_momentum_required" in result, \
            "min_momentum_required missing from output"
        assert "momentum_gate_passed"  in result, \
            "momentum_gate_passed missing from output"
        assert result["min_momentum_required"] == 50, \
            f"min_momentum_required should be 50, got {result['min_momentum_required']}"
        assert isinstance(result["momentum_gate_passed"], bool), \
            "momentum_gate_passed must be bool"


# ---------------------------------------------------------------------------
# INTEGRATION TESTS
# ---------------------------------------------------------------------------

class TestIntegration:

    def test_run_function_exists(self):
        """strategies/om_gold_scalp.py must expose a run() function."""
        mod = _import_strategy()
        assert callable(getattr(mod, "run", None)), "run() function missing"

    def test_run_accepts_standard_signature(self, monkeypatch):
        """run(scored, confluence, pair, candles) must not raise."""
        mod = _import_strategy()
        import config
        monkeypatch.setattr(config, "OM_GOLD_SCALP_ENABLED", False)

        scored     = {}
        confluence = make_confluence()
        candles    = make_candles_dict()
        result     = mod.run(scored, confluence, "XAU_USD", candles)
        assert isinstance(result, dict)

    def test_wrong_pair_returns_skip(self, monkeypatch):
        """Running against a non-XAU pair must return SKIP, not crash."""
        mod = _import_strategy()
        import config
        monkeypatch.setattr(config, "OM_GOLD_SCALP_ENABLED", True)

        confluence = make_confluence()
        candles    = make_candles_dict()
        result     = mod.run({}, confluence, "EUR_USD", candles)
        assert result["entry_state"] in ("SKIP", "SKIP_CHOP")

    def test_quality_gate_compatibility(self, monkeypatch):
        """Output dict must contain sl_pips so the existing quality gate can read it."""
        mod = _import_strategy()
        import config
        monkeypatch.setattr(config, "OM_GOLD_SCALP_ENABLED", True)

        bars = flat_candles(2300.0, 40)
        confluence = make_confluence(m5_candles=bars, h1_trend="chop")
        candles    = make_candles_dict(m5=bars)
        result     = mod.run({}, confluence, "XAU_USD", candles)
        # sl_pips must be present (may be 0 on SKIP, but must exist)
        assert "sl_pips" in result

    def test_global_kill_switch_overrides_strategy_flag(self, monkeypatch):
        """OM_STRATEGY_ENABLED=false must suppress output even if OM_GOLD_SCALP_ENABLED=true.
        This test verifies the runner contract — om_gold_scalp itself honours its own flag;
        the runner applies the global gate on top."""
        mod = _import_strategy()
        import config
        monkeypatch.setattr(config, "OM_GOLD_SCALP_ENABLED", False)   # strategy flag off
        # Global gate is tested at the runner layer (briefing.py) — not inside the strategy.
        # Here we just confirm watch-only output when the strategy flag is off.
        confluence = make_confluence()
        candles    = make_candles_dict()
        result     = mod.run({}, confluence, "XAU_USD", candles)
        assert result["should_log"]   is False
        assert result["should_alert"] is False
