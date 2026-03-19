"""
main.py — Forex Zone Scanner entry point

Usage:
  python main.py live            # Continuous scanner every 5 min
  python main.py live 60         # Scan every 60 seconds
  python main.py scan            # One-time scan
  python main.py briefing tokyo
  python main.py briefing new_york
  python main.py stats
"""

import sys
import time
import logging
import os
from datetime import datetime

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


def print_alert(result: dict, confluence: dict):
    """Print a clean, readable alert to terminal."""
    pair     = result["pair"]
    score    = result["score"]
    grade    = result.get("grade", "?")
    direction = result["direction"].upper()

    grade_emoji = {"A+": "🔥", "A": "✅", "B": "⚠️", "C": "❌"}.get(grade, "")
    dir_emoji   = "📈" if direction == "BULLISH" else "📉" if direction == "BEARISH" else "↔️"

    h1_struct    = confluence.get("h1", {}).get("structure", {})
    phase        = h1_struct.get("phase", "?")
    quality      = h1_struct.get("setup_quality", "?")
    trend        = h1_struct.get("trend", "?")
    depth        = h1_struct.get("pullback_depth", 0)
    tf_reading   = confluence.get("tf_reading", "")
    grade_meaning = result.get("grade_meaning", "")

    pattern      = result.get("entry_pattern") or {}
    pattern_desc = pattern.get("description", "")
    flags        = result.get("flags", [])

    # Score breakdown
    bd           = result.get("breakdown", {})
    bd_str       = f"Zone:{bd.get('zone',0)} TF:{bd.get('tf',0)} Pat:{bd.get('pattern',0)} Sess:{bd.get('session',0)} News:{bd.get('news',0)} Qual:{bd.get('quality_bonus',0)}"

    lines = [
        "",
        "=" * 65,
        f"{dir_emoji} {pair} | {direction} | {score}/100 | {grade_emoji} Grade {grade}",
        f"   {grade_meaning}",
        "-" * 65,
        f"📊 Trend: {trend} | Phase: {phase} | Quality: {quality} | Pullback: {round(depth*100)}%",
        f"🔑 Setup: {result.get('setup_type','').replace('_',' ').title()}",
        f"📐 Score: {bd_str}",
        "-" * 65,
        f"📖 {tf_reading}",
    ]

    if pattern_desc:
        lines.append(f"🕯️  M5 Candle: {pattern_desc}")
    else:
        lines.append("🕯️  M5: No confirmation candle yet — wait before entering")

    if flags:
        lines.append("-" * 65)
        for flag in flags:
            lines.append(f"   {flag}")

    # Zone approach warning
    approach = confluence.get("approaching_warning", "")
    if approach:
        lines.append(f"   {approach}")

    lines.append("=" * 65)
    print("\n".join(lines))


def run_live(interval_seconds: int = 300):
    from reports.briefing import scan_pair
    from alerts.slack import send_signal_alert, send_error_alert
    from config import PAIRS, SLACK_CONFIG

    slack_enabled = SLACK_CONFIG["webhook_url"] != "YOUR_SLACK_WEBHOOK_URL"
    logger.info(f"Starting live scanner — interval={interval_seconds}s | Slack={'ON' if slack_enabled else 'OFF'}")

    while True:
        try:
            logger.info("--- Scanning all pairs ---")
            for pair in PAIRS:
                result, confluence = scan_pair(pair, return_confluence=True)
                if result is None:
                    continue

                if result["should_alert"]:
                    print_alert(result, confluence)
                    if slack_enabled:
                        send_signal_alert(result, confluence)

                elif result.get("approaching_warning"):
                    # Zone approach — print lighter warning
                    print(f"\n🔜 {pair} — {confluence.get('approaching_warning','')}")

        except KeyboardInterrupt:
            logger.info("Scanner stopped.")
            break
        except Exception as e:
            logger.error(f"Scanner error: {e}", exc_info=True)

        logger.info(f"Sleeping {interval_seconds}s...")
        time.sleep(interval_seconds)


def run_scan():
    from reports.briefing import scan_pair
    from config import PAIRS

    print(f"\n{'='*65}")
    print(f"  FOREX SCAN — {datetime.utcnow().strftime('%Y-%m-%d %H:%M UTC')}")
    print(f"{'='*65}")

    for pair in PAIRS:
        result, confluence = scan_pair(pair, return_confluence=True)
        if result is None:
            continue
        if result["should_alert"] or result["should_log"]:
            print_alert(result, confluence)
        else:
            score = result.get("score", 0)
            grade = result.get("grade", "C")
            print(f"  ⬜ {pair} — Score: {score}/100 Grade: {grade} — No setup")


def run_briefing(session: str):
    from reports.briefing import generate_briefing, print_briefing_terminal
    from alerts.slack import send_presession_briefing
    from config import SLACK_CONFIG

    briefing = generate_briefing(session)
    print_briefing_terminal(briefing)

    if SLACK_CONFIG["webhook_url"] != "YOUR_SLACK_WEBHOOK_URL":
        send_presession_briefing(session, briefing)


def run_stats():
    from alerts.logger import get_performance_summary
    import json
    stats = get_performance_summary()
    print("\n📊 SIGNAL LOG STATS")
    print("=" * 40)
    print(json.dumps(stats, indent=2))


if __name__ == "__main__":
    args    = sys.argv[1:]
    command = args[0].lower() if args else ""

    if command == "live":
        interval = int(args[1]) if len(args) > 1 else 300
        run_live(interval_seconds=interval)
    elif command == "scan":
        run_scan()
    elif command == "briefing":
        session = args[1].lower() if len(args) > 1 else "new_york"
        run_briefing(session)
    elif command == "stats":
        run_stats()
    else:
        print(__doc__)