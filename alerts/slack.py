"""
slack.py — Send real-time alerts and pre-session briefings to Slack
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
    Only called when score >= threshold.
    """
    pair      = scored_signal["pair"]
    direction = scored_signal["direction"].upper()
    score     = scored_signal["score"]
    setup     = scored_signal["setup_type"].replace("_", " ").title()
    price     = scored_signal["current_price"]
    pattern   = scored_signal.get("entry_pattern") or {}
    zone      = scored_signal.get("top_zone") or {}
    session   = scored_signal.get("session_ctx", {}).get("session", "").replace("_", " ").title()

    direction_emoji = "🟢" if direction == "BULLISH" else "🔴"
    pattern_name    = pattern.get("pattern", "").replace("_", " ").title() if pattern else "—"
    zone_type       = zone.get("type", "").replace("_", " ").title() if zone else "—"

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

    h1_trend  = confluence["h1"]["structure"].get("trend", "—")
    m15_trend = confluence["m15"]["structure"].get("trend", "—")
    m5_trend  = confluence["m5"]["structure"].get("trend", "—")

    breakdown = scored_signal["breakdown"]

    text = (
        f"{direction_emoji} *{pair}* — {direction} | {setup}\n"
        f"━━━━━━━━━━━━━━━━━━━━━━\n"
        f"💰 Price:     `{price:.5f}`\n"
        f"🕐 Session:   {session}\n"
        f"📊 Setup:     {setup}\n"
        f"🧱 Zone:      {zone_type} ({zone.get('high', ''):.5f} – {zone.get('low', ''):.5f})\n"
        f"🕯️ Pattern:   {pattern_name}\n"
        f"⚡ FVG:       {fvg_line}\n"
        f"\n"
        f"*Timeframe Alignment*\n"
        f"  H1:  {_trend_emoji(h1_trend)} {h1_trend}\n"
        f"  M15: {_trend_emoji(m15_trend)} {m15_trend}\n"
        f"  M5:  {_trend_emoji(m5_trend)} {m5_trend}\n"
        f"\n"
        f"*Signal Score: {score_label(score)}*\n"
        f"`{format_score_bar(score)}`\n"
        f"  Zone {breakdown.get('zone_strength',0)}/25 | "
        f"TF {breakdown.get('tf_confluence',0)}/30 | "
        f"Candle {breakdown.get('candle_pattern',0)}/20 | "
        f"Session {breakdown.get('session_context',0)}/15 | "
        f"News {breakdown.get('news_clearance',0)}/10"
        + (f" | FVG +{scored_signal.get('fvg_bonus',0)}" if scored_signal.get('fvg_bonus') else "") + "\n"
        f"\n"
        f"_⏰ {datetime.utcnow().strftime('%Y-%m-%d %H:%M')} UTC_"
    )

    payload = {
        "text": text,
        "unfurl_links": False,
    }

    webhook = SLACK_CONFIG["webhook_url"]
    success = _send(webhook, payload)

    if success:
        logger.info(f"Alert sent for {pair} {direction} score={score}")
    return success


def send_presession_briefing(session: str, briefing_data: dict):
    """
    Send the pre-session briefing report to Slack.
    briefing_data comes from reports/briefing.py
    """
    session_label = session.replace("_", " ").title()
    session_emoji = "🌙" if session == "tokyo" else "🗽"
    now_str       = datetime.utcnow().strftime("%Y-%m-%d %H:%M UTC")

    setups    = briefing_data.get("setups", [])
    news_list = briefing_data.get("news", [])

    lines = [
        f"{session_emoji} *Pre-Session Briefing — {session_label}*",
        f"_{now_str}_",
        "━━━━━━━━━━━━━━━━━━━━━━",
        "",
    ]

    # News warnings first
    if news_list:
        lines.append("⚠️ *High-Impact News This Session*")
        for event in news_list:
            t = event["time"].strftime("%H:%M UTC") if hasattr(event["time"], "strftime") else event["time"]
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
            setup     = s["setup_type"].replace("_", " ").title()
            price     = s["current_price"]
            zone      = s.get("top_zone") or {}
            dir_emoji = "🟢" if direction == "BULLISH" else ("🔴" if direction == "BEARISH" else "⚪")

            lines.append(
                f"{dir_emoji} *{pair}*  {score_label(score)}  `{format_score_bar(score, 8)}`"
            )
            lines.append(f"   Price: `{price:.5f}` | {setup}")
            if zone:
                lines.append(f"   Zone: {zone.get('type','').title()} {zone.get('low',0):.5f}–{zone.get('high',0):.5f}")
            lines.append(f"   H1→M15→M5: {s.get('h1_trend','?')} → {s.get('m15_trend','?')} → {s.get('m5_trend','?')}")
            lines.append("")
    else:
        lines.append("📋 *No high-confluence setups right now.*")
        lines.append("_Watch for setups as session opens._")

    lines += [
        "━━━━━━━━━━━━━━━━━━━━━━",
        "_Alerts will fire in real-time when 1H+15M+5M align._",
    ]

    payload = {"text": "\n".join(lines), "unfurl_links": False}
    webhook = SLACK_CONFIG["webhook_url"]
    return _send(webhook, payload)


def send_error_alert(message: str):
    """Send a simple error notification to Slack."""
    payload = {"text": f"⚠️ *Scanner Error*\n{message}"}
    _send(SLACK_CONFIG["webhook_url"], payload)


def _trend_emoji(trend: str) -> str:
    if "up" in trend:
        return "📈"
    elif "down" in trend:
        return "📉"
    return "➡️"