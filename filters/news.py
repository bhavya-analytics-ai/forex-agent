"""
news.py — Economic calendar filter
Fetches high-impact news events and blocks signals around them.
Uses ForexFactory calendar (free, no API key needed).
"""

import requests
import pandas as pd
from datetime import datetime, timedelta
import logging
from config import NEWS_CONFIG

logger = logging.getLogger(__name__)

# Cache to avoid hammering the calendar endpoint
_news_cache = {"data": None, "fetched_at": None}
CACHE_MINUTES = 30


def fetch_forexfactory_calendar() -> pd.DataFrame:
    """
    Fetch today's economic calendar from ForexFactory JSON feed.
    Returns DataFrame of events with time, currency, impact, event name.
    """
    global _news_cache

    now = datetime.utcnow()

    # Return cached data if fresh
    if (
        _news_cache["data"] is not None
        and _news_cache["fetched_at"] is not None
        and (now - _news_cache["fetched_at"]).seconds < CACHE_MINUTES * 60
    ):
        return _news_cache["data"]

    try:
        # ForexFactory provides a JSON calendar feed
        url = "https://nfs.faireconomy.media/ff_calendar_thisweek.json"
        headers = {"User-Agent": "Mozilla/5.0"}
        resp = requests.get(url, headers=headers, timeout=10)
        resp.raise_for_status()
        data = resp.json()

        events = []
        for item in data:
            try:
                # Parse event datetime (ForexFactory uses EST)
                date_str = item.get("date", "")
                time_str = item.get("time", "")
                if not date_str or not time_str or time_str in ["All Day", "Tentative"]:
                    continue

                dt_str = f"{date_str} {time_str}"
                # Try multiple formats
                for fmt in ["%m-%d-%Y %I:%M%p", "%Y-%m-%dT%H:%M:%S"]:
                    try:
                        dt_est = datetime.strptime(dt_str, fmt)
                        break
                    except ValueError:
                        continue
                else:
                    continue

                # Convert EST → UTC (EST = UTC-5, EDT = UTC-4, use -5 conservatively)
                dt_utc = dt_est + timedelta(hours=5)

                events.append({
                    "time":     dt_utc,
                    "currency": item.get("country", "").upper(),
                    "impact":   item.get("impact", "").upper(),
                    "event":    item.get("title", ""),
                })
            except Exception:
                continue

        df = pd.DataFrame(events)
        if not df.empty:
            df = df[df["impact"].isin(["HIGH", "MEDIUM", "LOW"])]
            df = df.sort_values("time").reset_index(drop=True)

        _news_cache["data"]       = df
        _news_cache["fetched_at"] = now
        logger.info(f"Fetched {len(df)} calendar events")
        return df

    except Exception as e:
        logger.warning(f"Could not fetch ForexFactory calendar: {e}")
        return pd.DataFrame(columns=["time", "currency", "impact", "event"])


def get_upcoming_events(pair: str, minutes_ahead: int = 120) -> list:
    """
    Return upcoming high/medium impact events for currencies in this pair.
    """
    currencies = NEWS_CONFIG["pair_currencies"].get(pair, [])
    impact_filter = NEWS_CONFIG["impact_levels"]

    df = fetch_forexfactory_calendar()
    if df.empty:
        return []

    now = datetime.utcnow()
    window_end = now + timedelta(minutes=minutes_ahead)

    mask = (
        df["currency"].isin(currencies) &
        df["impact"].isin(impact_filter) &
        (df["time"] >= now) &
        (df["time"] <= window_end)
    )

    upcoming = df[mask].to_dict("records")
    return upcoming


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
        return {"safe": True, "reason": "No calendar data (proceeding with caution)", "events": []}

    now = datetime.utcnow()

    # Check for news in block window (before) or resume window (after)
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
    Get all high-impact events for the upcoming session.
    Used in pre-session briefing.
    session: 'tokyo' or 'new_york'
    """
    from config import SESSIONS, PAIRS

    session_cfg  = SESSIONS[session]
    session_start = datetime.utcnow().replace(
        hour=int(session_cfg["start"].split(":")[0]),
        minute=int(session_cfg["start"].split(":")[1]),
        second=0, microsecond=0,
    )
    session_end = session_start.replace(
        hour=int(session_cfg["end"].split(":")[0]),
        minute=int(session_cfg["end"].split(":")[1]),
    )

    # Get all currencies across all pairs
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