# DEVLOG — Forex Agent Build Log

---

## Session: 2026-05-12 — Hardening + Mode Brain Swap

### Vision Checkpoint
This system is not a bot. It is your trading brain in code.
It reads structure, classifies context, decides when NOT to trade, and learns from your actual outcomes.
Current phase: **paper trading + strategy hardening + learning loop active**.

---

### What Was Built This Session

#### 1. News Sniper — Dual-TF Execution (strategies/news_sniper.py)
Full rewrite. Three-gate sequence, strictly ordered:

- **Gate 1 — M5 Liquidity Sweep:** Wick through swing high/low (last 20 bars), close back inside. Institutional stop hunt confirmed. M1 CHoCH only arms after this fires.
- **Gate 2 — H1 Marubozu Check:** If last completed H1 candle body ≥ 80% range AND opposes reversal direction → escalate to strict CHoCH (pre-sweep swing break required, not just micro bounce).
- **Gate 3 — M1 CHoCH Quality Gates:**
  - Wick rejection: trigger candle wick ≥ 70% of range → rejected (no body commitment)
  - Displacement: trigger candle body must be ≥ 1.2× avg body of prior 5 candles
  - Standard: M1 closes beyond post-spike mini swing
  - Strict: M1 closes beyond pre-sweep structural swing (harder bar)

Key fix: M5 `bars_ago` → M1 lookback conversion. `m1_lookback = max((bars_ago + 1) * 5, 5)`. Without this, `post_spike` slice was always < 3 rows → CHoCH never fired.

---

#### 2. Finnhub News Bug Fix (filters/news.py)
**Critical.** Finnhub returns `"country"` (ISO 2-letter code e.g. `"US"`) not `"currency"`. All 395 news events had blank currency → `is_news_safe()` always returned safe. Fixed with `_COUNTRY_TO_CURRENCY` mapping dict.

---

#### 3. Mode Toggle — Real Brain Swap (main.py + mode_manager.py)
Toggle was wired to DB flag but scan loop ignored it. Now real:

- **NORMAL mode:** scans all PAIRS. Routes to `gold_strategy.py` (ICT sniper sequence) + H1 hard block.
- **NEWS SNIPER mode:** scans **XAU_USD only**. Routes to `news_sniper.py` (M5 sweep + M1 CHoCH). All other pairs skipped.

`main.py` now reads `get_active_mode()` at the top of every scan cycle. Terminal prints: `🧠 NEWS_SNIPER | Pairs: 1`.

---

#### 4. H1 50-EMA (core/confluence.py)
Computed in `analyze_timeframe()` for H1 only:
```python
ema_50 = float(df["close"].ewm(span=50, adjust=False).mean().iloc[-1])
```
Exposed as:
- `confluence["h1"]["ema_50"]`
- `confluence["h1_ema_50"]`
- `confluence["price_below_h1_ema"]` (bool)

---

#### 5. H1 Hard Block — Upgraded (strategies/gold_strategy.py)
Normal mode only. News Sniper never calls `gold_strategy`.

**BULL signal killed if:**
- (A) Last completed H1 candle is RED (close < open), OR
- (B) Price is below H1 50-EMA

**BEAR signal killed if:**
- Last completed H1 candle is GREEN (close > open)

Both gates use `df_h1.iloc[-2]` (last completed candle, not current forming).

---

#### 6. signal_mode Tagging (alerts/logger.py + ml/manual_trade_logger.py)
Every signal written to DB now captures active mode:
- `signal_mode = "normal"` or `"news_sniper"`
- `alerts/logger.py`: `_get_signal_mode()` called at log time
- `manual_trade_logger.py`: mode captured from `mode_manager.get_active_mode()`
- Backfill: all 89 existing rows set to `'normal'` via idempotent `init_db()` UPDATE

---

#### 7. Dashboard — Yellow Pulse Banner (dashboard/templates/dashboard.html)
When News Sniper active:
- Top banner: dark amber background, `2px solid #f5c400` border
- `⚡ SNIPER ACTIVE` badge pulses with CSS `box-shadow` glow keyframe (`sniper-pulse`)
- Stats bar updates to `1 (XAU)` pair count
- Document title: `⚡ SNIPER — Forex Agent`
- Toggle button and source label all amber (`#f5c400`), no more red

Mode badges on every row (both tables):
- `⚡ SNIPER` (yellow) or `◈ NORMAL` (blue) injected into `.perf-log-pair` span next to pair name
- CSS: `.badge-sniper` `.badge-normal`

---

#### 8. Archive System (dashboard/app.py + db/database.py)
- `is_archived` column added to both `agent_signals` and `manual_trades`
- Archive button on manual trade rows (UI)
- `/api/archive_manual_trade` POST endpoint
- `/api/bulk_archive` POST endpoint — archives by `pair_like` + `outcome` filter
- **14 XAG_USD LOSS records** set `is_archived=1` (all silver losses hidden from dashboard)
- `is_archived=0` rows hidden by default; "Show Archived" toggle re-renders both tables

---

#### 9. Mock Simulation — PASSED
XAU/USD News Sniper full gate simulation:
```
📉 SELL | XAU/USD | 🔥 ENTER NOW  ⚡ SNIPER
Price: $4,728 | SL: $4,734 (600p) | TP1: $4,712 | RR: 1:2.7
M5 Sweep: wick to $4,733 above swing $4,730 → bearish reversal ✓
M1 CHoCH: 13p body | 40% wick | 1.86x displacement ✓
P(win): 99% | EV: +2.63
```

---

### Database State (2026-05-12)
```
agent_signals:  49 rows | 0 NULL signal_mode | 14 XAG LOSS archived
manual_trades:  40 rows | 0 NULL signal_mode |  0 XAG LOSS (none)
level_edits:    10 rows
journal_entries: 1 local / 0 Railway (not yet synced)
Railway URL: https://forex-agent.up.railway.app
```

---

### Key Files — What Does What

| File | Role |
|------|------|
| `main.py` | Scan loop + mode brain switch (pairs_to_scan by mode) |
| `filters/mode_manager.py` | Mode state: manual override > auto > normal. `get_active_mode()` is the single source of truth |
| `filters/news.py` | ForexFactory + Finnhub news. Fixed: `country` field not `currency` |
| `core/confluence.py` | Multi-TF analysis. Now computes H1 50-EMA |
| `strategies/gold_strategy.py` | Normal mode XAU execution: sweep → CHoCH → FVG/OB. H1 hard block (candle + EMA) |
| `strategies/news_sniper.py` | News mode XAU execution: M5 sweep → Marubozu check → M1 CHoCH with quality gates |
| `strategies/forex_strategy.py` | Normal mode non-gold pairs |
| `filters/decision_layer.py` | Routes normal mode: XAU/XAG → gold_strategy, rest → forex_strategy |
| `alerts/scorer.py` | Bayesian P(win) + EV. Two likelihood tables: STANDARD and NEWS |
| `alerts/logger.py` | Logs ENTER_NOW signals to CSV + SQLite. Cooldown 15min per pair |
| `ml/manual_trade_logger.py` | Manual trade logging with mode capture |
| `ml/outcome_labeler.py` | Auto-labels outcomes by checking if SL/TP hit on OANDA candles |
| `db/database.py` | SQLite layer. All migrations idempotent. Backfills on `init_db()` |
| `dashboard/app.py` | Flask. All API endpoints |
| `dashboard/templates/dashboard.html` | Full single-page dashboard |
| `sync.py` | Railway → local mirror (one-way, all 4 tables) |
| `core/fetcher.py` | OANDA candle fetch. XAU pip = $0.01 |

---

### Pip Sizes (critical)
```
XAU_USD: 0.01  ($0.01 per pip)
XAG_USD: 0.001
JPY pairs: 0.01
All others: 0.0001
```

---

### What's Next
1. **Live sniper validation** — first real news event in sniper mode, compare signal vs chart
2. **Journal panel sync** — 1 local journal entry not on Railway yet
3. **H1 Hard Block tuning** — monitor if EMA gate is too aggressive on valid pullbacks
4. **Outcome labeler XAG** — archived XAG signals still have pips=0. Labeler runs but 0-pip wins are noise — consider excluding XAG from stats
5. **Vision: chart image in debate** — Phase A (later)

---

## Session: 2026-05-13 — Manual Trade Monitor Bug Fixes + Data Cleanup

### What Was Broken

#### Bug 1 — Manual Trade Monitor: Historical Candles Triggering SL (FIXED)
**Root cause:** `_monitor_trade()` used `fetch_candles()` (returns last N candles going back hours) with `>=` timestamp filter. This included the candle open AT entry time, which had price data from before the trade was logged. A 12:00 UTC candle with high=4700.065 triggered SL=4700 for a trade logged at 13:45 UTC — price never actually touched SL after entry.

**Fix:** Changed `>=` to `>` in two places in `ml/manual_trade_logger.py`:
```python
# Catch-up check (line ~263)
df_hist = df_hist[df_hist.index > pd.Timestamp(log_time, tz="UTC")]
# Live poll loop (line ~298)
df = df[df.index > pd.Timestamp(log_time, tz="UTC")]
```
Commit: `580c3f6`

---

#### Bug 2 — Manual Trade Monitor: Wrong SL/TP Level Watched (FIXED)
**Root cause:** When a trade is logged, `log_manual_trade()` calls `_calculate_levels()` which computes a **default 20-pip SL** (20 × pip_size). This default gets passed to `_start_monitor()`. The monitor starts watching the 20-pip default level immediately — BEFORE the user has typed their real SL/TP. User saves real SL (e.g. 4713 for gold) to DB, but the monitor never reads the DB again. On gold, price moves 20 pips in seconds → LOSS fires instantly.

For forex pairs this was invisible because users happened to accept the 20-pip default. Only showed up on gold where users set custom wide SL.

**Fix — Part A:** Monitor now reads SL/TP from DB on every poll cycle via `_get_levels_from_db(signal_id)`. Added 90s startup delay so user has time to save levels before first check. (`ml/manual_trade_logger.py`)

**Fix — Part B:** Dashboard now sends `sl_price` and `tp1_price` in the log trade request. Backend `/api/log_manual_trade` accepts them. `log_manual_trade()` accepts `sl_price` and `tp1_price` params — uses them directly if valid, falls back to calculated defaults only if not provided.

**Fix — Part C:** Dashboard JS wired up properly:
- `onSourceChange()` — "scanner" mode pre-fills SL/TP from live signal. "analysis" mode clears for manual entry
- `recalcTP()` — auto-calculates TP at 1:2 RR from entry + SL in "analysis" mode
- `submitManualTrade()` — reads and sends sl/tp fields, blocks submit if SL/TP missing
- `prefillEntryPrice()` — now also calls `onSourceChange()` when pair changes

Commits: `27c29ba`, `cc127f6`

---

#### Bug 3 — XAG Outcome Labeler Spam (FIXED via data cleanup)
**Root cause:** `get_unlabeled_taken_signals()` query had no filter for `is_archived`. Two XAG_USD signals with empty outcome (`XAG_USD_20260422_080406`, `XAG_USD_20260512_115923`) were being picked up every 5 min. Labeler tried fetching M5 candles from months ago → OANDA rejected with "Maximum value for count exceeded" → error logged every cycle.

**Fix:** Manually set April 22 XAG signal to LOSS -580 pips (SL was hit, XAG at 88+ now). Then deleted it entirely per user preference. May 12 XAG signal was already WIN on Railway. Both cleared → labeler error stops.

Note: Long-term fix would be to add `AND COALESCE(is_archived,0) != 1` to `get_unlabeled_taken_signals()` query in `db/database.py`.

---

### Data Cleanup Done This Session

**Deleted from Railway (both were fake LOSSes from Bug 2):**
- `manual_XAU_USD_20260513_134503` — XAU bearish, LOSS -3358.5p (bug-triggered)
- `manual_XAU_USD_20260513_134656` — XAU bearish, LOSS -2558.5p (bug-triggered)
- `manual_XAU_USD_20260513_183624` — XAU bearish, LOSS -20.0p (bug-triggered)
- `manual_XAU_USD_20260513_061736` — XAU bullish, WIN 40p (user removed)
- `XAG_USD_20260422_080406` — agent signal, deleted (old XAG noise)

**Stats after cleanup (Railway):**
```
manual_trades:  42 active | 0 archived
manual win rate: 51.3% | avg pips: +147.3
agent_signals:  35 active | 14 archived (all XAG LOSS)
```

---

### Database State (2026-05-13)
```
LOCAL:
  agent_signals: 49 total (35 active, 14 archived XAG)
  manual_trades: 40 total (40 active, 0 archived)

RAILWAY:
  agent_signals: 48 total (35 active, 14 archived XAG)  ← 1 XAG deleted
  manual_trades: 42 total (42 active, 0 archived)       ← 4 bad trades deleted

4 manual trades on Railway not yet synced to local (logged after last sync).
```

---

### Key Commits This Session
| Commit | What |
|--------|------|
| `580c3f6` | Fix monitor — candles strictly after entry time (`>` not `>=`) |
| `81c536f` | Wire Slack alerts — sniper format + webhook |
| `27c29ba` | Fix monitor — read SL/TP from DB every cycle + 90s startup delay |
| `cc127f6` | Fix log trade modal — scanner pre-fills SL/TP, sends to backend, backend uses them |

---

### Current System State
- Manual trade monitor: **fully fixed** — reads real SL/TP from DB, 90s delay on start
- Log trade modal: **fully fixed** — scanner pre-fills or user sets own SL/TP before logging
- Slack: **live** — sniper alert format wired, webhook active on Railway
- XAG labeler error: **resolved** via data cleanup
- Scanner logic for gold: **correct** — sweep detection, ICT, H1 hard block all working
- Om scalping panel: **parked** — concept agreed (separate gold panel with tight TP), not built yet

---

### What's Next
1. **Sync local** — run `python sync.py` to pull 4 Railway-only manual trades to local
2. **Om scalping panel** — second gold row on dashboard with 20-25 pip TP targets (discuss SL sizing first)
3. **Journal panel sync** — 1 local journal entry not on Railway
4. **Outcome labeler XAG** — add `AND COALESCE(is_archived,0) != 1` to `get_unlabeled_taken_signals()` as permanent fix
5. **h1_trend_at_entry** — column exists, all NULL, not being populated at log time
