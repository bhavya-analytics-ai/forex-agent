"""
reports/briefing.py — Pre-session briefing and full scan pipeline

Sessions: tokyo, london, new_york
"""

import logging
from datetime import datetime
from config import PAIRS, DEBUG_DECISIONS, OM_STRATEGY_ENABLED, LEGACY_GOLD_ENABLED, LEGACY_FOREX_ENABLED
from filters.market_hours import market_hours_gate
from filters.quality_gate import minimum_quality_gate
from core.fetcher import fetch_all_timeframes
from core.confluence import check_confluence
from alerts.scorer import score_signal
from alerts.logger import log_signal
from filters.news import get_session_news_summary
from filters.session import get_session_context

logger = logging.getLogger(__name__)


def _trace(scored: dict, signal_id: str) -> None:
    """
    Emit one compact INFO line per pair per scan when DEBUG_DECISIONS=true.
    Zero effect on trading/logging behavior — read-only view of scored dict.
    """
    pair         = scored.get("pair", "?")
    direction    = scored.get("direction", "?")
    grade        = scored.get("grade", "?")
    score        = scored.get("score", 0)
    setup_type   = scored.get("setup_type", "?")
    entry_state  = scored.get("entry_state", "—") or "—"
    should_log   = scored.get("should_log", False)
    should_alert = scored.get("should_alert", False)
    logged       = "YES" if signal_id else "NO"

    # Top block reason — dl_block_reason first, then approaching_warning, else blank
    block = (
        scored.get("dl_block_reason")
        or scored.get("approaching_warning")
        or ""
    )
    # Trim to keep line compact
    if block and len(block) > 50:
        block = block[:47] + "..."
    block_part = f" | block={block}" if block else ""

    logger.info(
        f"TRACE {pair} | {direction} | {grade} | {score}/100 | {setup_type}"
        f" | entry_state={entry_state} | should_log={should_log}"
        f" | should_alert={should_alert} | logged={logged}{block_part}"
    )


def scan_pair(pair: str, return_confluence: bool = False):
    """
    Full scan pipeline for one pair.
    return_confluence=True → returns (scored, confluence) tuple.
    """
    try:
        logger.info(f"Scanning {pair}...")

        candles = fetch_all_timeframes(pair)
        if any(df.empty for df in candles.values()):
            logger.warning(f"{pair}: Missing candle data, skipping")
            return (None, None) if return_confluence else None

        confluence = check_confluence(candles, pair)
        scored     = score_signal(confluence, pair)

        # Strategy router — mode_manager picks normal or news sniper
        try:
            from filters.mode_manager import apply_strategy, refresh_auto_mode
            refresh_auto_mode()
            scored = apply_strategy(scored, confluence, pair, candles)
        except Exception as e:
            logger.warning(f"Strategy error for {pair}: {e}")

        # ── EXTRA STRATEGIES (parallel execution) ────────────────────────────
        # Runs all eligible strategies beyond the primary legacy result.
        # Each produces an independent candidate dict (primary `scored` is NOT
        # modified). Watch-only enforcement applied inside each strategy + runner.
        # No DB writes, no Slack — all switches default false.
        _extra_candidates: list = []
        try:
            from strategies.runner import run_extra_strategies
            _extra_candidates = run_extra_strategies(scored, confluence, pair, candles)
        except Exception as _re:
            logger.warning(f"Extra strategy runner error for {pair}: {_re}")

        # Attach trend context for display
        scored["h1_trend"]  = confluence["h1"]["structure"].get("trend", "—")
        scored["m15_trend"] = confluence["m15"]["structure"].get("trend", "—")
        scored["m5_trend"]  = confluence["m5"]["structure"].get("trend", "—")

        # Approaching warning — wire into result so main.py and dashboard can read it
        scored["approaching_warning"] = confluence.get("approaching_warning", "")

        # ── OM STRATEGY KILL SWITCH ───────────────────────────────────────────
        # When OM_STRATEGY_ENABLED=false (default): suppress all ENTER_NOW from
        # the legacy loose scanner. Scanner still evaluates + grades for
        # observation but produces zero DB rows and zero Slack alerts.
        # Set OM_STRATEGY_ENABLED=true in Railway env once OM rules are live.
        if not OM_STRATEGY_ENABLED:
            scored["entry_state"]    = "WATCH_ONLY_GLOBAL_DISABLED"
            scored["should_alert"]   = False
            scored["should_log"]     = False
            scored["entry_allowed"]  = False
            scored["strategy_mode"]  = "legacy_watch_only"
            scored["scanner_action"] = "WATCH_ONLY_GLOBAL_DISABLED"

        # ── PER-STRATEGY LEGACY GATES ─────────────────────────────────────────
        # Only evaluated when OM_STRATEGY_ENABLED=true (global master is on).
        # Allows enabling gold-only or forex-only logging independently.
        # news_sniper and OM Gold Scalp are NOT gated here — separate paths.
        if OM_STRATEGY_ENABLED:
            _lg_gold   = scored.get("gold_mode", False)
            _lg_sniper = scored.get("signal_mode") == "news_sniper"
            _lg_forex  = not _lg_gold and not _lg_sniper

            if _lg_gold and not LEGACY_GOLD_ENABLED:
                scored["entry_state"]    = "WATCH_ONLY_LEGACY_GOLD_DISABLED"
                scored["should_alert"]   = False
                scored["should_log"]     = False
                scored["entry_allowed"]  = False

            elif _lg_forex and not LEGACY_FOREX_ENABLED:
                scored["entry_state"]    = "WATCH_ONLY_LEGACY_FOREX_DISABLED"
                scored["should_alert"]   = False
                scored["should_log"]     = False
                scored["entry_allowed"]  = False

        # ── MARKET HOURS GATE ─────────────────────────────────────────────────
        # Hard blocks (Saturday, Sunday pre-22:00, Friday 21:30+):
        #   - entry_state forced to SKIP_SESSION — strategy output overridden
        #   - entry_allowed=False written to scored for audit/dashboard
        #   - no logging, no alert (enforced in logging gate below)
        # Caution windows (Friday 21:00–21:30, Sunday 22:00–22:59):
        #   - score penalised, alerts suppressed — entry_state unchanged
        _mh = market_hours_gate()

        if _mh["blocked"]:
            # Force entry_state — strategy ENTER_NOW is not valid in a closed market
            scored["entry_state"]    = "SKIP_SESSION"
            scored["entry_allowed"]  = False
            scored["should_alert"]   = False
            scored["should_log"]     = False

        # Attach all audit fields regardless of block/caution status
        scored["weekend_block"]         = _mh.get("weekend_block",         False)
        scored["session_block"]         = _mh.get("session_block",         False)
        scored["market_closed"]         = _mh.get("market_closed",         False)
        scored["low_liquidity_window"]  = _mh.get("low_liquidity_window",  False)
        scored["blocked_reason"]        = _mh.get("blocked_reason",        "")
        if "entry_allowed" not in scored:
            scored["entry_allowed"]     = True

        if _mh["penalty_pts"]:
            scored["score"] = max(
                0, round((scored.get("score") or 0) - _mh["penalty_pts"], 1)
            )

        if _mh["alert_suppressed"]:
            scored["should_alert"] = False
        elif _mh["alert_min_grade"] == "A+":
            if scored.get("grade") != "A+":
                scored["should_alert"] = False

        if _mh["reason"]:
            _mh_sym = "🚫" if _mh["blocked"] else "⚠️"
            scored["flags"] = (
                scored.get("flags", []) + [f"{_mh_sym} {_mh['reason']}"]
            )[:5]

        # ── MINIMUM QUALITY GATE ──────────────────────────────────────────────
        _qg = minimum_quality_gate(scored, confluence, pair)

        if _qg["penalty_pts"]:
            scored["score"] = max(
                0, round((scored.get("score") or 0) - _qg["penalty_pts"], 1)
            )
        for _f in _qg["flags"]:
            scored["flags"] = (scored.get("flags", []) + [_f])[:5]
        if not _qg["passes"]:
            scored["flags"] = (
                scored.get("flags", []) + [f"🚫 {_qg['block_reason']}"]
            )[:5]
            scored["should_alert"] = False

        # ── GRADE C METAL ENTER_NOW ALERT SUPPRESSION ─────────────────────────
        # Grade C gold/silver ENTER_NOW still logs (strategy conviction) but
        # never fires a Slack alert — too low confidence for user notification.
        _gold   = scored.get("gold_mode", False)
        _sniper = scored.get("signal_mode") == "news_sniper"
        if (
            _gold
            and scored.get("entry_state") == "ENTER_NOW"
            and scored.get("grade") == "C"
        ):
            scored["should_alert"] = False
            scored["flags"] = (
                scored.get("flags", [])
                + ["⚠️ LOW CONFIDENCE ENTER_NOW — grade C, alert suppressed"]
            )[:5]

        # ── LOGGING GATE ──────────────────────────────────────────────────────
        signal_id = ""

        if _mh["blocked"] or not _qg["passes"]:
            # Market-hours hard block OR quality gate hard block
            _log_now = False
        elif _gold or _sniper:
            # Gold + news-sniper: ENTER_NOW is the gate (unchanged behavior)
            _log_now = scored.get("entry_state") == "ENTER_NOW"
        else:
            # Forex: ENTER_NOW gate — restores May 12 execution-ready contract.
            # forex_strategy.py sets entry_state="ENTER_NOW" only on strict FOREX PASS
            # (valid_rr >= 1.5 + valid_setup + valid_struct + news_safe).
            # EARLY ENTRY and watch candidates never set ENTER_NOW → never logged.
            _log_now = scored.get("entry_state") == "ENTER_NOW"

        if _log_now:
            signal_id = log_signal(scored, confluence, alerted=scored.get("should_alert", False))
        scored["signal_id"] = signal_id   # empty string if not logged

        if DEBUG_DECISIONS:
            try:
                _trace(scored, signal_id)
            except Exception:
                pass  # never crash scan on trace failure

        # Push to dashboard (non-blocking)
        try:
            from dashboard.app import update_dashboard
            ict = confluence.get("ict", {})
            update_dashboard(pair, scored, confluence, ict)
        except Exception:
            pass

        # Push extra strategy candidates to dashboard under isolated keys
        # (non-blocking; uses separate _extra_store so existing /api/signals is unaffected)
        for _cand in _extra_candidates:
            try:
                _cand_mode = _cand.get("signal_mode", "unknown")
                from dashboard.app import update_extra_candidate
                update_extra_candidate(pair, _cand_mode, _cand)
            except Exception:
                pass

        return (scored, confluence) if return_confluence else scored

    except Exception as e:
        logger.error(f"Error scanning {pair}: {e}", exc_info=True)
        return (None, None) if return_confluence else None


def generate_briefing(session: str) -> dict:
    """
    Generate a full pre-session briefing.
    Scans all pairs, returns top setups + news warnings.
    session: 'tokyo' | 'london' | 'new_york'
    """
    logger.info(f"Generating {session} briefing...")

    all_signals = []

    for pair in PAIRS:
        result = scan_pair(pair)
        if result:
            all_signals.append(result)

    all_signals.sort(key=lambda s: s["score"], reverse=True)

    alert_setups = [s for s in all_signals if s["should_alert"]]
    watch_setups = [s for s in all_signals if s["should_log"] and not s["should_alert"]]

    news = get_session_news_summary(session)

    briefing = {
        "session":       session,
        "generated_at":  datetime.utcnow().isoformat(),
        "setups":        alert_setups,
        "watch_list":    watch_setups,
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
    """Pretty-print the briefing to terminal."""
    session = briefing["session"].replace("_", " ").title()
    print(f"\n{'='*60}")
    print(f"  PRE-SESSION BRIEFING — {session}")
    print(f"  {briefing['generated_at']} UTC")
    print(f"{'='*60}")

    news = briefing.get("news", [])
    if news:
        print(f"\n⚠️  HIGH-IMPACT NEWS:")
        for event in news:
            t = (
                event["time"].strftime("%H:%M UTC")
                if hasattr(event["time"], "strftime")
                else event["time"]
            )
            print(f"   {event['currency']} — {event['event']} @ {t}")

    setups = briefing.get("setups", [])
    print(f"\n🔔  ALERT SETUPS ({len(setups)}):")
    if not setups:
        print("   None — no high-confluence setups right now.")

    for s in setups:
        dir_sym = "▲" if s["direction"] == "bullish" else "▼"
        grade   = s.get("grade", "?")
        score   = s.get("score", 0)
        print(f"\n   {dir_sym} {s['pair']}  [{score}/100 {grade}]  "
              f"{s.get('setup_type','').replace('_',' ').upper()}")
        print(f"     Price:   {s['current_price']:.5f}")
        print(f"     Trend:   H1={s.get('h1_trend','?')} | "
              f"M15={s.get('m15_trend','?')} | M5={s.get('m5_trend','?')}")

        zone = s.get("top_zone") or {}
        if zone:
            print(f"     Zone:    {zone.get('type','').title()} "
                  f"{zone.get('low',0):.5f}–{zone.get('high',0):.5f} "
                  f"(str={zone.get('strength',0)})")

        pattern = s.get("entry_pattern") or {}
        if pattern:
            print(f"     Pattern: {pattern.get('pattern','').replace('_',' ').title()} "
                  f"({pattern.get('direction','')})")

        # ICT summary if available
        ict_bonus = s.get("ict_bonus", 0)
        if ict_bonus > 0:
            bd = s.get("breakdown", {})
            print(f"     ICT:     +{ict_bonus} pts")

    watch = briefing.get("watch_list", [])
    print(f"\n👁️  WATCH LIST ({len(watch)}):")
    if not watch:
        print("   None")
    for s in watch:
        dir_sym = "▲" if s["direction"] == "bullish" else "▼"
        print(f"   {dir_sym} {s['pair']}  [{s['score']}/100]  "
              f"{s.get('setup_type','').replace('_',' ')}")

    print(f"\n{'='*60}\n")