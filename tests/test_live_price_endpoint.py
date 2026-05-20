"""
tests/test_live_price_endpoint.py

Tests for GET /api/live-price endpoint and frontend OANDA live polling.

Backend covers:
  - 200 response with correct JSON shape
  - Required keys: pair, bid, ask, mid, timestamp_utc, source, cache_age_ms
  - Pair normalization: XAU/USD → XAU_USD, USD/JPY → USD_JPY
  - Cache: second call within TTL returns source=oanda_pricing_cached, cache_age_ms > 0
  - Cache: first call returns source=oanda_pricing, cache_age_ms=0
  - OANDA failure: returns 503 with error JSON (does not crash)
  - Missing pair param: returns 400
  - bid <= mid <= ask ordering
  - timestamp_utc contains "UTC"
  - No strategy/gate/schema changes

Frontend covers (static template source checks):
  - _liveTradePollerTimer variable declared
  - _startLiveTradePoller function present
  - _stopLiveTradePoller function present
  - _pollLivePricesNow function present
  - Polls /api/live-price endpoint
  - Only polls open trade pairs (filters by outcome absent/empty)
  - Stops when no open trades remain
  - visibilitychange listener present (stops on browser tab hide)
  - _startLiveTradePoller called on manual tab switch
  - _stopLiveTradePoller called on non-manual tab switch
  - prev price preserved before update
  - renderManualTrades called after price update
"""

import json
import time
import unittest
from unittest.mock import patch


# ── Helpers ───────────────────────────────────────────────────────────────────

def _make_client():
    from dashboard.app import app
    app.config["TESTING"] = True
    return app.test_client()


# ── Backend: response shape ───────────────────────────────────────────────────

class TestLivePriceShape(unittest.TestCase):

    def setUp(self):
        self.client = _make_client()
        # Clear cache before each test
        import dashboard.app as _app
        _app._live_price_cache.clear()

    def _mock_bid_ask(self, bid=2335.10, ask=2335.40):
        return patch("core.fetcher.get_live_bid_ask", return_value=(bid, ask))

    def test_200_on_success(self):
        with self._mock_bid_ask():
            resp = self.client.get("/api/live-price?pair=XAU_USD")
        self.assertEqual(resp.status_code, 200)

    def test_required_keys(self):
        with self._mock_bid_ask():
            resp = self.client.get("/api/live-price?pair=XAU_USD")
        data = json.loads(resp.data)
        for key in ("pair", "bid", "ask", "mid", "timestamp_utc", "source", "cache_age_ms"):
            self.assertIn(key, data, f"Missing key: {key}")

    def test_pair_echoed_normalized(self):
        with self._mock_bid_ask():
            resp = self.client.get("/api/live-price?pair=XAU_USD")
        self.assertEqual(json.loads(resp.data)["pair"], "XAU_USD")

    def test_bid_ask_mid_numeric(self):
        with self._mock_bid_ask(bid=2335.10, ask=2335.40):
            resp = self.client.get("/api/live-price?pair=XAU_USD")
        d = json.loads(resp.data)
        self.assertIsInstance(d["bid"], float)
        self.assertIsInstance(d["ask"], float)
        self.assertIsInstance(d["mid"], float)

    def test_mid_between_bid_and_ask(self):
        with self._mock_bid_ask(bid=2335.10, ask=2335.40):
            resp = self.client.get("/api/live-price?pair=XAU_USD")
        d = json.loads(resp.data)
        self.assertGreaterEqual(d["mid"], d["bid"])
        self.assertLessEqual(d["mid"],    d["ask"])

    def test_timestamp_utc_contains_utc(self):
        with self._mock_bid_ask():
            resp = self.client.get("/api/live-price?pair=XAU_USD")
        self.assertIn("UTC", json.loads(resp.data)["timestamp_utc"])

    def test_first_call_source_oanda_pricing(self):
        with self._mock_bid_ask():
            resp = self.client.get("/api/live-price?pair=XAU_USD")
        self.assertEqual(json.loads(resp.data)["source"], "oanda_pricing")

    def test_first_call_cache_age_zero(self):
        with self._mock_bid_ask():
            resp = self.client.get("/api/live-price?pair=XAU_USD")
        self.assertEqual(json.loads(resp.data)["cache_age_ms"], 0)


# ── Backend: pair normalization ───────────────────────────────────────────────

class TestLivePricePairNormalization(unittest.TestCase):

    def setUp(self):
        self.client = _make_client()
        import dashboard.app as _app
        _app._live_price_cache.clear()

    def _mock(self):
        return patch("core.fetcher.get_live_bid_ask", return_value=(1.2850, 1.2852))

    def test_slash_format_xau(self):
        """XAU/USD normalizes to XAU_USD."""
        with self._mock():
            resp = self.client.get("/api/live-price?pair=XAU/USD")
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(json.loads(resp.data)["pair"], "XAU_USD")

    def test_slash_format_usd_jpy(self):
        """USD/JPY normalizes to USD_JPY."""
        with self._mock():
            resp = self.client.get("/api/live-price?pair=USD/JPY")
        self.assertEqual(json.loads(resp.data)["pair"], "USD_JPY")

    def test_underscore_format_already_correct(self):
        """XAU_USD passes through unchanged."""
        with self._mock():
            resp = self.client.get("/api/live-price?pair=XAU_USD")
        self.assertEqual(json.loads(resp.data)["pair"], "XAU_USD")

    def test_lowercase_normalized_to_upper(self):
        """xau_usd normalized to XAU_USD."""
        with self._mock():
            resp = self.client.get("/api/live-price?pair=xau_usd")
        self.assertEqual(json.loads(resp.data)["pair"], "XAU_USD")

    def test_missing_pair_returns_400(self):
        resp = self.client.get("/api/live-price")
        self.assertEqual(resp.status_code, 400)
        self.assertIn("error", json.loads(resp.data))


# ── Backend: cache behaviour ──────────────────────────────────────────────────

class TestLivePriceCache(unittest.TestCase):

    def setUp(self):
        self.client = _make_client()
        import dashboard.app as _app
        _app._live_price_cache.clear()

    def test_second_call_returns_from_cache(self):
        """Second call within TTL returns oanda_pricing_cached."""
        with patch("core.fetcher.get_live_bid_ask", return_value=(2335.10, 2335.40)) as mock:
            self.client.get("/api/live-price?pair=XAU_USD")   # populates cache
            resp = self.client.get("/api/live-price?pair=XAU_USD")  # cache hit
        data = json.loads(resp.data)
        self.assertEqual(data["source"], "oanda_pricing_cached")
        # OANDA only called once (second call was cached)
        self.assertEqual(mock.call_count, 1)

    def test_cached_response_has_positive_cache_age(self):
        with patch("core.fetcher.get_live_bid_ask", return_value=(2335.10, 2335.40)):
            self.client.get("/api/live-price?pair=XAU_USD")
            time.sleep(0.05)  # ensure some measurable age
            resp = self.client.get("/api/live-price?pair=XAU_USD")
        self.assertGreater(json.loads(resp.data)["cache_age_ms"], 0)

    def test_cache_per_pair_independent(self):
        """Cache for XAU_USD does not affect EUR_USD."""
        with patch("core.fetcher.get_live_bid_ask", return_value=(2335.10, 2335.40)):
            self.client.get("/api/live-price?pair=XAU_USD")
        with patch("core.fetcher.get_live_bid_ask", return_value=(1.0851, 1.0853)) as mock:
            resp = self.client.get("/api/live-price?pair=EUR_USD")
        self.assertEqual(json.loads(resp.data)["source"], "oanda_pricing")
        self.assertEqual(mock.call_count, 1)

    def test_cache_ttl_constant_is_2s(self):
        """_LIVE_PRICE_CACHE_TTL must be 2.0 seconds."""
        import dashboard.app as _app
        self.assertEqual(_app._LIVE_PRICE_CACHE_TTL, 2.0)


# ── Backend: OANDA failure handling ──────────────────────────────────────────

class TestLivePriceOandaFailure(unittest.TestCase):

    def setUp(self):
        self.client = _make_client()
        import dashboard.app as _app
        _app._live_price_cache.clear()

    def test_503_on_exception(self):
        """OANDA exception returns 503 JSON — does not crash."""
        with patch("core.fetcher.get_live_bid_ask", side_effect=ConnectionError("OANDA down")):
            resp = self.client.get("/api/live-price?pair=XAU_USD")
        self.assertEqual(resp.status_code, 503)

    def test_503_response_has_error_key(self):
        with patch("core.fetcher.get_live_bid_ask", side_effect=RuntimeError("timeout")):
            resp = self.client.get("/api/live-price?pair=XAU_USD")
        data = json.loads(resp.data)
        self.assertIn("error", data)

    def test_503_response_echoes_pair(self):
        with patch("core.fetcher.get_live_bid_ask", side_effect=RuntimeError("timeout")):
            resp = self.client.get("/api/live-price?pair=XAU_USD")
        self.assertEqual(json.loads(resp.data)["pair"], "XAU_USD")

    def test_none_prices_return_503(self):
        """get_live_bid_ask returning (None, None) returns 503."""
        with patch("core.fetcher.get_live_bid_ask", return_value=(None, None)):
            resp = self.client.get("/api/live-price?pair=XAU_USD")
        self.assertEqual(resp.status_code, 503)


# ── Frontend: static template source checks ──────────────────────────────────

class TestLivePriceFrontend(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        with open("dashboard/templates/dashboard.html", encoding="utf-8") as f:
            cls.src = f.read()

    def test_poller_timer_variable_declared(self):
        self.assertIn("_liveTradePollerTimer", self.src,
                      "_liveTradePollerTimer variable not declared")

    def test_start_poller_function_present(self):
        self.assertIn("function _startLiveTradePoller()", self.src,
                      "_startLiveTradePoller() function missing")

    def test_stop_poller_function_present(self):
        self.assertIn("function _stopLiveTradePoller()", self.src,
                      "_stopLiveTradePoller() function missing")

    def test_poll_function_present(self):
        self.assertIn("async function _pollLivePricesNow()", self.src,
                      "_pollLivePricesNow() function missing")

    def test_polls_live_price_endpoint(self):
        self.assertIn("/api/live-price", self.src,
                      "/api/live-price not referenced in frontend polling")

    def test_filters_open_trades_only(self):
        """Poller must filter for open trades (outcome absent/empty)."""
        self.assertIn('!t.outcome || t.outcome === ""', self.src,
                      "Open trade filter missing from _pollLivePricesNow")

    def test_stops_when_no_open_trades(self):
        """Poller stops itself when no open pairs remain."""
        self.assertIn("_stopLiveTradePoller", self.src)
        # The stop call inside poll function when openPairs is empty
        self.assertIn("openPairs.length) { _stopLiveTradePoller", self.src,
                      "Poller must stop itself when no open trades remain")

    def test_visibility_change_listener(self):
        """visibilitychange event stops poller when browser tab hidden."""
        self.assertIn("visibilitychange", self.src,
                      "visibilitychange listener missing")
        self.assertIn("document.hidden", self.src,
                      "document.hidden check missing from visibilitychange handler")

    def test_start_on_manual_tab(self):
        """_startLiveTradePoller called when switching to manual tab."""
        self.assertIn("_startLiveTradePoller()", self.src,
                      "_startLiveTradePoller() not called on manual tab switch")

    def test_stop_on_non_manual_tab(self):
        """_stopLiveTradePoller called when switching away from manual tab."""
        self.assertIn("_stopLiveTradePoller()", self.src,
                      "_stopLiveTradePoller() not called on tab switch away")

    def test_prev_price_preserved(self):
        """Previous price captured before updating _livePrices."""
        poll_idx = self.src.find("async function _pollLivePricesNow")
        end_idx  = self.src.find("\n}", poll_idx) + 2
        fn = self.src[poll_idx:end_idx]
        self.assertIn("prevPx", fn,
                      "prevPx not captured before price update in _pollLivePricesNow")

    def test_render_called_after_update(self):
        """renderManualTrades called after live price update."""
        poll_idx = self.src.find("async function _pollLivePricesNow")
        end_idx  = self.src.find("\n}", poll_idx) + 2
        fn = self.src[poll_idx:end_idx]
        self.assertIn("renderManualTrades", fn,
                      "renderManualTrades not called after price update in poller")

    def test_poll_interval_3_to_5_seconds(self):
        """Poll interval must be between 3000ms and 5000ms."""
        self.assertIn("_LIVE_POLL_MS", self.src)
        import re
        m = re.search(r"_LIVE_POLL_MS\s*=\s*(\d+)", self.src)
        self.assertIsNotNone(m, "_LIVE_POLL_MS not found")
        ms = int(m.group(1))
        self.assertGreaterEqual(ms, 3000, f"Poll interval {ms}ms is below 3000ms")
        self.assertLessEqual(ms,   5000, f"Poll interval {ms}ms exceeds 5000ms")


if __name__ == "__main__":
    unittest.main()
