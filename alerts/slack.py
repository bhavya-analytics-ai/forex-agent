"""
slack.py — Send real-time alerts and pre-session briefings to Slack

BUG FIX:
- breakdown keys fixed to match scorer.py (zone, tf, pattern, session, news)
  old keys (zone_strength, tf_confluence, candle_pattern) always returned 0
- ICT context added to live signal alerts
- London session emoji added
"""

import requests
import logging
from datetime import datetime
from config import SLACK_CONFIG
from alerts.scorer import format_score_bar, score_label

logger = logging.getLogger(__name__)


def _send(webhook_url: str, payload: dict) -> bool:
    """Raw Slack webhook POST."""
    try:
        resp = requests.post(webhook_url, json=payload, timeout=10)
        resp.raise_for_status()
        return True
    except Exception as e:
        logger.error(f"Slack send failed: {e}")
        return False


def send_signal_alert(scored_signal: dict, confluence: dict):
    """
    Send a real-time trade setup alert to Slack.
    Only called for A and A+ signals.
    """
    pair      = scored_signal["pair"]
    direction = scored_signal["direction"].upper()
    score     = scored_signal["score"]
    grade     = scored_signal.get("grade", "?")
    setup     = scored_signal.get("setup_type", "").replace("_", " ").title()
    price     = scored_signal.get("current_price", 0)
    pattern   = scored_signal.get("entry_pattern") or {}
    zone      = scored_signal.get("top_zone") or {}
    session   = scored_signal.get("session_ctx", {}).get("session", "").replace("_", " ").title()
    flags     = scored_signal.get("flags", [])

    dir_emoji    = "🟢" if direction == "BULLISH" else "🔴"
    grade_emoji  = {"A+": "🔥", "A": "✅", "B": "⚠️", "C": "❌"}.get(grade, "")
    pattern_name = pattern.get("pattern", "—").replace("_", " ").title()
    zone_type    = zone.get("type", "—").replace("_", " ").title()

    # FVG line
    fvg_overlap = scored_signal.get("has_fvg_overlap", False)
    active_fvgs = scored_signal.get("active_fvgs", [])
    if fvg_overlap:
        fvg_line = "⚡ FVG + Zone overlap — premium setup"
    elif active_fvgs:
        fvg_type = active_fvgs[0]["type"].title()
        fvg_line = f"📊 {fvg_type} FVG nearby ({active_fvgs[0]['bottom']:.5f}–{active_fvgs[0]['top']:.5f})"
    else:
        fvg_line = "—"

    # Structure
    h1_trend   = confluence["h1"]["structure"].get("trend", "—")
    h1_phase   = confluence["h1"]["structure"].get("phase", "—")
    h1_quality = confluence["h1"]["structure"].get("setup_quality", "—")
    h1_depth   = confluence["h1"]["structure"].get("pullback_depth", 0)
    m15_trend  = confluence["m15"]["structure"].get("trend", "—")
    m5_trend   = confluence["m5"]["structure"].get("trend", "—")

    # ICT context
    ict      = confluence.get("ict", {})
    ict_line = _format_ict_line(ict)

    # Killzone
    try:
        from filters.killzones import get_killzone_context, format_killzone_banner
        kz_ctx   = get_killzone_context(pair)
        kz_line  = format_killzone_banner(kz_ctx)
    except Exception:
        kz_line = ""

    # Score breakdown — fixed keys matching scorer.py
    breakdown = scored_signal.get("breakdown", {})
    bd_str = (
        f"Zone {breakdown.get('zone', 0)}/25 | "
        f"TF {breakdown.get('tf', 0)}/25 | "
        f"Pattern {breakdown.get('pattern', 0)}/20 | "
        f"Session {breakdown.get('session', 0)}/15 | "
        f"News {breakdown.get('news', 0)}/10"
    )
    if scored_signal.get("fvg_bonus"):
        bd_str += f" | FVG +{scored_signal['fvg_bonus']}"

    # Flags (only include first 2 to keep Slack clean)
    flags_str = ""
    if flags:
        flags_str = "\n" + "\n".join(f"   {f}" for f in flags[:2])

    # Targets
    h1_struct = confluence["h1"]["structure"]
    last_low  = h1_struct.get("last_low", 0)
    last_high = h1_struct.get("last_high", 0)

    if direction == "BEARISH" and last_low:
        targets = f"🎯 Scalp: {last_low:.5f}  |  Swing: next H1 low"
    elif direction == "BULLISH" and last_high:
        targets = f"🎯 Scalp: {last_high:.5f}  |  Swing: next H1 high"
    else:
        targets = ""

    text = (
        f"{dir_emoji} *{pair}* — {direction} | {grade_emoji} Grade {grade}\n"
        f"━━━━━━━━━━━━━━━━━━━━━━\n"
        f"💰 Price:    `{price:.5f}`\n"
        f"🕐 Session:  {session}\n"
        f"{kz_line}\n"
        f"📊 Setup:    {setup}\n"
        f"🧱 Zone:     {zone_type}"
        + (f" ({zone.get('low',0):.5f}–{zone.get('high',0):.5f})" if zone else "") + "\n"
        f"🕯️ Pattern:  {pattern_name}\n"
        f"⚡ FVG:      {fvg_line}\n"
        + (f"🤖 ICT:      {ict_line}\n" if ict_line else "")
        + (f"{targets}\n" if targets else "")
        + f"\n"
        f"*What This Means*\n"
        f"_{confluence.get('tf_reading', '')}_\n"
        f"\n"
        f"*Structure*\n"
        f"  H1:  {_trend_emoji(h1_trend)} {h1_trend} | {h1_phase} | {h1_quality}"
        + (f" | {int(h1_depth*100)}% pullback" if h1_depth > 0 else "") + "\n"
        f"  M15: {_trend_emoji(m15_trend)} {m15_trend}\n"
        f"  M5:  {_trend_emoji(m5_trend)} {m5_trend}\n"
        + (flags_str + "\n" if flags_str else "")
        + f"\n"
        f"*Score: {score_label(score)}*\n"
        f"`{format_score_bar(score)}`\n"
        f"_{bd_str}_\n"
        f"\n"
        f"_⏰ {datetime.utcnow().strftime('%Y-%m-%d %H:%M')} UTC_"
    )

    payload  = {"text": text, "unfurl_links": False}
    webhook  = SLACK_CONFIG.get("webhook_url", "")
    success  = _send(webhook, payload) if webhook else False

    if success:
        logger.info(f"Slack alert sent: {pair} {direction} {grade} {score}/100")

    return success


def send_presession_briefing(session: str, briefing_data: dict):
    """Send the pre-session briefing to Slack."""
    session_label = session.replace("_", " ").title()
    session_emoji = {
        "tokyo":    "🌙",
        "london":   "🇬🇧",
        "new_york": "🗽",
    }.get(session, "📊")

    now_str   = datetime.utcnow().strftime("%Y-%m-%d %H:%M UTC")
    setups    = briefing_data.get("setups", [])
    news_list = briefing_data.get("news", [])

    lines = [
        f"{session_emoji} *Pre-Session Briefing — {session_label}*",
        f"_{now_str}_",
        "━━━━━━━━━━━━━━━━━━━━━━",
        "",
    ]

    # News first
    if news_list:
        lines.append("⚠️ *High-Impact News This Session*")
        for event in news_list:
            t = (
                event["time"].strftime("%H:%M UTC")
                if hasattr(event["time"], "strftime")
                else event["time"]
            )
            lines.append(f"  • {event['currency']} — {event['event']} @ {t}")
        lines.append("")

    # Setups
    if setups:
        lines.append(f"📋 *Setups to Watch ({len(setups)} pairs)*")
        lines.append("")

        for s in setups:
            pair      = s["pair"]
            direction = s["direction"].upper()
            score     = s["score"]
            grade     = s.get("grade", "?")
            setup     = s.get("setup_type", "").replace("_", " ").title()
            price     = s.get("current_price", 0)
            zone      = s.get("top_zone") or {}
            dir_emoji = "🟢" if direction == "BULLISH" else ("🔴" if direction == "BEARISH" else "⚪")
            g_emoji   = {"A+": "🔥", "A": "✅", "B": "⚠️"}.get(grade, "")

            lines.append(
                f"{dir_emoji} *{pair}*  {g_emoji} {grade}  `{format_score_bar(score, 8)}`"
            )
            lines.append(f"   Price: `{price:.5f}` | {setup}")
            if zone:
                lines.append(
                    f"   Zone: {zone.get('type','').title()} "
                    f"{zone.get('low',0):.5f}–{zone.get('high',0):.5f}"
                )
            lines.append(
                f"   H1→M15→M5: {s.get('h1_trend','?')} → "
                f"{s.get('m15_trend','?')} → {s.get('m5_trend','?')}"
            )
            lines.append("")
    else:
        lines.append("📋 *No high-confluence setups right now.*")
        lines.append("_Watch for setups as session opens._")

    lines += [
        "━━━━━━━━━━━━━━━━━━━━━━",
        "_Alerts fire in real-time when H1+M15+M5 align._",
    ]

    payload = {"text": "\n".join(lines), "unfurl_links": False}
    webhook = SLACK_CONFIG.get("webhook_url", "")
    return _send(webhook, payload) if webhook else False


def send_error_alert(message: str):
    """Send a simple error notification to Slack."""
    payload = {"text": f"⚠️ *Scanner Error*\n{message}"}
    webhook = SLACK_CONFIG.get("webhook_url", "")
    if webhook:
        _send(webhook, payload)


def _format_ict_line(ict: dict) -> str:
    if not ict:
        return ""
    parts = []
    if ict.get("has_mss"):
        t = (ict.get("mss_m5") or ict.get("mss_m15") or {}).get("type", "")
        parts.append(f"MSS {t}")
    if ict.get("has_choch"):
        t = (ict.get("choch_m5") or ict.get("choch_m15") or {}).get("type", "")
        parts.append(f"ChoCH {t}")
    if ict.get("has_sweep"):
        parts.append("Liquidity Sweep")
    if ict.get("has_ob"):
        ob = ict.get("top_ob", {})
        parts.append(f"{ob.get('type','').title()} OB")
    pd_zone = ict.get("premium_discount", {}).get("zone", "")
    if pd_zone in ["premium", "discount"]:
        pct = round(ict["premium_discount"].get("pct", 0) * 100)
        parts.append(f"{pd_zone.upper()} {pct}%")
    return " | ".join(parts)


def _trend_emoji(trend: str) -> str:
    if not trend:
        return "➡️"
    if "up" in trend:
        return "📈"
    if "down" in trend:
        return "📉"
    return "➡️"