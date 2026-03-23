"""
core/streamer.py — Real-time OANDA streaming mode

On every M1 candle close:
  → runs full ICT check (OB, MSS, ChoCH, sweep)
  → fires instant alert if ChoCH or MSS detected
  → shows candle countdown so you know how long the window is open

Usage: python main.py stream
"""

import json
import time
import logging
import threading
from datetime import datetime, timezone
from collections import defaultdict

import pandas as pd
from oandapyV20 import API
from oandapyV20.endpoints.pricing import PricingStream

from config import OANDA_API_KEY, OANDA_ACCOUNT_ID, OANDA_ENVIRONMENT, PAIRS
from core.fetcher import fetch_all_timeframes, pip_size
from core.ict import get_ict_context, format_ict_summary
from core.structure import detect_market_structure
from core.zones import get_active_zones
from core.candles import detect_patterns
from alerts.scorer import score_signal
from alerts.logger import log_signal
from filters.killzones import get_killzone_context, should_suppress_signal, format_killzone_banner

logger = logging.getLogger(__name__)

# In-memory M1 candle builder per pair
# Accumulates ticks → builds complete M1 candles
_candle_builders = defaultdict(lambda: {
    "open": None, "high": None, "low": None, "close": None,
    "volume": 0, "minute": None,
})

# Track last alert per pair to avoid spam
_last_alert = {}
ALERT_COOLDOWN_SECONDS = 60


def start_streamer():
    """
    Connect to OANDA streaming API.
    Subscribe to all 11 pairs.
    On every tick: update M1 candle builder.
    On M1 close: run full ICT analysis.
    """
    client     = API(access_token=OANDA_API_KEY, environment=OANDA_ENVIRONMENT)
    pairs_str  = ",".join(PAIRS)

    params = {"instruments": pairs_str}

    logger.info(f"Connecting to OANDA stream for {len(PAIRS)} pairs...")
    print(f"\n🔴 STREAMING LIVE — watching {len(PAIRS)} pairs")
    print(f"   Dashboard: http://localhost:5000")
    print(f"   Press Ctrl+C to stop\n")

    # Start countdown display thread
    countdown_thread = threading.Thread(target=_show_countdown, daemon=True)
    countdown_thread.start()

    try:
        req = PricingStream(accountID=OANDA_ACCOUNT_ID, params=params)

        for raw_msg in client.request(req):
            try:
                _handle_tick(raw_msg)
            except Exception as e:
                logger.debug(f"Tick error: {e}")

    except KeyboardInterrupt:
        logger.info("Streamer stopped by user.")
    except Exception as e:
        logger.error(f"Stream error: {e}", exc_info=True)
        print(f"\n⚠️ Stream disconnected: {e}")
        print("Reconnecting in 5 seconds...")
        time.sleep(5)
        start_streamer()   # Auto-reconnect


def _handle_tick(msg: dict):
    """Process a single tick from the stream."""
    if msg.get("type") != "PRICE":
        return

    pair = msg.get("instrument", "").replace("/", "_")
    if pair not in PAIRS:
        return

    # Use mid price
    bids = msg.get("bids", [{}])
    asks = msg.get("asks", [{}])
    if not bids or not asks:
        return

    bid = float(bids[0].get("price", 0))
    ask = float(asks[0].get("price", 0))
    mid = (bid + ask) / 2

    if mid == 0:
        return

    # Current UTC minute
    now    = datetime.now(timezone.utc)
    minute = now.replace(second=0, microsecond=0)

    builder = _candle_builders[pair]

    # New minute = previous candle is complete
    if builder["minute"] is not None and builder["minute"] != minute:
        _on_candle_close(pair, builder)

        # Start new candle
        _candle_builders[pair] = {
            "open": mid, "high": mid, "low": mid, "close": mid,
            "volume": 1, "minute": minute,
        }
    else:
        # Update current candle
        if builder["open"] is None:
            builder["open"]   = mid
            builder["minute"] = minute

        builder["high"]   = max(builder["high"] or mid, mid)
        builder["low"]    = min(builder["low"]  or mid, mid)
        builder["close"]  = mid
        builder["volume"] += 1
        builder["minute"]  = minute


def _on_candle_close(pair: str, candle: dict):
    """
    Called when a M1 candle closes.
    Fetches full candle data and runs ICT analysis.
    """
    logger.debug(f"M1 close: {pair} @ {candle['close']:.5f}")

    try:
        # Fetch fresh candles for all timeframes
        candles = fetch_all_timeframes(pair)
        if any(df.empty for df in candles.values()):
            return

        df_h1  = candles["H1"]
        df_m15 = candles["M15"]
        df_m5  = candles["M5"]
        df_m1  = candles["M1"]

        # Run ICT analysis
        ict = get_ict_context(df_h1, df_m15, df_m5)

        # Check for instant trigger conditions
        mss_fired   = ict["mss_m5"]["detected"] or ict["mss_m15"]["detected"]
        choch_fired = ict["choch_m5"]["detected"] or ict["choch_m15"]["detected"]
        sweep_fired = ict["has_sweep"]

        if not (mss_fired or choch_fired or sweep_fired):
            return  # Nothing actionable on this M1 close

        # Cooldown check — don't spam alerts for same pair
        now       = time.time()
        last_time = _last_alert.get(pair, 0)
        if now - last_time < ALERT_COOLDOWN_SECONDS:
            return

        # Build full confluence for scoring
        from core.confluence import check_confluence
        confluence = check_confluence(candles, pair)
        confluence["ict"] = ict

        scored = score_signal(confluence, pair)

        # Killzone filter
        kz_ctx = get_killzone_context(pair)
        if should_suppress_signal(scored["grade"], kz_ctx):
            return

        # Only alert on A/A+ from streaming
        if scored["grade"] not in ["A+", "A"]:
            return

        _last_alert[pair] = now

        # Print streaming alert
        _print_stream_alert(pair, scored, confluence, ict, kz_ctx)

        # Log it
        if scored["should_log"]:
            log_signal(scored, confluence, alerted=True)

        # Push to Slack
        try:
            from config import SLACK_CONFIG
            if SLACK_CONFIG.get("webhook_url"):
                from alerts.slack import send_signal_alert
                send_signal_alert(scored, confluence)
        except Exception:
            pass

        # Update dashboard
        try:
            from dashboard.app import update_dashboard
            update_dashboard(pair, scored, confluence, ict)
        except Exception:
            pass

    except Exception as e:
        logger.error(f"Error processing M1 close for {pair}: {e}", exc_info=True)


def _print_stream_alert(
    pair: str,
    scored: dict,
    confluence: dict,
    ict: dict,
    kz_ctx: dict,
):
    """
    Print the live trigger alert in the new ICT format.

    ⚡⚡⚡ LIVE TRIGGER — GBP_JPY
    ─────────────────────────────
    🔴 BEARISH | MSS confirmed on M5
    💧 Liquidity swept: buy-side @ 191.340
    📦 Bearish OB: 191.180 – 191.290 (M15)
    📉 Price in PREMIUM zone (68%)
    🕐 NY Open Killzone — 14 min remaining
    ⏱  Impulse window: ~3 M1 candles (~3 min)
    🎯 Scalp: sell-side liq @ 190.820
    🎯 Swing: next H1 level @ 190.400
    ─────────────────────────────
    Score: 91/100 | Grade: A+
    """
    direction = scored.get("direction", "").upper()
    dir_sym   = "🔴 BEARISH" if direction == "BEARISH" else "🟢 BULLISH"
    grade     = scored.get("grade", "?")
    score     = scored.get("score", 0)

    # ICT triggers that fired
    mss   = ict.get("mss_m5") or ict.get("mss_m15") or {}
    choch = ict.get("choch_m5") or ict.get("choch_m15") or {}
    sweep = ict.get("recent_sweep") or {}
    ob    = ict.get("top_ob") or {}
    pd    = ict.get("premium_discount") or {}

    # Build trigger line
    triggers = []
    if mss.get("detected"):
        triggers.append(f"MSS confirmed on {'M5' if ict['mss_m5']['detected'] else 'M15'}")
    if choch.get("detected"):
        triggers.append(f"ChoCH on {'M5' if ict['choch_m5']['detected'] else 'M15'}")

    trigger_str = " + ".join(triggers) if triggers else "ICT trigger"

    lines = [
        "",
        "⚡⚡⚡ LIVE TRIGGER — " + pair,
        "─" * 45,
        f"{dir_sym} | {trigger_str}",
    ]

    # Liquidity sweep
    if sweep:
        sweep_type = sweep.get("type", "").replace("_", "-")
        swept_at   = sweep.get("swept_level", 0)
        lines.append(f"💧 Liquidity swept: {sweep_type} @ {swept_at:.5f}")

    # Order block
    if ob:
        tf_label = ob.get("timeframe", "M15")
        lines.append(
            f"📦 {ob['type'].title()} OB: {ob['low']:.5f} – {ob['high']:.5f} ({tf_label})"
        )

    # Premium/discount
    if pd.get("zone") in ["premium", "discount"]:
        pct = round(pd.get("pct", 0) * 100)
        zone_label = pd["zone"].upper()
        lines.append(f"{'📈' if zone_label=='PREMIUM' else '📉'} Price in {zone_label} zone ({pct}%)")

    # Killzone
    lines.append(format_killzone_banner(kz_ctx))

    # Impulse window estimate (3 M1 candles = ~3 min)
    lines.append("⏱  Impulse window: ~3 M1 candles (~3 min)")

    # Targets
    h1_struct = confluence.get("h1", {}).get("structure", {})
    last_low  = h1_struct.get("last_low", 0)
    last_high = h1_struct.get("last_high", 0)
    price     = scored.get("current_price", 0)

    if direction == "BEARISH" and last_low:
        lines.append(f"🎯 Scalp target: sell-side liquidity @ {last_low:.5f}")
        lines.append(f"🎯 Swing target: next H1 low")
    elif direction == "BULLISH" and last_high:
        lines.append(f"🎯 Scalp target: buy-side liquidity @ {last_high:.5f}")
        lines.append(f"🎯 Swing target: next H1 high")

    lines += [
        "─" * 45,
        f"Score: {score}/100 | Grade: {grade}",
        f'"{_setup_tagline(scored, ict)}"',
        "",
    ]

    print("\n".join(lines))


def _setup_tagline(scored: dict, ict: dict) -> str:
    """Generate a one-line plain-English description of the setup."""
    parts = []

    if ict.get("top_ob"):
        parts.append("OB")
    if ict.get("has_mss"):
        parts.append("MSS")
    if ict.get("has_choch"):
        parts.append("ChoCH")
    if ict.get("has_sweep"):
        parts.append("liquidity sweep")

    pd_zone = ict.get("premium_discount", {}).get("zone", "")
    if pd_zone in ["premium", "discount"]:
        parts.append(pd_zone)

    direction = scored.get("direction", "")
    grade     = scored.get("grade", "")

    if parts:
        return f"{' + '.join(parts)} = {'textbook ICT ' + direction if grade == 'A+' else direction + ' setup'}"
    return f"{grade} {direction} setup"


def _show_countdown():
    """
    Background thread that shows M1 candle countdown.
    Updates every second in the terminal title bar.
    """
    while True:
        try:
            now     = datetime.now(timezone.utc)
            secs    = 60 - now.second
            minutes = now.strftime("%H:%M")

            # Update terminal title with countdown
            print(f"\r⏱  Next M1 candle in {secs:02d}s  [{minutes} UTC]", end="", flush=True)
            time.sleep(1)
        except Exception:
            time.sleep(1)