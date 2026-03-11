"""
fetcher.py — Pull candles from OANDA API
"""

import pandas as pd
from datetime import datetime
import logging
from oandapyV20 import API
from oandapyV20.endpoints.instruments import InstrumentsCandles
from config import OANDA_API_KEY, OANDA_ENVIRONMENT, CANDLE_COUNTS

logger = logging.getLogger(__name__)

client = API(access_token=OANDA_API_KEY, environment=OANDA_ENVIRONMENT)


def fetch_candles(pair: str, timeframe: str) -> pd.DataFrame:
    """
    Fetch OHLCV candles for a pair and timeframe.
    Returns a clean DataFrame with columns: time, open, high, low, close, volume
    """
    count = CANDLE_COUNTS.get(timeframe, 100)

    params = {
        "granularity": timeframe,
        "count": count,
        "price": "M",  # Midpoint candles
    }

    try:
        req = InstrumentsCandles(instrument=pair, params=params)
        client.request(req)
        raw = req.response["candles"]

        rows = []
        for c in raw:
            if not c["complete"]:
                continue
            rows.append({
                "time":   pd.to_datetime(c["time"]),
                "open":   float(c["mid"]["o"]),
                "high":   float(c["mid"]["h"]),
                "low":    float(c["mid"]["l"]),
                "close":  float(c["mid"]["c"]),
                "volume": int(c["volume"]),
            })

        df = pd.DataFrame(rows)
        df.set_index("time", inplace=True)
        df.sort_index(inplace=True)

        logger.info(f"Fetched {len(df)} candles for {pair} {timeframe}")
        return df

    except Exception as e:
        logger.error(f"Failed to fetch {pair} {timeframe}: {e}")
        return pd.DataFrame()


def fetch_all_timeframes(pair: str) -> dict:
    """
    Fetch H1, M15, M5 candles for a pair in one call.
    Returns dict: { "H1": df, "M15": df, "M5": df }
    """
    return {
        "H1":  fetch_candles(pair, "H1"),
        "M15": fetch_candles(pair, "M15"),
        "M5":  fetch_candles(pair, "M5"),
    }


def get_current_price(pair: str) -> float:
    """Get the latest close price for a pair."""
    df = fetch_candles(pair, "M5")
    if df.empty:
        return None
    return df["close"].iloc[-1]


def pip_size(pair: str) -> float:
    """Return pip size for a pair."""
    if "JPY" in pair:
        return 0.01
    elif pair in ["XAU_USD"]:
        return 0.1
    elif pair in ["XAG_USD"]:
        return 0.001
    return 0.0001