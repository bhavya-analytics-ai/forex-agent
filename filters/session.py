"""
session.py — Trading session detection and scoring

Sessions (UTC):
  Tokyo:    00:00 – 06:00   JPY pairs, ranging
  London:   07:00 – 12:00   GBP/EUR pairs, trending
  New York: 13:00 – 22:00   USD/metals, trending

BUG FIXES:
- London session was missing entirely
- Only had old 5 pairs — updated to all 11
- Off-hours pair list now pulled from config dynamically
"""

from datetime import datetime, time, timedelta
import logging
from config import SESSIONS, PAIRS

logger = logging.getLogger(__name__)


def get_current_session() -> str:
    """Return which session is currently active."""
    now = datetime.utcnow().time()

    tokyo_start  = time(0,  0)
    tokyo_end    = time(6,  0)
    london_start = time(7,  0)
    london_end   = time(12, 0)
    ny_start     = time(13, 0)
    ny_end       = time(22, 0)

    if tokyo_start <= now <= tokyo_end:
        return "tokyo"
    elif london_start <= now <= london_end:
        return "london"
    elif ny_start <= now <= ny_end:
        return "new_york"
    else:
        return "off_hours"


# Pair activity by session
# active   = best pairs to trade this session
# inactive = pairs to deprioritize
SESSION_PAIRS = {
    "tokyo": {
        "active":    ["USD_JPY", "GBP_JPY", "EUR_JPY", "CHF_JPY", "CAD_JPY", "NZD_JPY"],
        "secondary": ["XAU_USD", "XAG_USD"],
        "inactive":  ["GBP_USD", "EUR_USD", "EUR_GBP"],
        "character": "ranging",
        "note":      "Tokyo — JPY pairs most active, range-bound sessions, S/R bounces favored",
    },
    "london": {
        "active":    ["GBP_JPY", "GBP_USD", "EUR_USD", "EUR_GBP", "EUR_JPY"],
        "secondary": ["CHF_JPY", "XAU_USD"],
        "inactive":  ["CAD_JPY", "NZD_JPY", "XAG_USD"],
        "character": "trending",
        "note":      "London Open — GBP/EUR pairs most active, trending moves, breakout setups favored",
    },
    "new_york": {
        "active":    ["GBP_USD", "EUR_USD", "XAU_USD", "USD_JPY", "GBP_JPY"],
        "secondary": ["EUR_JPY", "CHF_JPY", "XAG_USD", "EUR_GBP"],
        "inactive":  ["CAD_JPY", "NZD_JPY"],
        "character": "trending",
        "note":      "New York — USD pairs and Gold most active, trend continuation favored",
    },
    "off_hours": {
        "active":    [],
        "secondary": [],
        "inactive":  PAIRS,   # All pairs inactive off-hours
        "character": "avoid",
        "note":      "Off-hours — low liquidity, avoid new positions",
    },
}


def get_session_context(pair: str) -> dict:
    """
    Return session context and pair-specific score for current session.

    Score breakdown (max 15):
      Active pair + trending session  → 15
      Active pair + ranging session   → 10
      Secondary pair                  → 7
      Inactive pair                   → 3
      Off-hours                       → 0
    """
    session = get_current_session()
    ctx     = SESSION_PAIRS.get(session, SESSION_PAIRS["off_hours"])

    is_active    = pair in ctx["active"]
    is_secondary = pair in ctx.get("secondary", [])
    character    = ctx["character"]

    if session == "off_hours":
        score = 0
    elif is_active and character == "trending":
        score = 15
    elif is_active and character == "ranging":
        score = 10
    elif is_secondary:
        score = 7
    else:
        score = 3

    return {
        "session":     session,
        "pair_active": is_active,
        "character":   character,
        "score":       score,
        "note":        _session_note(session, pair, is_active, is_secondary, character),
    }


def _session_note(
    session: str,
    pair: str,
    is_active: bool,
    is_secondary: bool,
    character: str,
) -> str:
    if session == "off_hours":
        return "Off-hours — low liquidity, avoid new positions"
    if not is_active and not is_secondary:
        return f"{pair} is less active during {session.replace('_', ' ').title()} session"
    if is_secondary:
        return f"{pair} is secondary during {session.replace('_', ' ').title()} — valid if setup is A/A+"
    if character == "ranging":
        return "Tokyo session — range play, S/R bounces more reliable than breakouts"
    if character == "trending":
        sess_name = session.replace("_", " ").title()
        return f"{sess_name} — trending conditions, breakout/retest setups favored"
    return ""


def minutes_to_session(session: str) -> int:
    """How many minutes until the next session open."""
    cfg = SESSIONS.get(session, {})
    if not cfg:
        return 999

    h, m = map(int, cfg["start"].split(":"))
    now  = datetime.utcnow()

    target = now.replace(hour=h, minute=m, second=0, microsecond=0)
    if target <= now:
        target += timedelta(days=1)

    return int((target - now).total_seconds() / 60)


def is_briefing_time(session: str, window_minutes: int = 45) -> bool:
    """
    True if we're within `window_minutes` before a session open.
    Used by scheduler to trigger pre-session briefings.
    """
    mins = minutes_to_session(session)
    return 0 <= mins <= window_minutes