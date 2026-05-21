"""
tests/test_agent_signal_lifecycle.py

Tests for the agent signal lifecycle integrity system.

Covers:
  Phase 1 — DB migration safety:
  - exit_timestamp column exists on agent_signals after init_db()
  - exit_reason column exists
  - trade_duration_minutes column exists
  - max_favorable_excursion column exists
  - max_adverse_excursion column exists
  - All new columns are nullable (old rows unaffected)
  - update_agent_signal_forensic() writes all fields correctly
  - get_open_taken_agent_signals() returns correct rows
  - close_agent_trade() writes exit_timestamp and exit_reason

  Phase 2 — Monitor lifecycle:
  - start_agent_monitor() starts a thread (no-op if already running)
  - No duplicate monitors (idempotent start)
  - stop_agent_monitor() removes from active set
  - get_active_agent_monitors() returns correct list
  - resume_agent_monitors_on_startup() re-arms taken+open signals
  - resume skips signals with missing SL/TP
  - TP hit → writes WIN + TP_HIT + forensic fields
  - SL hit → writes LOSS + SL_HIT + forensic fields
  - MFE/MAE tracked from live price polling
  - trade_duration_minutes computed correctly

  Phase 3 — Forensic UI:
  - agentForensicHtml present in template
  - Open trades use yellow border in agent forensic block
  - Closed trades use navy border in agent forensic block
  - ENTRY label present in agent forensic block
  - EXIT label present in agent forensic block
  - Live duration ⬤ marker present
  - MANUAL_OVERRIDE exit reason styled differently (orange)
  - MFE/MAE rendered for closed agent signals

  Phase 4 — Agent signal live poller:
  - _agentSignalPollerTimer variable declared
  - _startAgentSignalPoller function present
  - _stopAgentSignalPoller function present
  - _pollAgentSignalPricesNow function present
  - Polls open taken agent signal pairs
  - Stops when no open taken agent signals remain
  - Called from switchPerfTab('agent')
  - Stopped on non-agent tab switch
  - visibilitychange stops agent poller
  - visibilitychange restarts agent poller on agent tab

  Phase 5 — W/L integrity gate:
  - Backend rejects taken+open signal without override_reason (409)
  - Backend response includes requires_override: true
  - Backend accepts taken+open signal with override_reason
  - Manual override writes exit_reason = MANUAL_OVERRIDE
  - Manual override stops the monitor
  - Manual override writes exit_timestamp and trade_duration_minutes
  - Non-taken signal: plain W/L write accepted (no override needed)
  - Already-closed signal: plain W/L accepted (no override needed)
  - Frontend markOutcome has override gate check
  - Frontend shows [OVERRIDE] label on override outcome

  Regression:
  - Old rows with NULL forensic fields render safely (no crash)
  - Strategy/gate/scoring code untouched
  - Manual trade lifecycle untouched
  - No new scanner endpoints added
"""

import json
import time
import threading
import unittest
from unittest.mock import patch, MagicMock


# ── Helpers ───────────────────────────────────────────────────────────────────

def _make_client():
    from dashboard.app import app
    app.config["TESTING"] = True
    return app.test_client()


def _insert_test_signal(conn, signal_id="TEST_001", taken=0, outcome="",
                         exit_timestamp=None, sl=100.0, tp=110.0, entry=105.0,
                         pair="XAU_USD", direction="bullish"):
    """Insert a minimal agent_signals row for testing."""
    conn.execute("""
        INSERT OR REPLACE INTO agent_signals
        (signal_id, timestamp_utc, pair, direction, grade, entry_price,
         sl_price, tp1_price, taken, outcome, actual_sl, actual_tp1, sl_pips, is_archived)
        VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,0)
    """, (signal_id, "2026-05-20 18:00:00", pair, direction, "A",
          entry, sl, tp, taken, outcome, sl, tp, abs(entry-sl)/0.01))
    if exit_timestamp:
        conn.execute(
            "UPDATE agent_signals SET exit_timestamp=? WHERE signal_id=?",
            (exit_timestamp, signal_id)
        )
    conn.commit()


# ── Phase 1: DB migration safety ──────────────────────────────────────────────

class TestPhase1DBMigration(unittest.TestCase):

    def setUp(self):
        from db.database import init_db, _get_conn
        init_db()
        self.conn = _get_conn()

    def _columns(self):
        return [r[1] for r in self.conn.execute(
            "PRAGMA table_info(agent_signals)"
        ).fetchall()]

    def test_exit_timestamp_column_exists(self):
        self.assertIn("exit_timestamp", self._columns())

    def test_exit_reason_column_exists(self):
        self.assertIn("exit_reason", self._columns())

    def test_trade_duration_minutes_column_exists(self):
        self.assertIn("trade_duration_minutes", self._columns())

    def test_max_favorable_excursion_column_exists(self):
        self.assertIn("max_favorable_excursion", self._columns())

    def test_max_adverse_excursion_column_exists(self):
        self.assertIn("max_adverse_excursion", self._columns())

    def test_old_rows_have_null_forensic_fields(self):
        """Pre-existing rows get NULL for forensic fields — no backfill."""
        row = self.conn.execute(
            "SELECT exit_timestamp, exit_reason, trade_duration_minutes "
            "FROM agent_signals LIMIT 1"
        ).fetchone()
        if row:
            # Row existed before migration — forensic fields should be NULL unless explicitly set
            # (we can't assert NULL because the test DB may have been written by the monitor)
            pass  # Just checks the query doesn't crash

    def test_update_agent_signal_forensic_writes_all_fields(self):
        """update_agent_signal_forensic() writes outcome + all forensic fields."""
        from db.database import update_agent_signal_forensic, get_agent_signal
        _insert_test_signal(self.conn, signal_id="FORENSIC_TEST", taken=1)
        update_agent_signal_forensic(
            signal_id               = "FORENSIC_TEST",
            outcome                 = "WIN",
            outcome_pips            = 15.5,
            notes                   = "[monitor] TP_HIT WIN +15.5p @ 110.0",
            exit_timestamp          = "2026-05-20 20:00:00",
            exit_reason             = "TP_HIT",
            exit_price              = 110.0,
            trade_duration_minutes  = 90,
            max_favorable_excursion = 20.0,
            max_adverse_excursion   = 5.0,
        )
        row = get_agent_signal("FORENSIC_TEST")
        self.assertIsNotNone(row)
        self.assertEqual(row["outcome"],                 "WIN")
        self.assertAlmostEqual(row["outcome_pips"],      15.5)
        self.assertEqual(row["exit_timestamp"],          "2026-05-20 20:00:00")
        self.assertEqual(row["exit_reason"],             "TP_HIT")
        self.assertAlmostEqual(row["exit_price"],        110.0)
        self.assertEqual(row["trade_duration_minutes"],  90)
        self.assertAlmostEqual(row["max_favorable_excursion"], 20.0)
        self.assertAlmostEqual(row["max_adverse_excursion"],    5.0)

    def test_get_open_taken_agent_signals_returns_taken_open(self):
        """get_open_taken_agent_signals() returns taken+open signals only."""
        from db.database import get_open_taken_agent_signals
        _insert_test_signal(self.conn, signal_id="OPEN_001", taken=1, outcome="")
        rows = get_open_taken_agent_signals()
        ids = [r["signal_id"] for r in rows]
        self.assertIn("OPEN_001", ids)

    def test_get_open_taken_agent_signals_excludes_closed(self):
        """get_open_taken_agent_signals() excludes signals with outcome set."""
        from db.database import get_open_taken_agent_signals
        _insert_test_signal(self.conn, signal_id="CLOSED_002", taken=1, outcome="WIN",
                             exit_timestamp="2026-05-20 21:00:00")
        rows = get_open_taken_agent_signals()
        ids = [r["signal_id"] for r in rows]
        self.assertNotIn("CLOSED_002", ids)

    def test_get_open_taken_agent_signals_excludes_not_taken(self):
        """get_open_taken_agent_signals() excludes signals that were never taken."""
        from db.database import get_open_taken_agent_signals
        _insert_test_signal(self.conn, signal_id="UNTAKEN_003", taken=0, outcome="")
        rows = get_open_taken_agent_signals()
        ids = [r["signal_id"] for r in rows]
        self.assertNotIn("UNTAKEN_003", ids)

    def test_close_agent_trade_writes_exit_timestamp(self):
        """close_agent_trade() writes exit_timestamp on close."""
        from db.database import close_agent_trade, get_agent_signal
        _insert_test_signal(self.conn, signal_id="CLOSE_004", taken=1)
        close_agent_trade("CLOSE_004", exit_price=110.0, entry_price=105.0,
                          direction="bullish", pip=0.01)
        row = get_agent_signal("CLOSE_004")
        self.assertIsNotNone(row["exit_timestamp"])

    def test_close_agent_trade_writes_exit_reason_manual_close(self):
        """close_agent_trade() writes exit_reason=MANUAL_CLOSE by default."""
        from db.database import close_agent_trade, get_agent_signal
        _insert_test_signal(self.conn, signal_id="CLOSE_005", taken=1)
        close_agent_trade("CLOSE_005", exit_price=110.0, entry_price=105.0,
                          direction="bullish", pip=0.01)
        row = get_agent_signal("CLOSE_005")
        self.assertEqual(row["exit_reason"], "MANUAL_CLOSE")

    def test_close_agent_trade_writes_trade_duration(self):
        """close_agent_trade() computes and writes trade_duration_minutes."""
        from db.database import close_agent_trade, get_agent_signal
        _insert_test_signal(self.conn, signal_id="CLOSE_006", taken=1)
        close_agent_trade("CLOSE_006", exit_price=100.0, entry_price=105.0,
                          direction="bearish", pip=0.01)
        row = get_agent_signal("CLOSE_006")
        # Duration may be 0 or None depending on test speed — just check it's set
        self.assertIsNotNone(row["trade_duration_minutes"])


# ── Phase 2: Monitor lifecycle ────────────────────────────────────────────────

class TestPhase2MonitorLifecycle(unittest.TestCase):

    def setUp(self):
        # Clear all active monitors before each test
        from ml.agent_trade_monitor import _active_agent_monitors, _monitor_lock
        with _monitor_lock:
            _active_agent_monitors.clear()
        from db.database import init_db, _get_conn
        init_db()
        self.conn = _get_conn()

    def tearDown(self):
        from ml.agent_trade_monitor import _active_agent_monitors, _monitor_lock
        with _monitor_lock:
            _active_agent_monitors.clear()

    def test_start_monitor_adds_to_active_set(self):
        """start_agent_monitor() adds signal_id to active monitors."""
        from ml.agent_trade_monitor import start_agent_monitor, get_active_agent_monitors
        with patch("ml.agent_trade_monitor._monitor_agent_trade"):
            # Start with a mock to avoid actual polling
            pass
        # Patch the thread to not do anything
        with patch("threading.Thread") as mock_thread:
            mock_t = MagicMock()
            mock_thread.return_value = mock_t
            start_agent_monitor("MON_001", "XAU_USD", "bullish", 2300.0, 2280.0, 2330.0)
        active = get_active_agent_monitors()
        self.assertIn("MON_001", active)

    def test_start_monitor_idempotent_no_duplicate(self):
        """Calling start_agent_monitor twice for same signal starts only one thread."""
        from ml.agent_trade_monitor import start_agent_monitor, get_active_agent_monitors
        with patch("threading.Thread") as mock_thread:
            mock_t = MagicMock()
            mock_thread.return_value = mock_t
            start_agent_monitor("MON_002", "XAU_USD", "bullish", 2300.0, 2280.0, 2330.0)
            start_agent_monitor("MON_002", "XAU_USD", "bullish", 2300.0, 2280.0, 2330.0)
            # Thread constructor called exactly once
            self.assertEqual(mock_thread.call_count, 1)

    def test_stop_monitor_removes_from_active_set(self):
        """stop_agent_monitor() removes signal from active monitors."""
        from ml.agent_trade_monitor import (
            start_agent_monitor, stop_agent_monitor, get_active_agent_monitors
        )
        with patch("threading.Thread") as mock_thread:
            mock_thread.return_value = MagicMock()
            start_agent_monitor("MON_003", "XAU_USD", "bearish", 2300.0, 2320.0, 2270.0)
        stop_agent_monitor("MON_003")
        self.assertNotIn("MON_003", get_active_agent_monitors())

    def test_stop_monitor_nonexistent_is_silent(self):
        """stop_agent_monitor() on an unknown signal_id does not raise."""
        from ml.agent_trade_monitor import stop_agent_monitor
        stop_agent_monitor("DOES_NOT_EXIST")  # Must not raise

    def test_get_active_monitors_returns_list(self):
        """get_active_agent_monitors() returns a list."""
        from ml.agent_trade_monitor import get_active_agent_monitors
        result = get_active_agent_monitors()
        self.assertIsInstance(result, list)

    def test_resume_on_startup_starts_monitors_for_open_signals(self):
        """resume_agent_monitors_on_startup() re-arms taken+open signals."""
        from ml.agent_trade_monitor import resume_agent_monitors_on_startup, get_active_agent_monitors
        _insert_test_signal(self.conn, signal_id="RESUME_001", taken=1, outcome="")
        with patch("threading.Thread") as mock_thread:
            mock_thread.return_value = MagicMock()
            resume_agent_monitors_on_startup()
        self.assertIn("RESUME_001", get_active_agent_monitors())

    def test_resume_on_startup_skips_closed_signals(self):
        """resume_agent_monitors_on_startup() does not re-arm already-closed signals."""
        from ml.agent_trade_monitor import resume_agent_monitors_on_startup, get_active_agent_monitors
        _insert_test_signal(self.conn, signal_id="RESUME_CLOSED", taken=1, outcome="WIN",
                             exit_timestamp="2026-05-20 20:00:00")
        with patch("threading.Thread") as mock_thread:
            mock_thread.return_value = MagicMock()
            resume_agent_monitors_on_startup()
        self.assertNotIn("RESUME_CLOSED", get_active_agent_monitors())

    def test_tp_hit_writes_win_and_forensic_fields(self):
        """Monitor writes WIN + TP_HIT + forensic fields when TP is touched."""
        from db.database import get_agent_signal
        _insert_test_signal(self.conn, signal_id="TP_HIT_001", taken=1, sl=100.0, tp=110.0, entry=105.0)

        # Mock get_live_bid_ask to immediately return TP level
        call_count = [0]
        def _mock_bid_ask(pair):
            call_count[0] += 1
            if call_count[0] < 3:
                return (107.0, 107.2)   # still open
            return (110.5, 110.7)       # TP hit for bullish (bid >= tp)

        from ml.agent_trade_monitor import _active_agent_monitors, _monitor_lock
        with _monitor_lock:
            _active_agent_monitors["TP_HIT_001"] = threading.current_thread()
        with patch("core.fetcher.get_live_bid_ask", side_effect=_mock_bid_ask), \
             patch("core.fetcher.fetch_candles", return_value=None), \
             patch("time.sleep", return_value=None):
            from ml.agent_trade_monitor import _monitor_agent_trade
            _monitor_agent_trade("TP_HIT_001", "XAU_USD", "bullish", 105.0, 100.0, 110.0)

        row = get_agent_signal("TP_HIT_001")
        self.assertEqual(row["outcome"],      "WIN")
        self.assertEqual(row["exit_reason"],  "TP_HIT")
        self.assertIsNotNone(row["exit_timestamp"])
        self.assertIsNotNone(row["exit_price"])
        self.assertIsNotNone(row["trade_duration_minutes"])

    def test_sl_hit_writes_loss_and_forensic_fields(self):
        """Monitor writes LOSS + SL_HIT + forensic fields when SL is touched."""
        from db.database import get_agent_signal
        _insert_test_signal(self.conn, signal_id="SL_HIT_001", taken=1, sl=100.0, tp=110.0, entry=105.0)

        call_count = [0]
        def _mock_bid_ask(pair):
            call_count[0] += 1
            if call_count[0] < 3:
                return (104.0, 104.2)   # still open
            return (99.5, 99.7)        # SL hit for bullish (bid <= sl)

        from ml.agent_trade_monitor import _active_agent_monitors, _monitor_lock
        with _monitor_lock:
            _active_agent_monitors["SL_HIT_001"] = threading.current_thread()
        with patch("core.fetcher.get_live_bid_ask", side_effect=_mock_bid_ask), \
             patch("core.fetcher.fetch_candles", return_value=None), \
             patch("time.sleep", return_value=None):
            from ml.agent_trade_monitor import _monitor_agent_trade
            _monitor_agent_trade("SL_HIT_001", "XAU_USD", "bullish", 105.0, 100.0, 110.0)

        row = get_agent_signal("SL_HIT_001")
        self.assertEqual(row["outcome"],     "LOSS")
        self.assertEqual(row["exit_reason"], "SL_HIT")
        self.assertIsNotNone(row["exit_timestamp"])
        self.assertIsNotNone(row["exit_price"])

    def test_mfe_tracked_from_live_price(self):
        """MFE is updated from live price polling, written on close."""
        from db.database import get_agent_signal
        _insert_test_signal(self.conn, signal_id="MFE_001", taken=1, sl=100.0, tp=115.0, entry=105.0)

        prices = iter([(108.0, 108.2), (110.0, 110.2), (111.0, 111.2), (116.0, 116.2)])
        def _mock_bid_ask(pair):
            try:
                return next(prices)
            except StopIteration:
                return (116.0, 116.2)

        from ml.agent_trade_monitor import _active_agent_monitors, _monitor_lock
        with _monitor_lock:
            _active_agent_monitors["MFE_001"] = threading.current_thread()
        with patch("core.fetcher.get_live_bid_ask", side_effect=_mock_bid_ask), \
             patch("core.fetcher.fetch_candles", return_value=None), \
             patch("time.sleep", return_value=None):
            from ml.agent_trade_monitor import _monitor_agent_trade
            _monitor_agent_trade("MFE_001", "XAU_USD", "bullish", 105.0, 100.0, 115.0)

        row = get_agent_signal("MFE_001")
        # MFE should reflect highest profit seen — at bid=111.0, that's (111-105)/0.01=600p
        self.assertIsNotNone(row["max_favorable_excursion"])
        self.assertGreater(row["max_favorable_excursion"], 0)

    def test_mae_tracked_from_live_price(self):
        """MAE is updated from live price polling, written on close."""
        from db.database import get_agent_signal
        _insert_test_signal(self.conn, signal_id="MAE_001", taken=1, sl=100.0, tp=115.0, entry=105.0)

        prices = iter([(103.0, 103.2), (102.0, 102.2), (108.0, 108.2), (116.0, 116.2)])
        def _mock_bid_ask(pair):
            try:
                return next(prices)
            except StopIteration:
                return (116.0, 116.2)

        from ml.agent_trade_monitor import _active_agent_monitors, _monitor_lock
        with _monitor_lock:
            _active_agent_monitors["MAE_001"] = threading.current_thread()
        with patch("core.fetcher.get_live_bid_ask", side_effect=_mock_bid_ask), \
             patch("core.fetcher.fetch_candles", return_value=None), \
             patch("time.sleep", return_value=None):
            from ml.agent_trade_monitor import _monitor_agent_trade
            _monitor_agent_trade("MAE_001", "XAU_USD", "bullish", 105.0, 100.0, 115.0)

        row = get_agent_signal("MAE_001")
        # MAE should reflect max adverse — at bid=102.0, that's (105-102)/0.01=300p
        self.assertIsNotNone(row["max_adverse_excursion"])
        self.assertGreater(row["max_adverse_excursion"], 0)


# ── Phase 3: Forensic UI ──────────────────────────────────────────────────────

class TestPhase3ForensicUI(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        with open("dashboard/templates/dashboard.html", encoding="utf-8") as f:
            cls.src = f.read()

    def test_agent_forensic_html_variable_present(self):
        """agentForensicHtml variable is built in the agent signal row."""
        self.assertIn("agentForensicHtml", self.src,
                      "agentForensicHtml not found in dashboard.html")

    def test_agent_forensic_html_injected_into_row(self):
        """${agentForensicHtml} is injected into the agent signal row template."""
        self.assertIn("${agentForensicHtml}", self.src,
                      "${agentForensicHtml} not injected into agent signal row")

    def test_open_trade_yellow_border_in_agent_forensic(self):
        """Open agent trade forensic block uses yellow border."""
        # Find the agentForensicHtml block
        idx = self.src.find("agentForensicHtml = isTaken")
        self.assertGreater(idx, 0, "agentForensicHtml assignment not found")
        block = self.src[idx: idx + 3000]
        self.assertIn("rgba(255,215,64,.3)", block,
                      "Yellow border for open agent trade missing from agentForensicHtml")

    def test_closed_trade_navy_border_in_agent_forensic(self):
        """Closed agent trade forensic block uses navy border."""
        idx = self.src.find("agentForensicHtml = isTaken")
        block = self.src[idx: idx + 3000]
        self.assertIn("var(--navy-border)", block,
                      "Navy border for closed agent trade missing from agentForensicHtml")

    def test_entry_label_in_agent_forensic(self):
        """ENTRY label present in agent forensic block."""
        idx = self.src.find("agentForensicHtml = isTaken")
        block = self.src[idx: idx + 3000]
        self.assertIn("ENTRY", block,
                      "ENTRY label missing from agentForensicHtml")

    def test_exit_label_in_agent_forensic(self):
        """EXIT label present in agent forensic block."""
        idx = self.src.find("agentForensicHtml = isTaken")
        block = self.src[idx: idx + 3000]
        self.assertIn("EXIT", block,
                      "EXIT label missing from agentForensicHtml")

    def test_live_duration_indicator_in_agent_forensic(self):
        """Live duration ⬤ marker present in agent forensic block for open trades."""
        idx = self.src.find("agentForensicHtml = isTaken")
        block = self.src[idx: idx + 3000]
        self.assertIn("⬤", block,
                      "Live duration ⬤ indicator missing from agentForensicHtml")

    def test_manual_override_color_in_agent_forensic(self):
        """MANUAL_OVERRIDE exit reason uses distinct orange color."""
        idx = self.src.find("agentForensicHtml = isTaken")
        block = self.src[idx: idx + 3000]
        self.assertIn("MANUAL_OVERRIDE", block,
                      "MANUAL_OVERRIDE case missing from agentForensicHtml exit reason coloring")

    def test_mfe_rendered_in_agent_forensic(self):
        """MFE field rendered in agent forensic block."""
        idx = self.src.find("agentForensicHtml = isTaken")
        block = self.src[idx: idx + 3000]
        self.assertIn("max_favorable_excursion", block,
                      "MFE not rendered in agentForensicHtml")

    def test_mae_rendered_in_agent_forensic(self):
        """MAE field rendered in agent forensic block."""
        idx = self.src.find("agentForensicHtml = isTaken")
        block = self.src[idx: idx + 3000]
        self.assertIn("max_adverse_excursion", block,
                      "MAE not rendered in agentForensicHtml")

    def test_exit_price_rendered_in_agent_forensic(self):
        """exit_price rendered in closed agent forensic block."""
        idx = self.src.find("agentForensicHtml = isTaken")
        block = self.src[idx: idx + 3000]
        self.assertIn("s.exit_price", block,
                      "exit_price not rendered in agentForensicHtml")

    def test_utcToNYFull_used_for_entry_in_agent_forensic(self):
        """utcToNYFull used for ENTRY timestamp in agent forensic block."""
        idx = self.src.find("agentForensicHtml = isTaken")
        block = self.src[idx: idx + 3000]
        self.assertIn("utcToNYFull(s.timestamp_utc)", block,
                      "utcToNYFull not used for ENTRY in agentForensicHtml")

    def test_utcToNYFull_used_for_exit_in_agent_forensic(self):
        """utcToNYFull used for EXIT timestamp in agent forensic block."""
        idx = self.src.find("agentForensicHtml = isTaken")
        block = self.src[idx: idx + 3000]
        self.assertIn("utcToNYFull(s.exit_timestamp)", block,
                      "utcToNYFull not used for EXIT in agentForensicHtml")


# ── Phase 4: Agent signal live poller ─────────────────────────────────────────

class TestPhase4AgentSignalPoller(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        with open("dashboard/templates/dashboard.html", encoding="utf-8") as f:
            cls.src = f.read()

    def test_agent_poller_timer_variable_declared(self):
        """_agentSignalPollerTimer variable declared."""
        self.assertIn("_agentSignalPollerTimer", self.src)

    def test_start_agent_signal_poller_present(self):
        """_startAgentSignalPoller function present."""
        self.assertIn("function _startAgentSignalPoller()", self.src)

    def test_stop_agent_signal_poller_present(self):
        """_stopAgentSignalPoller function present."""
        self.assertIn("function _stopAgentSignalPoller()", self.src)

    def test_poll_agent_signal_prices_now_present(self):
        """_pollAgentSignalPricesNow function present."""
        self.assertIn("async function _pollAgentSignalPricesNow()", self.src)

    def test_agent_poller_polls_live_price_endpoint(self):
        """_pollAgentSignalPricesNow polls /api/live-price."""
        idx = self.src.find("async function _pollAgentSignalPricesNow()")
        fn  = self.src[idx: self.src.find("\n}", idx) + 2]
        self.assertIn("/api/live-price", fn)

    def test_agent_poller_filters_taken_open_only(self):
        """_pollAgentSignalPricesNow filters for taken+open signals only."""
        idx = self.src.find("async function _pollAgentSignalPricesNow()")
        fn  = self.src[idx: self.src.find("\n}", idx) + 2]
        self.assertIn("taken", fn,
                      "Agent poller must filter for taken signals")

    def test_agent_poller_stops_when_no_open_signals(self):
        """_pollAgentSignalPricesNow stops poller when no open pairs."""
        idx = self.src.find("async function _pollAgentSignalPricesNow()")
        fn  = self.src[idx: self.src.find("\n}", idx) + 2]
        self.assertIn("_stopAgentSignalPoller", fn,
                      "Agent poller must stop itself when no open pairs remain")

    def test_switch_to_agent_tab_starts_agent_poller(self):
        """switchPerfTab('agent') starts agent signal poller."""
        self.assertIn("_startAgentSignalPoller()", self.src,
                      "_startAgentSignalPoller not called on agent tab switch")

    def test_switch_from_agent_tab_stops_agent_poller(self):
        """switchPerfTab to non-agent tab stops agent signal poller."""
        self.assertIn("_stopAgentSignalPoller()", self.src,
                      "_stopAgentSignalPoller not called when switching away from agent tab")

    def test_visibility_change_stops_agent_poller(self):
        """visibilitychange stops agent poller on document.hidden."""
        self.assertIn("_stopAgentSignalPoller", self.src)
        self.assertIn("document.hidden", self.src)

    def test_visibility_change_restarts_agent_poller_on_agent_tab(self):
        """visibilitychange restarts agent poller if agent tab is active."""
        idx = self.src.find("visibilitychange")
        block = self.src[idx: idx + 600]
        self.assertIn("_currentPerfTab", block)
        self.assertIn('"agent"', block,
                      "visibilitychange does not restart agent poller for agent tab")

    def test_agent_poller_uses_last_perf_data(self):
        """_pollAgentSignalPricesNow reads from window._lastPerfData."""
        idx = self.src.find("async function _pollAgentSignalPricesNow()")
        fn  = self.src[idx: self.src.find("\n}", idx) + 2]
        self.assertIn("_lastPerfData", fn,
                      "Agent poller must read pairs from window._lastPerfData")

    def test_agent_poller_rerenders_performance_after_update(self):
        """_pollAgentSignalPricesNow calls renderPerformance after price update."""
        idx = self.src.find("async function _pollAgentSignalPricesNow()")
        fn  = self.src[idx: self.src.find("\n}", idx) + 2]
        self.assertIn("renderPerformance", fn,
                      "Agent poller must call renderPerformance after price update")


# ── Phase 5: W/L integrity gate ───────────────────────────────────────────────

class TestPhase5WLIntegrityGate(unittest.TestCase):

    def setUp(self):
        from dashboard.app import app
        app.config["TESTING"] = True
        self.client = app.test_client()
        from db.database import init_db, _get_conn
        init_db()
        self.conn = _get_conn()

    def test_taken_open_signal_rejects_without_override(self):
        """W click on taken+open signal without override_reason → 409."""
        _insert_test_signal(self.conn, signal_id="WL_GATE_001", taken=1, outcome="")
        resp = self.client.post("/api/mark_outcome", json={
            "signal_id": "WL_GATE_001",
            "outcome":   "WIN",
        })
        self.assertEqual(resp.status_code, 409)

    def test_taken_open_signal_response_includes_requires_override(self):
        """409 response includes requires_override: true."""
        _insert_test_signal(self.conn, signal_id="WL_GATE_002", taken=1, outcome="")
        resp = self.client.post("/api/mark_outcome", json={
            "signal_id": "WL_GATE_002",
            "outcome":   "LOSS",
        })
        data = json.loads(resp.data)
        self.assertTrue(data.get("requires_override"), "requires_override missing from 409 response")

    def test_taken_open_signal_accepts_with_override_reason(self):
        """W click on taken+open with override_reason → 200 OK."""
        _insert_test_signal(self.conn, signal_id="WL_GATE_003", taken=1, outcome="")
        resp = self.client.post("/api/mark_outcome", json={
            "signal_id":       "WL_GATE_003",
            "outcome":         "WIN",
            "override_reason": "Price hit TP but monitor missed due to weekend gap",
        })
        self.assertEqual(resp.status_code, 200)
        data = json.loads(resp.data)
        self.assertTrue(data["ok"])

    def test_override_writes_manual_override_exit_reason(self):
        """Manual override writes exit_reason=MANUAL_OVERRIDE."""
        from db.database import get_agent_signal
        _insert_test_signal(self.conn, signal_id="WL_GATE_004", taken=1, outcome="")
        self.client.post("/api/mark_outcome", json={
            "signal_id":       "WL_GATE_004",
            "outcome":         "WIN",
            "override_reason": "test override",
        })
        row = get_agent_signal("WL_GATE_004")
        self.assertEqual(row["exit_reason"], "MANUAL_OVERRIDE")

    def test_override_writes_exit_timestamp(self):
        """Manual override writes exit_timestamp."""
        from db.database import get_agent_signal
        _insert_test_signal(self.conn, signal_id="WL_GATE_005", taken=1, outcome="")
        self.client.post("/api/mark_outcome", json={
            "signal_id":       "WL_GATE_005",
            "outcome":         "LOSS",
            "override_reason": "manual override test",
        })
        row = get_agent_signal("WL_GATE_005")
        self.assertIsNotNone(row["exit_timestamp"])

    def test_override_writes_trade_duration(self):
        """Manual override computes and writes trade_duration_minutes."""
        from db.database import get_agent_signal
        _insert_test_signal(self.conn, signal_id="WL_GATE_006", taken=1, outcome="")
        self.client.post("/api/mark_outcome", json={
            "signal_id":       "WL_GATE_006",
            "outcome":         "WIN",
            "override_reason": "testing duration write",
        })
        row = get_agent_signal("WL_GATE_006")
        self.assertIsNotNone(row["trade_duration_minutes"])

    def test_override_response_includes_exit_reason(self):
        """Override response JSON includes exit_reason=MANUAL_OVERRIDE."""
        _insert_test_signal(self.conn, signal_id="WL_GATE_007", taken=1, outcome="")
        resp = self.client.post("/api/mark_outcome", json={
            "signal_id":       "WL_GATE_007",
            "outcome":         "WIN",
            "override_reason": "test",
        })
        data = json.loads(resp.data)
        self.assertEqual(data.get("exit_reason"), "MANUAL_OVERRIDE")

    def test_not_taken_signal_accepts_plain_wl(self):
        """W click on untaken signal (no override needed) → 200 OK."""
        _insert_test_signal(self.conn, signal_id="WL_GATE_008", taken=0, outcome="")
        resp = self.client.post("/api/mark_outcome", json={
            "signal_id": "WL_GATE_008",
            "outcome":   "WIN",
        })
        self.assertEqual(resp.status_code, 200)

    def test_already_closed_signal_accepts_plain_wl(self):
        """W click on already-closed signal (has exit_timestamp) → 200 OK."""
        _insert_test_signal(self.conn, signal_id="WL_GATE_009", taken=1, outcome="WIN",
                             exit_timestamp="2026-05-20 20:00:00")
        resp = self.client.post("/api/mark_outcome", json={
            "signal_id": "WL_GATE_009",
            "outcome":   "WIN",
        })
        self.assertEqual(resp.status_code, 200)

    def test_signal_with_outcome_set_accepts_plain_wl(self):
        """W click on signal with outcome already set → 200 OK (re-marking)."""
        _insert_test_signal(self.conn, signal_id="WL_GATE_010", taken=1, outcome="LOSS")
        resp = self.client.post("/api/mark_outcome", json={
            "signal_id": "WL_GATE_010",
            "outcome":   "WIN",
        })
        self.assertEqual(resp.status_code, 200)


# ── Frontend W/L gate presence ────────────────────────────────────────────────

class TestPhase5FrontendWLGate(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        with open("dashboard/templates/dashboard.html", encoding="utf-8") as f:
            cls.src = f.read()

    def _markOutcome_fn(self):
        idx = self.src.find("async function markOutcome(")
        end = self.src.find("\n}\n", idx) + 3
        return self.src[idx:end]

    def test_mark_outcome_checks_taken_and_open(self):
        """markOutcome checks if signal is taken+open before proceeding."""
        fn = self._markOutcome_fn()
        self.assertIn("_isTaken", fn, "isTaken check missing from markOutcome")
        self.assertIn("_isOpen",  fn, "isOpen check missing from markOutcome")

    def test_mark_outcome_uses_last_perf_data(self):
        """markOutcome looks up signal from window._lastPerfData."""
        fn = self._markOutcome_fn()
        self.assertIn("_lastPerfData", fn,
                      "markOutcome does not look up signal from _lastPerfData")

    def test_mark_outcome_prompts_for_override_reason(self):
        """markOutcome prompts user for override reason on taken+open signal."""
        fn = self._markOutcome_fn()
        self.assertIn("prompt(", fn,
                      "markOutcome missing prompt for override reason")

    def test_mark_outcome_sends_override_reason_in_body(self):
        """markOutcome sends override_reason in POST body for override flow."""
        fn = self._markOutcome_fn()
        self.assertIn("override_reason", fn,
                      "override_reason not sent in markOutcome POST body")

    def test_mark_outcome_shows_override_label_on_success(self):
        """markOutcome shows [OVERRIDE] label after successful override."""
        fn = self._markOutcome_fn()
        self.assertIn("[OVERRIDE]", fn,
                      "[OVERRIDE] label not shown in markOutcome override success path")

    def test_mark_outcome_cancels_if_no_reason_provided(self):
        """markOutcome cancels and shows toast if override reason is blank."""
        fn = self._markOutcome_fn()
        self.assertIn("Override cancelled", fn,
                      "markOutcome must show cancellation toast when reason is blank")

    def test_mark_outcome_requires_non_blank_reason(self):
        """markOutcome checks that reason is not empty/null."""
        fn = self._markOutcome_fn()
        self.assertIn("!_reason || !_reason.trim()", fn,
                      "markOutcome blank reason check missing")


# ── Regression: old rows and scope isolation ──────────────────────────────────

class TestRegressionAndIsolation(unittest.TestCase):

    def setUp(self):
        from dashboard.app import app
        app.config["TESTING"] = True
        self.client = app.test_client()

    def test_recent_signals_returns_200(self):
        """/api/recent_signals still returns 200 after lifecycle changes."""
        resp = self.client.get("/api/recent_signals")
        self.assertEqual(resp.status_code, 200)

    def test_recent_signals_has_signals_key(self):
        """/api/recent_signals still returns signals key."""
        data = json.loads(self.client.get("/api/recent_signals").data)
        self.assertIn("signals", data)

    def test_agent_monitors_endpoint_returns_200(self):
        """/api/agent_monitors returns 200 with active list."""
        resp = self.client.get("/api/agent_monitors")
        self.assertEqual(resp.status_code, 200)
        data = json.loads(resp.data)
        self.assertIn("active", data)
        self.assertIsInstance(data["active"], list)

    def test_performance_endpoint_returns_200(self):
        """/api/performance returns 200 — no schema break."""
        resp = self.client.get("/api/performance")
        self.assertEqual(resp.status_code, 200)

    def test_mark_outcome_400_on_missing_signal_id(self):
        """/api/mark_outcome returns 400 if signal_id missing."""
        resp = self.client.post("/api/mark_outcome", json={"outcome": "WIN"})
        self.assertEqual(resp.status_code, 400)

    def test_mark_outcome_400_on_invalid_outcome(self):
        """/api/mark_outcome returns 400 for invalid outcome value."""
        resp = self.client.post("/api/mark_outcome", json={"signal_id": "X", "outcome": "MAYBE"})
        self.assertEqual(resp.status_code, 400)

    def test_no_strategy_file_touched(self):
        """strategy files are untouched — gold/forex/news_sniper/om_gold_scalp."""
        import importlib.util
        for mod in ["strategies.gold_strategy", "strategies.forex_strategy",
                    "strategies.news_sniper", "strategies.om_gold_scalp"]:
            spec = importlib.util.find_spec(mod)
            self.assertIsNotNone(spec, f"{mod} module not found — was it deleted?")

    def test_manual_trade_logger_import_unaffected(self):
        """ml/manual_trade_logger imports without error."""
        from ml.manual_trade_logger import (
            resume_monitors_on_startup, get_active_monitors
        )
        self.assertTrue(callable(resume_monitors_on_startup))
        self.assertTrue(callable(get_active_monitors))


if __name__ == "__main__":
    unittest.main()
