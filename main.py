"""
main.py — Forex Zone Scanner

Usage:
  python main.py live              # polling every 5 min + dashboard
  python main.py live 60           # every 60 seconds
  python main.py scan              # one-time scan
  python main.py stream            # real-time tick feed + dashboard
  python main.py briefing tokyo/london/new_york
  python main.py took GBP_JPY short
  python main.py stats
"""

import sys
import time
import logging
import os
from datetime import datetime

os.makedirs("logs", exist_ok=True)
logging.basicConfig(
    level=logging.WARNING,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    handlers=[
        logging.FileHandler("logs/app.log"),
        logging.StreamHandler(sys.stdout),
    ],
)
logger = logging.getLogger("main")

# Alert cooldown — don't alert same pair within N minutes
ALERT_COOLDOWN_MINUTES   = 15
BREAKOUT_COOLDOWN_MINUTES = 60  # Breakout alerts max once per hour per pair

_last_alerted   = {}  # pair → datetime
_last_breakout  = {}  # pair → datetime


def _is_cooldown(pair: str, store: dict, minutes: int) -> bool:
    last = store.get(pair)
    if last is None:
        return False
    return (datetime.utcnow() - last).total_seconds() < minutes * 60


def print_alert(result: dict, confluence: dict):
    """Print clean alert with trade levels to terminal."""
    pair      = result["pair"]
    score     = result["score"]
    grade     = result.get("grade", "?")
    direction = result["direction"].upper()
    levels    = result.get("trade_levels", {})

    grade_emoji = {"A+": "🔥", "A": "✅", "B": "⚠️", "C": "❌"}.get(grade, "")
    dir_emoji   = "📈" if direction == "BULLISH" else "📉"

    h1_struct = confluence.get("h1", {}).get("structure", {})
    phase     = h1_struct.get("phase", "?")
    quality   = h1_struct.get("setup_quality", "?")
    trend     = h1_struct.get("trend", "?")
    depth     = h1_struct.get("pullback_depth", 0)

    bd     = result.get("breakdown", {})
    bd_str = (
        f"Zone:{bd.get('zone',0)} TF:{bd.get('tf',0)} "
        f"Pat:{bd.get('pattern',0)} Sess:{bd.get('session',0)} "
        f"News:{bd.get('news',0)} ICT:{bd.get('ict',0)}"
    )

    pattern       = result.get("entry_pattern") or {}
    pattern_desc  = pattern.get("description", "")
    flags         = result.get("flags", [])
    tf_reading    = confluence.get("tf_reading", "")
    grade_meaning = result.get("grade_meaning", "")

    try:
        from filters.killzones import format_killzone_banner
        kz_line = format_killzone_banner(result.get("kz_ctx", {}))
    except Exception:
        kz_line = ""

    lines = [
        "",
        "=" * 65,
        f"{dir_emoji} {pair} | {direction} | {score}/100 | {grade_emoji} Grade {grade}",
        f"   {grade_meaning}",
        "-" * 65,
        f"📊 Trend: {trend} | Phase: {phase} | Quality: {quality} | Depth: {round(depth*100)}%",
        f"🔑 Setup: {result.get('setup_type','').replace('_',' ').title()}",
        f"📐 Score: {bd_str}",
    ]

    if kz_line:
        lines.append(f"{kz_line}")

    lines.append("-" * 65)

    if levels:
        lines += [
            f"📍 Entry:  {levels.get('entry_price','—')}",
            f"🛑 SL:     {levels.get('sl_price','—')}  ({levels.get('sl_pips','?')} pips)",
            f"🎯 TP1:    {levels.get('tp1_price','—')}  ({levels.get('tp1_pips','?')} pips | {levels.get('rr1','1:2')})",
            f"🎯 TP2:    {levels.get('tp2_price','—')}  ({levels.get('tp2_pips','?')} pips | {levels.get('rr2','1:3')})",
        ]
        lines.append("-" * 65)

    lines.append(f"📖 {tf_reading}")

    if pattern_desc:
        lines.append(f"🕯️  M5: {pattern_desc}")
    else:
        lines.append("🕯️  M5: No confirmation candle yet — wait before entering")

    if flags:
        lines.append("-" * 65)
        for flag in flags:
            lines.append(f"   {flag}")

    approach = result.get("approaching_warning", "")
    if approach:
        lines.append(f"   {approach}")

    lines.append("=" * 65)
    print("\n".join(lines))


def print_breakout_alert(pair: str, breakout: dict, kz_info: str):
    """Print momentum breakout alert — fires outside killzones too."""
    direction  = breakout["direction"].upper()
    atr_ratio  = breakout["atr_ratio"]
    pips_moved = breakout["pips_moved"]
    consecutive = breakout["consecutive"]
    dir_emoji  = "📉" if direction == "BEARISH" else "📈"

    consec_str = f" | {consecutive} candles in a row" if consecutive > 1 else ""

    lines = [
        "",
        "⚡" * 3 + f" MOMENTUM BREAKOUT — {pair}",
        "─" * 50,
        f"{dir_emoji} {direction} | {atr_ratio}x ATR | {pips_moved} pips{consec_str}",
        f"🕐 {kz_info}",
        "─" * 50,
        f"Smart money moving. Watch for entry when killzone opens.",
        "=" * 50,
    ]
    print("\n".join(lines))


def _check_momentum_breakouts(pair: str, candles: dict) -> dict:
    """Check for momentum breakout on H1."""
    try:
        from core.candles import detect_momentum_breakout
        df_h1 = candles.get("H1")
        if df_h1 is None or df_h1.empty:
            return {"detected": False}
        return detect_momentum_breakout(df_h1, pair)
    except Exception as e:
        logger.debug(f"Breakout check error for {pair}: {e}")
        return {"detected": False}


def run_live(interval_seconds: int = 300):
    from reports.briefing import scan_pair
    from config import PAIRS, SLACK_CONFIG
    from dashboard.app import start_dashboard
    from core.fetcher import fetch_all_timeframes
    import threading

    # Start dashboard
    dash_thread = threading.Thread(target=start_dashboard, daemon=True)
    dash_thread.start()
    time.sleep(2)
    print("\n🖥️  Dashboard: http://localhost:5000\n")

    slack_enabled = bool(SLACK_CONFIG.get("webhook_url"))
    print(f"🔍 Live scanner — interval={interval_seconds}s | Slack={'ON' if slack_enabled else 'OFF'}")

    scan_count = 0

    while True:
        try:
            scan_count += 1
            print(f"\n[{datetime.utcnow().strftime('%H:%M:%S')} UTC] Scan #{scan_count}")

            for pair in PAIRS:
                # Full scan
                result, confluence = scan_pair(pair, return_confluence=True)
                if result is None:
                    continue

                result["approaching_warning"] = confluence.get("approaching_warning", "")

                # Normal signal alert
                if result["should_alert"] and not _is_cooldown(pair, _last_alerted, ALERT_COOLDOWN_MINUTES):
                    print_alert(result, confluence)
                    _last_alerted[pair] = datetime.utcnow()
                    if slack_enabled:
                        try:
                            from alerts.slack import send_signal_alert
                            send_signal_alert(result, confluence)
                        except Exception as e:
                            logger.error(f"Slack error: {e}")

                elif result.get("approaching_warning"):
                    print(f"  🔜 {result['approaching_warning']}")

                # Momentum breakout check — fires regardless of killzone
                if not _is_cooldown(pair, _last_breakout, BREAKOUT_COOLDOWN_MINUTES):
                    candles   = confluence.get("_candles") or {}
                    breakout  = _check_momentum_breakouts(pair, candles)

                    if not candles:
                        # Fetch fresh if not cached in confluence
                        try:
                            from core.fetcher import fetch_all_timeframes
                            candles  = fetch_all_timeframes(pair)
                            breakout = _check_momentum_breakouts(pair, candles)
                        except Exception:
                            breakout = {"detected": False}

                    if breakout.get("detected") and breakout.get("atr_ratio", 0) >= 1.5:
                        try:
                            from filters.killzones import get_active_killzone, minutes_to_next_killzone
                            kz = get_active_killzone()
                            if kz["active"]:
                                kz_info = f"{kz['label']} — {kz['mins_left']} min remaining"
                            else:
                                mins, next_kz = minutes_to_next_killzone()
                                kz_info = f"{next_kz.get('label','Next killzone')} in {mins} min"
                        except Exception:
                            kz_info = "check killzone"

                        print_breakout_alert(pair, breakout, kz_info)
                        _last_breakout[pair] = datetime.utcnow()

                        if slack_enabled:
                            try:
                                from alerts.slack import send_signal_alert
                                # Build minimal result for slack
                                send_signal_alert(result, confluence)
                            except Exception:
                                pass

            # Auto-labeler
            _run_labeler_quietly()

        except KeyboardInterrupt:
            print("\nScanner stopped.")
            break
        except Exception as e:
            logger.error(f"Scanner error: {e}", exc_info=True)

        time.sleep(interval_seconds)


def _run_labeler_quietly():
    try:
        from ml.outcome_labeler import label_pending_signals
        count = label_pending_signals()
        if count > 0:
            print(f"  ✅ Auto-labeled {count} signal outcomes")
    except Exception as e:
        logger.debug(f"Labeler error: {e}")


def run_scan():
    from reports.briefing import scan_pair
    from core.fetcher import fetch_all_timeframes
    from config import PAIRS

    print(f"\n{'='*65}")
    print(f"  FOREX SCAN — {datetime.utcnow().strftime('%Y-%m-%d %H:%M UTC')}")
    print(f"{'='*65}")

    for pair in PAIRS:
        result, confluence = scan_pair(pair, return_confluence=True)
        if result is None:
            continue

        result["approaching_warning"] = confluence.get("approaching_warning", "")

        if result["should_alert"] or result["should_log"]:
            print_alert(result, confluence)
        else:
            score = result.get("score", 0)
            grade = result.get("grade", "C")
            warn  = result.get("approaching_warning", "")
            if warn:
                print(f"  🔜 {warn}")
            else:
                print(f"  ⬜ {pair} — {score}/100 {grade} — No setup")

        # Check momentum breakout regardless of score
        candles  = fetch_all_timeframes(pair)
        breakout = _check_momentum_breakouts(pair, candles)
        if breakout.get("detected") and breakout.get("atr_ratio", 0) >= 1.5:
            try:
                from filters.killzones import get_active_killzone, minutes_to_next_killzone
                kz = get_active_killzone()
                if kz["active"]:
                    kz_info = f"{kz['label']} — {kz['mins_left']} min remaining"
                else:
                    mins, next_kz = minutes_to_next_killzone()
                    kz_info = f"{next_kz.get('label','Next killzone')} in {mins} min"
            except Exception:
                kz_info = "check killzone"
            print_breakout_alert(pair, breakout, kz_info)


def run_stream():
    from core.streamer import start_streamer
    from dashboard.app import start_dashboard
    import threading

    print("\n🔴 Stream mode starting...")
    dash_thread = threading.Thread(target=start_dashboard, daemon=True)
    dash_thread.start()
    time.sleep(2)
    print("🖥️  Dashboard: http://localhost:5000\n")
    start_streamer()


def run_briefing(session: str):
    from reports.briefing import generate_briefing, print_briefing_terminal
    from config import SLACK_CONFIG

    briefing = generate_briefing(session)
    print_briefing_terminal(briefing)

    if SLACK_CONFIG.get("webhook_url"):
        try:
            from alerts.slack import send_presession_briefing
            send_presession_briefing(session, briefing)
        except Exception as e:
            logger.warning(f"Slack briefing failed: {e}")


def run_took(pair: str, direction: str):
    from alerts.logger import mark_taken
    pair = pair.upper().replace("/", "_")
    ok   = mark_taken(pair)
    if ok:
        print(f"✅ Marked {pair} {direction} as taken.")
    else:
        print(f"❌ No recent signal found for {pair}.")


def run_stats():
    from alerts.logger import get_performance_summary
    import json
    stats = get_performance_summary()
    print("\n📊 SIGNAL LOG STATS")
    print("=" * 40)
    print(json.dumps(stats, indent=2, default=str))


if __name__ == "__main__":
    args    = sys.argv[1:]
    command = args[0].lower() if args else ""

    if command == "live":
        interval = int(args[1]) if len(args) > 1 else 300
        run_live(interval_seconds=interval)
    elif command == "scan":
        run_scan()
    elif command == "stream":
        run_stream()
    elif command == "briefing":
        session = args[1].lower() if len(args) > 1 else "new_york"
        run_briefing(session)
    elif command == "took":
        if len(args) < 3:
            print("Usage: python main.py took GBP_JPY short")
        else:
            run_took(pair=args[1], direction=args[2])
    elif command == "stats":
        run_stats()
    else:
        print(__doc__)