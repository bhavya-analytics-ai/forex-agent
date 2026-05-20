"""
version.py — Build/deploy identity for /api/version endpoint.

Resolution order for git_sha:
  1. GIT_SHA env var  (set manually or by CI)
  2. RAILWAY_GIT_COMMIT_SHA env var  (Railway injects this on git-linked deploys)
  3. RAILWAY_GIT_COMMIT_SHA is also tried as RAILWAY_GIT_COMMIT (older Railway name)
  4. Local `git rev-parse HEAD` subprocess call (works in dev, not in Railway container)
  5. "unknown"

Resolution order for git_branch:
  1. GIT_BRANCH env var
  2. RAILWAY_GIT_BRANCH env var
  3. Local `git rev-parse --abbrev-ref HEAD`
  4. "unknown"

build_time_utc: module import time (proxy for process start time).
"""

import logging
import os
import subprocess
from datetime import datetime, timezone

logger = logging.getLogger(__name__)


def _run_git(args: list[str]) -> str:
    """Run a git command and return stripped stdout, or '' on any error."""
    try:
        result = subprocess.run(
            ["git"] + args,
            capture_output=True, text=True, timeout=3,
        )
        if result.returncode == 0:
            return result.stdout.strip()
    except Exception:
        pass
    return ""


def _resolve_sha() -> str:
    for env_var in ("GIT_SHA", "RAILWAY_GIT_COMMIT_SHA", "RAILWAY_GIT_COMMIT"):
        val = os.getenv(env_var, "").strip()
        if val:
            return val
    local = _run_git(["rev-parse", "HEAD"])
    return local or "unknown"


def _resolve_branch() -> str:
    for env_var in ("GIT_BRANCH", "RAILWAY_GIT_BRANCH"):
        val = os.getenv(env_var, "").strip()
        if val:
            return val
    local = _run_git(["rev-parse", "--abbrev-ref", "HEAD"])
    return local or "unknown"


# Resolved once at import time (i.e. process startup)
_SHA    = _resolve_sha()
_BRANCH = _resolve_branch()
_BUILD_TIME = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")


def get_version() -> dict:
    """Return the version payload served by /api/version."""
    return {
        "app":            "forex-agent",
        "git_sha":        _SHA,
        "git_branch":     _BRANCH,
        "build_time_utc": _BUILD_TIME,
    }


def log_startup_version():
    """Log version info at startup. Call once from main.py."""
    v = get_version()
    logger.warning(
        f"[STARTUP] forex-agent | sha={v['git_sha']} branch={v['git_branch']} "
        f"built={v['build_time_utc']}"
    )
