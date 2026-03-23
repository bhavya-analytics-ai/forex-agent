"""
news.py — Economic calendar filter
Fetches high-impact news events and blocks signals around them.
Uses ForexFactory calendar JSON feed (free, no API key needed).

BUG FIX:
- ForexFactory returns dates as "01/19/2025" and times as "8:30am"
  Previous format strings used wrong separators and wrong time format
  causing ALL events to fail parsing and returning 0 results.
- Added EDT offset detection (UTC-4 in summer, UTC-5 in winter)
"""

import requests
import pandas as pd
from datetime import datetime, timedelta
import logging
from config import NEWS_CONFIG

logger = logging.getLogger(__name__)

_news_cache    = {"data": None, "fetched_at": None}
CACHE_MINUTES  = 30


def _est_offset() -> int:
    """
    Return EST/EDT offset from UTC.
    EDT (Mar–Nov): UTC-4 → add 4 hours to convert to UTC
    EST (Nov–Mar): UTC-5 → add 5 hours
    """
    now   = datetime.utcnow()
    month = now.month
    # EDT roughly March–November
    if 3 <= month <= 11:
        return 4
    return 5


def fetch_forexfactory_calendar() -> pd.DataFrame:
    """
    Fetch this week's economic calendar from ForexFactory JSON feed.
    Returns DataFrame: time (UTC), currency, impact, event
    """
    global _news_cache

    now = datetime.utcnow()

    if (
        _news_cache["data"] is not None
        and _news_cache["fetched_at"] is not None
        and (now - _news_cache["fetched_at"]).total_seconds() < CACHE_MINUTES * 60
    ):
        return _news_cache["data"]

    try:
        url     = "https://nfs.faireconomy.media/ff_calendar_thisweek.json"
        headers = {"User-Agent": "Mozilla/5.0"}
        resp    = requests.get(url, headers=headers, timeout=10)
        resp.raise_for_status()
        data    = resp.json()

        offset = _est_offset()
        events = []

        for item in data:
            try:
                date_str = item.get("date", "").strip()
                time_str = item.get("time", "").strip()

                if not date_str or not time_str:
                    continue
                if time_str.lower() in ["all day", "tentative", ""]:
                    continue

                # ForexFactory format: "01/19/2025" and "8:30am" / "12:00pm"
                dt_str = f"{date_str} {time_str.upper()}"

                dt_local = None
                for fmt in [
                    "%m/%d/%Y %I:%M%p",   # "01/19/2025 8:30AM"
                    "%m/%d/%Y %I%p",      # "01/19/2025 8AM"  (no minutes)
                    "%Y-%m-%dT%H:%M:%S",  # ISO fallback
                ]:
                    try:
                        dt_local = datetime.strptime(dt_str, fmt)
                        break
                    except ValueError:
                        continue

                if dt_local is None:
                    logger.debug(f"Could not parse event time: '{dt_str}'")
                    continue

                # Convert local (EST/EDT) → UTC
                dt_utc = dt_local + timedelta(hours=offset)

                events.append({
                    "time":     dt_utc,
                    "currency": item.get("country", "").upper(),
                    "impact":   item.get("impact",  "").upper(),
                    "event":    item.get("title",   ""),
                })

            except Exception as parse_err:
                logger.debug(f"Skipped event: {parse_err}")
                continue

        df = pd.DataFrame(events) if events else pd.DataFrame(
            columns=["time", "currency", "impact", "event"]
        )

        if not df.empty:
            df = df[df["impact"].isin(["HIGH", "MEDIUM", "LOW"])]
            df = df.sort_values("time").reset_index(drop=True)

        _news_cache["data"]       = df
        _news_cache["fetched_at"] = now
        logger.info(f"Fetched {len(df)} calendar events from ForexFactory")
        return df

    except Exception as e:
        logger.warning(f"Could not fetch ForexFactory calendar: {e}")
        return pd.DataFrame(columns=["time", "currency", "impact", "event"])


def get_upcoming_events(pair: str, minutes_ahead: int = 120) -> list:
    """
    Return upcoming high-impact events for currencies in this pair.
    """
    currencies    = NEWS_CONFIG["pair_currencies"].get(pair, [])
    impact_filter = NEWS_CONFIG["impact_levels"]

    df = fetch_forexfactory_calendar()
    if df.empty:
        return []

    now        = datetime.utcnow()
    window_end = now + timedelta(minutes=minutes_ahead)

    mask = (
        df["currency"].isin(currencies) &
        df["impact"].isin(impact_filter) &
        (df["time"] >= now) &
        (df["time"] <= window_end)
    )

    return df[mask].to_dict("records")


def is_news_safe(pair: str) -> dict:
    """
    Check if it's safe to trade this pair right now.
    Returns: { safe: bool, reason: str, events: list }
    """
    block_window  = NEWS_CONFIG["block_window_minutes"]
    resume_window = NEWS_CONFIG["resume_window_minutes"]
    currencies    = NEWS_CONFIG["pair_currencies"].get(pair, [])
    impact_filter = NEWS_CONFIG["impact_levels"]

    df = fetch_forexfactory_calendar()
    if df.empty:
        return {
            "safe":   True,
            "reason": "No calendar data available — proceeding with caution",
            "events": [],
        }

    now  = datetime.utcnow()
    mask = (
        df["currency"].isin(currencies) &
        df["impact"].isin(impact_filter) &
        (df["time"] >= now - timedelta(minutes=resume_window)) &
        (df["time"] <= now + timedelta(minutes=block_window))
    )

    flagged = df[mask].to_dict("records")

    if flagged:
        events_str = ", ".join([
            f"{e['currency']} {e['event']} @ {e['time'].strftime('%H:%M')} UTC"
            for e in flagged
        ])
        return {
            "safe":   False,
            "reason": f"High-impact news nearby: {events_str}",
            "events": flagged,
        }

    return {"safe": True, "reason": "Clear of high-impact news", "events": []}


def get_session_news_summary(session: str) -> list:
    """
    Get all high-impact events during the upcoming session window.
    Used in pre-session briefing.
    """
    from config import SESSIONS, PAIRS

    session_cfg = SESSIONS.get(session, {})
    if not session_cfg:
        return []

    now = datetime.utcnow()

    sh, sm = map(int, session_cfg["start"].split(":"))
    eh, em = map(int, session_cfg["end"].split(":"))

    session_start = now.replace(hour=sh, minute=sm, second=0, microsecond=0)
    session_end   = now.replace(hour=eh, minute=em, second=0, microsecond=0)

    # If session already passed today, look at tomorrow
    if session_end < now:
        session_start += timedelta(days=1)
        session_end   += timedelta(days=1)

    all_currencies = set()
    for p in PAIRS:
        all_currencies.update(NEWS_CONFIG["pair_currencies"].get(p, []))

    df = fetch_forexfactory_calendar()
    if df.empty:
        return []

    mask = (
        df["currency"].isin(all_currencies) &
        df["impact"].isin(["HIGH"]) &
        (df["time"] >= session_start) &
        (df["time"] <= session_end)
    )

    return df[mask].to_dict("records")