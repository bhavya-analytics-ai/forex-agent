"""
main.py — Entry point for the Forex Zone Scanner

Usage:
  python main.py briefing tokyo      # Generate Tokyo pre-session briefing
  python main.py briefing new_york   # Generate NY pre-session briefing
  python main.py scan                # One-time scan of all pairs
  python main.py live                # Continuous real-time scanner loop
  python main.py stats               # Show performance stats from signal log
"""

import sys
import time
import logging
import os
from datetime import datetime

# Setup logging
os.makedirs("logs", exist_ok=True)
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    handlers=[
        logging.FileHandler("logs/app.log"),
        logging.StreamHandler(sys.stdout),
    ],
)
logger = logging.getLogger("main")


def run_briefing(session: str):
    """Generate and send a pre-session briefing."""
    from reports.briefing import generate_briefing, print_briefing_terminal
    from alerts.slack import send_presession_briefing

    briefing = generate_briefing(session)
    print_briefing_terminal(briefing)

    # Send to Slack if webhook is configured
    from config import SLACK_CONFIG
    if SLACK_CONFIG["webhook_url"] != "YOUR_SLACK_WEBHOOK_URL":
        send_presession_briefing(session, briefing)
        logger.info("Briefing sent to Slack")
    else:
        logger.info("Slack not configured — briefing printed to terminal only")


def run_scan():
    """One-time scan of all pairs, print results."""
    from reports.briefing import scan_pair, print_briefing_terminal
    from config import PAIRS

    results = []
    for pair in PAIRS:
        result = scan_pair(pair)
        if result:
            results.append(result)

    # Use briefing printer for clean output
    print_briefing_terminal({
        "session": "manual_scan",
        "generated_at": datetime.utcnow().isoformat(),
        "setups":    [r for r in results if r["should_alert"]],
        "watch_list": [r for r in results if r["should_log"] and not r["should_alert"]],
        "news":      [],
        "pairs_scanned": len(PAIRS),
        "total_signals": len(results),
    })


def run_live(interval_seconds: int = 300):
    """
    Continuous scanner — checks all pairs every N seconds.
    Fires Slack alerts when confluence triggers.
    Default: every 5 minutes (300s).
    """
    from reports.briefing import scan_pair
    from alerts.slack import send_signal_alert, send_error_alert
    from config import PAIRS, SLACK_CONFIG
    from core.fetcher import fetch_all_timeframes
    from core.confluence import check_confluence

    slack_enabled = SLACK_CONFIG["webhook_url"] != "YOUR_SLACK_WEBHOOK_URL"
    logger.info(f"Starting live scanner — interval={interval_seconds}s | Slack={'ON' if slack_enabled else 'OFF (terminal only)'}")

    while True:
        try:
            logger.info("--- Scanning all pairs ---")
            for pair in PAIRS:
                result = scan_pair(pair)
                if result and result["should_alert"]:
                    logger.info(f"🔔 ALERT: {pair} {result['direction']} score={result['score']}")
                    print(
                        f"\n🔔 ALERT | {pair} | {result['direction'].upper()} | "
                        f"Score: {result['score']}/100 | {result['setup_type'].replace('_',' ').title()}"
                    )
                    if slack_enabled:
                        # Need full confluence for Slack formatter
                        candles    = fetch_all_timeframes(pair)
                        confluence = check_confluence(candles, pair)
                        send_signal_alert(result, confluence)

        except KeyboardInterrupt:
            logger.info("Scanner stopped by user")
            break
        except Exception as e:
            logger.error(f"Scanner error: {e}", exc_info=True)
            if slack_enabled:
                send_error_alert(str(e))

        logger.info(f"Sleeping {interval_seconds}s...")
        time.sleep(interval_seconds)


def run_stats():
    """Print performance stats from signal log."""
    from alerts.logger import get_performance_summary
    import json

    stats = get_performance_summary()
    print("\n📊 SIGNAL LOG PERFORMANCE STATS")
    print("=" * 40)
    print(json.dumps(stats, indent=2))
    print("=" * 40)


if __name__ == "__main__":
    args = sys.argv[1:]

    if not args:
        print(__doc__)
        sys.exit(0)

    command = args[0].lower()

    if command == "briefing":
        session = args[1].lower() if len(args) > 1 else "new_york"
        if session not in ["tokyo", "new_york"]:
            print("Session must be 'tokyo' or 'new_york'")
            sys.exit(1)
        run_briefing(session)

    elif command == "scan":
        run_scan()

    elif command == "live":
        interval = int(args[1]) if len(args) > 1 else 300
        run_live(interval_seconds=interval)

    elif command == "stats":
        run_stats()

    else:
        print(f"Unknown command: {command}")
        print(__doc__)
        sys.exit(1)