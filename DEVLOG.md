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
