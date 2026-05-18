"""
tests/test_performance_exclusions.py — Performance stats exclude archived/bad-window signals

Tests for:
  db/database.py   :: get_performance_summary_db(), archive_bad_run_window()
  alerts/logger.py :: get_performance_summary() + _is_bad_window_csv()

Run:
  cd /Users/ompandya/Desktop/forex-agent
  python -m pytest tests/test_performance_exclusions.py -v
"""

import os
import csv
import tempfile
import pytest
from datetime import datetime, timezone


# ─── helpers ──────────────────────────────────────────────────────────────────

def _make_db_with_signals(signals: list[dict]):
    """
    Create a fresh in-memory SQLite DB populated with agent_signals rows.
    Returns a monkeypatched _get_conn() that returns this connection.
    """
    import sqlite3
    conn = sqlite3.connect(":memory:", check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys=ON")
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS agent_signals (
            signal_id       TEXT PRIMARY KEY,
            timestamp_utc   TEXT,
            pair            TEXT,
            direction       TEXT,
            grade           TEXT DEFAULT '',
            setup_type      TEXT DEFAULT '',
            entry_price     REAL,
            sl_price        REAL,
            tp1_price       REAL,
            tp2_price       REAL,
            sl_pips         REAL,
            tp1_pips        REAL,
            tp2_pips        REAL,
            score           REAL,
            score_zone      REAL, score_tf REAL, score_pattern REAL,
            score_session   REAL, score_news REAL, score_quality_bonus REAL,
            score_fvg       REAL, score_ict REAL,
            h1_zone_type    TEXT, h1_zone_high REAL, h1_zone_low REAL,
            h1_zone_strength REAL,
            h1_trend        TEXT, m15_trend TEXT, m5_trend TEXT,
            entry_pattern   TEXT,
            session         TEXT, killzone TEXT,
            news_safe       INTEGER,
            alerted         INTEGER DEFAULT 0,
            taken           INTEGER DEFAULT 0,
            outcome         TEXT DEFAULT '',
            outcome_pips    REAL,
            notes           TEXT DEFAULT '',
            signal_mode     TEXT DEFAULT 'normal',
            is_archived     INTEGER DEFAULT 0,
            weekend_block   INTEGER DEFAULT 0,
            session_block   INTEGER DEFAULT 0,
            market_closed   INTEGER DEFAULT 0,
            low_liquidity_window INTEGER DEFAULT 0,
            blocked_reason  TEXT DEFAULT '',
            entry_allowed   INTEGER DEFAULT 1,
            archive_reason  TEXT DEFAULT '',
            manual_exclusion INTEGER DEFAULT 0
        );
        CREATE TABLE IF NOT EXISTS manual_trades (
            signal_id       TEXT PRIMARY KEY,
            source          TEXT DEFAULT 'manual',
            timestamp_utc   TEXT,
            pair            TEXT,
            direction       TEXT,
            setup_type      TEXT,
            entry_price     REAL,
            sl_price        REAL,  tp1_price REAL, tp2_price REAL,
            sl_pips         REAL,  tp1_pips  REAL, tp2_pips  REAL,
            rr1             TEXT,
            outcome         TEXT DEFAULT '',
            outcome_pips    REAL,
            post_mortem     TEXT DEFAULT '',
            notes           TEXT DEFAULT ''
        );
    """)
    for i, sig in enumerate(signals):
        conn.execute("""
            INSERT INTO agent_signals
                (signal_id, timestamp_utc, pair, grade, outcome, outcome_pips,
                 taken, is_archived, weekend_block, session_block, market_closed,
                 blocked_reason, entry_allowed, archive_reason, manual_exclusion)
            VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
        """, (
            sig.get("signal_id", f"SIG_{i:03d}"),
            sig.get("timestamp_utc", "2026-05-12 10:00:00"),
            sig.get("pair",         "XAU_USD"),
            sig.get("grade",        "A+"),
            sig.get("outcome",      ""),
            sig.get("outcome_pips", None),
            sig.get("taken",        0),
            sig.get("is_archived",  0),
            sig.get("weekend_block", 0),
            sig.get("session_block", 0),
            sig.get("market_closed", 0),
            sig.get("blocked_reason", ""),
            sig.get("entry_allowed", 1),
            sig.get("archive_reason", ""),
            sig.get("manual_exclusion", 0),
        ))
    conn.commit()
    return conn


def _call_summary_db(signals: list[dict], bad_run_window=None) -> dict:
    """
    Call get_performance_summary_db() with a fake DB injected via monkeypatch.
    Uses module-level import hack: temporarily replaces _get_conn.
    """
    import db.database as db_mod

    conn = _make_db_with_signals(signals)
    original = db_mod._get_conn

    def _fake_conn():
        return conn

    db_mod._get_conn = _fake_conn
    try:
        result = db_mod.get_performance_summary_db(bad_run_window=bad_run_window)
    finally:
        db_mod._get_conn = original

    return result


# ─── CSV bad-window filter ────────────────────────────────────────────────────

class TestIsBadWindowCsv:
    from alerts.logger import _is_bad_window_csv as _fn

    def test_saturday_midnight(self):
        from alerts.logger import _is_bad_window_csv
        assert _is_bad_window_csv("2026-05-16 00:00:00") is True   # Saturday

    def test_saturday_noon(self):
        from alerts.logger import _is_bad_window_csv
        assert _is_bad_window_csv("2026-05-16 12:30:00") is True

    def test_saturday_23_59(self):
        from alerts.logger import _is_bad_window_csv
        assert _is_bad_window_csv("2026-05-16 23:59:00") is True

    def test_sunday_00_00_blocked(self):
        from alerts.logger import _is_bad_window_csv
        assert _is_bad_window_csv("2026-05-17 00:00:00") is True   # Sunday 00:00

    def test_sunday_21_59_blocked(self):
        from alerts.logger import _is_bad_window_csv
        assert _is_bad_window_csv("2026-05-17 21:59:00") is True

    def test_sunday_22_00_not_blocked(self):
        from alerts.logger import _is_bad_window_csv
        assert _is_bad_window_csv("2026-05-17 22:00:00") is False  # market open

    def test_friday_21_30_blocked(self):
        from alerts.logger import _is_bad_window_csv
        assert _is_bad_window_csv("2026-05-15 21:30:00") is True   # Friday 21:30

    def test_friday_21_29_not_blocked(self):
        from alerts.logger import _is_bad_window_csv
        assert _is_bad_window_csv("2026-05-15 21:29:00") is False  # Friday, just before cutoff

    def test_monday_clean(self):
        from alerts.logger import _is_bad_window_csv
        assert _is_bad_window_csv("2026-05-18 08:00:00") is False  # Monday

    def test_malformed_timestamp_not_excluded(self):
        from alerts.logger import _is_bad_window_csv
        assert _is_bad_window_csv("not-a-date") is False  # fails safe


# ─── CSV get_performance_summary — bad-window rows excluded ──────────────────

class TestCsvPerformanceSummary:
    def _write_csv(self, rows: list[dict]) -> str:
        """Write rows to a temp CSV, return path."""
        fieldnames = [
            "signal_id", "timestamp_utc", "pair", "grade",
            "outcome", "outcome_pips", "taken",
            "direction", "setup_type", "entry_price",
            "sl_price", "tp1_price", "tp2_price",
            "sl_pips", "tp1_pips", "tp2_pips",
            "score", "score_zone", "score_tf", "score_pattern",
            "score_session", "score_news", "score_quality_bonus",
            "score_fvg", "score_ict",
            "h1_zone_type", "h1_zone_high", "h1_zone_low", "h1_zone_strength",
            "h1_trend", "m15_trend", "m5_trend",
            "entry_pattern", "session", "killzone", "news_safe",
            "alerted", "user_sl", "user_tp1", "actual_sl", "actual_tp1",
            "notes", "signal_mode",
        ]
        fh = tempfile.NamedTemporaryFile(
            mode="w", suffix=".csv", delete=False, newline=""
        )
        writer = csv.DictWriter(fh, fieldnames=fieldnames, extrasaction="ignore")
        writer.writeheader()
        for row in rows:
            writer.writerow({f: row.get(f, "") for f in fieldnames})
        fh.close()
        return fh.name

    def _call(self, rows, bad_run_window=None):
        import alerts.logger as lg_mod
        original_path = lg_mod.LOG_PATH
        path = self._write_csv(rows)
        lg_mod.LOG_PATH = path
        try:
            return lg_mod.get_performance_summary(bad_run_window=bad_run_window)
        finally:
            lg_mod.LOG_PATH = original_path
            os.unlink(path)

    def test_stats_source_is_csv(self):
        rows = [
            {"timestamp_utc": "2026-05-12 10:00:00", "outcome": "WIN", "outcome_pips": "10"},
        ]
        r = self._call(rows)
        assert r["stats_source"] == "csv"

    def test_saturday_rows_excluded(self):
        rows = [
            {"timestamp_utc": "2026-05-16 12:00:00", "outcome": "WIN", "outcome_pips": "20"},  # Sat → excluded
            {"timestamp_utc": "2026-05-12 10:00:00", "outcome": "LOSS", "outcome_pips": "-10"}, # Mon → kept
        ]
        r = self._call(rows)
        assert r["excluded_bad_window_count"] == 1
        assert r["wins"]   == 0
        assert r["losses"] == 1

    def test_sunday_pre22_excluded(self):
        rows = [
            {"timestamp_utc": "2026-05-17 10:00:00", "outcome": "WIN", "outcome_pips": "20"},  # Sun 10:00 → excluded
            {"timestamp_utc": "2026-05-17 22:30:00", "outcome": "WIN", "outcome_pips": "20"},  # Sun 22:30 → kept
        ]
        r = self._call(rows)
        assert r["excluded_bad_window_count"] == 1
        assert r["wins"] == 1

    def test_friday_post_cutoff_excluded(self):
        rows = [
            {"timestamp_utc": "2026-05-15 21:30:00", "outcome": "LOSS", "outcome_pips": "-15"}, # Fri 21:30 → excluded
            {"timestamp_utc": "2026-05-15 20:00:00", "outcome": "WIN",  "outcome_pips": "10"},  # Fri 20:00 → kept
        ]
        r = self._call(rows)
        assert r["excluded_bad_window_count"] == 1
        assert r["wins"]   == 1
        assert r["losses"] == 0

    def test_bad_run_window_not_applied_by_default(self):
        rows = [
            {"timestamp_utc": "2026-05-15 18:00:00", "outcome": "WIN", "outcome_pips": "10"},
        ]
        r = self._call(rows)
        assert r["bad_run_window_applied"] is False
        assert r["excluded_bad_run_count"] == 0

    def test_bad_run_window_applied_when_passed(self):
        rows = [
            {"timestamp_utc": "2026-05-15 18:00:00", "outcome": "WIN",  "outcome_pips": "10"},  # in window
            {"timestamp_utc": "2026-05-12 10:00:00", "outcome": "LOSS", "outcome_pips": "-5"},  # before window
        ]
        r = self._call(rows, bad_run_window=("2026-05-15 00:00:00", "2026-05-18 01:07:52"))
        assert r["bad_run_window_applied"] is True
        assert r["excluded_bad_run_count"] == 1
        assert r["wins"]   == 0
        assert r["losses"] == 1

    def test_empty_csv_returns_gracefully(self):
        r = self._call([])
        assert r.get("stats_source") == "csv"
        assert r.get("completed", 0) == 0


# ─── DB get_performance_summary_db — archived rows excluded ──────────────────

class TestDbPerformanceSummary:
    def test_stats_source_is_sqlite(self):
        r = _call_summary_db([])
        assert r["stats_source"] == "sqlite"

    def test_archived_signals_excluded_from_stats(self):
        signals = [
            {"outcome": "WIN",  "outcome_pips": 20, "is_archived": 0},   # active → included
            {"outcome": "LOSS", "outcome_pips": -10, "is_archived": 1},  # archived → excluded
        ]
        r = _call_summary_db(signals)
        assert r["agent"]["wins"]   == 1
        assert r["agent"]["losses"] == 0

    def test_excluded_archived_count_reported(self):
        signals = [
            {"outcome": "WIN",  "outcome_pips": 10, "is_archived": 0},
            {"outcome": "LOSS", "outcome_pips": -5, "is_archived": 1},
            {"outcome": "LOSS", "outcome_pips": -5, "is_archived": 1},
        ]
        r = _call_summary_db(signals)
        assert r["excluded_archived_count"] == 2

    def test_no_archived_signals_count_is_zero(self):
        signals = [
            {"outcome": "WIN", "outcome_pips": 10, "is_archived": 0},
        ]
        r = _call_summary_db(signals)
        assert r["excluded_archived_count"] == 0

    def test_bad_run_window_not_applied_by_default(self):
        signals = [
            {"timestamp_utc": "2026-05-15 18:00:00", "outcome": "WIN", "outcome_pips": 10},
        ]
        r = _call_summary_db(signals)
        assert r["bad_run_window_applied"]    is False
        assert r["excluded_bad_window_count"] == 0
        assert r["agent"]["wins"] == 1

    def test_bad_run_window_applied_when_passed(self):
        signals = [
            {"timestamp_utc": "2026-05-15 18:00:00", "outcome": "WIN",  "outcome_pips": 10,  "is_archived": 0},  # in window
            {"timestamp_utc": "2026-05-12 10:00:00", "outcome": "LOSS", "outcome_pips": -5,  "is_archived": 0},  # outside
        ]
        r = _call_summary_db(signals, bad_run_window=("2026-05-15 00:00:00", "2026-05-18 01:07:52"))
        assert r["bad_run_window_applied"]    is True
        assert r["excluded_bad_window_count"] == 1
        assert r["agent"]["wins"]   == 0
        assert r["agent"]["losses"] == 1

    def test_archived_plus_bad_run_both_excluded(self):
        signals = [
            {"timestamp_utc": "2026-05-15 18:00:00", "outcome": "WIN",  "outcome_pips": 10,  "is_archived": 0},  # bad-run window
            {"timestamp_utc": "2026-05-12 10:00:00", "outcome": "LOSS", "outcome_pips": -5,  "is_archived": 1},  # archived
            {"timestamp_utc": "2026-05-12 11:00:00", "outcome": "WIN",  "outcome_pips": 8,   "is_archived": 0},  # clean
        ]
        r = _call_summary_db(signals, bad_run_window=("2026-05-15 00:00:00", "2026-05-18 01:07:52"))
        assert r["excluded_archived_count"]   == 1
        assert r["excluded_bad_window_count"] == 1
        assert r["agent"]["wins"]   == 1  # only the clean May-12 signal
        assert r["agent"]["losses"] == 0

    def test_total_signals_excludes_archived(self):
        signals = [
            {"is_archived": 0, "outcome": ""},
            {"is_archived": 0, "outcome": ""},
            {"is_archived": 1, "outcome": ""},
        ]
        r = _call_summary_db(signals)
        assert r["total_signals"] == 2

    def test_win_rate_correct_after_exclusion(self):
        signals = [
            {"outcome": "WIN",  "outcome_pips": 10, "is_archived": 0},
            {"outcome": "WIN",  "outcome_pips": 10, "is_archived": 0},
            {"outcome": "LOSS", "outcome_pips": -5, "is_archived": 0},
            {"outcome": "LOSS", "outcome_pips": -5, "is_archived": 1},  # excluded
        ]
        r = _call_summary_db(signals)
        # 2 wins, 1 loss → 66.7%
        assert r["agent"]["wins"]   == 2
        assert r["agent"]["losses"] == 1
        assert r["agent"]["win_rate"] == pytest.approx(66.7, abs=0.1)

    def test_empty_db_returns_clean(self):
        r = _call_summary_db([])
        assert r["stats_source"]            == "sqlite"
        assert r["excluded_archived_count"] == 0
        assert r["agent"]["total"]          == 0
        assert r["win_rate"]                == 0


# ─── archive_bad_run_window ───────────────────────────────────────────────────

class TestArchiveBadRunWindow:
    """archive_bad_run_window() stamps rows with is_archived=1 + audit fields."""

    def _fake_db(self, signals):
        """Return a monkeypatched db_mod with an in-memory DB."""
        import db.database as db_mod
        conn = _make_db_with_signals(signals)
        original = db_mod._get_conn
        db_mod._get_conn = lambda: conn
        return db_mod, original, conn

    def _restore(self, db_mod, original):
        db_mod._get_conn = original

    def test_rows_in_window_archived(self):
        import db.database as db_mod
        signals = [
            {"signal_id": "IN1",  "timestamp_utc": "2026-05-15 12:00:00", "outcome": "WIN",  "outcome_pips": 10},
            {"signal_id": "IN2",  "timestamp_utc": "2026-05-17 22:30:00", "outcome": "LOSS", "outcome_pips": -5},
            {"signal_id": "OUT1", "timestamp_utc": "2026-05-14 23:59:59", "outcome": "WIN",  "outcome_pips": 8},  # before
            {"signal_id": "OUT2", "timestamp_utc": "2026-05-18 01:07:53", "outcome": "WIN",  "outcome_pips": 8},  # after
        ]
        db_mod_real, orig, conn = self._fake_db(signals)
        try:
            count = db_mod.archive_bad_run_window(
                start_utc="2026-05-15 00:00:00",
                end_utc="2026-05-18 01:07:52",
            )
            assert count == 2
            rows = conn.execute(
                "SELECT signal_id, is_archived, manual_exclusion, blocked_reason, archive_reason "
                "FROM agent_signals ORDER BY signal_id"
            ).fetchall()
            by_id = {r["signal_id"]: dict(r) for r in rows}
            assert by_id["IN1"]["is_archived"]      == 1
            assert by_id["IN1"]["manual_exclusion"] == 1
            assert by_id["IN1"]["blocked_reason"]   == "bad_run_bug_window"
            assert by_id["IN1"]["archive_reason"]   == "scanner_over_signaling_may15_may18"
            assert by_id["IN2"]["is_archived"]      == 1
            assert by_id["OUT1"]["is_archived"]     == 0   # untouched
            assert by_id["OUT2"]["is_archived"]     == 0   # untouched
        finally:
            self._restore(db_mod_real, orig)

    def test_idempotent_second_call_archives_zero(self):
        import db.database as db_mod
        signals = [
            {"signal_id": "SIG1", "timestamp_utc": "2026-05-15 12:00:00"},
        ]
        db_mod_real, orig, conn = self._fake_db(signals)
        try:
            count1 = db_mod.archive_bad_run_window(
                start_utc="2026-05-15 00:00:00",
                end_utc="2026-05-18 01:07:52",
            )
            count2 = db_mod.archive_bad_run_window(
                start_utc="2026-05-15 00:00:00",
                end_utc="2026-05-18 01:07:52",
            )
            assert count1 == 1
            assert count2 == 0   # already archived — no second change
        finally:
            self._restore(db_mod_real, orig)

    def test_stats_exclude_bad_run_rows_after_archive(self):
        """After archive_bad_run_window(), get_performance_summary_db() excludes them."""
        import db.database as db_mod
        signals = [
            {"signal_id": "GOOD", "timestamp_utc": "2026-05-12 10:00:00", "outcome": "WIN",  "outcome_pips": 10},
            {"signal_id": "BAD",  "timestamp_utc": "2026-05-15 18:00:00", "outcome": "LOSS", "outcome_pips": -5},
        ]
        db_mod_real, orig, conn = self._fake_db(signals)
        try:
            db_mod.archive_bad_run_window(
                start_utc="2026-05-15 00:00:00",
                end_utc="2026-05-18 01:07:52",
            )
            r = db_mod.get_performance_summary_db()
            assert r["agent"]["wins"]   == 1
            assert r["agent"]["losses"] == 0
            assert r["excluded_archived_count"] >= 1
        finally:
            self._restore(db_mod_real, orig)

    def test_constants_exported(self):
        """BAD_RUN_WINDOW_START/END are importable for wiring into api_performance."""
        from db.database import BAD_RUN_WINDOW_START, BAD_RUN_WINDOW_END
        assert BAD_RUN_WINDOW_START == "2026-05-15 00:00:00"
        assert BAD_RUN_WINDOW_END   == "2026-05-18 01:07:52"
