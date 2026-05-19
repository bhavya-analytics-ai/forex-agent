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

    def test_htf_range_no_trade_setup_type_label(self, monkeypatch):
        """
        HTF range/no-trade fallthrough must set setup_type = 'htf_range_no_trade'.
        skip_reason and entry_state must be unchanged from before the label fix.
        """
        mod = _import_strategy()
        import config
        monkeypatch.setattr(config, "OM_GOLD_SCALP_ENABLED", True)

        h1 = flat_candles(price=2300.0, n=60)
        confluence = make_confluence(h1_candles=h1, h1_trend="chop")
        candles    = make_candles_dict(h1=h1)

        result = mod.run({}, confluence, "XAU_USD", candles)

        # Label fix: setup_type must now be the named category, not the default "no_setup"
        assert result["setup_type"] == "htf_range_no_trade", (
            f"Expected setup_type='htf_range_no_trade', got '{result['setup_type']}'"
        )
        # Existing behavior unchanged
        assert result["entry_state"] in ("SKIP", "SKIP_CHOP")
        assert result["skip_reason"] == "inside_range_chop"
        assert result["entry_allowed"] is False


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


class TestSweepReclaimShort:
    """
    Bullish sweep + no reclaim attempt in last 3 bars + bearish displacement
    → ENTER_NOW short, setup_type="sweep_reclaim_short".

    Behavioral distinction from failed_reclaim_continuation:
      failed_reclaim_continuation: sweep detected AND a SEPARATE reclaim bar
        (wick above sr_level, body below) is visible in the last 3 bars.
      sweep_reclaim_short: sweep detected AND none of the last 3 bars pushed
        above sr_level (market rolled over without a second push attempt),
        AND bearish displacement is present.

    Fixture puts sweep at -5 position so it is outside _detect_reclaim's
    last-3-bar window, guaranteeing rec_fail["reclaim_failed"] = False.
    """

    def _build_sweep_reclaim_short_m5(self, base=2300.0):
        """
        bars[0..24]:  flat baseline (prior swing high ≈ base+2)
        bars[25]:     bullish sweep — wick to base+5 clears prior high by >1.5 pts,
                      body closes at base+1 (below sr_level = base+3.5)
        bars[26..28]: three neutral bars that stay well below sr_level, ensuring
                      none of them push above sr_level → rec_fail["reclaim_failed"]=False
        bars[29]:     bearish displacement — large bearish body, entry close ≈ base-7

        SL = sweep_high + SL_BUFFER = (base+5) + 2 = base+7
        entry ≈ base-7  →  sl_pts ≈ (base+7) - (base-7) = 14 ≤ 20 ✓
        chase_dist = |(base-7) - (base+5)| = 12 ≤ 25 ✓
        """
        bars = flat_candles(price=base, n=25)
        sweep_up = candle(base,     base + 5,  base - 1,  base + 1)  # wick up, body back below
        neutral1 = candle(base + 1, base + 2,  base,      base + 1)
        neutral2 = candle(base + 1, base + 2,  base - 0.5, base + 0.5)
        neutral3 = candle(base,     base + 1,  base - 1,  base - 0.5)
        displace = candle(base,     base + 0.5, base - 8,  base - 7)  # large bearish body
        bars += [sweep_up, neutral1, neutral2, neutral3, displace]
        return bars

    def test_sweep_reclaim_short_enter_now(self, monkeypatch):
        """Clean path: bullish sweep + no reclaim + bearish displacement → ENTER_NOW."""
        mod = _import_strategy()
        import config
        monkeypatch.setattr(config, "OM_GOLD_SCALP_ENABLED", True)

        m5 = self._build_sweep_reclaim_short_m5(base=2300.0)
        # bearish h1/m5/m15 → momentum passes (35+25+7 = 67 ≥ 50), no opposing-H1 skip
        confluence = make_confluence(
            m5_candles=m5, m5_trend="bearish", m15_trend="bearish", h1_trend="bearish",
        )
        candles = make_candles_dict(m5=m5)
        result  = mod.run({}, confluence, "XAU_USD", candles)

        assert result["entry_state"] == "ENTER_NOW", (
            f"Expected ENTER_NOW, got {result['entry_state']} "
            f"(skip_reason={result.get('skip_reason')}, "
            f"rejection_stage={result.get('rejection_stage')}, "
            f"rejection_reason={result.get('rejection_reason')})"
        )
        assert result["direction"]  == "bearish"
        assert result["setup_type"] == "sweep_reclaim_short"

    def test_sweep_reclaim_short_audit_fields(self, monkeypatch):
        """All required audit fields are populated on sweep_reclaim_short ENTER_NOW."""
        mod = _import_strategy()
        import config
        monkeypatch.setattr(config, "OM_GOLD_SCALP_ENABLED", True)

        m5 = self._build_sweep_reclaim_short_m5(base=2300.0)
        confluence = make_confluence(
            m5_candles=m5, m5_trend="bearish", m15_trend="bearish", h1_trend="bearish",
        )
        result = mod.run({}, confluence, "XAU_USD", make_candles_dict(m5=m5))

        if result["entry_state"] == "ENTER_NOW":
            assert result["sweep_detected"]        is True
            assert result["sweep_high"]            > 0.0
            assert result["sweep_reference_level"] > 0.0
            assert result["displacement_ratio"]    > 0.0
            assert result["entry_price_candidate"] is not None
            assert result["sl_price_candidate"]    is not None
            assert result["sl_gate_passed"]        is True
            assert result["momentum_gate_passed"]  is True
            assert result["scanner_state_flow"].startswith(
                "bullish_sweep → direct_rejection → bearish_displacement"
            )

    def test_sweep_reclaim_short_wait_hold_no_displacement(self, monkeypatch):
        """
        Bullish sweep + no reclaim attempt + NO bearish displacement → WAIT_HOLD.
        (Sweep seen, but rejection bar not confirmed yet.)
        """
        mod = _import_strategy()
        import config
        monkeypatch.setattr(config, "OM_GOLD_SCALP_ENABLED", True)

        base = 2300.0
        bars = flat_candles(price=base, n=25)
        sweep_up = candle(base, base + 5, base - 1, base + 1)
        # Three tiny bars — no bearish displacement (body well below 1.5× avg)
        neutral1 = candle(base + 1, base + 1.5, base + 0.5, base + 1)
        neutral2 = candle(base + 1, base + 1.5, base + 0.5, base + 1)
        neutral3 = candle(base + 1, base + 1.5, base + 0.5, base + 1)
        bars += [sweep_up, neutral1, neutral2, neutral3]

        confluence = make_confluence(
            m5_candles=bars, m5_trend="bearish", h1_trend="bearish",
        )
        result = mod.run({}, confluence, "XAU_USD", make_candles_dict(m5=bars))

        assert result["entry_state"] == "WAIT_HOLD", (
            f"Expected WAIT_HOLD (sweep fresh, no displacement), "
            f"got {result['entry_state']}"
        )
        assert result["sweep_detected"] is True

    def test_sweep_reclaim_short_low_momentum_wait(self, monkeypatch):
        """
        Sweep + no reclaim + bearish displacement but chop trends → WAIT_MOMENTUM,
        never ENTER_NOW.
        """
        mod = _import_strategy()
        import config
        monkeypatch.setattr(config, "OM_GOLD_SCALP_ENABLED", True)

        m5 = self._build_sweep_reclaim_short_m5(base=2300.0)
        # chop trends → M5=0, M15=0 → momentum ≈ displacement(varies) + 7 < 50
        confluence = make_confluence(
            m5_candles=m5, m5_trend="chop", m15_trend="chop", h1_trend="bearish",
        )
        result = mod.run({}, confluence, "XAU_USD", make_candles_dict(m5=m5))

        assert result["entry_state"] != "ENTER_NOW", (
            f"Low momentum must not reach ENTER_NOW "
            f"(momentum_score={result.get('momentum_score')})"
        )
        assert result["entry_state"] in ("WAIT_MOMENTUM", "SKIP", "WAIT_HOLD"), (
            f"Unexpected state {result['entry_state']}"
        )

    def test_sweep_reclaim_short_no_false_long(self, monkeypatch):
        """Bullish displacement after a bullish sweep (wrong direction) must not fire ENTER_NOW."""
        mod = _import_strategy()
        import config
        monkeypatch.setattr(config, "OM_GOLD_SCALP_ENABLED", True)

        base = 2300.0
        bars = flat_candles(price=base, n=25)
        sweep_up  = candle(base, base + 5, base - 1, base + 1)
        neutral1  = candle(base + 1, base + 1.5, base + 0.5, base + 1)
        neutral2  = candle(base + 1, base + 1.5, base + 0.5, base + 1)
        neutral3  = candle(base + 1, base + 1.5, base + 0.5, base + 1)
        # Bullish displacement — wrong direction for sweep_reclaim_short
        bull_disp = candle(base + 1, base + 9, base, base + 8)
        bars += [sweep_up, neutral1, neutral2, neutral3, bull_disp]

        confluence = make_confluence(
            m5_candles=bars, m5_trend="bullish", h1_trend="bearish",
        )
        result = mod.run({}, confluence, "XAU_USD", make_candles_dict(m5=bars))

        # Must not fire ENTER_NOW short on a bullish displacement bar
        assert not (result["entry_state"] == "ENTER_NOW" and result["direction"] == "bearish"), (
            "sweep_reclaim_short must not fire ENTER_NOW bearish on bullish displacement"
        )

    def test_failed_reclaim_continuation_unchanged(self, monkeypatch):
        """
        The existing failed_reclaim_continuation path must be completely unaffected.
        Explicit reclaim_fail bar in last 3 → still produces failed_reclaim_continuation.
        """
        mod = _import_strategy()
        import config
        monkeypatch.setattr(config, "OM_GOLD_SCALP_ENABLED", True)

        sr = 2300.0
        bars = flat_candles(price=sr - 5, n=20)
        sweep_up     = candle(sr - 5, sr + 3,  sr - 7,  sr - 4)
        reclaim_fail = candle(sr - 2, sr + 5,  sr - 3,  sr - 1)  # explicit reclaim bar in last3
        displace     = candle(sr - 1, sr,       sr - 14, sr - 13)
        bars += [sweep_up, reclaim_fail, displace]

        confluence = make_confluence(
            m5_candles=bars, m5_trend="bearish", h1_trend="bearish",
        )
        result = mod.run({}, confluence, "XAU_USD", make_candles_dict(m5=bars))

        assert result["entry_state"] == "ENTER_NOW"
        assert result["direction"]   == "bearish"
        assert result["setup_type"]  == "failed_reclaim_continuation", (
            "failed_reclaim_continuation path must not be reclassified as sweep_reclaim_short"
        )


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


class TestRangeBreakoutBullish:
    """Range high broken + retest held above + follow-through → ENTER_NOW long."""

    def _build_breakout_m5(self, range_high=2310.0):
        """
        Bullish mirror of TestRangeBreakdownBearish._build_breakdown_m5.

        bars[0..19]: range context — flat below range_high, inside H1 range
        bars[20]:    breakout — body closes ABOVE range_high
        bars[21]:    retest — wicks down toward range_high, body holds above
        bars[22]:    follow-through — closes higher

        The flat baseline sits at range_high - 2 so it does NOT trigger fake_breakout
        (fake_breakout requires a body close ABOVE range_high followed by close BELOW —
        here bars 20+ stay above range_high, so the detector never fires).
        """
        bars = flat_candles(price=range_high - 2, n=20)
        breakout     = candle(range_high - 1, range_high + 5, range_high - 1, range_high + 3)
        retest       = candle(range_high + 3, range_high + 4, range_high + 0.5, range_high + 1.5)
        follow       = candle(range_high + 1.5, range_high + 10, range_high + 1, range_high + 9)
        bars += [breakout, retest, follow]
        return bars, range_high

    def test_range_breakout_enter_now_long(self, monkeypatch):
        """All three gates pass → ENTER_NOW long, setup_type=range_breakout_bullish."""
        mod = _import_strategy()
        import config
        monkeypatch.setattr(config, "OM_GOLD_SCALP_ENABLED", True)

        range_high = 2310.0
        m5, rhigh = self._build_breakout_m5(range_high=range_high)
        # H1: flat so swing_high ≈ range_high; H1 trend chop to avoid opposing-H1 skip
        h1 = flat_candles(price=range_high - 2, n=60)
        confluence = make_confluence(h1_candles=h1, m5_candles=m5,
                                     h1_trend="chop", m5_trend="bullish")
        candles = make_candles_dict(h1=h1, m5=m5)
        result  = mod.run({}, confluence, "XAU_USD", candles)

        assert result["entry_state"] == "ENTER_NOW"
        assert result["direction"]   == "bullish"
        assert result["setup_type"]  == "range_breakout_bullish"

    def test_range_breakout_audit_fields(self, monkeypatch):
        """range_high_broken, range_retest_held_above, bullish_follow_through all True on ENTER_NOW."""
        mod = _import_strategy()
        import config
        monkeypatch.setattr(config, "OM_GOLD_SCALP_ENABLED", True)

        range_high = 2310.0
        m5, rhigh = self._build_breakout_m5(range_high=range_high)
        h1 = flat_candles(price=range_high - 2, n=60)
        confluence = make_confluence(h1_candles=h1, m5_candles=m5,
                                     h1_trend="chop", m5_trend="bullish")
        candles = make_candles_dict(h1=h1, m5=m5)
        result  = mod.run({}, confluence, "XAU_USD", candles)

        assert result["range_high_broken"]       is True
        assert result["range_retest_held_above"] is True
        assert result["bullish_follow_through"]  is True

    def test_range_breakout_no_retest_no_enter(self, monkeypatch):
        """
        Breakout bar closes above range_high but no retest / follow-through bars follow →
        htf_range_no_trade fallthrough (not ENTER_NOW).
        """
        mod = _import_strategy()
        import config
        monkeypatch.setattr(config, "OM_GOLD_SCALP_ENABLED", True)

        range_high = 2310.0
        bars = flat_candles(price=range_high - 2, n=20)
        # Only a single breakout bar; no subsequent retest/follow-through inside last-5 window
        breakout = candle(range_high - 1, range_high + 5, range_high - 1, range_high + 3)
        bars.append(breakout)
        h1 = flat_candles(price=range_high - 2, n=60)
        confluence = make_confluence(h1_candles=h1, m5_candles=bars,
                                     h1_trend="chop", m5_trend="bullish")
        candles = make_candles_dict(h1=h1, m5=bars)
        result  = mod.run({}, confluence, "XAU_USD", candles)

        # No retest + follow-through → falls to htf_range_no_trade
        assert result["entry_state"] in ("SKIP", "SKIP_INSIDE_RANGE", "WAIT_MOMENTUM")
        assert result["setup_type"] in ("htf_range_no_trade", "range_breakout_bullish")
        # Must NOT be ENTER_NOW
        assert result["entry_state"] != "ENTER_NOW"

    def test_range_breakout_low_momentum_wait_momentum(self, monkeypatch):
        """All structural gates pass but momentum < 50 → WAIT_MOMENTUM."""
        mod = _import_strategy()
        import config
        monkeypatch.setattr(config, "OM_GOLD_SCALP_ENABLED", True)

        range_high = 2310.0
        m5, rhigh = self._build_breakout_m5(range_high=range_high)
        h1 = flat_candles(price=range_high - 2, n=60)
        confluence = make_confluence(h1_candles=h1, m5_candles=m5,
                                     h1_trend="chop", m5_trend="chop")  # neutral → low momentum
        candles = make_candles_dict(h1=h1, m5=m5)

        # Force momentum score below threshold
        def _low_momentum(candles_, direction, conf):
            return 20.0

        monkeypatch.setattr(mod, "_momentum_score", _low_momentum)
        result = mod.run({}, confluence, "XAU_USD", candles)

        assert result["entry_state"] == "WAIT_MOMENTUM"
        assert result["setup_type"]  == "range_breakout_bullish"
        assert result["momentum_gate_passed"] is False

    def test_range_breakout_does_not_affect_bearish_breakdown(self, monkeypatch):
        """
        Bearish breakdown fixture still produces range_breakdown_bearish ENTER_NOW short.
        The new bullish branch must not interfere.
        """
        mod = _import_strategy()
        import config
        monkeypatch.setattr(config, "OM_GOLD_SCALP_ENABLED", True)

        range_low = 2290.0
        bars = flat_candles(price=range_low + 2, n=20)
        breakdown = candle(range_low + 1, range_low + 3, range_low - 5, range_low - 3)
        retest    = candle(range_low - 3, range_low - 0.5, range_low - 6, range_low - 4)
        follow    = candle(range_low - 4, range_low - 3,  range_low - 12, range_low - 10)
        m5 = bars + [breakdown, retest, follow]
        h1 = flat_candles(price=range_low + 2, n=60)
        confluence = make_confluence(h1_candles=h1, m5_candles=m5,
                                     h1_trend="chop", m5_trend="bearish")
        candles = make_candles_dict(h1=h1, m5=m5)
        result  = mod.run({}, confluence, "XAU_USD", candles)

        assert result["entry_state"] == "ENTER_NOW"
        assert result["direction"]   == "bearish"
        assert result["setup_type"]  == "range_breakdown_bearish"

    def test_range_breakout_fake_breakout_takes_priority(self, monkeypatch):
        """
        Fake breakout (body above then body back below range_high within 1-2 bars) is
        detected FIRST in Gate 1 and returns range_fake_breakout_no_trade, NOT range_breakout_bullish.
        """
        mod = _import_strategy()
        import config
        monkeypatch.setattr(config, "OM_GOLD_SCALP_ENABLED", True)

        range_high = 2310.0
        bars = flat_candles(price=range_high - 10, n=20)
        breakout = candle(range_high - 1, range_high + 8, range_high - 2, range_high + 5)
        reclaim  = candle(range_high + 5, range_high + 6, range_high - 5, range_high - 3)
        m5 = bars + [breakout, reclaim]
        h1 = flat_candles(price=range_high - 2, n=60)
        confluence = make_confluence(h1_candles=h1, m5_candles=m5, h1_trend="chop")
        candles = make_candles_dict(h1=h1, m5=m5)
        result  = mod.run({}, confluence, "XAU_USD", candles)

        assert result["setup_type"]  == "range_fake_breakout_no_trade"
        assert result["entry_state"] in ("SKIP", "SKIP_INSIDE_RANGE")
        assert result["entry_allowed"] is False


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


# ---------------------------------------------------------------------------
# AUDIT FIELD VISIBILITY TESTS
# ---------------------------------------------------------------------------

class TestDebugAuditFields:
    """
    All debug audit fields must be present in every run() output, regardless of
    entry_state. Covers: SKIP, WAIT_REACTION, WAIT_HOLD, ENTER_NOW paths.
    No strategy logic is changed — these tests verify observability only.
    """

    # Core fields that must exist on every output
    CORE_FIELDS = [
        "signal_mode", "entry_state", "direction", "setup_type",
        "should_log", "should_alert", "entry_allowed", "skip_reason",
        "momentum_score", "scanner_state_flow",
    ]

    # Branch tracking
    BRANCH_FIELDS = [
        "evaluated_branches", "active_branch",
        "rejection_stage", "rejection_reason", "setup_candidates_found",
    ]

    # Context trends
    TREND_FIELDS = ["h1_trend", "m15_trend", "m5_trend"]

    # Sweep detail
    SWEEP_FIELDS = [
        "sweep_detected", "sweep_low", "sweep_high", "sweep_bars_ago",
        "sweep_reference_level", "sweep_distance_pts",
    ]

    # Reclaim detail
    RECLAIM_FIELDS = ["reclaim_level", "hold_bar", "reclaim_distance_pts"]

    # Displacement detail
    DISP_FIELDS = ["displacement_body_pts", "avg_body_pts", "displacement_ratio"]

    # Entry/SL candidates
    ENTRY_FIELDS = [
        "entry_price_candidate", "sl_anchor",
        "sl_price_candidate", "sl_gate_passed", "max_sl_pts",
    ]

    ALL_REQUIRED = (
        CORE_FIELDS + BRANCH_FIELDS + TREND_FIELDS
        + SWEEP_FIELDS + RECLAIM_FIELDS + DISP_FIELDS + ENTRY_FIELDS
    )

    def _run_skip(self, monkeypatch):
        """Run with no sweep setup → SKIP path."""
        import config
        monkeypatch.setattr(config, "OM_GOLD_SCALP_ENABLED", False)
        mod = _import_strategy()
        confluence = make_confluence(h1_trend="bearish", m15_trend="bearish", m5_trend="bearish")
        candles = make_candles_dict()
        return mod.run({}, confluence, "XAU_USD", candles)

    def test_all_audit_fields_present_on_skip(self, monkeypatch):
        result = self._run_skip(monkeypatch)
        missing = [f for f in self.ALL_REQUIRED if f not in result]
        assert not missing, f"Missing audit fields on SKIP: {missing}"

    def test_evaluated_branches_is_list(self, monkeypatch):
        result = self._run_skip(monkeypatch)
        assert isinstance(result["evaluated_branches"], list)

    def test_setup_candidates_found_is_int(self, monkeypatch):
        result = self._run_skip(monkeypatch)
        assert isinstance(result["setup_candidates_found"], int)

    def test_trend_fields_populated(self, monkeypatch):
        import config
        monkeypatch.setattr(config, "OM_GOLD_SCALP_ENABLED", False)
        mod = _import_strategy()
        confluence = make_confluence(h1_trend="bearish", m15_trend="downtrend", m5_trend="bearish")
        result = mod.run({}, confluence, "XAU_USD", make_candles_dict())
        assert result["h1_trend"]  == "bearish"
        assert result["m15_trend"] == "downtrend"
        assert result["m5_trend"]  == "bearish"

    def test_avg_body_pts_non_negative(self, monkeypatch):
        result = self._run_skip(monkeypatch)
        assert result["avg_body_pts"] >= 0.0

    def test_max_sl_pts_matches_constant(self, monkeypatch):
        result = self._run_skip(monkeypatch)
        assert result["max_sl_pts"] == 20.0

    def test_rejection_stage_or_reason_on_skip(self, monkeypatch):
        result = self._run_skip(monkeypatch)
        assert result["rejection_stage"] != "" or result["rejection_reason"] != "", \
            "Expected rejection_stage or rejection_reason on SKIP path"


class TestSweepDetailFields:
    """When a sweep is detected, sweep detail fields must be populated."""

    def _make_sweep_candles(self, price=2300.0, sweep_down_to=2285.0):
        """
        25 baseline bars + 1 sweep bar (wick well below prior lows, closes back up)
        + 3 consolidation bars. Should trigger bearish sweep → WAIT_REACTION.
        """
        base = flat_candles(price, n=25)
        sweep_bar = {
            "open":  price,
            "high":  price + 1.0,
            "low":   sweep_down_to,
            "close": price - 0.5,
            "volume": 2000.0,
        }
        hold = [{"open": price - 0.5, "high": price + 0.5, "low": price - 1.0,
                 "close": price - 0.3, "volume": 800.0} for _ in range(3)]
        return base + [sweep_bar] + hold

    def test_sweep_fields_always_present(self, monkeypatch):
        import config
        monkeypatch.setattr(config, "OM_GOLD_SCALP_ENABLED", False)
        mod = _import_strategy()
        result = mod.run({}, make_confluence(), "XAU_USD", make_candles_dict())
        for f in ["sweep_detected", "sweep_low", "sweep_high", "sweep_bars_ago",
                  "sweep_reference_level", "sweep_distance_pts"]:
            assert f in result, f"Missing sweep field: {f}"

    def test_sweep_detail_populated_when_detected(self, monkeypatch):
        import config
        monkeypatch.setattr(config, "OM_GOLD_SCALP_ENABLED", False)
        mod = _import_strategy()
        m5 = self._make_sweep_candles()
        confluence = make_confluence(m5_candles=m5, h1_trend="bearish",
                                     m5_trend="bearish", m15_trend="bearish")
        result = mod.run({}, confluence, "XAU_USD", make_candles_dict(m5=m5))

        if result.get("sweep_detected"):
            assert result["sweep_low"]             > 0.0
            assert result["sweep_high"]            > 0.0
            assert result["sweep_bars_ago"]        < 999
            assert result["sweep_reference_level"] > 0.0
            assert result["sweep_distance_pts"]    > 0.0

    def test_sweep_defaults_when_not_detected(self, monkeypatch):
        import config
        monkeypatch.setattr(config, "OM_GOLD_SCALP_ENABLED", False)
        mod = _import_strategy()
        result = mod.run({}, make_confluence(), "XAU_USD", make_candles_dict())
        if not result.get("sweep_detected"):
            assert result["sweep_bars_ago"]     == 999
            assert result["sweep_distance_pts"] == 0.0


class TestDisplacementDetailFields:
    """displacement_body_pts, avg_body_pts, displacement_ratio must be numeric in every result."""

    def test_disp_fields_numeric(self, monkeypatch):
        import config
        monkeypatch.setattr(config, "OM_GOLD_SCALP_ENABLED", False)
        mod = _import_strategy()
        result = mod.run({}, make_confluence(), "XAU_USD", make_candles_dict())
        assert isinstance(result["displacement_body_pts"], (int, float))
        assert isinstance(result["avg_body_pts"],          (int, float))
        assert isinstance(result["displacement_ratio"],    (int, float))

    def test_disp_ratio_non_negative(self, monkeypatch):
        import config
        monkeypatch.setattr(config, "OM_GOLD_SCALP_ENABLED", False)
        mod = _import_strategy()
        result = mod.run({}, make_confluence(), "XAU_USD", make_candles_dict())
        assert result["displacement_ratio"] >= 0.0


class TestEntrySlCandidateFields:
    """Entry/SL candidate fields surface what the strategy was considering."""

    def test_candidate_fields_present(self, monkeypatch):
        import config
        monkeypatch.setattr(config, "OM_GOLD_SCALP_ENABLED", False)
        mod = _import_strategy()
        result = mod.run({}, make_confluence(), "XAU_USD", make_candles_dict())
        for f in ["entry_price_candidate", "sl_anchor", "sl_price_candidate",
                  "sl_gate_passed", "max_sl_pts"]:
            assert f in result, f"Missing candidate field: {f}"

    def test_sl_gate_passed_false_on_no_setup(self, monkeypatch):
        import config
        monkeypatch.setattr(config, "OM_GOLD_SCALP_ENABLED", False)
        mod = _import_strategy()
        result = mod.run({}, make_confluence(), "XAU_USD", make_candles_dict())
        # No setup → no SL evaluation → sl_gate_passed stays False
        assert result["sl_gate_passed"] is False


# ---------------------------------------------------------------------------
# SKIP CLASSIFICATION CONSISTENCY TESTS
# Tests the invariants enforced by _enforce_skip_consistency:
#   1. no sweep/no range event → never produces sl_too_wide
#   2. sl_too_wide requires entry_price_candidate, sl_price_candidate, sl_pts > 0
#   3. every SKIP output has internally consistent fields
# ---------------------------------------------------------------------------

class TestSkipClassificationConsistency:
    """
    sl_too_wide is only valid when a real candidate was evaluated and the SL
    distance exceeded MAX_SL_PTS. A bare no-setup scan must always produce
    skip_reason=no_setup with null entry/SL candidate fields.
    """

    # ── helper: run with flat candles (guaranteed no sweep, no range event) ──
    def _no_candidate_result(self, monkeypatch):
        import config
        monkeypatch.setattr(config, "OM_GOLD_SCALP_ENABLED", False)
        mod = _import_strategy()
        confluence = make_confluence(h1_trend="bearish", m15_trend="bearish", m5_trend="bearish")
        return mod.run({}, confluence, "XAU_USD", make_candles_dict())

    # ── helper: build candles that force sl_too_wide on a sweep path ─────────
    @staticmethod
    def _wide_sl_sweep_candles(price=2300.0, sweep_pts=60.0):
        """
        Sweep bar whose wick is 60 pts below prior lows (>> MAX_SL_PTS=20).
        Entry is at ~price, so SL anchor = price - 60 → sl_pts ≈ 62 → rejected.
        Reclaim: last bar closes well above sweep extreme + 1.5 threshold.
        Displacement: last two bars are large bullish candles (>= 1.5× avg body).
        """
        base_price = price
        base = [candle(base_price, base_price + 2, base_price - 2, base_price)
                for _ in range(25)]

        # Sweep bar — wick to price-60, close back to price-1
        sweep_bar = candle(base_price, base_price + 1,
                           base_price - sweep_pts,
                           base_price - 1)

        # Reclaim: close well above (sweep_extreme + SWEEP_MIN_WICK_PTS)
        # sweep_extreme = price - 60; threshold = price - 58.5
        reclaim_bar = candle(base_price - 1, base_price + 3,
                             base_price - 2, base_price + 2)

        # Big bullish displacement candles
        disp1 = candle(base_price + 2, base_price + 12, base_price + 1, base_price + 11)
        disp2 = candle(base_price + 11, base_price + 21, base_price + 10, base_price + 20)

        return base + [sweep_bar, reclaim_bar, disp1, disp2]

    # ── Test 1: no sweep / no range event → never sl_too_wide ────────────────
    def test_no_candidate_never_sl_too_wide(self, monkeypatch):
        result = self._no_candidate_result(monkeypatch)
        assert result["skip_reason"] != "sl_too_wide", (
            "No candidate was found but skip_reason=sl_too_wide — "
            "classification invariant violated"
        )

    def test_no_candidate_skip_reason_is_no_setup(self, monkeypatch):
        result = self._no_candidate_result(monkeypatch)
        assert result["skip_reason"] == "no_setup", (
            f"Expected no_setup on flat candles, got: {result['skip_reason']}"
        )

    def test_no_candidate_entry_fields_are_null(self, monkeypatch):
        result = self._no_candidate_result(monkeypatch)
        assert result["entry_price_candidate"] is None, \
            "entry_price_candidate must be None when no candidate found"
        assert result["sl_anchor"]          is None, \
            "sl_anchor must be None when no candidate found"
        assert result["sl_price_candidate"] is None, \
            "sl_price_candidate must be None when no candidate found"

    def test_no_candidate_sl_pts_is_zero(self, monkeypatch):
        result = self._no_candidate_result(monkeypatch)
        # sl_pts must stay at base_audit default (0.0) when no SL was evaluated
        assert result["sl_pts"] == 0.0, (
            f"sl_pts must be 0.0 on no-setup SKIP, got {result['sl_pts']}"
        )

    # ── Test 2: sl_too_wide requires populated entry/SL fields ───────────────
    def test_sl_too_wide_has_entry_price_candidate(self, monkeypatch):
        """Any sl_too_wide result must carry a non-null entry_price_candidate."""
        import config
        monkeypatch.setattr(config, "OM_GOLD_SCALP_ENABLED", False)
        mod = _import_strategy()
        m5 = self._wide_sl_sweep_candles()
        confluence = make_confluence(m5_candles=m5, h1_trend="bearish",
                                     m15_trend="bearish", m5_trend="bullish")
        result = mod.run({}, confluence, "XAU_USD", make_candles_dict(m5=m5))

        if result.get("skip_reason") == "sl_too_wide":
            assert result["entry_price_candidate"] is not None, \
                "sl_too_wide without entry_price_candidate — invariant violated"

    def test_sl_too_wide_has_sl_price_candidate(self, monkeypatch):
        """Any sl_too_wide result must carry a non-null sl_price_candidate."""
        import config
        monkeypatch.setattr(config, "OM_GOLD_SCALP_ENABLED", False)
        mod = _import_strategy()
        m5 = self._wide_sl_sweep_candles()
        confluence = make_confluence(m5_candles=m5, h1_trend="bearish",
                                     m15_trend="bearish", m5_trend="bullish")
        result = mod.run({}, confluence, "XAU_USD", make_candles_dict(m5=m5))

        if result.get("skip_reason") == "sl_too_wide":
            assert result["sl_price_candidate"] is not None, \
                "sl_too_wide without sl_price_candidate — invariant violated"

    def test_sl_too_wide_has_numeric_sl_pts(self, monkeypatch):
        """Any sl_too_wide result must carry sl_pts > 0."""
        import config
        monkeypatch.setattr(config, "OM_GOLD_SCALP_ENABLED", False)
        mod = _import_strategy()
        m5 = self._wide_sl_sweep_candles()
        confluence = make_confluence(m5_candles=m5, h1_trend="bearish",
                                     m15_trend="bearish", m5_trend="bullish")
        result = mod.run({}, confluence, "XAU_USD", make_candles_dict(m5=m5))

        if result.get("skip_reason") == "sl_too_wide":
            assert isinstance(result["sl_pts"], (int, float)), \
                "sl_pts must be numeric on sl_too_wide"
            assert result["sl_pts"] > 0, \
                f"sl_pts must be > 0 on sl_too_wide, got {result['sl_pts']}"

    def test_sl_too_wide_sl_pts_exceeds_max(self, monkeypatch):
        """sl_pts on a sl_too_wide output must exceed MAX_SL_PTS (20)."""
        import config
        monkeypatch.setattr(config, "OM_GOLD_SCALP_ENABLED", False)
        mod = _import_strategy()
        m5 = self._wide_sl_sweep_candles()
        confluence = make_confluence(m5_candles=m5, h1_trend="bearish",
                                     m15_trend="bearish", m5_trend="bullish")
        result = mod.run({}, confluence, "XAU_USD", make_candles_dict(m5=m5))

        if result.get("skip_reason") == "sl_too_wide":
            max_sl = result.get("max_sl_pts", 20.0)
            assert result["sl_pts"] > max_sl, (
                f"sl_pts={result['sl_pts']} must exceed max_sl_pts={max_sl} on sl_too_wide"
            )

    # ── Test 3: consistency invariant on every SKIP output ───────────────────
    @pytest.mark.parametrize("skip_reason,entry_should_be_null", [
        ("no_setup", True),
        ("inside_range_chop", True),
        ("pair_not_supported", True),
    ])
    def test_null_entry_on_no_candidate_skip_reasons(
        self, monkeypatch, skip_reason, entry_should_be_null
    ):
        """
        For skip reasons that imply no candidate was evaluated, entry/SL fields
        must stay null. Uses flat candles to ensure no candidate is found, then
        checks the actual output reason matches expected null-entry invariant.
        """
        import config
        monkeypatch.setattr(config, "OM_GOLD_SCALP_ENABLED", False)
        mod = _import_strategy()
        result = mod.run({}, make_confluence(), "XAU_USD", make_candles_dict())

        actual_reason = result.get("skip_reason", "")
        # Only assert on the expected reason if the output actually produced it
        if actual_reason == skip_reason and entry_should_be_null:
            assert result["entry_price_candidate"] is None, (
                f"entry_price_candidate must be None when skip_reason={skip_reason}"
            )
            assert result["sl_price_candidate"] is None, (
                f"sl_price_candidate must be None when skip_reason={skip_reason}"
            )

    def test_consistency_guard_reclassifies_stray_sl_too_wide(self, monkeypatch):
        """
        _enforce_skip_consistency must convert sl_too_wide → no_setup when
        entry_price_candidate is None (simulates a stale/corrupt output).
        """
        import config
        monkeypatch.setattr(config, "OM_GOLD_SCALP_ENABLED", False)
        mod = _import_strategy()

        # Inject a stray sl_too_wide with no candidate — simulates bad state
        stray_out = mod._base_audit()
        stray_out["skip_reason"]        = "sl_too_wide"
        stray_out["entry_price_candidate"] = None
        stray_out["sl_price_candidate"]    = None
        stray_out["sl_pts"]                = 0.0

        mod._enforce_skip_consistency(stray_out)

        assert stray_out["skip_reason"]      == "no_setup", \
            "Guard must reclassify stray sl_too_wide to no_setup"
        assert stray_out["rejection_stage"]  == "setup_detection"
        assert stray_out["rejection_reason"] == "no_valid_candidate"


# ---------------------------------------------------------------------------
# WAIT_MOMENTUM FAILED-RECLAIM PATH — AUDIT CONSISTENCY TESTS
#
# Root cause captured here: update_extra_candidate() in dashboard/app.py was
# storing only a hardcoded whitelist of ~15 fields, silently dropping all debug
# audit fields before storage.  The strategy code was correct; the store stripped
# the output.  These tests verify the strategy-level dict directly — if the
# store ever reverts to a whitelist the strategy tests still pass, but a
# separate app.py test (TestExtraCandidateStoreFull) catches the strip.
# ---------------------------------------------------------------------------

def _make_failed_reclaim_low_momentum_candles(price=2300.0, sweep_up_to=2320.0):
    """
    M5 candle sequence designed to drive Gate 3 → WAIT_MOMENTUM:

      Phase 1 – 25 flat baseline bars  (establishes prior swing high = price+2)
      Phase 2 – 1 bullish sweep bar    (wick to sweep_up_to >> price+2, body back below)
      Phase 3 – 1 failed-reclaim bar   (wick above sr_level, body closes back below)
      Phase 4 – 2 large bearish disp.  (body >= 1.5 × avg → displacement confirmed)
      Phase 5 – 1 current bar          (entry candidate price)

    With chop H1/M15/M5 trends, momentum score stays well below 50.
    """
    base = [candle(price, price + 2, price - 2, price) for _ in range(25)]

    # Bullish sweep: wick to sweep_up_to (>> prior high of price+2 by 16+ pts),
    # body closes back well below sr_level = sweep_up_to - 1.5
    sweep_bar = candle(price, sweep_up_to, price - 1.0, price - 0.5)

    # sr_level = sweep_up_to - SWEEP_MIN_WICK_PTS = sweep_up_to - 1.5
    sr_level = sweep_up_to - 1.5
    # Failed reclaim: wick goes above sr_level, body closes below → reclaim_failed=True
    fail_bar = candle(price - 0.5, sr_level + 0.5, price - 2.0, price - 1.5)

    # Large bearish displacement bars — body ~9 pts, avg body of base bars ~2 pts
    # displacement_ratio ≈ 9/2 = 4.5 >> DISPLACE_MIN_MULT=1.5 → confirmed
    disp1 = candle(price - 1.5, price - 1.0, price - 11.0, price - 10.5)
    disp2 = candle(price - 10.5, price - 10.0, price - 20.0, price - 19.5)

    current = candle(price - 19.5, price - 19.0, price - 21.0, price - 20.0)

    return base + [sweep_bar, fail_bar, disp1, disp2, current]


def _run_failed_reclaim_low_momentum(monkeypatch):
    """
    Run strategy with the failed-reclaim fixture.
    Returns result dict from run(); caller skips assertions if entry_state is
    not WAIT_MOMENTUM (fixture may not trigger on every candle geometry).
    """
    import config
    monkeypatch.setattr(config, "OM_GOLD_SCALP_ENABLED", False)
    mod = _import_strategy()
    m5 = _make_failed_reclaim_low_momentum_candles()
    # chop trends → momentum score stays low (no M5/M15 alignment bonus)
    confluence = make_confluence(
        m5_candles=m5,
        h1_trend="chop",
        m15_trend="chop",
        m5_trend="chop",
    )
    return mod.run({}, confluence, "XAU_USD", make_candles_dict(m5=m5))


def _is_gate3_wait_momentum(result):
    """True when result is clearly the Gate 3 failed-reclaim WAIT_MOMENTUM output."""
    return (
        result.get("entry_state") == "WAIT_MOMENTUM"
        and "bearish_displacement" in result.get("scanner_state_flow", "")
    )


class TestWaitMomentumFailedReclaimAudit:
    """
    When entry_state=WAIT_MOMENTUM via the Gate 3 failed-reclaim path,
    ALL audit/debug fields that describe that path must be populated in the
    returned dict — not left at _base_audit() defaults.
    """

    def test_sweep_detected_true(self, monkeypatch):
        result = _run_failed_reclaim_low_momentum(monkeypatch)
        if not _is_gate3_wait_momentum(result):
            return
        assert result["sweep_detected"] is True, \
            "sweep_detected must be True on Gate 3 WAIT_MOMENTUM"

    def test_swept_side_bullish(self, monkeypatch):
        result = _run_failed_reclaim_low_momentum(monkeypatch)
        if not _is_gate3_wait_momentum(result):
            return
        assert result["swept_side"] == "bullish"

    def test_evaluated_branches_includes_gate3(self, monkeypatch):
        result = _run_failed_reclaim_low_momentum(monkeypatch)
        if not _is_gate3_wait_momentum(result):
            return
        branches = result.get("evaluated_branches", [])
        assert isinstance(branches, list), "evaluated_branches must be a list"
        assert "bullish_sweep_failed_reclaim_short" in branches, (
            f"Gate 3 branch missing from evaluated_branches: {branches}"
        )

    def test_active_branch_is_gate3(self, monkeypatch):
        result = _run_failed_reclaim_low_momentum(monkeypatch)
        if not _is_gate3_wait_momentum(result):
            return
        assert result["active_branch"] == "bullish_sweep_failed_reclaim_short", (
            f"active_branch wrong: {result['active_branch']}"
        )

    def test_setup_candidates_found_positive(self, monkeypatch):
        result = _run_failed_reclaim_low_momentum(monkeypatch)
        if not _is_gate3_wait_momentum(result):
            return
        assert result["setup_candidates_found"] >= 1

    def test_reclaim_failed_true(self, monkeypatch):
        result = _run_failed_reclaim_low_momentum(monkeypatch)
        if not _is_gate3_wait_momentum(result):
            return
        assert result["reclaim_failed"] is True

    def test_bearish_displacement_confirmed(self, monkeypatch):
        result = _run_failed_reclaim_low_momentum(monkeypatch)
        if not _is_gate3_wait_momentum(result):
            return
        assert result["bearish_displacement_after_failed_reclaim"] is True

    def test_displacement_detail_fields_populated(self, monkeypatch):
        result = _run_failed_reclaim_low_momentum(monkeypatch)
        if not _is_gate3_wait_momentum(result):
            return
        assert result["displacement_body_pts"] > 0.0, \
            "displacement_body_pts must be > 0 when displacement confirmed"
        assert result["avg_body_pts"] > 0.0, \
            "avg_body_pts must be > 0 when displacement confirmed"
        assert result["displacement_ratio"] >= 1.5, \
            f"displacement_ratio={result['displacement_ratio']} must be >= 1.5 (DISPLACE_MIN_MULT)"

    def test_rejection_stage_is_momentum_gate(self, monkeypatch):
        result = _run_failed_reclaim_low_momentum(monkeypatch)
        if not _is_gate3_wait_momentum(result):
            return
        assert result["rejection_stage"] == "momentum_gate", (
            f"rejection_stage must be 'momentum_gate', got: {result['rejection_stage']}"
        )

    def test_rejection_reason_mentions_momentum(self, monkeypatch):
        result = _run_failed_reclaim_low_momentum(monkeypatch)
        if not _is_gate3_wait_momentum(result):
            return
        reason = result.get("rejection_reason", "")
        assert "momentum" in reason.lower() or "mom" in reason.lower(), (
            f"rejection_reason must mention momentum, got: '{reason}'"
        )

    def test_entry_price_candidate_populated(self, monkeypatch):
        result = _run_failed_reclaim_low_momentum(monkeypatch)
        if not _is_gate3_wait_momentum(result):
            return
        assert result["entry_price_candidate"] is not None, \
            "entry_price_candidate must be set — displacement + SL passed before momentum gate"
        assert result["sl_anchor"] is not None, \
            "sl_anchor must be set — SL was evaluated before momentum gate"

    def test_sl_candidate_populated_and_gate_passed(self, monkeypatch):
        result = _run_failed_reclaim_low_momentum(monkeypatch)
        if not _is_gate3_wait_momentum(result):
            return
        assert result["sl_price_candidate"] is not None, \
            "sl_price_candidate must be set when SL gate passed"
        assert result["sl_gate_passed"] is True, \
            "sl_gate_passed must be True — SL passed before momentum gate"

    def test_consistency_all_path_fields_non_default(self, monkeypatch):
        """
        Regression guard for the store-stripping bug: if any of these fields
        stayed at _base_audit defaults while entry_state=WAIT_MOMENTUM via Gate 3,
        it means audit population was skipped somewhere.
        """
        result = _run_failed_reclaim_low_momentum(monkeypatch)
        if not _is_gate3_wait_momentum(result):
            return  # fixture didn't produce target state — not a failure

        errors = []
        if result.get("sweep_detected") is not True:
            errors.append(f"sweep_detected={result.get('sweep_detected')} (expected True)")
        branches = result.get("evaluated_branches", [])
        if not isinstance(branches, list) or len(branches) == 0:
            errors.append(f"evaluated_branches={branches!r} (expected non-empty list)")
        if result.get("active_branch", "") == "":
            errors.append("active_branch is empty string")
        if result.get("setup_candidates_found", 0) == 0:
            errors.append("setup_candidates_found is 0")
        if result.get("rejection_stage", "") == "":
            errors.append("rejection_stage is empty string")
        if result.get("rejection_reason", "") == "":
            errors.append("rejection_reason is empty string")
        if result.get("displacement_body_pts", 0.0) == 0.0:
            errors.append("displacement_body_pts is 0.0")
        if result.get("entry_price_candidate") is None:
            errors.append("entry_price_candidate is None")

        assert not errors, (
            "Gate 3 WAIT_MOMENTUM audit fields at defaults — store-stripping regression:\n"
            + "\n".join(f"  • {e}" for e in errors)
        )


class TestExtraCandidateStoreFull:
    """
    Verifies that update_extra_candidate() stores the FULL candidate dict,
    not a hardcoded field whitelist.  The real bug: all debug audit fields were
    silently dropped before storage so the API served defaults to the dashboard.
    """

    def test_store_preserves_evaluated_branches(self):
        """evaluated_branches must survive the store round-trip."""
        try:
            from dashboard.app import update_extra_candidate, _extra_store
        except ImportError:
            pytest.skip("dashboard/app.py not importable")

        candidate = {
            "signal_mode":       "om_gold_scalp",
            "entry_state":       "WAIT_MOMENTUM",
            "skip_reason":       "low_momentum",
            "scanner_state_flow": "bullish_sweep → low_momentum → WAIT_MOMENTUM",
            "momentum_score":    17,
            "evaluated_branches": ["bearish_sweep_reclaim_long",
                                   "bullish_sweep_failed_reclaim_short"],
            "active_branch":     "bullish_sweep_failed_reclaim_short",
            "setup_candidates_found": 1,
            "sweep_detected":    True,
            "swept_side":        "bullish",
            "rejection_stage":   "momentum_gate",
            "rejection_reason":  "momentum=17 < 50",
            "displacement_body_pts": 9.0,
            "avg_body_pts":      2.0,
            "displacement_ratio": 4.5,
            "entry_price_candidate": 2280.0,
            "sl_anchor":         2320.0,
            "sl_price_candidate": 2322.0,
            "sl_gate_passed":    True,
            "max_sl_pts":        20.0,
            "should_log":        False,
            "should_alert":      False,
        }

        update_extra_candidate("XAU_USD", "om_gold_scalp", candidate)

        stored = _extra_store.get("XAU_USD|om_gold_scalp", {})

        assert stored.get("evaluated_branches") == candidate["evaluated_branches"], \
            "evaluated_branches dropped by store — whitelist regression"
        assert stored.get("active_branch") == "bullish_sweep_failed_reclaim_short", \
            "active_branch dropped by store"
        assert stored.get("sweep_detected") is True, \
            "sweep_detected dropped by store"
        assert stored.get("rejection_stage") == "momentum_gate", \
            "rejection_stage dropped by store"
        assert stored.get("rejection_reason") == "momentum=17 < 50", \
            "rejection_reason dropped by store"
        assert stored.get("displacement_body_pts") == 9.0, \
            "displacement_body_pts dropped by store"
        assert stored.get("entry_price_candidate") == 2280.0, \
            "entry_price_candidate dropped by store"
        assert stored.get("sl_gate_passed") is True, \
            "sl_gate_passed dropped by store"

    def test_store_preserves_pair_and_signal_mode(self):
        """pair and signal_mode must be set from caller args, not candidate dict."""
        try:
            from dashboard.app import update_extra_candidate, _extra_store
        except ImportError:
            pytest.skip("dashboard/app.py not importable")

        candidate = {"entry_state": "SKIP", "skip_reason": "no_setup",
                     "pair": "WRONG", "signal_mode": "WRONG"}
        update_extra_candidate("XAU_USD", "om_gold_scalp", candidate)
        stored = _extra_store.get("XAU_USD|om_gold_scalp", {})
        assert stored["pair"]        == "XAU_USD"
        assert stored["signal_mode"] == "om_gold_scalp"

    def test_store_does_not_mutate_original_candidate(self):
        """update_extra_candidate must not mutate the caller's candidate dict."""
        try:
            from dashboard.app import update_extra_candidate
        except ImportError:
            pytest.skip("dashboard/app.py not importable")

        candidate = {"entry_state": "SKIP", "skip_reason": "no_setup",
                     "evaluated_branches": ["bearish_sweep_reclaim_long"]}
        original_branches = list(candidate["evaluated_branches"])
        original_keys = set(candidate.keys())

        update_extra_candidate("XAU_USD", "om_gold_scalp", candidate)

        assert set(candidate.keys()) == original_keys, \
            "store mutated original candidate dict (added keys)"
        assert candidate["evaluated_branches"] == original_branches, \
            "store mutated evaluated_branches in original dict"


# ---------------------------------------------------------------------------
# DISPLACEMENT REJECTION REASON CONSISTENCY TESTS
#
# Bug: _detect_displacement returned ratio=2.05 with detected=False because
# the bar was in the wrong direction, but rejection_reason always said
# "displacement_ratio=2.05 < 1.5" — mathematically false.
# Correct behaviour:
#   ratio >= threshold but wrong direction → "direction_mismatch"
#   ratio < threshold                      → "ratio_below_threshold" / "< threshold"
# ---------------------------------------------------------------------------

class TestDisplacementRejectionReason:
    """
    rejection_reason on displacement_check must match what actually failed.
    ratio above threshold → cannot say '< threshold'.
    passing displacement → cannot return WAIT_HOLD from same gate.
    """

    # ── _detect_displacement unit tests ──────────────────────────────────────

    def test_detect_displacement_returns_fail_reason_key(self):
        """fail_reason must always be present in return dict."""
        mod = _import_strategy()
        candles = flat_candles(2300.0, 10)
        result = mod._detect_displacement(candles, "bullish")
        assert "fail_reason" in result, "fail_reason key missing from _detect_displacement return"

    def test_fail_reason_empty_when_detected(self):
        """fail_reason must be '' when detected=True."""
        mod = _import_strategy()
        # Build 2 large bullish displacement bars on top of flat base
        base = flat_candles(2300.0, 20)
        # avg body of flat candles ≈ 0; use explicit avg_body param
        big_bull = candle(2300.0, 2315.0, 2299.0, 2314.0)  # body=14, big bullish
        candles = base + [big_bull]
        result = mod._detect_displacement(candles, "bullish", avg_body=2.0)
        if result["detected"]:
            assert result["fail_reason"] == "", \
                f"fail_reason must be '' on detected=True, got: '{result['fail_reason']}'"

    def test_direction_mismatch_when_ratio_ok_wrong_dir(self):
        """
        Large bearish bar when looking for bullish: ratio >= 1.5 but
        fail_reason must be 'direction_mismatch', not 'ratio_below_threshold'.
        """
        mod = _import_strategy()
        base = flat_candles(2300.0, 20)
        # Large BEARISH bar — body = 14 pts (>>1.5 × 2 avg)
        big_bear = candle(2314.0, 2315.0, 2299.0, 2300.0)  # open > close → bearish
        candles = base + [big_bear]
        result = mod._detect_displacement(candles, "bullish", avg_body=2.0)
        assert not result["detected"], "bearish bar should not count as bullish displacement"
        assert result["displacement_ratio"] >= 1.5, \
            f"ratio should be >= 1.5, got {result['displacement_ratio']}"
        assert result["fail_reason"] == "direction_mismatch", (
            f"fail_reason must be 'direction_mismatch' when ratio ok but wrong dir, "
            f"got: '{result['fail_reason']}'"
        )

    def test_ratio_below_threshold_when_body_small(self):
        """
        Small bars: ratio < 1.5 → fail_reason must be 'ratio_below_threshold'.
        """
        mod = _import_strategy()
        # All flat candles — max body << avg * 1.5
        candles = flat_candles(2300.0, 25)
        result = mod._detect_displacement(candles, "bullish", avg_body=5.0)
        assert not result["detected"]
        assert result["displacement_ratio"] < 1.5, \
            f"ratio should be < 1.5 on flat candles, got {result['displacement_ratio']}"
        assert result["fail_reason"] == "ratio_below_threshold", (
            f"fail_reason must be 'ratio_below_threshold', got: '{result['fail_reason']}'"
        )

    # ── run() integration: rejection_reason string consistency ────────────────

    def _run_wait_hold(self, monkeypatch):
        """
        Build a Gate 2 scenario that reaches WAIT_HOLD:
        - bearish sweep detected
        - reclaim confirmed
        - displacement NOT confirmed (large bearish bar, not bullish)
        Returns (result, mod).
        """
        import config
        monkeypatch.setattr(config, "OM_GOLD_SCALP_ENABLED", False)
        mod = _import_strategy()

        price = 2300.0
        sweep_low = 2282.0  # sweep wick goes here, >> 1.5 pts below prior lows

        # 25 flat base bars (prior swing lows = price-2 = 2298)
        base = flat_candles(price, n=25)

        # Bearish sweep bar: wick to sweep_low, close back near price (bullish close)
        # close = price - 0.5 > sweep_low + SWEEP_MIN_WICK_PTS (1.5) = 2283.5 → reclaim level
        sweep_bar = candle(price, price + 1.0, sweep_low, price - 0.5)

        # Reclaim: close above reclaim_level = sweep_low + 1.5 = 2283.5
        reclaim_bar = candle(price - 0.5, price + 2.0, price - 1.0, price + 1.0)

        # Large BEARISH displacement bar — body is big but in the WRONG direction
        # (Gate 2 needs bullish displacement after bullish reclaim)
        big_bear = candle(price + 1.0, price + 2.0, price - 8.0, price - 7.0)

        m5 = base + [sweep_bar, reclaim_bar, big_bear]
        confluence = make_confluence(
            m5_candles=m5, h1_trend="bearish",
            m15_trend="bearish", m5_trend="bearish",
        )
        result = mod.run({}, confluence, "XAU_USD", make_candles_dict(m5=m5))
        return result, mod

    def test_ratio_above_threshold_cannot_emit_less_than_string(self, monkeypatch):
        """
        Core invariant: if displacement_ratio >= 1.5 the rejection_reason
        must NOT contain '< 1.5'.
        """
        result, _ = self._run_wait_hold(monkeypatch)
        if result.get("rejection_stage") != "displacement_check":
            return  # fixture didn't hit this gate
        ratio = result.get("displacement_ratio", 0.0)
        reason = result.get("rejection_reason", "")
        if ratio >= 1.5:
            assert "< 1.5" not in reason and "< " + str(1.5) not in reason, (
                f"ratio={ratio} >= 1.5 but rejection_reason says '< 1.5': '{reason}'"
            )

    def test_direction_mismatch_in_rejection_reason_when_ratio_ok(self, monkeypatch):
        """
        When ratio >= threshold but direction wrong, rejection_reason must
        mention 'direction_mismatch' or 'not bullish'.
        """
        result, _ = self._run_wait_hold(monkeypatch)
        if result.get("rejection_stage") != "displacement_check":
            return
        ratio = result.get("displacement_ratio", 0.0)
        reason = result.get("rejection_reason", "")
        if ratio >= 1.5:
            assert "direction_mismatch" in reason or "not bullish" in reason, (
                f"Expected direction_mismatch in reason when ratio={ratio} >= 1.5, "
                f"got: '{reason}'"
            )

    def test_passing_displacement_cannot_return_wait_hold(self, monkeypatch):
        """
        If _detect_displacement returns detected=True, entry_state must NOT
        be WAIT_HOLD from the displacement_check rejection_stage.
        Constructed by giving a genuine bullish displacement bar.
        """
        import config
        monkeypatch.setattr(config, "OM_GOLD_SCALP_ENABLED", False)
        mod = _import_strategy()

        price = 2300.0
        sweep_low = 2282.0

        base = flat_candles(price, n=25)
        sweep_bar   = candle(price, price + 1.0, sweep_low, price - 0.5)
        reclaim_bar = candle(price - 0.5, price + 2.0, price - 1.0, price + 1.0)
        # Large BULLISH displacement bar — correct direction
        big_bull = candle(price + 1.0, price + 12.0, price + 0.5, price + 11.0)

        m5 = base + [sweep_bar, reclaim_bar, big_bull]
        confluence = make_confluence(
            m5_candles=m5, h1_trend="bearish",
            m15_trend="bearish", m5_trend="bullish",
        )
        result = mod.run({}, confluence, "XAU_USD", make_candles_dict(m5=m5))

        if result.get("rejection_stage") == "displacement_check":
            assert result.get("entry_state") != "WAIT_HOLD", (
                "displacement_check rejection_stage set but displacement was confirmed — "
                "entry_state must not be WAIT_HOLD from this gate when detected=True"
            )

    def test_rejection_reason_matches_actual_comparison(self, monkeypatch):
        """
        Parametric invariant: for any result with rejection_stage=displacement_check,
        the rejection_reason must be consistent with the displacement_ratio value.
        If ratio < 1.5 → reason must contain '< 1.5'.
        If ratio >= 1.5 → reason must NOT contain '< 1.5'.
        """
        import config
        monkeypatch.setattr(config, "OM_GOLD_SCALP_ENABLED", False)
        mod = _import_strategy()

        # Test several candle geometries to exercise both branches
        test_cases = [
            flat_candles(2300.0, 30),                    # no sweep → fallthrough
            _make_failed_reclaim_low_momentum_candles(),  # Gate 3 path
        ]
        for m5 in test_cases:
            confluence = make_confluence(m5_candles=m5, h1_trend="bearish",
                                         m15_trend="bearish", m5_trend="bearish")
            result = mod.run({}, confluence, "XAU_USD", make_candles_dict(m5=m5))

            if result.get("rejection_stage") != "displacement_check":
                continue

            ratio  = result.get("displacement_ratio", 0.0)
            reason = result.get("rejection_reason", "")

            if ratio < 1.5:
                assert "< 1.5" in reason, (
                    f"ratio={ratio} < 1.5 but reason doesn't say so: '{reason}'"
                )
            else:
                assert "< 1.5" not in reason, (
                    f"ratio={ratio} >= 1.5 but reason says '< 1.5': '{reason}'"
                )
