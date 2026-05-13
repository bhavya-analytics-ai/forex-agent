"""
tests/test_news_country_mapping.py

Verifies that ForexFactory country codes are mapped to currency codes
the same way Finnhub does — fixing the bug where "US" != "USD" caused
XAU/USD to be marked safe during USD news when ForexFactory was active.
"""

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from datetime import datetime, timedelta
from unittest.mock import patch
import pandas as pd

from filters.news import _COUNTRY_TO_CURRENCY, is_news_safe


# ── 1. Country code mapping table ─────────────────────────────────────────────

def test_country_code_mapping():
    assert _COUNTRY_TO_CURRENCY.get("US") == "USD", "US must map to USD"
    assert _COUNTRY_TO_CURRENCY.get("GB") == "GBP", "GB must map to GBP"
    assert _COUNTRY_TO_CURRENCY.get("JP") == "JPY", "JP must map to JPY"
    assert _COUNTRY_TO_CURRENCY.get("EU") == "EUR", "EU must map to EUR"
    assert _COUNTRY_TO_CURRENCY.get("CA") == "CAD", "CA must map to CAD"
    assert _COUNTRY_TO_CURRENCY.get("AU") == "AUD", "AU must map to AUD"
    assert _COUNTRY_TO_CURRENCY.get("CH") == "CHF", "CH must map to CHF"
    print("PASS: _COUNTRY_TO_CURRENCY table correct")


# ── 2. ForexFactory normalisation: "US" → "USD" ───────────────────────────────

def test_forexfactory_country_normalization():
    """
    Simulate a raw ForexFactory event with country="US".
    After normalization through _COUNTRY_TO_CURRENCY the stored
    currency field must be "USD", not "US".
    """
    raw_country = "US"
    normalized  = _COUNTRY_TO_CURRENCY.get(raw_country.upper(), raw_country.upper())
    assert normalized == "USD", f"Expected 'USD', got '{normalized}'"
    print("PASS: ForexFactory 'US' normalizes to 'USD'")


# ── 3. is_news_safe("XAU_USD") blocks on USD event from ForexFactory data ─────

def test_is_news_safe_xau_blocks_on_usd_event():
    """
    Inject a mock calendar DataFrame that looks like it came from ForexFactory
    (currency already normalized to "USD" via the fix).
    is_news_safe("XAU_USD") must return safe=False.
    """
    now = datetime.utcnow()
    mock_df = pd.DataFrame([{
        "time":     now + timedelta(minutes=30),   # inside the 60-min block window
        "currency": "USD",                          # what the fix produces
        "impact":   "HIGH",
        "event":    "Non-Farm Payrolls",
        "forecast": "200K",
        "previous": "185K",
        "actual":   "",
    }])

    with patch("filters.news.fetch_forexfactory_calendar", return_value=mock_df):
        result = is_news_safe("XAU_USD")

    assert result["safe"] is False, (
        f"XAU_USD should be blocked by USD HIGH event. Got: {result}"
    )
    assert "USD" in result["reason"] or "Non-Farm" in result["reason"], (
        f"Reason should mention the event. Got: {result['reason']}"
    )
    print(f"PASS: is_news_safe('XAU_USD') blocked — reason: {result['reason']}")


# ── 4. Regression: "US" raw (pre-fix) would NOT have blocked ──────────────────

def test_regression_raw_us_does_not_match_xau():
    """
    Confirm the old bug: if currency is left as raw "US" it does NOT block XAU_USD.
    This is the exact failure mode the fix addresses.
    """
    now = datetime.utcnow()
    mock_df = pd.DataFrame([{
        "time":     now + timedelta(minutes=30),
        "currency": "US",   # pre-fix: raw country code, never mapped
        "impact":   "HIGH",
        "event":    "Non-Farm Payrolls",
        "forecast": "", "previous": "", "actual": "",
    }])

    with patch("filters.news.fetch_forexfactory_calendar", return_value=mock_df):
        result = is_news_safe("XAU_USD")

    # With raw "US" the old code returned safe=True — this is the bug
    assert result["safe"] is True, (
        "Regression check: raw 'US' should not match 'USD' in pair_currencies. "
        f"Got safe={result['safe']} — this confirms the fix is necessary."
    )
    print("PASS: regression confirmed — raw 'US' does not block XAU_USD (fix is required)")


# ─────────────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    test_country_code_mapping()
    test_forexfactory_country_normalization()
    test_is_news_safe_xau_blocks_on_usd_event()
    test_regression_raw_us_does_not_match_xau()
    print("\nAll tests passed.")
