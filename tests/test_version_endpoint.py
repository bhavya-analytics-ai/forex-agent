"""
tests/test_version_endpoint.py

Tests for /api/version endpoint and version.py module.

Covers:
  - get_version() returns required keys with correct types
  - git_sha resolves GIT_SHA env var first
  - git_sha resolves RAILWAY_GIT_COMMIT_SHA second
  - git_sha resolves RAILWAY_GIT_COMMIT third
  - git_sha falls back to "unknown" when no env var and git not available
  - git_branch resolves GIT_BRANCH env var
  - git_branch resolves RAILWAY_GIT_BRANCH env var
  - build_time_utc is a non-empty UTC string
  - /api/version HTTP endpoint returns 200 with correct JSON shape
  - /api/version returns same sha as get_version()
"""

import importlib
import json
import os
import sys
import unittest
from unittest.mock import patch


# ── version module tests ───────────────────────────────────────────────────────

class TestGetVersion(unittest.TestCase):
    """version.get_version() returns correct shape and types."""

    def _fresh_version(self, env: dict):
        """Re-import version module with patched env to test resolution logic."""
        # Patch os.getenv and subprocess so resolution is deterministic
        with patch.dict(os.environ, env, clear=False):
            # Force reimport so module-level _SHA/_BRANCH recompute
            if "version" in sys.modules:
                del sys.modules["version"]
            import version as v
            result = v.get_version()
        # Restore module cache
        if "version" in sys.modules:
            del sys.modules["version"]
        return result

    def test_required_keys_present(self):
        """get_version() must return all four required keys."""
        import version
        v = version.get_version()
        for key in ("app", "git_sha", "git_branch", "build_time_utc"):
            self.assertIn(key, v, f"Missing key: {key}")

    def test_app_name(self):
        """app field must be 'forex-agent'."""
        import version
        self.assertEqual(version.get_version()["app"], "forex-agent")

    def test_all_values_are_strings(self):
        """All values must be strings."""
        import version
        v = version.get_version()
        for key, val in v.items():
            self.assertIsInstance(val, str, f"Key '{key}' must be a string, got {type(val)}")

    def test_git_sha_uses_GIT_SHA_env_first(self):
        """GIT_SHA env var takes priority over RAILWAY_GIT_COMMIT_SHA."""
        env = {
            "GIT_SHA": "aaa1111",
            "RAILWAY_GIT_COMMIT_SHA": "bbb2222",
        }
        v = self._fresh_version(env)
        self.assertEqual(v["git_sha"], "aaa1111")

    def test_git_sha_uses_RAILWAY_GIT_COMMIT_SHA_second(self):
        """RAILWAY_GIT_COMMIT_SHA used when GIT_SHA not set."""
        # Ensure GIT_SHA is absent
        env = {"RAILWAY_GIT_COMMIT_SHA": "ccc3333"}
        # Temporarily unset GIT_SHA
        with patch.dict(os.environ, env, clear=False):
            os.environ.pop("GIT_SHA", None)
            os.environ.pop("RAILWAY_GIT_COMMIT", None)
            if "version" in sys.modules:
                del sys.modules["version"]
            import version as v_mod
            result = v_mod.get_version()
        if "version" in sys.modules:
            del sys.modules["version"]
        self.assertEqual(result["git_sha"], "ccc3333")

    def test_git_sha_uses_RAILWAY_GIT_COMMIT_third(self):
        """RAILWAY_GIT_COMMIT (older name) used as third fallback."""
        with patch.dict(os.environ, {"RAILWAY_GIT_COMMIT": "ddd4444"}, clear=False):
            os.environ.pop("GIT_SHA", None)
            os.environ.pop("RAILWAY_GIT_COMMIT_SHA", None)
            if "version" in sys.modules:
                del sys.modules["version"]
            import version as v_mod
            result = v_mod.get_version()
        if "version" in sys.modules:
            del sys.modules["version"]
        self.assertEqual(result["git_sha"], "ddd4444")

    def test_git_sha_falls_back_to_unknown_when_no_env_no_git(self):
        """When no env vars and git subprocess fails, sha='unknown'."""
        with patch.dict(os.environ, {}, clear=False):
            os.environ.pop("GIT_SHA", None)
            os.environ.pop("RAILWAY_GIT_COMMIT_SHA", None)
            os.environ.pop("RAILWAY_GIT_COMMIT", None)
            if "version" in sys.modules:
                del sys.modules["version"]
            # Patch subprocess so git call fails
            with patch("subprocess.run", side_effect=FileNotFoundError("git not found")):
                import version as v_mod
                result = v_mod.get_version()
        if "version" in sys.modules:
            del sys.modules["version"]
        self.assertEqual(result["git_sha"], "unknown")

    def test_git_branch_uses_GIT_BRANCH_env(self):
        """GIT_BRANCH env var used for branch."""
        with patch.dict(os.environ, {"GIT_BRANCH": "feature/test"}, clear=False):
            os.environ.pop("RAILWAY_GIT_BRANCH", None)
            if "version" in sys.modules:
                del sys.modules["version"]
            import version as v_mod
            result = v_mod.get_version()
        if "version" in sys.modules:
            del sys.modules["version"]
        self.assertEqual(result["git_branch"], "feature/test")

    def test_git_branch_uses_RAILWAY_GIT_BRANCH(self):
        """RAILWAY_GIT_BRANCH used when GIT_BRANCH not set."""
        with patch.dict(os.environ, {"RAILWAY_GIT_BRANCH": "main"}, clear=False):
            os.environ.pop("GIT_BRANCH", None)
            if "version" in sys.modules:
                del sys.modules["version"]
            import version as v_mod
            result = v_mod.get_version()
        if "version" in sys.modules:
            del sys.modules["version"]
        self.assertEqual(result["git_branch"], "main")

    def test_build_time_utc_contains_utc(self):
        """build_time_utc must contain 'UTC'."""
        import version
        self.assertIn("UTC", version.get_version()["build_time_utc"])

    def test_build_time_utc_nonempty(self):
        """build_time_utc must not be empty or 'unknown'."""
        import version
        bt = version.get_version()["build_time_utc"]
        self.assertTrue(bt and bt != "unknown",
                        f"build_time_utc should be a real timestamp, got: {bt}")


# ── /api/version HTTP endpoint tests ──────────────────────────────────────────

class TestVersionEndpoint(unittest.TestCase):
    """
    /api/version endpoint returns correct JSON via Flask test client.
    Does not require a live Railway deployment.
    """

    def setUp(self):
        from dashboard.app import app
        app.config["TESTING"] = True
        self.client = app.test_client()

    def test_version_endpoint_returns_200(self):
        resp = self.client.get("/api/version")
        self.assertEqual(resp.status_code, 200,
                         f"Expected 200, got {resp.status_code}")

    def test_version_endpoint_returns_json(self):
        resp = self.client.get("/api/version")
        self.assertEqual(resp.content_type, "application/json",
                         "Response must be application/json")

    def test_version_endpoint_required_keys(self):
        resp = self.client.get("/api/version")
        data = json.loads(resp.data)
        for key in ("app", "git_sha", "git_branch", "build_time_utc"):
            self.assertIn(key, data, f"Missing key in /api/version response: {key}")

    def test_version_endpoint_app_name(self):
        resp = self.client.get("/api/version")
        data = json.loads(resp.data)
        self.assertEqual(data["app"], "forex-agent")

    def test_version_endpoint_git_sha_nonempty(self):
        resp = self.client.get("/api/version")
        data = json.loads(resp.data)
        self.assertIsInstance(data["git_sha"], str)
        self.assertTrue(len(data["git_sha"]) > 0,
                        "git_sha must be non-empty string")

    def test_version_endpoint_sha_matches_get_version(self):
        """HTTP endpoint returns same sha as get_version() module call."""
        import version
        expected_sha = version.get_version()["git_sha"]
        resp = self.client.get("/api/version")
        data = json.loads(resp.data)
        self.assertEqual(data["git_sha"], expected_sha,
                         "HTTP endpoint sha must match version.get_version()")

    def test_version_endpoint_build_time_utc(self):
        resp = self.client.get("/api/version")
        data = json.loads(resp.data)
        self.assertIn("UTC", data["build_time_utc"])


if __name__ == "__main__":
    unittest.main()
