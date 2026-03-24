"""
fetcher.py — Pull candles from OANDA API
M1 added as entry trigger timeframe.

FIX: XAU_USD pip size corrected from 0.1 → 0.01
     Old: SL calculations were 10x too wide for gold
     New: 1 pip gold = $0.01 (correct)
"""

import pandas as pd
from datetime import datetime
import logging
from oandapyV20 import API
from oandapyV20.endpoints.instruments import InstrumentsCandles
from config import OANDA_API_KEY, OANDA_ENVIRONMENT, CANDLE_COUNTS, CANDLE_COUNTS_METALS, METAL_PAIRS

logger = logging.getLogger(__name__)

client = API(access_token=OANDA_API_KEY, environment=OANDA_ENVIRONMENT)


def fetch_candles(pair: str, timeframe: str) -> pd.DataFrame:
    counts = CANDLE_COUNTS_METALS if pair in METAL_PAIRS else CANDLE_COUNTS
    count  = counts.get(timeframe, 100)

    params = {
        "granularity": timeframe,
        "count":       count,
        "price":       "M",
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
        if df.empty:
            return df
        df.set_index("time", inplace=True)
        df.sort_index(inplace=True)

        logger.info(f"Fetched {len(df)} candles for {pair} {timeframe}")
        return df

    except Exception as e:
        logger.error(f"Failed to fetch {pair} {timeframe}: {e}")
        return pd.DataFrame()


def fetch_all_timeframes(pair: str) -> dict:
    return {
        "H1":  fetch_candles(pair, "H1"),
        "M15": fetch_candles(pair, "M15"),
        "M5":  fetch_candles(pair, "M5"),
        "M1":  fetch_candles(pair, "M1"),
    }


def get_current_price(pair: str) -> float:
    df = fetch_candles(pair, "M1")
    if df.empty:
        df = fetch_candles(pair, "M5")
    if df.empty:
        return None
    return df["close"].iloc[-1]


def pip_size(pair: str) -> float:
    """
    Return pip size for a given pair.

    FIX: XAU_USD was 0.1 — WRONG. Gold pip = $0.01
    This was causing SL/TP to be 10x too wide on gold.
    Example: 20 pip SL on gold = $0.20 move (correct)
             Previously was being calculated as $2.00 move (wrong)
    """
    if "JPY" in pair:
        return 0.01
    elif pair == "XAU_USD":
        return 0.01   # FIX: was 0.1, now correct
    elif pair == "XAG_USD":
        return 0.001
    return 0.0001