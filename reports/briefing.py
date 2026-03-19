"""
briefing.py — Generate pre-session briefing data for Tokyo and New York sessions.
"""

import logging
from datetime import datetime
from config import PAIRS
from core.fetcher import fetch_all_timeframes
from core.confluence import check_confluence, is_tradeable
from alerts.scorer import score_signal
from alerts.logger import log_signal
from filters.news import get_session_news_summary
from filters.session import get_session_context

logger = logging.getLogger(__name__)


def scan_pair(pair: str, return_confluence: bool = False):
    """
    Full scan pipeline for one pair.
    return_confluence=True returns (scored, confluence) tuple for alert printing.
    """
    try:
        logger.info(f"Scanning {pair}...")

        candles = fetch_all_timeframes(pair)
        if any(df.empty for df in candles.values()):
            logger.warning(f"{pair}: Missing candle data, skipping")
            return (None, None) if return_confluence else None

        confluence = check_confluence(candles, pair)
        scored     = score_signal(confluence, pair)

        scored["h1_trend"]  = confluence["h1"]["structure"].get("trend", "—")
        scored["m15_trend"] = confluence["m15"]["structure"].get("trend", "—")
        scored["m5_trend"]  = confluence["m5"]["structure"].get("trend", "—")

        if scored["should_log"]:
            log_signal(scored, confluence, alerted=scored["should_alert"])

        return (scored, confluence) if return_confluence else scored

    except Exception as e:
        logger.error(f"Error scanning {pair}: {e}", exc_info=True)
        return (None, None) if return_confluence else None


def generate_briefing(session: str) -> dict:
    """
    Generate a full pre-session briefing.
    Scans all pairs, returns top setups + news warnings.

    session: 'tokyo' or 'new_york'
    """
    logger.info(f"Generating {session} briefing...")

    all_signals = []

    for pair in PAIRS:
        result = scan_pair(pair)
        if result:
            all_signals.append(result)

    # Sort by score
    all_signals.sort(key=lambda s: s["score"], reverse=True)

    # Separate high-quality setups from noise
    alert_setups = [s for s in all_signals if s["should_alert"]]
    watch_setups = [
        s for s in all_signals
        if s["should_log"] and not s["should_alert"]
    ]

    # Get news for this session
    news = get_session_news_summary(session)

    briefing = {
        "session":       session,
        "generated_at":  datetime.utcnow().isoformat(),
        "setups":        alert_setups,   # High confidence — alert now
        "watch_list":    watch_setups,   # Worth watching — not alerting yet
        "news":          news,
        "pairs_scanned": len(PAIRS),
        "total_signals": len(all_signals),
    }

    logger.info(
        f"Briefing done: {len(alert_setups)} alert setups, "
        f"{len(watch_setups)} watch-list, {len(news)} news events"
    )

    return briefing


def print_briefing_terminal(briefing: dict):
    """
    Pretty-print the briefing to terminal (for testing without Slack).
    """
    session = briefing["session"].replace("_", " ").title()
    print(f"\n{'='*60}")
    print(f"  PRE-SESSION BRIEFING — {session}")
    print(f"  {briefing['generated_at']} UTC")
    print(f"{'='*60}")

    # News
    news = briefing.get("news", [])
    if news:
        print(f"\n⚠️  HIGH-IMPACT NEWS:")
        for event in news:
            t = event["time"].strftime("%H:%M UTC") if hasattr(event["time"], "strftime") else event["time"]
            print(f"   {event['currency']} — {event['event']} @ {t}")

    # Alert setups
    setups = briefing.get("setups", [])
    print(f"\n🔔  ALERT SETUPS ({len(setups)}):")
    if not setups:
        print("   None — no high-confluence setups right now.")
    for s in setups:
        direction_sym = "▲" if s["direction"] == "bullish" else "▼"
        print(f"\n   {direction_sym} {s['pair']}  [{s['score']}/100]  {s['setup_type'].replace('_',' ').upper()}")
        print(f"     Price:   {s['current_price']:.5f}")
        print(f"     Trend:   H1={s.get('h1_trend','?')} | M15={s.get('m15_trend','?')} | M5={s.get('m5_trend','?')}")
        zone = s.get("top_zone") or {}
        if zone:
            print(f"     Zone:    {zone.get('type','').title()} {zone.get('low',0):.5f}–{zone.get('high',0):.5f} (str={zone.get('strength',0)})")
        pattern = s.get("entry_pattern") or {}
        if pattern:
            print(f"     Pattern: {pattern.get('pattern','').replace('_',' ').title()} ({pattern.get('direction','')})")

    # Watch list
    watch = briefing.get("watch_list", [])
    print(f"\n👁️  WATCH LIST ({len(watch)}):")
    if not watch:
        print("   None")
    for s in watch:
        direction_sym = "▲" if s["direction"] == "bullish" else "▼"
        print(f"   {direction_sym} {s['pair']}  [{s['score']}/100]  {s['setup_type'].replace('_',' ')}")

    print(f"\n{'='*60}\n")