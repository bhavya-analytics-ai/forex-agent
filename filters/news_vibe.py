"""
filters/news_vibe.py — Market Vibe Headlines (NewsData.io)

Separate module — does NOT affect any trading logic.
Provides headline data for the dashboard's Market Vibe panel only.
Called on-demand when user opens the panel, not on every scan cycle.
"""

import os
import requests
import logging
from datetime import datetime, timedelta

logger = logging.getLogger(__name__)

_vibe_cache    = {}   # pair → {"data": [...], "fetched_at": datetime}
_CACHE_MINUTES = 10   # headlines don't change that fast

_PAIR_QUERIES = {
    "XAU_USD": "gold price",
    "XAG_USD": "silver price",
    "GBP_USD": "pound dollar sterling",
    "EUR_USD": "euro dollar",
    "EUR_GBP": "euro pound",
    "USD_JPY": "dollar yen japan",
    "GBP_JPY": "pound yen",
    "EUR_JPY": "euro yen",
    "CHF_JPY": "swiss franc yen",
    "CAD_JPY": "canada dollar yen",
    "NZD_JPY": "new zealand dollar yen",
}


def get_vibe_headlines(pair: str, count: int = 6) -> dict:
    """
    Get latest market headlines for a pair from NewsData.io.
    Returns dict with headlines list. Cached for 10 minutes.
    Falls back to stale cache if API fails.
    """
    api_key = os.getenv("NEWSDATA_API_KEY", "")
    if not api_key or api_key == "your_newsdata_key_here":
        return {
            "headlines": [],
            "pair":      pair,
            "error":     "NEWSDATA_API_KEY not set — add it to .env",
        }

    now    = datetime.utcnow()
    cached = _vibe_cache.get(pair)

    # Return cached if still fresh
    if (
        cached
        and cached.get("fetched_at")
        and (now - cached["fetched_at"]).total_seconds() < _CACHE_MINUTES * 60
    ):
        return {"headlines": cached["data"], "pair": pair, "cached": True}

    query = _PAIR_QUERIES.get(pair, pair.replace("_", " ").lower())

    try:
        resp = requests.get(
            "https://newsdata.io/api/1/latest",
            params={
                "apikey":   api_key,
                "q":        query,
                "language": "en",
                "category": "business",
                "size":     count,
            },
            timeout=10,
        )
        resp.raise_for_status()
        data = resp.json()

        if data.get("status") != "success":
            raise ValueError(f"NewsData error: {data.get('message', 'unknown')}")

        headlines = []
        for item in (data.get("results") or [])[:count]:
            pub = item.get("pubDate", "")
            # Clean up pubDate to just time if today
            try:
                dt = datetime.strptime(pub[:19], "%Y-%m-%d %H:%M:%S")
                if dt.date() == now.date():
                    pub = dt.strftime("%H:%M UTC")
                else:
                    pub = dt.strftime("%b %d %H:%M")
            except Exception:
                pass

            headlines.append({
                "title":     item.get("title", ""),
                "source":    item.get("source_id", ""),
                "time":      pub,
                "link":      item.get("link", "#"),
                "sentiment": item.get("sentiment", ""),
            })

        _vibe_cache[pair] = {"data": headlines, "fetched_at": now}
        logger.info(f"Vibe: {len(headlines)} headlines for {pair}")
        return {"headlines": headlines, "pair": pair, "cached": False}

    except Exception as e:
        logger.warning(f"NewsData.io failed for {pair}: {e}")
        # Stale fallback
        if cached and cached.get("data"):
            return {"headlines": cached["data"], "pair": pair, "cached": True, "stale": True}
        return {"headlines": [], "pair": pair, "error": str(e)}
