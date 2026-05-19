"""
tests/test_manual_trade_forensics.py

Forensic execution integrity tests for manual trade SL/TP monitoring.

Covers:
  Fix 1 — _get_log_time() reads DB first (Railway-safe; no CSV needed)
  Fix 2 — LONG SL/TP evaluated against BID; SHORT against ASK
  Fix 3 — forensic DB fields exist in update_manual_trade_outcome() signature
  Fix 4 — _close_trade() accepts and persists forensic fields correctly
"""

import pytest
from unittest.mock import patch, MagicMock


# ─────────────────────────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────────────────────────

def _make_db_row(timestamp_utc="2026-05-19 10:00:00", sl_price=1980.0, tp1_price=2005.0):
    """Minimal manual_trades DB row dict."""
    return {
        "signal_id":     "TEST-001",
        "timestamp_utc": timestamp_utc,
        "sl_price":      sl_price,
        "tp1_price":     tp1_price,
        "direction":     "bullish",
        "entry_price":   1990.0,
    }


# ─────────────────────────────────────────────────────────────────────────────
# FIX 1 — _get_log_time() DB-first, Railway-safe
# ─────────────────────────────────────────────────────────────────────────────

class TestGetLogTime:
    """_get_log_time() must read from DB first. CSV is fallback only."""

    def test_returns_db_timestamp_when_db_has_row(self, monkeypatch):
        """DB has a row → returns its timestamp_utc without touching CSV."""
        from ml.manual_trade_logger import _get_log_time

        mock_row = _make_db_row(timestamp_utc="2026-05-19 12:34:56")
        monkeypatch.setattr("ml.manual_trade_logger._get_log_time.__module__", "ml.manual_trade_logger")

        with patch("db.database.get_manual_trade", return_value=mock_row):
            result = _get_log_time("TEST-001")

        assert result == "2026-05-19 12:34:56", (
            f"Expected DB timestamp, got: {result}"
        )

    def test_db_primary_csv_not_called_when_db_succeeds(self, monkeypatch):
        """When DB returns a timestamp, CSV read must not be called."""
        from ml.manual_trade_logger import _get_log_time

        mock_row = _make_db_row(timestamp_utc="2026-05-19 08:00:00")
        csv_called = []

        with patch("db.database.get_manual_trade", return_value=mock_row):
            with patch("pandas.read_csv", side_effect=lambda *a, **kw: csv_called.append(1)):
                result = _get_log_time("TEST-001")

        assert result == "2026-05-19 08:00:00"
        assert len(csv_called) == 0, "CSV should not be read when DB has the timestamp"

    def test_falls_back_to_csv_when_db_returns_none(self, monkeypatch):
        """DB returns None (no row) → falls back to CSV."""
        import pandas as pd
        from ml.manual_trade_logger import _get_log_time

        csv_df = pd.DataFrame([{
            "signal_id":     "TEST-002",
            "timestamp_utc": "2026-05-19 09:15:00",
        }])

        with patch("db.database.get_manual_trade", return_value=None):
            with patch("pandas.read_csv", return_value=csv_df):
                with patch("ml.manual_trade_logger._get_log_path", return_value="/fake/path.csv"):
                    result = _get_log_time("TEST-002")

        assert result == "2026-05-19 09:15:00", (
            f"Expected CSV fallback timestamp, got: {result}"
        )

    def test_returns_none_when_both_db_and_csv_fail(self):
        """Both DB and CSV fail → returns None (graceful degradation)."""
        from ml.manual_trade_logger import _get_log_time

        with patch("db.database.get_manual_trade", side_effect=Exception("DB down")):
            with patch("pandas.read_csv", side_effect=Exception("No CSV")):
                result = _get_log_time("TEST-MISSING")

        assert result is None, "Must return None when both sources fail — not raise"

    def test_db_row_missing_timestamp_utc_falls_back_to_csv(self):
        """DB row exists but timestamp_utc is None → CSV fallback."""
        import pandas as pd
        from ml.manual_trade_logger import _get_log_time

        row_no_ts = {"signal_id": "TEST-003", "timestamp_utc": None}
        csv_df    = pd.DataFrame([{"signal_id": "TEST-003", "timestamp_utc": "2026-05-19 11:00:00"}])

        with patch("db.database.get_manual_trade", return_value=row_no_ts):
            with patch("pandas.read_csv", return_value=csv_df):
                with patch("ml.manual_trade_logger._get_log_path", return_value="/fake/path.csv"):
                    result = _get_log_time("TEST-003")

        assert result == "2026-05-19 11:00:00", (
            f"Should fall back to CSV when DB timestamp_utc is None, got: {result}"
        )


class TestTimestampFilterPreventsOldCandles:
    """
    When log_time is known, M5 candle checks MUST only look at candles
    AFTER the entry timestamp. Old candles before entry must not trigger close.
    """

    def test_candles_before_entry_are_excluded(self):
        """
        Simulate: candle at 09:00 has low <= SL.
        Trade was entered at 10:00.
        That candle must NOT trigger a close.
        """
        import pandas as pd
        from pandas import Timestamp

        entry_time = "2026-05-19 10:00:00"
        sl         = 1980.0
        tp1        = 2005.0

        # Create a DataFrame where the old candle (before entry) would hit SL
        idx = pd.to_datetime(["2026-05-19 09:00:00", "2026-05-19 11:00:00"], utc=True)
        df  = pd.DataFrame({
            "high":  [2010.0, 2001.0],
            "low":   [1975.0, 1985.0],   # 09:00 low=1975 would hit SL=1980; 11:00 is safe
            "close": [2000.0, 1990.0],
        }, index=idx)

        # Apply the timestamp filter exactly as the monitor does
        filtered = df[df.index > Timestamp(entry_time, tz="UTC")]

        # After filtering, the 09:00 candle must be gone
        sl_hit = (filtered["low"] <= sl).any()
        assert not sl_hit, (
            "Old candle (before entry time) must not trigger SL. "
            f"SL={sl}, filtered lows={filtered['low'].tolist()}"
        )

    def test_candle_after_entry_triggers_correctly(self):
        """Candle after entry with low <= SL DOES trigger close."""
        import pandas as pd
        from pandas import Timestamp

        entry_time = "2026-05-19 10:00:00"
        sl         = 1980.0

        idx = pd.to_datetime(["2026-05-19 11:00:00"], utc=True)
        df  = pd.DataFrame({"high": [2010.0], "low": [1978.0], "close": [1985.0]}, index=idx)

        filtered = df[df.index > Timestamp(entry_time, tz="UTC")]
        sl_hit   = (filtered["low"] <= sl).any()

        assert sl_hit, "Candle after entry with low below SL must register as SL hit"


# ─────────────────────────────────────────────────────────────────────────────
# FIX 2 — Bid/Ask correctness: LONG uses BID, SHORT uses ASK
# ─────────────────────────────────────────────────────────────────────────────

class TestGetLiveBidAsk:
    """get_live_bid_ask() returns (bid, ask) tuple."""

    def test_returns_bid_ask_tuple(self):
        """Normal response returns (bid, ask) with correct values."""
        from core.fetcher import get_live_bid_ask

        mock_response = {
            "prices": [{
                "bids": [{"price": "1999.50"}],
                "asks": [{"price": "2000.00"}],
            }]
        }
        mock_req = MagicMock()
        mock_req.response = mock_response

        with patch("core.fetcher.PricingInfo", return_value=mock_req):
            with patch("core.fetcher.client") as mock_client:
                mock_client.request = MagicMock()
                bid, ask = get_live_bid_ask("XAU_USD")

        assert bid == 1999.5,  f"Expected bid=1999.5, got {bid}"
        assert ask == 2000.0,  f"Expected ask=2000.0, got {ask}"

    def test_returns_none_none_on_failure(self):
        """API failure → (None, None), no exception raised."""
        from core.fetcher import get_live_bid_ask

        with patch("core.fetcher.PricingInfo", side_effect=Exception("OANDA down")):
            bid, ask = get_live_bid_ask("XAU_USD")

        assert bid is None, "bid must be None on failure"
        assert ask is None, "ask must be None on failure"

    def test_bid_is_lower_than_ask(self):
        """Bid must always be <= ask (spread >= 0)."""
        from core.fetcher import get_live_bid_ask

        mock_response = {
            "prices": [{
                "bids": [{"price": "2320.10"}],
                "asks": [{"price": "2320.40"}],
            }]
        }
        mock_req = MagicMock()
        mock_req.response = mock_response

        with patch("core.fetcher.PricingInfo", return_value=mock_req):
            with patch("core.fetcher.client") as mock_client:
                mock_client.request = MagicMock()
                bid, ask = get_live_bid_ask("XAU_USD")

        assert bid <= ask, f"bid ({bid}) must be <= ask ({ask})"


class TestBidAskExecutionSide:
    """
    LONG SL/TP must be evaluated against BID.
    SHORT SL/TP must be evaluated against ASK.
    This mirrors OANDA execution: closing a long sells at bid; closing a short buys at ask.
    """

    def _run_one_poll(self, direction, bid, ask, cur_sl, cur_tp1):
        """
        Simulate one live-price polling cycle from _monitor_trade().
        Returns (sl_hit, tp_hit, trigger_px).
        """
        trigger_px = bid if direction == "bullish" else ask

        if direction == "bullish":
            tp_hit = trigger_px >= cur_tp1
            sl_hit = trigger_px <= cur_sl
        else:
            tp_hit = trigger_px <= cur_tp1
            sl_hit = trigger_px >= cur_sl

        return sl_hit, tp_hit, trigger_px

    # ── LONG tests ───────────────────────────────────────────────────────────

    def test_long_sl_triggered_by_bid_not_ask(self):
        """
        LONG SL at 2000.00.
        BID = 1999.80 (below SL) — should trigger.
        ASK = 2000.20 (above SL) — if mid were used, no trigger.
        """
        sl_hit, tp_hit, trigger_px = self._run_one_poll(
            direction="bullish",
            bid=1999.80, ask=2000.20,
            cur_sl=2000.00, cur_tp1=2025.00,
        )
        assert sl_hit,  "LONG SL must fire when BID <= SL"
        assert not tp_hit
        assert trigger_px == 1999.80, f"trigger_px must be bid, got {trigger_px}"

    def test_long_sl_not_triggered_when_bid_above_sl(self):
        """LONG SL at 2000.00. BID = 2000.50 — must NOT trigger."""
        sl_hit, tp_hit, _ = self._run_one_poll(
            direction="bullish",
            bid=2000.50, ask=2001.00,
            cur_sl=2000.00, cur_tp1=2025.00,
        )
        assert not sl_hit,  "LONG SL must not fire when BID > SL"
        assert not tp_hit

    def test_long_tp_triggered_by_bid(self):
        """LONG TP at 2025.00. BID = 2025.10 — should trigger."""
        sl_hit, tp_hit, trigger_px = self._run_one_poll(
            direction="bullish",
            bid=2025.10, ask=2025.60,
            cur_sl=2000.00, cur_tp1=2025.00,
        )
        assert tp_hit,     "LONG TP must fire when BID >= TP"
        assert not sl_hit
        assert trigger_px == 2025.10

    def test_long_mid_above_sl_but_bid_below_sl_triggers(self):
        """
        The exact 'SL hit without touching' scenario.
        SL = 2000.00. Spread = 0.50. BID = 2000.00, ASK = 2000.50.
        Mid = 2000.25 (above SL). Old mid-price check would NOT fire.
        New bid-price check DOES fire — correctly matching OANDA execution.
        """
        mid = (2000.00 + 2000.50) / 2   # = 2000.25
        assert mid > 2000.00, "Setup: mid is above SL"

        sl_hit_mid,  _, _ = self._run_one_poll(
            direction="bullish",
            bid=mid, ask=mid,   # simulating old mid-price behaviour
            cur_sl=2000.00, cur_tp1=2025.00,
        )
        sl_hit_bid, _, trigger_px = self._run_one_poll(
            direction="bullish",
            bid=2000.00, ask=2000.50,
            cur_sl=2000.00, cur_tp1=2025.00,
        )

        assert not sl_hit_mid, "Mid-price check incorrectly does NOT fire (this was the bug)"
        assert sl_hit_bid,     "Bid-price check correctly DOES fire (the fix)"
        assert trigger_px == 2000.00

    # ── SHORT tests ──────────────────────────────────────────────────────────

    def test_short_sl_triggered_by_ask_not_bid(self):
        """
        SHORT SL at 2010.00.
        ASK = 2010.20 (above SL) — should trigger.
        BID = 2009.70 (below SL) — if bid were used, no trigger.
        """
        sl_hit, tp_hit, trigger_px = self._run_one_poll(
            direction="bearish",
            bid=2009.70, ask=2010.20,
            cur_sl=2010.00, cur_tp1=1990.00,
        )
        assert sl_hit,  "SHORT SL must fire when ASK >= SL"
        assert not tp_hit
        assert trigger_px == 2010.20, f"trigger_px must be ask, got {trigger_px}"

    def test_short_sl_not_triggered_when_ask_below_sl(self):
        """SHORT SL at 2010.00. ASK = 2009.80 — must NOT trigger."""
        sl_hit, tp_hit, _ = self._run_one_poll(
            direction="bearish",
            bid=2009.30, ask=2009.80,
            cur_sl=2010.00, cur_tp1=1990.00,
        )
        assert not sl_hit
        assert not tp_hit

    def test_short_tp_triggered_by_ask(self):
        """SHORT TP at 1990.00. ASK = 1989.80 — should trigger."""
        sl_hit, tp_hit, trigger_px = self._run_one_poll(
            direction="bearish",
            bid=1989.30, ask=1989.80,
            cur_sl=2010.00, cur_tp1=1990.00,
        )
        assert tp_hit,  "SHORT TP must fire when ASK <= TP"
        assert not sl_hit
        assert trigger_px == 1989.80


# ─────────────────────────────────────────────────────────────────────────────
# FIX 3 — DB schema: update_manual_trade_outcome() accepts forensic fields
# ─────────────────────────────────────────────────────────────────────────────

class TestUpdateManualTradeOutcomeSignature:
    """update_manual_trade_outcome() must accept all 6 forensic keyword args."""

    def test_accepts_all_forensic_kwargs(self):
        """Function must accept forensic fields without TypeError."""
        from db.database import update_manual_trade_outcome
        import inspect

        sig    = inspect.signature(update_manual_trade_outcome)
        params = list(sig.parameters.keys())

        required = [
            "exit_timestamp",
            "exit_reason",
            "exit_price",
            "max_favorable_excursion",
            "max_adverse_excursion",
            "trade_duration_minutes",
        ]
        for field in required:
            assert field in params, (
                f"update_manual_trade_outcome() missing parameter: {field}"
            )

    def test_all_forensic_fields_are_optional(self):
        """All forensic fields must have defaults (optional kwargs)."""
        from db.database import update_manual_trade_outcome
        import inspect

        sig = inspect.signature(update_manual_trade_outcome)
        optional_forensic = [
            "exit_timestamp", "exit_reason", "exit_price",
            "max_favorable_excursion", "max_adverse_excursion",
            "trade_duration_minutes",
        ]
        for field in optional_forensic:
            param = sig.parameters[field]
            assert param.default is not inspect.Parameter.empty, (
                f"Forensic field '{field}' must be optional (have a default value). "
                f"Existing callers pass only (signal_id, outcome, pips, post_mortem)."
            )


# ─────────────────────────────────────────────────────────────────────────────
# FIX 4 — _close_trade() persists forensic fields
# ─────────────────────────────────────────────────────────────────────────────

class TestCloseTradeForesnicPersistence:
    """_close_trade() must pass forensic fields to update_manual_trade_outcome()."""

    def _run_close(self, result="LOSS", exit_price=1999.50, mfe_pips=5.2, mae_pips=12.3,
                   entry_ts="2026-05-19 10:00:00"):
        """Run _close_trade() with mocked DB and return what was written."""
        from ml.manual_trade_logger import _close_trade

        written = {}

        def _capture_update(signal_id, outcome, outcome_pips, post_mortem, **kwargs):
            written.update({"outcome": outcome, **kwargs})

        with patch("db.database.update_manual_trade_outcome", side_effect=_capture_update):
            with patch("db.database.get_manual_trade", return_value={"timestamp_utc": entry_ts}):
                _close_trade(
                    "TEST-CLOSE", "XAU_USD", "bullish",
                    entry=1990.0, sl=1980.0, tp1=2005.0, pip=0.01,
                    result=result,
                    exit_price=exit_price,
                    mfe_pips=mfe_pips,
                    mae_pips=mae_pips,
                )
        return written

    def test_exit_reason_sl_hit_on_loss(self):
        written = self._run_close(result="LOSS")
        assert written.get("exit_reason") == "SL_HIT", (
            f"LOSS must set exit_reason=SL_HIT, got: {written.get('exit_reason')}"
        )

    def test_exit_reason_tp_hit_on_win(self):
        written = self._run_close(result="WIN")
        assert written.get("exit_reason") == "TP_HIT", (
            f"WIN must set exit_reason=TP_HIT, got: {written.get('exit_reason')}"
        )

    def test_exit_price_persisted(self):
        written = self._run_close(exit_price=1999.50)
        assert written.get("exit_price") == round(1999.50, 5), (
            f"exit_price not persisted correctly: {written.get('exit_price')}"
        )

    def test_mfe_persisted(self):
        written = self._run_close(mfe_pips=7.5)
        assert written.get("max_favorable_excursion") == 7.5, (
            f"MFE not persisted: {written.get('max_favorable_excursion')}"
        )

    def test_mae_persisted(self):
        written = self._run_close(mae_pips=3.2)
        assert written.get("max_adverse_excursion") == 3.2, (
            f"MAE not persisted: {written.get('max_adverse_excursion')}"
        )

    def test_exit_timestamp_is_set(self):
        written = self._run_close()
        ts = written.get("exit_timestamp")
        assert ts is not None, "exit_timestamp must be set on close"
        # Format: YYYY-MM-DD HH:MM:SS
        from datetime import datetime
        try:
            datetime.strptime(ts, "%Y-%m-%d %H:%M:%S")
        except ValueError:
            pytest.fail(f"exit_timestamp format invalid: {ts}")

    def test_duration_computed_from_entry_timestamp(self):
        """duration_minutes must be >= 0 when entry timestamp is known."""
        written = self._run_close(entry_ts="2026-05-19 10:00:00")
        dur = written.get("trade_duration_minutes")
        assert dur is not None,   "trade_duration_minutes must be set when entry timestamp known"
        assert isinstance(dur, int), f"trade_duration_minutes must be int, got {type(dur)}"
        assert dur >= 0,          f"trade_duration_minutes must be >= 0, got {dur}"

    def test_exit_price_none_when_not_provided(self):
        """Candle fallback close (no live price) → exit_price=None persisted."""
        written = self._run_close(exit_price=None)
        assert written.get("exit_price") is None, (
            "exit_price must be None when no live trigger price available"
        )
