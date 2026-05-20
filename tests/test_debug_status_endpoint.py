"""
tests/test_debug_status_endpoint.py

Tests for GET /api/debug/status endpoint.

Covers:
  - HTTP 200 and application/json content-type
  - All top-level keys present: version, env, database, scanner
  - version block: git_sha, branch, build_time_utc are strings
  - env block: all 4 flags present as booleans, read live (not cached)
  - database block: resolved_path matches _db_path(), exists is bool,
    tables is list, signals_table is None|str, counts are int|None
  - scanner block: mode is str, watch_only is bool
  - watch_only=True  when OM_STRATEGY_ENABLED=false
  - watch_only=False when OM_STRATEGY_ENABLED=true
  - env flags toggled live (not stuck at import-time cache)
  - endpoint is GET-only: POST returns 405
  - safe when DB doesn't exist (no crash, exists=False)
  - signals_table auto-detected without hardcoding
  - recent_signal_count_30m is int >= 0 when DB exists, or None when missing
  - database.resolved_path is an absolute path
  - no DB writes: table count unchanged before/after call
"""

import json
import os
import sqlite3
import tempfile
import unittest
from unittest.mock import patch


class TestDebugStatusShape(unittest.TestCase):
    """HTTP shape and top-level structure."""

    def setUp(self):
        from dashboard.app import app
        app.config["TESTING"] = True
        self.client = app.test_client()

    def test_returns_200(self):
        resp = self.client.get("/api/debug/status")
        self.assertEqual(resp.status_code, 200)

    def test_content_type_json(self):
        resp = self.client.get("/api/debug/status")
        self.assertIn("application/json", resp.content_type)

    def test_top_level_keys(self):
        resp = self.client.get("/api/debug/status")
        data = json.loads(resp.data)
        for key in ("version", "env", "database", "scanner"):
            self.assertIn(key, data, f"Missing top-level key: {key}")

    def test_post_returns_405(self):
        resp = self.client.post("/api/debug/status")
        self.assertEqual(resp.status_code, 405,
                         "POST to read-only endpoint must return 405")


class TestDebugStatusVersion(unittest.TestCase):
    """version block keys and types."""

    def setUp(self):
        from dashboard.app import app
        app.config["TESTING"] = True
        self.client = app.test_client()
        resp = self.client.get("/api/debug/status")
        self.data = json.loads(resp.data)["version"]

    def test_version_keys(self):
        for key in ("git_sha", "branch", "build_time_utc"):
            self.assertIn(key, self.data, f"Missing version key: {key}")

    def test_version_values_are_strings(self):
        for key, val in self.data.items():
            self.assertIsInstance(val, str, f"version.{key} must be str, got {type(val)}")

    def test_version_git_sha_nonempty(self):
        self.assertTrue(len(self.data["git_sha"]) > 0)

    def test_version_build_time_contains_utc(self):
        self.assertIn("UTC", self.data["build_time_utc"])

    def test_version_matches_api_version_endpoint(self):
        """git_sha must be identical to /api/version response."""
        from dashboard.app import app
        app.config["TESTING"] = True
        client = app.test_client()
        v_resp = json.loads(client.get("/api/version").data)
        self.assertEqual(self.data["git_sha"], v_resp["git_sha"])


class TestDebugStatusEnv(unittest.TestCase):
    """env block: presence, types, live reads."""

    _ENV_KEYS = ("OM_STRATEGY_ENABLED", "LEGACY_GOLD_ENABLED",
                 "LEGACY_FOREX_ENABLED", "OM_GOLD_SCALP_ENABLED")

    def setUp(self):
        from dashboard.app import app
        app.config["TESTING"] = True
        self.client = app.test_client()

    def _env_block(self):
        return json.loads(self.client.get("/api/debug/status").data)["env"]

    def test_all_env_keys_present(self):
        env = self._env_block()
        for key in self._ENV_KEYS:
            self.assertIn(key, env, f"Missing env key: {key}")

    def test_env_values_are_booleans(self):
        env = self._env_block()
        for key, val in env.items():
            self.assertIsInstance(val, bool, f"env.{key} must be bool, got {type(val)}")

    def test_env_reads_live_om_strategy_false(self):
        """Reads os.getenv at request time, not import-time cache."""
        with patch.dict(os.environ, {"OM_STRATEGY_ENABLED": "false"}, clear=False):
            env = self._env_block()
        self.assertFalse(env["OM_STRATEGY_ENABLED"])

    def test_env_reads_live_om_strategy_true(self):
        with patch.dict(os.environ, {"OM_STRATEGY_ENABLED": "true"}, clear=False):
            env = self._env_block()
        self.assertTrue(env["OM_STRATEGY_ENABLED"])

    def test_env_legacy_gold_live(self):
        with patch.dict(os.environ, {"LEGACY_GOLD_ENABLED": "true"}, clear=False):
            env = self._env_block()
        self.assertTrue(env["LEGACY_GOLD_ENABLED"])

    def test_env_legacy_forex_live(self):
        with patch.dict(os.environ, {"LEGACY_FOREX_ENABLED": "true"}, clear=False):
            env = self._env_block()
        self.assertTrue(env["LEGACY_FOREX_ENABLED"])


class TestDebugStatusDatabase(unittest.TestCase):
    """database block keys, types, correctness."""

    def setUp(self):
        from dashboard.app import app
        app.config["TESTING"] = True
        self.client = app.test_client()
        resp = self.client.get("/api/debug/status")
        self.data = json.loads(resp.data)["database"]

    def test_database_keys(self):
        for key in ("resolved_path", "exists", "tables",
                    "signals_table", "recent_signal_count_30m",
                    "last_signal_timestamp"):
            self.assertIn(key, self.data, f"Missing database key: {key}")

    def test_resolved_path_is_absolute(self):
        self.assertTrue(
            os.path.isabs(self.data["resolved_path"]),
            f"resolved_path must be absolute, got: {self.data['resolved_path']}"
        )

    def test_resolved_path_matches_db_helper(self):
        """resolved_path must equal _db_path() — no guessing."""
        from db.database import _db_path
        self.assertEqual(self.data["resolved_path"], _db_path())

    def test_exists_is_bool(self):
        self.assertIsInstance(self.data["exists"], bool)

    def test_tables_is_list(self):
        self.assertIsInstance(self.data["tables"], list)

    def test_signals_table_is_none_or_str(self):
        val = self.data["signals_table"]
        self.assertTrue(val is None or isinstance(val, str),
                        f"signals_table must be None or str, got {type(val)}")

    def test_recent_count_is_int_or_none(self):
        val = self.data["recent_signal_count_30m"]
        self.assertTrue(val is None or isinstance(val, int),
                        f"recent_signal_count_30m must be int or None, got {type(val)}")

    def test_no_db_writes(self):
        """Calling the endpoint must not add rows to any table."""
        from db.database import _db_path
        db_path = _db_path()
        if not os.path.exists(db_path):
            self.skipTest("DB not present in this environment")

        conn = sqlite3.connect(db_path)
        cur  = conn.cursor()
        cur.execute("SELECT name FROM sqlite_master WHERE type='table'")
        before = {}
        for (tbl,) in cur.fetchall():
            cur.execute(f"SELECT COUNT(*) FROM {tbl}")
            before[tbl] = cur.fetchone()[0]
        conn.close()

        self.client.get("/api/debug/status")

        conn = sqlite3.connect(db_path)
        cur  = conn.cursor()
        for tbl, cnt in before.items():
            cur.execute(f"SELECT COUNT(*) FROM {tbl}")
            after = cur.fetchone()[0]
            self.assertEqual(cnt, after,
                             f"Table '{tbl}' row count changed after debug call: {cnt} → {after}")
        conn.close()


class TestDebugStatusDbMissing(unittest.TestCase):
    """Endpoint is safe when DB file doesn't exist."""

    def test_safe_when_db_missing(self):
        """No crash, exists=False, tables=[], counts=None."""
        from dashboard.app import app
        app.config["TESTING"] = True
        client = app.test_client()

        with patch("db.database._DB_PATH", "/nonexistent/path/forex.db"):
            resp = client.get("/api/debug/status")

        self.assertEqual(resp.status_code, 200)
        data = json.loads(resp.data)
        db   = data["database"]
        self.assertFalse(db["exists"])
        self.assertEqual(db["tables"], [])
        self.assertIsNone(db["signals_table"])
        self.assertIsNone(db["recent_signal_count_30m"])
        self.assertIsNone(db["last_signal_timestamp"])


class TestDebugStatusScanner(unittest.TestCase):
    """scanner block keys, types, watch_only logic."""

    def setUp(self):
        from dashboard.app import app
        app.config["TESTING"] = True
        self.client = app.test_client()

    def _scanner_block(self, env_overrides=None):
        env = env_overrides or {}
        with patch.dict(os.environ, env, clear=False):
            resp = self.client.get("/api/debug/status")
        return json.loads(resp.data)["scanner"]

    def test_scanner_keys(self):
        sc = self._scanner_block()
        self.assertIn("mode", sc)
        self.assertIn("watch_only", sc)

    def test_mode_is_string(self):
        sc = self._scanner_block()
        self.assertIsInstance(sc["mode"], str)

    def test_watch_only_is_bool(self):
        sc = self._scanner_block()
        self.assertIsInstance(sc["watch_only"], bool)

    def test_watch_only_true_when_om_disabled(self):
        sc = self._scanner_block({"OM_STRATEGY_ENABLED": "false"})
        self.assertTrue(sc["watch_only"],
                        "watch_only must be True when OM_STRATEGY_ENABLED=false")

    def test_watch_only_false_when_om_enabled(self):
        sc = self._scanner_block({"OM_STRATEGY_ENABLED": "true"})
        self.assertFalse(sc["watch_only"],
                         "watch_only must be False when OM_STRATEGY_ENABLED=true")

    def test_mode_nonempty(self):
        sc = self._scanner_block()
        self.assertTrue(len(sc["mode"]) > 0, "mode must be a non-empty string")


if __name__ == "__main__":
    unittest.main()
