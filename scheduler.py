"""
scheduler.py — Auto-run briefings before Tokyo and New York sessions.
Run this once and leave it — it fires the briefing 30 min before each session.

Usage: python scheduler.py
"""

import time
import logging
from datetime import datetime
from filters.session import is_briefing_time, minutes_to_session

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[
        logging.FileHandler("logs/scheduler.log"),
        logging.StreamHandler(),
    ]
)
logger = logging.getLogger("scheduler")

# Track last briefing sent to avoid duplicates
_last_briefing = {"tokyo": None, "new_york": None}
BRIEFING_COOLDOWN_MINUTES = 120  # Don't re-send within 2 hours


def should_send(session: str) -> bool:
    """Check if we should send the briefing — within window and not recently sent."""
    last = _last_briefing[session]
    now  = datetime.utcnow()

    if last:
        mins_since = (now - last).total_seconds() / 60
        if mins_since < BRIEFING_COOLDOWN_MINUTES:
            return False

    return is_briefing_time(session, window_minutes=35)


def run_scheduler():
    logger.info("Scheduler started. Watching for Tokyo and New York session opens...")

    while True:
        try:
            for session in ["tokyo", "new_york"]:
                if should_send(session):
                    logger.info(f"Triggering {session} briefing...")
                    from main import run_briefing
                    run_briefing(session)
                    _last_briefing[session] = datetime.utcnow()

            # Log next session times every 30 min
            now = datetime.utcnow()
            if now.minute % 30 == 0 and now.second < 60:
                for session in ["tokyo", "new_york"]:
                    mins = minutes_to_session(session)
                    logger.info(f"  {session.title()}: {mins} min away")

        except Exception as e:
            logger.error(f"Scheduler error: {e}", exc_info=True)

        time.sleep(60)  # Check every minute


if __name__ == "__main__":
    run_scheduler()