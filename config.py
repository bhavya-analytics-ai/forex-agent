# ============================================================
# FOREX SCANNER CONFIG
# ============================================================

import os
from dotenv import load_dotenv

load_dotenv()

OANDA_API_KEY     = os.getenv("OANDA_API_KEY")
OANDA_ACCOUNT_ID  = os.getenv("OANDA_ACCOUNT_ID")
OANDA_ENVIRONMENT = os.getenv("OANDA_ENVIRONMENT", "practice")

# --- PAIRS (11 total) ---
PAIRS = [
    # JPY pairs
    "USD_JPY",
    "GBP_JPY",
    "EUR_JPY",
    "CHF_JPY",
    "CAD_JPY",
    "NZD_JPY",
    # Majors
    "GBP_USD",
    "EUR_USD",
    "EUR_GBP",
    # Metals
    "XAU_USD",  # Gold
    "XAG_USD",  # Silver
]

# --- TIMEFRAMES ---
TIMEFRAMES = {
    "structure":    "H1",   # Mark zones and structure
    "confirmation": "M15",  # Mid confirmation
    "entry":        "M5",   # Entry trigger
    "trigger":      "M1",   # M1 — actual entry candle
}

# Candle counts to fetch per timeframe
CANDLE_COUNTS = {
    "H1":  400,
    "M15": 100,
    "M5":  60,
    "M1":  60,
}

# Metals need more history to find proper zones
CANDLE_COUNTS_METALS = {
    "H1":  500,
    "M15": 200,
    "M5":  100,
    "M1":  60,
}

METAL_PAIRS = ["XAU_USD", "XAG_USD"]

# --- SESSIONS (UTC) ---
SESSIONS = {
    "tokyo": {
        "start":      "00:00",
        "end":        "06:00",
        "brief_time": "23:30",  # Day before UTC
    },
    "london": {
        "start":      "07:00",
        "end":        "12:00",
        "brief_time": "06:30",
    },
    "new_york": {
        "start":      "13:00",
        "end":        "22:00",
        "brief_time": "12:30",
    },
}

# --- ZONE DETECTION ---
ZONE_CONFIG = {
    "swing_lookback":       10,   # Bars each side to confirm swing high/low
    "zone_merge_pips":      10,   # Merge zones within this many pips
    "min_zone_touches":     2,    # Min touches to count as valid zone
    "supply_demand_bars":   5,    # Bars of consolidation before big move
    "big_move_multiplier":  1.5,  # Move must be X times avg candle size
}

# --- SIGNAL SCORING THRESHOLDS ---
SCORING = {
    "min_score_alert": 65,
    "min_score_log":   40,
    "weights": {
        "zone_strength":   25,
        "tf_confluence":   25,
        "candle_pattern":  20,
        "session_context": 15,
        "news_clearance":  10,
        "quality_bonus":   15,
        "fvg_bonus":       10,
    }
}

# --- NEWS FILTER ---
NEWS_CONFIG = {
    "block_window_minutes":  60,
    "resume_window_minutes": 30,
    "impact_levels": ["HIGH"],
    "pair_currencies": {
        "USD_JPY": ["USD", "JPY"],
        "GBP_JPY": ["GBP", "JPY"],
        "EUR_JPY": ["EUR", "JPY"],
        "CHF_JPY": ["CHF", "JPY"],
        "CAD_JPY": ["CAD", "JPY"],
        "NZD_JPY": ["NZD", "JPY"],
        "GBP_USD": ["GBP", "USD"],
        "EUR_USD": ["EUR", "USD"],
        "EUR_GBP": ["EUR", "GBP"],
        "XAU_USD": ["USD", "XAU"],
        "XAG_USD": ["USD", "XAG"],
    }
}

# --- NEWS API KEYS ---
FINNHUB_API_KEY  = os.getenv("FINNHUB_API_KEY", "")
NEWSDATA_API_KEY = os.getenv("NEWSDATA_API_KEY", "")

# --- SLACK ---
SLACK_CONFIG = {
    "webhook_url":     os.getenv("SLACK_WEBHOOK_URL", ""),
    "alert_channel":   os.getenv("SLACK_ALERT_CHANNEL", "#forex-alerts"),
    "brief_channel":   os.getenv("SLACK_BRIEF_CHANNEL", "#forex-briefing"),
}

# --- DASHBOARD ---
DASHBOARD_CONFIG = {
    "host":            "127.0.0.1",
    "port":            5000,
    "refresh_seconds": 30,
}

# --- LOGGING ---
LOG_CONFIG = {
    "signal_log_path":  "logs/agent_signals.csv",   # agent ENTER_NOW signals
    "manual_log_path":  "logs/manual_trades.csv",   # your manually logged trades
    "app_log_path":     "logs/app.log",
}