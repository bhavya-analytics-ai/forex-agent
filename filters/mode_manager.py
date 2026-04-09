"""
filters/mode_manager.py — Strategy mode detection and routing

Two modes:
  normal      — standard Bayesian scorer + gold/forex strategy
  news_sniper — news spike + M1 CHoCH + aggressive NEWS_LIKELIHOODS

Mode selection (priority order):
  1. Manual override (dashboard toggle) — always wins
  2. Auto-detect — HIGH impact news within 15 minutes
  3. Default — normal mode

The two likelihood tables never mix.
NEWS_LIKELIHOODS only passed to scorer when news_sniper is active.
"""

import logging
import threading
from datetime import datetime, timedelta

logger = logging.getLogger(__name__)

# ── MODE STATE ────────────────────────────────────────────────────────────────

_lock          = threading.Lock()
_manual_override = None   # None = no override, "normal" or "news_sniper"
_auto_mode       = "normal"
_last_auto_check = None
_AUTO_CHECK_INTERVAL_SECS = 60   # re-evaluate auto mode every 60 seconds
_NEWS_WINDOW_MINS         = 15   # auto-switch if HIGH news within 15 mins


# ── AUTO DETECTION ────────────────────────────────────────────────────────────

def _check_auto_mode() -> str:
    """
    Auto-detects whether news sniper mode should be active.
    Checks ForexFactory feed for HIGH-impact events within 15 minutes.
    Returns "news_sniper" or "normal".
    """
    try:
        from filters.news import fetch_forexfactory_calendar
        df  = fetch_forexfactory_calendar()
        now = datetime.utcnow()

        if df.empty:
            return "normal"

        window_start = now - timedelta(minutes=5)    # 5 min post-news still active
        window_end   = now + timedelta(minutes=_NEWS_WINDOW_MINS)

        mask = (
            (df["impact"] == "HIGH") &
            (df["time"] >= window_start) &
            (df["time"] <= window_end)
        )
        if df[mask].shape[0] > 0:
            return "news_sniper"

    except Exception as e:
        logger.warning(f"Auto mode check failed: {e}")

    return "normal"


def refresh_auto_mode():
    """Refresh the auto-detected mode. Called each scan cycle."""
    global _auto_mode, _last_auto_check
    now = datetime.utcnow()

    with _lock:
        if (
            _last_auto_check is None
            or (now - _last_auto_check).total_seconds() >= _AUTO_CHECK_INTERVAL_SECS
        ):
            _auto_mode       = _check_auto_mode()
            _last_auto_check = now
            logger.info(f"Auto mode refreshed: {_auto_mode}")


# ── MANUAL TOGGLE ─────────────────────────────────────────────────────────────

def set_manual_mode(mode: str):
    """
    Set manual override from dashboard toggle.
    mode: "normal" | "news_sniper" | None (clear override)
    """
    global _manual_override
    with _lock:
        if mode in ("normal", "news_sniper", None):
            _manual_override = mode
            logger.info(f"Manual mode override set to: {mode}")


def clear_manual_override():
    """Remove manual override — system returns to auto-detect."""
    global _manual_override
    with _lock:
        _manual_override = None
        logger.info("Manual override cleared — auto-detect resumed")


# ── ACTIVE MODE GETTER ────────────────────────────────────────────────────────

def get_active_mode() -> str:
    """
    Returns the currently active strategy mode.
    Manual override always wins over auto-detect.
    """
    with _lock:
        if _manual_override is not None:
            return _manual_override
        return _auto_mode


def get_mode_info() -> dict:
    """
    Returns full mode state for dashboard display.
    """
    with _lock:
        active   = _manual_override if _manual_override is not None else _auto_mode
        is_manual = _manual_override is not None
        return {
            "mode":       active,
            "is_manual":  is_manual,
            "is_news":    active == "news_sniper",
            "source":     "manual" if is_manual else "auto",
            "label":      "NEWS SNIPER ACTIVE" if active == "news_sniper" else "NORMAL",
        }


# ── SCORER ROUTER ─────────────────────────────────────────────────────────────

def get_likelihoods_for_mode() -> dict:
    """
    Returns the correct likelihood table for the active mode.
    STANDARD_LIKELIHOODS for normal, NEWS_LIKELIHOODS for news_sniper.
    The scorer never decides which table to use — mode_manager does.
    """
    from alerts.scorer import STANDARD_LIKELIHOODS, NEWS_LIKELIHOODS
    mode = get_active_mode()
    return NEWS_LIKELIHOODS if mode == "news_sniper" else STANDARD_LIKELIHOODS


def apply_strategy(scored: dict, confluence: dict, pair: str, candles: dict = None) -> dict:
    """
    Route to the correct strategy based on active mode.

    Normal mode:      gold_strategy or forex_strategy (via decision_layer)
    News sniper mode: news_sniper for all pairs
    """
    mode = get_active_mode()

    if mode == "news_sniper":
        from strategies.news_sniper import apply_news_sniper
        return apply_news_sniper(scored, confluence, pair, candles or {})

    from filters.decision_layer import apply_decision_layer
    return apply_decision_layer(scored, confluence, pair)
