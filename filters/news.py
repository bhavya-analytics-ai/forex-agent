"""
filters/news.py — Economic calendar filter

FIXES & ADDITIONS:
1. MEDIUM impact now returns a WARNING (not a block, but flagged)
   Previously only HIGH was checked — medium events like PMI, Retail
   Sales were completely ignored. These move markets 50-100 pips.

2. POST-NEWS SPIKE DETECTION
   After a high-impact news event, detect the spike candle and look for
   the ICT setup: liquidity sweep → ChoCH → entry in opposite direction.
   This is one of the cleanest setups in existence — we now catch it.

3. DASHBOARD DATA FUNCTION
   get_news_dashboard_data() returns upcoming events formatted for
   the dashboard news ticker with countdown timers.

4. CAUTION vs BLOCK logic
   HIGH impact within 60 min → BLOCK (safe=False)
   MEDIUM impact within 30 min → CAUTION (safe=True but warn flag)
   Post-news within 30 min → flag for spike setup opportunity
"""

import os
import requests
import pandas as pd
from datetime import datetime, timedelta, timezone
import logging
from config import NEWS_CONFIG

logger = logging.getLogger(__name__)

_news_cache             = {"data": None, "fetched_at": None, "source": None}
CACHE_MINUTES           = 60    # normal cache — refresh once per hour
_CACHE_NEAR_EVENT_SECS  = 20    # adaptive: poll fast when HIGH event < 5 mins away
_NEAR_EVENT_WINDOW_MINS = 5
_CACHE_FAILURE_SECS     = 300   # on total failure: wait 5 min before retrying
_finnhub_403            = False  # latched True if Finnhub returns 403 (paid-only endpoint)


def _adaptive_ttl_seconds(cached_df) -> int:
    """
    Shorter TTL when a HIGH impact event is imminent (to catch actual vs forecast).
    Returns failure backoff TTL if cache is empty (both sources failed last time).
    """
    if cached_df is None or cached_df.empty:
        return _CACHE_FAILURE_SECS  # both failed — wait 5 min before retrying
    now = datetime.utcnow()
    try:
        near = cached_df[
            (cached_df["impact"] == "HIGH") &
            (cached_df["time"] >= now - timedelta(minutes=1)) &
            (cached_df["time"] <= now + timedelta(minutes=_NEAR_EVENT_WINDOW_MINS))
        ]
        if not near.empty:
            return _CACHE_NEAR_EVENT_SECS
    except Exception:
        pass
    return CACHE_MINUTES * 60


def _fetch_finnhub_raw() -> pd.DataFrame:
    """
    Fetch economic calendar from Finnhub (primary source).
    Returns empty DataFrame if key not set, 403 (paid-only), or fetch fails.
    Includes actual vs forecast data when available.
    """
    global _finnhub_403

    _EMPTY = pd.DataFrame(columns=["time", "currency", "impact", "event", "forecast", "previous", "actual"])

    if _finnhub_403:
        return _EMPTY   # already confirmed 403 — don't retry

    api_key = os.getenv("FINNHUB_API_KEY", "")
    if not api_key or api_key == "your_finnhub_key_here":
        return _EMPTY

    now       = datetime.utcnow()
    from_date = now.strftime("%Y-%m-%d")
    to_date   = (now + timedelta(days=2)).strftime("%Y-%m-%d")

    try:
        resp = requests.get(
            "https://finnhub.io/api/v1/calendar/economic",
            params={"from": from_date, "to": to_date, "token": api_key},
            headers={"User-Agent": "Mozilla/5.0"},
            timeout=10,
        )
        resp.raise_for_status()
        data = resp.json()

        events = []
        for item in data.get("economicCalendar", []):
            try:
                raw_time = item.get("time", "")
                if not raw_time:
                    continue
                dt = datetime.fromisoformat(raw_time.replace("Z", "+00:00"))
                if dt.tzinfo is not None:
                    dt = dt.astimezone(timezone.utc).replace(tzinfo=None)

                impact_map = {"high": "HIGH", "medium": "MEDIUM", "low": "LOW"}
                impact = impact_map.get(item.get("impact", "").lower(), "")
                if not impact:
                    continue

                events.append({
                    "time":     dt,
                    "currency": item.get("currency", "").upper(),
                    "impact":   impact,
                    "event":    item.get("event", ""),
                    "forecast": str(item.get("estimate", "")) if item.get("estimate") is not None else "",
                    "previous": str(item.get("prev", ""))     if item.get("prev")     is not None else "",
                    "actual":   str(item.get("actual", ""))   if item.get("actual")   is not None else "",
                })
            except Exception as e:
                logger.debug(f"Finnhub parse: {e}")
                continue

        if not events:
            return pd.DataFrame(columns=["time", "currency", "impact", "event", "forecast", "previous", "actual"])

        df = pd.DataFrame(events).sort_values("time").reset_index(drop=True)
        logger.info(f"Finnhub: {len(df)} calendar events ✓")
        return df

    except Exception as e:
        if "403" in str(e):
            _finnhub_403 = True
            logger.warning("Finnhub 403 — economic calendar is a paid feature. Switching to ForexFactory only.")
        else:
            logger.warning(f"Finnhub calendar failed: {e}")
        return _EMPTY


def _est_offset() -> int:
    now   = datetime.utcnow()
    month = now.month
    if 3 <= month <= 11:
        return 4
    return 5


def fetch_forexfactory_calendar() -> pd.DataFrame:
    global _news_cache

    now = datetime.utcnow()
    ttl = _adaptive_ttl_seconds(_news_cache.get("data"))

    if (
        _news_cache["data"] is not None
        and _news_cache["fetched_at"] is not None
        and (now - _news_cache["fetched_at"]).total_seconds() < ttl
    ):
        return _news_cache["data"]

    # Stamp fetched_at NOW so if both sources fail,
    # the 11 pairs don't all retry on the same scan cycle
    _news_cache["fetched_at"] = now

    # ── PRIMARY: Finnhub ───────────────────────────────────────────────────────
    df = _fetch_finnhub_raw()
    if not df.empty:
        _news_cache["data"]   = df
        _news_cache["source"] = "finnhub"
        return df

    # ── FALLBACK: ForexFactory ─────────────────────────────────────────────────
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

                if not date_str:
                    continue

                # Skip all-day / tentative entries (no fixed time)
                if time_str.lower() in ["all day", "tentative"]:
                    continue

                # nfs.faireconomy.media embeds full datetime in "date" field:
                #   "2026-03-23T08:45:00-04:00"  ← ISO 8601 with tz offset
                # Older / fallback format may be just a date with separate "time" field.
                dt_utc  = None
                dt_local = None

                if "T" in date_str:
                    # Full ISO 8601 datetime — parse and convert to UTC directly
                    try:
                        dt_aware = datetime.fromisoformat(date_str)
                        dt_utc   = dt_aware.astimezone(timezone.utc).replace(tzinfo=None)
                    except Exception:
                        # Strip tz suffix and treat as EST
                        clean    = date_str[:19]
                        dt_local = datetime.strptime(clean, "%Y-%m-%dT%H:%M:%S")
                        dt_utc   = dt_local + timedelta(hours=offset)
                else:
                    # Plain date + separate time field (legacy format)
                    if not time_str:
                        continue
                    combined = f"{date_str} {time_str}"
                    for fmt in ("%Y-%m-%d %I:%M%p", "%Y-%m-%d %H:%M", "%b %d, %Y %I:%M%p"):
                        try:
                            dt_local = datetime.strptime(combined, fmt)
                            break
                        except ValueError:
                            continue
                    if dt_local is None:
                        continue
                    dt_utc = dt_local + timedelta(hours=offset)

                if dt_utc is None:
                    continue

                events.append({
                    "time":     dt_utc,
                    "currency": item.get("country", "").upper(),
                    "impact":   item.get("impact",  "").upper(),
                    "event":    item.get("title",   ""),
                    "forecast": item.get("forecast", ""),
                    "previous": item.get("previous", ""),
                    "actual":   str(item.get("actual", "") or ""),
                })

            except Exception as parse_err:
                logger.debug(f"Skipped event: {parse_err}")
                continue

        _COLS = ["time", "currency", "impact", "event", "forecast", "previous", "actual"]
        df = pd.DataFrame(events) if events else pd.DataFrame(columns=_COLS)

        if not df.empty:
            df = df[df["impact"].isin(["HIGH", "MEDIUM", "LOW"])]
            df = df.sort_values("time").reset_index(drop=True)

        _news_cache["data"]       = df
        _news_cache["fetched_at"] = now
        logger.info(f"Fetched {len(df)} calendar events from ForexFactory ✓")
        return df

    except Exception as e:
        logger.warning(f"Could not fetch ForexFactory calendar: {e}")
        # Return cached data if available even if stale
        if _news_cache["data"] is not None:
            logger.info("Using stale news cache as fallback")
            return _news_cache["data"]
        return pd.DataFrame(columns=["time", "currency", "impact", "event", "forecast", "previous", "actual"])


def get_upcoming_events(pair: str, minutes_ahead: int = 120) -> list:
    currencies    = NEWS_CONFIG["pair_currencies"].get(pair, [])
    impact_filter = ["HIGH", "MEDIUM"]

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

    HIGH impact within 60 min before or 30 min after → BLOCK (safe=False)
    MEDIUM impact within 30 min → CAUTION (safe=True, warn=True)
    Post-news spike window → flag as spike setup opportunity
    """
    block_window  = NEWS_CONFIG["block_window_minutes"]   # 60 min
    resume_window = NEWS_CONFIG["resume_window_minutes"]  # 30 min
    currencies    = NEWS_CONFIG["pair_currencies"].get(pair, [])

    df = fetch_forexfactory_calendar()
    if df.empty:
        return {
            "safe":        True,
            "caution":     False,
            "reason":      "No calendar data — proceeding with caution",
            "events":      [],
            "post_news":   False,
            "spike_watch": False,
        }

    now = datetime.utcnow()

    # HIGH impact check — BLOCK
    high_mask = (
        df["currency"].isin(currencies) &
        (df["impact"] == "HIGH") &
        (df["time"] >= now - timedelta(minutes=resume_window)) &
        (df["time"] <= now + timedelta(minutes=block_window))
    )
    high_events = df[high_mask].to_dict("records")

    if high_events:
        events_str = ", ".join([
            f"{e['currency']} {e['event']} @ {e['time'].strftime('%H:%M')} UTC"
            for e in high_events
        ])
        # Check if we're in post-news window (event already happened)
        post_news_events = [e for e in high_events if e["time"] < now]
        spike_watch      = len(post_news_events) > 0

        return {
            "safe":        False,
            "caution":     False,
            "reason":      f"High-impact news: {events_str}",
            "events":      high_events,
            "post_news":   spike_watch,
            "spike_watch": spike_watch,  # True = watch for ICT post-news setup
            "spike_note":  "⚡ POST-NEWS WINDOW — watch for liquidity sweep + ChoCH entry" if spike_watch else "",
        }

    # MEDIUM impact check — CAUTION only, don't block
    medium_mask = (
        df["currency"].isin(currencies) &
        (df["impact"] == "MEDIUM") &
        (df["time"] >= now - timedelta(minutes=15)) &
        (df["time"] <= now + timedelta(minutes=30))
    )
    medium_events = df[medium_mask].to_dict("records")

    if medium_events:
        events_str = ", ".join([
            f"{e['currency']} {e['event']} @ {e['time'].strftime('%H:%M')} UTC"
            for e in medium_events
        ])
        return {
            "safe":        True,  # Don't block, just warn
            "caution":     True,
            "reason":      f"⚠️ Medium-impact news nearby: {events_str} — reduce size",
            "events":      medium_events,
            "post_news":   False,
            "spike_watch": False,
        }

    return {
        "safe":        True,
        "caution":     False,
        "reason":      "Clear of high-impact news",
        "events":      [],
        "post_news":   False,
        "spike_watch": False,
    }


def detect_post_news_spike(df_h1, pair: str) -> dict:
    """
    After a high-impact news event fires, detect the spike candle.
    Returns info about the spike for the scanner to look for ICT reversal setup.

    The classic ICT post-news setup:
    1. News drops → big spike candle (1.5x+ ATR)
    2. Spike wicks above swing high (buy side sweep) or below swing low (sell side)
    3. Closes back in range = liquidity grab
    4. Next 1-3 candles: ChoCH in opposite direction
    5. ENTRY on the ChoCH candle with SL at wick extreme

    This function detects step 1-3. ICT module handles 4-5.
    """
    if df_h1 is None or len(df_h1) < 5:
        return {"detected": False}

    news_check = is_news_safe(pair)

    # Only relevant if we just had high impact news
    if not news_check.get("spike_watch") and not news_check.get("post_news"):
        return {"detected": False}

    atr       = df_h1["high"].sub(df_h1["low"]).rolling(14).mean().iloc[-1]
    last_3    = df_h1.iloc[-3:]

    for i in range(len(last_3)):
        candle     = last_3.iloc[i]
        candle_range = candle["high"] - candle["low"]

        if candle_range < atr * 1.5:
            continue

        # Big candle found — check if it's a spike (wick-heavy, not a clean body move)
        body    = abs(candle["close"] - candle["open"])
        wick_pct = (candle_range - body) / candle_range if candle_range > 0 else 0

        if wick_pct < 0.3:
            continue  # Clean body move, not a spike/sweep

        # Determine spike direction (which way did it spike?)
        upper_wick = candle["high"] - max(candle["open"], candle["close"])
        lower_wick = min(candle["open"], candle["close"]) - candle["low"]

        if upper_wick > lower_wick:
            spike_direction  = "up"
            reversal_bias    = "bearish"
            spike_extreme    = candle["high"]
        else:
            spike_direction  = "down"
            reversal_bias    = "bullish"
            spike_extreme    = candle["low"]

        return {
            "detected":       True,
            "spike_direction": spike_direction,
            "reversal_bias":   reversal_bias,
            "spike_extreme":   spike_extreme,
            "atr_ratio":       round(candle_range / atr, 1),
            "candles_ago":     len(last_3) - i - 1,
            "description": (
                f"📰 Post-news spike {'UP' if spike_direction == 'up' else 'DOWN'} "
                f"({round(candle_range/atr,1)}x ATR) — "
                f"watch for {reversal_bias.upper()} ChoCH entry, "
                f"SL at {spike_extreme:.5f}"
            ),
        }

    return {"detected": False}


def get_news_dashboard_data(pairs: list = None) -> dict:
    """
    Returns formatted news data for the dashboard.
    Called by app.py every refresh cycle.

    Returns:
    {
      "upcoming":  [ { pair, currency, event, impact, time, mins_away } ],
      "blocking":  [ pairs currently blocked by news ],
      "caution":   [ pairs on caution ],
      "next_high": { event, time, mins_away } or None
    }
    """
    from config import PAIRS, NEWS_CONFIG
    if pairs is None:
        pairs = PAIRS

    df  = fetch_forexfactory_calendar()
    now = datetime.utcnow()

    upcoming  = []
    blocking  = []
    caution   = []
    next_high = None

    if not df.empty:
        # Get HIGH and MEDIUM events in next 3 hours
        window = now + timedelta(hours=3)
        mask   = (
            (df["impact"].isin(["HIGH", "MEDIUM"])) &
            (df["time"] >= now - timedelta(minutes=30)) &
            (df["time"] <= window)
        )
        near_events = df[mask].sort_values("time")

        for _, row in near_events.iterrows():
            mins_away = int((row["time"] - now).total_seconds() / 60)
            upcoming.append({
                "currency":  row["currency"],
                "event":     row["event"],
                "impact":    row["impact"],
                "time":      row["time"].strftime("%H:%M UTC"),
                "mins_away": mins_away,
                "past":      mins_away < 0,
            })

            # Track next HIGH event
            if row["impact"] == "HIGH" and mins_away > 0 and next_high is None:
                next_high = {
                    "currency":  row["currency"],
                    "event":     row["event"],
                    "time":      row["time"].strftime("%H:%M UTC"),
                    "mins_away": mins_away,
                }

    # Check each pair
    for pair in pairs:
        check = is_news_safe(pair)
        if not check["safe"]:
            blocking.append(pair)
        elif check.get("caution"):
            caution.append(pair)

    return {
        "upcoming":  upcoming,
        "blocking":  blocking,
        "caution":   caution,
        "next_high": next_high,
    }


def get_upcoming_news(hours_ahead: int = 6) -> list:
    """
    Returns all HIGH/MEDIUM/LOW events within the next N hours.
    Formatted for the dashboard news panel.

    Returns list of:
    {
        "currency": "USD",
        "impact":   "HIGH",
        "title":    "CPI",
        "time":     "08:30 UTC",
        "mins_away": 45,
        "past":     False,
    }
    """
    df  = fetch_forexfactory_calendar()
    now = datetime.utcnow()

    if df.empty:
        return []

    window_end   = now + timedelta(hours=hours_ahead)
    window_start = now - timedelta(minutes=30)

    mask = (
        df["impact"].isin(["HIGH", "MEDIUM", "LOW"]) &
        (df["time"] >= window_start) &
        (df["time"] <= window_end)
    )

    filtered = df[mask].sort_values("time")

    events = []
    for _, row in filtered.iterrows():
        mins_away = int((row["time"] - now).total_seconds() / 60)
        events.append({
            "currency":  row["currency"],
            "impact":    row["impact"],
            "title":     row["event"],
            "time":      row["time"].strftime("%H:%M UTC"),
            "mins_away": mins_away,
            "past":      mins_away < 0,
            "forecast":  row.get("forecast", "") if hasattr(row, "get") else "",
            "actual":    row.get("actual",   "") if hasattr(row, "get") else "",
        })

    return events


def get_session_news_summary(session: str) -> list:
    from config import SESSIONS, PAIRS

    session_cfg = SESSIONS.get(session, {})
    if not session_cfg:
        return []

    now = datetime.utcnow()

    sh, sm = map(int, session_cfg["start"].split(":"))
    eh, em = map(int, session_cfg["end"].split(":"))

    session_start = now.replace(hour=sh, minute=sm, second=0, microsecond=0)
    session_end   = now.replace(hour=eh, minute=em, second=0, microsecond=0)

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