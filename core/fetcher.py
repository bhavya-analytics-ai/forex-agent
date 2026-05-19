"""
fetcher.py — Pull candles from OANDA API
M1 added as entry trigger timeframe.

FIX: XAU_USD pip size corrected from 0.1 → 0.01
     Old: SL calculations were 10x too wide for gold
     New: 1 pip gold = $0.01 (correct)
"""

import pandas as pd
from datetime import datetime, timezone
import logging
from oandapyV20 import API
from oandapyV20.endpoints.instruments import InstrumentsCandles
from oandapyV20.endpoints.pricing import PricingInfo
from config import OANDA_API_KEY, OANDA_ENVIRONMENT, OANDA_ACCOUNT_ID, CANDLE_COUNTS, CANDLE_COUNTS_METALS, METAL_PAIRS

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


def fetch_candles_from(pair: str, timeframe: str, from_time: datetime) -> pd.DataFrame:
    """
    Fetch all M5 (or any TF) candles from from_time to now.
    Uses OANDA 'from'/'to' params instead of count — supports historical lookback
    of any length. Paginates automatically (OANDA max 5000 candles per call).
    Returns DataFrame with columns: open, high, low, close, volume — indexed by UTC time.
    """
    now = datetime.now(timezone.utc)
    if from_time.tzinfo is None:
        from_time = from_time.replace(tzinfo=timezone.utc)

    all_rows = []
    cursor = from_time

    while cursor < now:
        params = {
            "granularity": timeframe,
            "from":        cursor.strftime("%Y-%m-%dT%H:%M:%SZ"),
            "to":          now.strftime("%Y-%m-%dT%H:%M:%SZ"),
            "price":       "M",
        }
        try:
            req = InstrumentsCandles(instrument=pair, params=params)
            client.request(req)
            raw = req.response["candles"]
        except Exception as e:
            logger.error(f"fetch_candles_from {pair} {timeframe} failed: {e}")
            break

        if not raw:
            break

        rows = []
        for c in raw:
            if not c["complete"]:
                continue
            rows.append({
                "time":   pd.to_datetime(c["time"], utc=True),
                "open":   float(c["mid"]["o"]),
                "high":   float(c["mid"]["h"]),
                "low":    float(c["mid"]["l"]),
                "close":  float(c["mid"]["c"]),
                "volume": int(c["volume"]),
            })

        all_rows.extend(rows)

        # OANDA max is 5000 per call — if less came back, we've reached now
        if len(raw) < 5000:
            break

        # Advance cursor to last candle time + 1 second to avoid duplicates
        last_time = pd.to_datetime(raw[-1]["time"], utc=True)
        cursor = last_time.to_pydatetime() + pd.Timedelta(seconds=1)

    if not all_rows:
        return pd.DataFrame()

    df = pd.DataFrame(all_rows)
    df.set_index("time", inplace=True)
    df.sort_index(inplace=True)
    df = df[~df.index.duplicated(keep="first")]
    logger.info(f"fetch_candles_from: {pair} {timeframe} from {from_time} → {len(df)} candles")
    return df


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


def get_live_price(pair: str) -> float:
    """
    Fetch the current mid price for a pair via OANDA PricingInfo (real-time bid/ask).
    Returns mid = (bid + ask) / 2, or None on failure.
    Used by the real-time SL/TP monitor — faster than candle polling.
    """
    try:
        req  = PricingInfo(accountID=OANDA_ACCOUNT_ID, params={"instruments": pair})
        client.request(req)
        px   = req.response["prices"][0]
        bid  = float(px["bids"][0]["price"])
        ask  = float(px["asks"][0]["price"])
        return round((bid + ask) / 2, 5)
    except Exception as e:
        logger.warning(f"get_live_price({pair}) failed: {e}")
        return None


def get_live_bid_ask(pair: str):
    """
    Fetch current bid and ask prices for a pair via OANDA PricingInfo.
    Returns (bid, ask) tuple, or (None, None) on failure.

    Used by the SL/TP monitor for correct execution-side evaluation:
      LONG:  SL and TP both trigger when BID reaches the level
             (closing a long = selling at bid)
      SHORT: SL and TP both trigger when ASK reaches the level
             (closing a short = buying at ask)

    Using mid-price for SL/TP detection creates a systematic gap equal to
    half the spread. For gold (spread ~0.20–0.50 pts) this causes OANDA to
    fire SL before the mid-price monitor detects it — the "didn't touch"
    false impression on a mid-price chart.
    """
    try:
        req = PricingInfo(accountID=OANDA_ACCOUNT_ID, params={"instruments": pair})
        client.request(req)
        px  = req.response["prices"][0]
        bid = round(float(px["bids"][0]["price"]), 5)
        ask = round(float(px["asks"][0]["price"]), 5)
        return bid, ask
    except Exception as e:
        logger.warning(f"get_live_bid_ask({pair}) failed: {e}")
        return None, None


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