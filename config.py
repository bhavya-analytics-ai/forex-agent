# ============================================================
# FOREX SCANNER CONFIG
# Fill in your OANDA credentials below
# ============================================================

import os
from dotenv import load_dotenv

load_dotenv()

OANDA_API_KEY     = os.getenv("OANDA_API_KEY")
OANDA_ACCOUNT_ID  = os.getenv("OANDA_ACCOUNT_ID")
OANDA_ENVIRONMENT = os.getenv("OANDA_ENVIRONMENT", "practice")
SLACK_CONFIG = {
    "webhook_url": os.getenv("SLACK_WEBHOOK_URL", ""),
    "alert_channel": os.getenv("SLACK_ALERT_CHANNEL", "#forex-alerts"),
    "brief_channel": os.getenv("SLACK_BRIEF_CHANNEL", "#forex-briefing"),
}

# --- PAIRS ---
PAIRS = [
    "USD_JPY",
    "GBP_JPY",
    "EUR_JPY",
    "XAU_USD",  # Gold
    "XAG_USD",  # Silver
]

# --- TIMEFRAMES ---
TIMEFRAMES = {
    "structure": "H1",   # Mark zones and structure
    "confirmation": "M15",  # Mid confirmation
    "entry": "M5",          # Entry trigger
}

# Candle counts to fetch per timeframe
CANDLE_COUNTS = {
    "H1": 200,
    "M15": 100,
    "M5":  60,
}

# --- SESSIONS (UTC) ---
SESSIONS = {
    "tokyo": {
        "start": "00:00",
        "end":   "06:00",
        "brief_time": "23:30",  # Day before UTC
    },
    "new_york": {
        "start": "13:00",
        "end":   "22:00",
        "brief_time": "12:30",
    },
}

# --- ZONE DETECTION ---
ZONE_CONFIG = {
    "swing_lookback": 10,        # Bars each side to confirm swing high/low
    "zone_merge_pips": 10,       # Merge zones within this many pips
    "min_zone_touches": 2,       # Min touches to count as valid zone
    "supply_demand_bars": 5,     # Bars of consolidation before big move
    "big_move_multiplier": 1.5,  # Move must be X times avg candle size
}

# --- SIGNAL SCORING THRESHOLDS ---
SCORING = {
    "min_score_alert": 65,       # Only alert above this score
    "min_score_log": 40,         # Log everything above this
    "weights": {
        "zone_strength":     25,  # Max points from zone quality
        "tf_confluence":     30,  # Max points from 3 TF alignment
        "candle_pattern":    20,  # Max points from confirmation candle
        "session_context":   15,  # Max points from session fit
        "news_clearance":    10,  # Max points from news safety
    }
}

# --- NEWS FILTER ---
NEWS_CONFIG = {
    "block_window_minutes": 60,   # Block signals X min before high-impact news
    "resume_window_minutes": 30,  # Resume X min after news
    "impact_levels": ["HIGH"],    # Which impact levels to block on
    # Currency mapping per pair
    "pair_currencies": {
        "USD_JPY": ["USD", "JPY"],
        "GBP_JPY": ["GBP", "JPY"],
        "EUR_JPY": ["EUR", "JPY"],
        "XAU_USD": ["USD", "XAU"],
        "XAG_USD": ["USD", "XAG"],
    }
}

# --- SLACK ---
SLACK_CONFIG = {
    "webhook_url": "YOUR_SLACK_WEBHOOK_URL",
    "alert_channel": "#forex-alerts",
    "brief_channel": "#forex-briefing",
}

# --- LOGGING ---
LOG_CONFIG = {
    "signal_log_path": "logs/signals.csv",
    "app_log_path":    "logs/app.log",
}