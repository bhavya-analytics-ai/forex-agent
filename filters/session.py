"""
session.py — Trading session detection and bias weighting
Tokyo: 00:00–06:00 UTC | New York: 13:00–22:00 UTC
"""

from datetime import datetime, time
import logging
from config import SESSIONS

logger = logging.getLogger(__name__)


def get_current_session() -> str:
    """Return which session is currently active."""
    now = datetime.utcnow().time()

    tokyo_start = time(0, 0)
    tokyo_end   = time(6, 0)
    ny_start    = time(13, 0)
    ny_end      = time(22, 0)

    if tokyo_start <= now <= tokyo_end:
        return "tokyo"
    elif ny_start <= now <= ny_end:
        return "new_york"
    else:
        return "off_hours"


def get_session_context(pair: str) -> dict:
    """
    Return session context and pair-specific bias for current session.

    Tokyo:    JPY pairs most active, often range-bound
    New York: USD pairs most active, trend/breakout moves
    """
    session = get_current_session()

    # Pair activity by session
    session_pairs = {
        "tokyo": {
            "active":   ["USD_JPY", "GBP_JPY", "EUR_JPY"],
            "inactive": ["XAU_USD", "XAG_USD"],
            "character": "ranging",  # Tokyo tends to consolidate
        },
        "new_york": {
            "active":   ["USD_JPY", "XAU_USD", "XAG_USD"],
            "inactive": [],
            "character": "trending",  # NY tends to trend/break
        },
        "off_hours": {
            "active":   [],
            "inactive": ["USD_JPY", "GBP_JPY", "EUR_JPY", "XAU_USD", "XAG_USD"],
            "character": "avoid",
        },
    }

    ctx = session_pairs.get(session, session_pairs["off_hours"])
    is_active = pair in ctx["active"]
    character = ctx["character"]

    # Score: active pair in trending session = highest
    if session == "off_hours":
        score = 0
    elif is_active and character == "trending":
        score = 15
    elif is_active and character == "ranging":
        score = 10
    else:
        score = 5

    return {
        "session":    session,
        "pair_active": is_active,
        "character":  character,
        "score":      score,
        "note":       _session_note(session, pair, is_active, character),
    }


def _session_note(session: str, pair: str, is_active: bool, character: str) -> str:
    if session == "off_hours":
        return "Off-hours — low liquidity, avoid new positions"
    if not is_active:
        return f"{pair} is less active during {session.replace('_', ' ').title()} session"
    if character == "ranging":
        return f"Tokyo session — expect range play, S/R bounces more reliable than breakouts"
    if character == "trending":
        return f"New York session — trending conditions, breakout/retest setups favored"
    return ""


def minutes_to_session(session: str) -> int:
    """How many minutes until the next session open."""
    cfg   = SESSIONS.get(session, {})
    start = cfg.get("start", "00:00")
    h, m  = map(int, start.split(":"))

    now        = datetime.utcnow()
    target     = now.replace(hour=h, minute=m, second=0, microsecond=0)
    if target < now:
        from datetime import timedelta
        target += timedelta(days=1)

    delta = target - now
    return int(delta.total_seconds() / 60)


def is_briefing_time(session: str, window_minutes: int = 45) -> bool:
    """
    Returns True if we're within `window_minutes` before a session open.
    Used by scheduler to know when to send the pre-session briefing.
    """
    mins = minutes_to_session(session)
    return 0 <= mins <= window_minutes