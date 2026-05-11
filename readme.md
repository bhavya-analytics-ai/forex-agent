# FOREX AGENT — ICT DECISION ENGINE
### Personal trading scanner built on ICT/Smart Money Concepts

**Status: Paper trading. Live on Railway. Do NOT trade scanner-only signals — always validate against your chart first.**

---

## WHAT IT IS

A personal trading decision engine that reads market data, applies ICT/Smart Money logic top-down, and tells you exactly whether to enter now, wait, or skip — with probability and expected value attached to every signal.

Not a bot. Not a black box. A scanner that thinks the way an ICT trader thinks.

Three jobs in one system:
1. **Multi-timeframe confluence engine** — H1 structure → M15 confirm → M5/M1 trigger, every scan
2. **Bayesian decision layer** — P(win) + EV math, two separate likelihood tables, auto-routes to correct strategy
3. **News sniper mode** — detects post-news spikes, M1 wick sweep + CHoCH sequence, separate silo that never bleeds into normal mode

---

## QUICK START (local)

```bash
# 1. Install
pip install -r requirements.txt

# 2. .env file
OANDA_API_KEY=your_key
OANDA_ACCOUNT_ID=your_account
OANDA_ENVIRONMENT=practice
FINNHUB_API_KEY=optional
NEWSDATA_API_KEY=optional
SLACK_WEBHOOK_URL=optional
NIM_API_KEY=your_nvidia_nim_key   # required for Signal Debate feature

# 3. Run
python main.py scan        # single scan
python main.py live        # live mode (scans every 5 min + dashboard at localhost:5000)
python main.py live 60     # live with custom interval (seconds)
python main.py stream      # real-time tick feed
python main.py stats       # performance stats
python main.py briefing london   # pre-session briefing
```

---

## RAILWAY DEPLOYMENT

**Live URL:** https://forex-agent.up.railway.app

**Project:** https://railway.com/project/1de9af86-ce4d-4a0d-ac42-1eb787dacf88

### Deploy from scratch
```bash
railway login
railway link   # select forex-agent project
railway up     # deploy

# Set env vars (one time)
railway variables set OANDA_API_KEY=... OANDA_ACCOUNT_ID=... OANDA_ENVIRONMENT=practice \
  FINNHUB_API_KEY=... NEWSDATA_API_KEY=...
```

### Critical: Volume for DB persistence
Railway containers are ephemeral — without a Volume, the DB is wiped on every redeploy.

**Must have:** Volume mounted at `/data` in Railway UI → service → Volumes tab.

DB path auto-detects:
- Railway: `/data/forex.db`
- Local: `logs/trades.db`

### Seed data on first deploy
```bash
python seed_railway.py --url https://forex-agent.up.railway.app
```
Reads local DB, POSTs to `/api/import`. Safe to run multiple times (INSERT OR IGNORE).

---

## DAILY BACKUP

```bash
# Manual
python backup.py --url https://forex-agent.up.railway.app

# With SQLite snapshot too
python backup.py --url https://forex-agent.up.railway.app --sqlite
```

Saves to `backups/forex_backup_YYYYMMDD.json`. Keeps last 30 days. Overwrites same-day runs (no duplicates).

**Auto backup:** launchd agent runs daily + on every Mac login (catches missed runs):
```
~/Library/LaunchAgents/com.forexagent.backup.plist
```
Logs to `logs/backup.log`.

---

## HOW THE SYSTEM WORKS

Each scan cycle, in order:

**Step 1 — Fetch candles (OANDA API)**
H1 (400), M15 (100), M5 (60), M1 (60) per pair. Metals get more history.

**Step 2 — Multi-TF confluence**
- H1: market structure, swing highs/lows, bias direction
- M15: confirms or denies H1 bias
- M5/M1: entry timing
- Detects 3 setup types: pullback, breakout, reversal

**Step 3 — ICT concept detection**
OB, FVG, liquidity sweeps, MSS, CHoCH, premium/discount zones

**Step 4 — Mode detection**
HIGH impact news within 15 min → news sniper mode auto-activates. Dashboard toggle for manual override.

**Step 5 — Strategy router**
- Gold (XAU/XAG) → `gold_strategy.py` — ICT sniper: sweep → CHoCH → OB tap
- Forex → `forex_strategy.py` — hard filters (mid-range, HTF zone, TF conflict, choppy, RR)
- News → `news_sniper.py` — M1 spike + wick sweep + M1 CHoCH

**Step 6 — Bayesian scorer**
P(win) + EV per signal. STANDARD_LIKELIHOODS vs NEWS_LIKELIHOODS — strict silo, never mix.

**Step 7 — Output**
`ENTER_NOW` / `WAIT_RETEST` / `SKIP` + entry/SL/TP levels + grade (A+/A/B/C) + flags.

---

## THE TWO MODES

### NORMAL MODE

**Gold (XAU_USD, XAG_USD)** — ICT sniper sequence:
1. Liquidity sweep (wick beyond swing, closes back inside)
2. CHoCH fires in opposite direction
3. Price pulls back into OB or FVG
4. All 3 → ENTER_NOW. Sweep + CHoCH but no zone → WAIT_RETEST. No sweep → SKIP.

SL: M5 swing extreme → M15 swing → OB edge → ATR×1.5 fallback. Capped at ATR×2. XAU floor: $15.
TP: nearest opposing liquidity with RR ≥ 1.2.

**Forex (all other pairs)** — hard filters in order:
| Filter | Condition | Result |
|--------|-----------|--------|
| Mid-range | Price 40–60% of HTF range, weak structure | SKIP |
| HTF zone | Strong opposing zone within ATR×0.5 | SKIP |
| TF conflict | H1/M15/M5 biases don't align | SKIP |
| Choppy | Ranging + structure strength = 1 | SKIP |
| RR < 1.2 | TP doesn't justify SL | SKIP |

Momentum override: breakout ATR ratio ≥ 1.3 → mid-range + HTF zone filters skipped.

### NEWS SNIPER MODE

Auto-activates 15 min before HIGH impact ForexFactory events (stays active 5 min post-event).

Sequence — all 3 required, in order:
```
HIGH IMPACT NEWS FIRES → M1 SPIKE (≥1.5x ATR) → WICK SWEEPS SWING → M1 CHoCH → ENTER NOW
```
SL: spike extreme + buffer. TP: nearest opposing swing, RR ≥ 1.5.
NEWS_LIKELIHOODS only. Zero bleed with normal mode.

---

## BAYESIAN SCORING

```
Base rate P(W) = 0.45 (conservative until N=50 labeled outcomes)

For each condition (sweep, CHoCH, FVG, zone, trend, news safe...):
  true  → P(W) × sensitivity
  false → P(W) × (1 - sensitivity)

EV = P(win) × RR − P(loss)
```

At N≥50 labeled outcomes → base rates auto-update from real results. Bayesian status: EST → LIVE.
Current: 27 labeled outcomes. Need 23 more.

---

## ICT CONCEPTS

| Concept | What it is |
|---------|-----------|
| OB | Last bearish candle before bullish impulse (or vice versa). Institutional entry zone. |
| FVG | Gap between candle 1 and candle 3 of a 3-candle impulse. Price returns to fill it. |
| Liquidity Sweep | Wick pierces swing high/low, closes back inside. Stops taken, reversal likely. |
| MSS | H1 breaks a key swing in opposite direction. Trend officially changing. |
| CHoCH | First short-term structure break against trend. Early reversal warning. |
| Premium zone | Price above 60–70% of H1 range. Sell bias. |
| Discount zone | Price below 30–40% of H1 range. Buy bias. |

---

## PAIRS & SESSIONS

```
XAU_USD  XAG_USD
GBP_USD  EUR_USD  EUR_GBP
USD_JPY  GBP_JPY  EUR_JPY  CHF_JPY  CAD_JPY  NZD_JPY
```

| Session | UTC | Notes |
|---------|-----|-------|
| Tokyo KZ | 00:00–06:00 | JPY pairs |
| London Open KZ | 07:00–10:00 | GBP, EUR |
| NY Open KZ | 13:00–16:00 | Gold, USD |

Outside killzones: score dampened, A+ capped to A.

---

## DATA LAYER

**SQLite DB** (`logs/trades.db` local, `/data/forex.db` on Railway)

Three tables:
- `manual_trades` — your manually logged trades
- `agent_signals` — scanner ENTER_NOW signals. Key columns: `scanner_sl/tp` (never touched), `user_sl/tp` (what you set), `actual_sl/tp` (what model trains on)
- `level_edits` — every SL/TP change: old/new levels + reason + timestamp

**Dual-write:** SQLite primary + CSV backup. Reads: SQLite first, CSV fallback. Old data never lost.

**Current data:** 39 agent signals, 34 manual trades, 53 labeled outcomes (25 agent + 28 manual).

**Nightly sync:** `sync.py` runs at 2am via launchd — full mirror Railway → local including deletions. Manual: `python sync.py`.

---

## DASHBOARD

**Railway:** https://forex-agent.up.railway.app
**Local:** http://localhost:5000

- Signals sorted A+ first, then by score
- Live news ticker with countdown to next HIGH event
- Mode toggle (Normal ↔ News Sniper)
- Timestamps in NY time AM/PM (stored UTC, converted in JS)
- Refreshes every 30 seconds

**Performance panel:**
- AGENT SIGNALS tab — all ENTER_NOW signals, WIN/LOSS/TOOK IT buttons
- MY MANUAL TRADES tab — your manually logged trades, live current price, monitoring status
- Stats: Signals Today / Total Labeled / Win Rate / Avg Pips / Unicorn Win Rate / Bayesian Status

**Actions per row:**
- `TOOK IT` — mark signal taken, save your custom SL/TP (scanner levels preserved separately)
- `W / L` — mark outcome on any signal (re-markable at any time, updates instantly)
- `✕ / DEL` — delete any signal or manual trade permanently
- `⚡ Debate` — AI bull/bear debate on A/A+ signals (see Signal Debate below)
- `Edit SL/TP` — update levels mid-trade, select reason, logs to level_edits
- `+ Note` — append timestamped note to any trade (open or closed)
- `Close ✕` — close manual trade, auto-calculates pips from live OANDA price

**Refresh:**
- Full dashboard: every 30s
- Performance stats: every 10s (independent of full refresh)
- W/L saves: instant with green/red toast feedback

---

## API ENDPOINTS

| Method | Endpoint | What |
|--------|----------|------|
| GET | `/api/signals` | Live scanner signals (all pairs) |
| GET | `/api/recent_signals` | Last 500 agent ENTER_NOW signals |
| GET | `/api/recent_manual_trades` | Last 100 manual trades |
| GET | `/api/performance` | Stats summary (win rate, avg pips, by grade) |
| GET | `/api/export` | Full DB dump as JSON (all trades + signals) |
| GET | `/api/news` | Upcoming news events |
| GET | `/api/mode` | Current strategy mode |
| POST | `/api/import` | Bulk insert trades from JSON (used by seed_railway.py) |
| POST | `/api/mode/toggle` | Switch Normal ↔ News Sniper |
| POST | `/api/mark_taken` | Mark signal taken + save user SL/TP + notes |
| POST | `/api/mark_outcome` | WIN/LOSS/NEUTRAL on agent signal (SQLite-first, re-markable) |
| POST | `/api/delete_signal` | Delete an agent signal permanently |
| POST | `/api/delete_manual` | Delete a manual trade permanently |
| POST | `/api/debate_signal` | Run 3-call ICT bull/bear debate on a signal |
| POST | `/api/update_trade_levels` | Update SL/TP on manual trade + log to level_edits |
| POST | `/api/update_agent_levels` | Update user SL/TP on agent signal |
| POST | `/api/save_note` | Append note to any trade (agent or manual) |
| POST | `/api/log_manual_trade` | Log a manual trade, start monitor |
| POST | `/api/close_manual_trade` | Close open trade, calc pips from live price |

---

## FILE STRUCTURE

```
forex-agent/
├── main.py                     # Entry point — all run modes
├── config.py                   # Pairs, sessions, scoring weights
├── scheduler.py                # Auto-briefing scheduler
├── backup.py                   # Daily backup script (hits /api/export)
├── seed_railway.py             # One-time Railway DB seeder
├── Procfile                    # Railway: web: python main.py live
│
├── core/
│   ├── fetcher.py              # OANDA candle fetching
│   ├── confluence.py           # Multi-TF engine
│   ├── structure.py            # Swing highs/lows, trend
│   ├── ict.py                  # OB, MSS, CHoCH, FVG, premium/discount
│   ├── zones.py                # S/R zones
│   ├── candles.py              # Candlestick patterns
│   ├── fvg.py                  # Fair Value Gap detection
│   ├── liquidity.py            # SL/TP anchor points
│   ├── streamer.py             # Live tick streaming
│   └── debate.py               # 3-call ICT bull/bear debate via NVIDIA NIM
│
├── filters/
│   ├── decision_layer.py       # Thin orchestrator → routes to strategy
│   ├── mode_manager.py         # Auto/manual mode detection
│   ├── killzones.py            # ICT killzone filter
│   ├── news.py                 # ForexFactory news filter
│   ├── news_vibe.py            # NewsData.io headlines
│   └── session.py              # Session detection
│
├── strategies/
│   ├── gold_strategy.py        # XAU/XAG — sweep→CHoCH→OB
│   ├── forex_strategy.py       # All other pairs — hard filters
│   └── news_sniper.py          # M1 spike + CHoCH sequence
│
├── alerts/
│   ├── scorer.py               # Bayesian scorer — P(win), EV, grade
│   ├── logger.py               # CSV + SQLite signal logger
│   └── slack.py                # Slack alerts
│
├── dashboard/
│   ├── app.py                  # Flask + all API routes
│   └── templates/
│       └── dashboard.html      # Navy/blue UI
│
├── db/
│   └── database.py             # SQLite core — all read/write helpers
│
├── ml/
│   ├── outcome_labeler.py      # Auto WIN/LOSS labeler (background thread, every 5 min)
│   ├── manual_trade_logger.py  # Manual trade logger + TP/SL monitor
│   └── trainer.py              # Base rate updater (needs 50+ signals)
│
├── reports/
│   └── briefing.py             # Pre-session briefings
│
├── backups/                    # Daily JSON backups (auto-created)
│
└── logs/
    ├── trades.db               # SQLite DB (primary store)
    ├── agent_signals.csv       # CSV backup — agent signals
    ├── manual_trades.csv       # CSV backup — manual trades
    └── app.log
```

---

## SIGNAL DEBATE (A/A+ only)

On any A or A+ signal, hit **⚡ Debate** before deciding to take the trade.

Three separate NIM calls run in sequence:

1. **Bull** — makes the strongest case FOR the trade using ICT logic (structure, zone freshness, session, killzone, entry pattern, RR)
2. **Bear** — reads bull's argument and attacks it specifically (mitigated zones, wrong session, liquidity sweeps, weak score breakdown, news risk)
3. **Judge** — applies 7 hard ICT rules then weighs the debate. Verdict: `TAKE` / `PASS` / `WAIT`

**Hard rules the judge enforces:**
- HTF trend against direction → PASS
- Outside killzone → WAIT
- Zone strength < 40 → PASS (zone mitigated)
- RR < 1.5 → PASS
- News unsafe → WAIT
- M15 + M5 both oppose → PASS
- Bear made a point bull didn't address → weighted heavily

**Output on the card:**
- Verdict + one-line reason
- Bull score vs Bear score (e.g. Bull 7/10 · Bear 9/10)
- Full bull argument
- Full bear rebuttal
- Key risk warning (even on TAKE verdicts)

**Not a trading system.** Read-only second opinion. You decide.

**Requires:** `NIM_API_KEY` env var (NVIDIA NIM). Model: `moonshotai/kimi-k2-instruct`.

---

## WHAT'S DONE

### Phase 1–3 — Core engine
- Multi-TF confluence, ICT concepts (OB/FVG/MSS/CHoCH/sweep)
- Bayesian scorer (P(win) + EV, two likelihood tables)
- News sniper mode (M1 spike → sweep → CHoCH)
- Mode manager (auto-detect + manual override)

### Phase 4 — Learning engine
- Unicorn model (FVG + Breaker Block, killzone-gated)
- Outcome labeler thread (auto WIN/LOSS every 5 min)
- Manual trade logger (monitors TP/SL indefinitely, resumes on restart)
- Dashboard: performance panel, LOG TRADE, WIN/LOSS/TOOK IT, Close ✕

### Phase 5 — SQLite + SL/TP tracking
- `db/database.py` — WAL mode, write lock, per-thread connections
- `level_edits` table — every SL/TP change logged (old/new/reason/timestamp)
- Inline SL/TP edit on open trades, reset to auto button
- Dual-write pattern (SQLite + CSV), reads SQLite first with CSV fallback

### Phase 6 — TOOK IT flow + notes + agent levels
- TOOK IT modal — scanner levels as reference, save your own SL/TP separately
- `user_sl/tp`, `actual_sl/tp` columns — scanner levels never overwritten, model trains on actual
- `+ note` on every row (open or closed), appends with NY timestamp
- Notes field in TOOK IT + Edit SL/TP modals
- NY time display throughout (stored UTC, JS conversion)
- Entry price column on agent signals, live price on manual trades

### Phase 7 — Railway deployment + backup
- Railway deployment (Hobby plan, 1 service)
- SQLite Volume at `/data` for persistence across deploys
- DB path auto-detection (`/data` on Railway, `logs/trades.db` local)
- `busy_timeout = 5000ms` pragma (no crashes under concurrent writes)
- `/api/export` — full JSON dump of all data
- `/api/import` — bulk insert for seeding
- `backup.py` — daily local backup, date-only filename (no duplicates)
- `seed_railway.py` — one-time seeder for Railway
- launchd agent — auto backup on Mac login + every 24h

### Phase 8 — Dashboard fixes + Signal Debate
- **Bug fix:** `mark_outcome` and `close_trade_manually` now write SQLite first (CSV was checked first on Railway — CSV doesn't exist there, so outcomes never saved)
- **Re-mark:** W/L buttons always visible on signal rows — change any outcome at any time
- **Delete:** ✕/DEL button on every agent signal and manual trade row
- **Error feedback:** green/red toast on W/L save success/failure, buttons dim while saving
- **Performance refresh:** stats panel polls every 10s independent of 30s full refresh
- **Signal Debate:** 3-call ICT bull/bear debate via NVIDIA NIM on A/A+ signals (see above)
- **TradingView chart panel:** click any manual trade row → live chart opens below with H1/M15/M5/M1 tabs
- **NZD/JPY added** to log trade pair dropdown
- **Model training fields** captured at entry: session, killzone, h1_trend, m15_trend, m5_trend, news_safe

### Phase 9 — Data integrity + sync
- **Labeled count fix:** dashboard now combines agent + manual (was agent-only, showed 32, now correct 53)
- **CSV crash fix:** CSV write always best-effort wrapped in try/except — SQLite saves first, CSV never blocks
- **Monitor resume fix:** reads open trades from SQLite on restart (was reading CSV which doesn't exist on Railway)
- **SL/TP update fix:** `update_trade_levels` now SQLite-first (was CSV-first, returned 400 on Railway)
- **Scanner SL/TP visible:** shown on every agent signal row (was only shown after TOOK IT)
- **Auto-labeler audit:** 9 auto-labeled signals checked against real candles — 4 were wrong (marked LOSS, actually WIN), all 7 non-taken signals deleted except 2 correct WINs
- **Nightly sync:** `sync.py` + launchd — full Railway→local mirror every 2am including deletions

---

## WHAT'S NEXT

1. **50 labeled outcomes** — Bayesian flips EST → LIVE (need ~0 more — already at 53, flip pending)
2. **Auto-labeler fix** — currently uses 15min window + reads CSV; needs SQLite + full trade window
3. **OANDA paper trading** — "Take Trade" button sends order to OANDA demo account directly from dashboard
4. **Journal panel** — session-level notes tagged (pattern/mistake/observation/rule)
5. **Vision chart spec** — `docs/vision_chart_spec.md` — Phase A: chart images in debate; Phase B: training at 200+ outcomes

---

## RULES

**Only trade when the scanner agrees with YOUR chart read.**

Scanner gives you: probability, RR, entry state.
Your chart gives you: does this actually look right?

Both have to agree. Scanner-only = no trade.
