# FOREX AGENT — ICT DECISION ENGINE
### Personal trading scanner built on ICT/Smart Money Concepts

**Status: Paper trading. Live on Railway. Do NOT trade scanner-only signals — always validate against your chart first.**

---

## WHAT IT IS

A personal trading decision engine that reads market data, applies ICT/Smart Money logic top-down, and tells you exactly whether to enter now, wait, or skip — with probability and expected value attached to every signal.

Not a bot. Not a black box. A scanner that thinks the way an ICT trader thinks.

---

## LIVE DEPLOYMENT

- **Railway URL:** https://forex-agent.up.railway.app
- **Railway Project:** https://railway.com/project/1de9af86-ce4d-4a0d-ac42-1eb787dacf88
- Railway Volume mounted at `/data` — SQLite persists across deploys
- DB: `/data/forex.db` (Railway) or `logs/trades.db` (local)
- Deploy: `railway up --detach`

---

## QUICK START (local)

```bash
pip install -r requirements.txt

# .env
OANDA_API_KEY=your_key
OANDA_ACCOUNT_ID=your_account
OANDA_ENVIRONMENT=practice
NIM_API_KEY=your_nvidia_nim_key   # required for Signal Debate
FINNHUB_API_KEY=optional
NEWSDATA_API_KEY=optional
SLACK_WEBHOOK_URL=optional

python main.py live   # scans every 5min + dashboard at localhost:5000
```

---

## DATA LAYER — 4 TABLES

SQLite is source of truth. CSV is best-effort backup only. On Railway, no CSV exists — all code paths use SQLite.

| Table | PK | Key columns |
|---|---|---|
| `agent_signals` | signal_id | sl_price, tp1_price, user_sl, user_tp1, actual_sl, actual_tp1, exit_price, taken, outcome, outcome_pips, oanda_trade_id |
| `manual_trades` | signal_id | entry_price, sl_price, tp1_price, outcome, outcome_pips |
| `level_edits` | id | signal_id, old_sl, new_sl, old_tp1, new_tp1, reason, source (manual/agent), oanda_synced, timestamp |
| `journal_entries` | id | entry_date, session, tags, content, created_at |

Write safety: WAL mode + write lock + busy_timeout=5000ms + per-thread connections.

---

## BACKUP & SYNC

```bash
# Backup Railway → local JSON
python backup.py --url https://forex-agent.up.railway.app

# Full sync Railway → local SQLite (all 4 tables, Railway is master)
python sync.py --url https://forex-agent.up.railway.app

# Seed Railway DB from local (first deploy only)
python seed_railway.py --url https://forex-agent.up.railway.app
```

**Auto sync (launchd):**
- `com.forexagent.sync.plist` — runs every 2 hours + on Mac login → pulls all Railway changes to local
- `com.forexagent.backup.plist` — runs daily 2am + on Mac login → JSON backup to `backups/`
- If Mac was off/asleep, both run immediately on next login — nothing is missed
- Sync log: `logs/sync.log` | Backup log: `logs/backup.log`

**What syncs:** every column, every table. Outcomes, SL/TP edits, early closes, journal entries, deletions — all of it. Local is always an exact copy of Railway after sync runs.

---

## DASHBOARD

**https://forex-agent.up.railway.app**

### Signal Summary Bar (top)
Always-visible bar showing:
- **Agent Signals:** Total | Took It | W / L | Win %
- **Manual Trades:** Total | W / L | Win %

### Main Scanner Table
- All pairs sorted A+ first. Click row to expand.
- A/A+ signals with signal_id show: **🚀 TAKE TRADE** + **⚡ AI Debate** in expanded detail

### Performance Panel (bottom, 3 tabs)
1. **AGENT SIGNALS** — TOOK IT / 🚀 Take / 📊 Chart (open positions) / live position tracker / inline SL/TP edit / ⚡ Debate / Close ✕ / W·L·DEL
2. **MY MANUAL TRADES** — live position tracker / SL·TP edit / +note / Close ✕ / W·L·DEL
3. **JOURNAL** — session diary, tags: pattern/mistake/observation/rule

### Live Position Tracker
Progress bar between SL and TP with live price. Updates every 30s from OANDA current price.

---

## TAKE TRADE FLOW (OANDA)

1. Hit 🚀 TAKE TRADE on any A/A+ signal
2. Modal opens: TradingView chart + SL/TP inputs + unit size
3. SEND TO OANDA → MarketOrder on practice account → GTC SL/TP set via TradeCRCDO
4. `oanda_trade_id` saved to agent_signals
5. Edit SL/TP later → updates OANDA live GTC order + logs to level_edits (oanda_synced=1)

---

## EARLY CLOSE FLOW

1. Hit **Close ✕** on any taken + open agent signal in the performance panel
2. Enter your actual exit price
3. WIN/LOSS + pips calculated direction-aware (BULL: exit−entry, BEAR: entry−exit)
4. `exit_price`, `outcome`, `outcome_pips` written to DB immediately
5. Auto-labeler skips this signal — early close takes priority

---

## AUTO-LABELER

Runs every 5 minutes in background on Railway.

- Finds all signals with SL/TP set and no outcome yet (taken or not — market always hits one)
- Fetches full M5 candle history from entry time → now via OANDA (no time cap)
- Walks candles in order — first level touched = outcome
- Level priority: `user_sl/tp1` → `actual_sl/tp1` → `sl_price/tp1_price`
- WIN: TP hit first | LOSS: SL hit first
- Both hit same candle: uses open price to determine which side was hit first
- Skips signals where `exit_price` is already set (early close takes priority)
- Results written to Railway SQLite → pulled to local on next sync

---

## SIGNAL DEBATE (A/A+ only)

3-call NVIDIA NIM sequence:
1. **Bull** — strongest ICT case FOR the trade
2. **Bear** — reads bull, attacks specifically
3. **Judge** — 7 hard ICT rules → verdict: `TAKE` / `PASS` / `WAIT`

Model: `meta/llama-3.3-70b-instruct` (NIM). 90s timeout. Read-only — you always decide.

Hard rules: HTF trend against → PASS | outside killzone → WAIT | zone strength <40 → PASS | RR<1.5 → PASS | news unsafe → WAIT | M15+M5 both oppose → PASS

---

## API ENDPOINTS

| Method | Endpoint | What |
|---|---|---|
| GET | `/api/signals` | Live scanner (all pairs) |
| GET | `/api/recent_signals` | Last 500 agent signals |
| GET | `/api/recent_manual_trades` | Last 100 manual trades |
| GET | `/api/performance` | Stats summary (includes total_signals, total_manual, taken_count) |
| GET | `/api/export` | Full DB dump — all 4 tables |
| POST | `/api/import` | Bulk insert — all 4 tables |
| POST | `/api/take_trade` | Place MarketOrder on OANDA |
| POST | `/api/mark_taken` | Mark taken + save user SL/TP |
| POST | `/api/mark_outcome` | WIN/LOSS on agent signal |
| POST | `/api/close_agent_trade` | Close agent signal early at exit_price — calculates WIN/LOSS + pips |
| POST | `/api/update_trade_levels` | SL/TP edit on manual trade |
| POST | `/api/update_agent_levels` | SL/TP edit on agent signal + OANDA GTC update |
| POST | `/api/debate_signal` | Run 3-call bull/bear debate |
| POST | `/api/log_manual_trade` | Log manual trade |
| POST | `/api/close_manual_trade` | Close manual trade, calc pips |
| POST | `/api/save_note` | Append note (agent or manual) |
| POST | `/api/delete_signal` | Delete agent signal |
| POST | `/api/delete_manual` | Delete manual trade |
| GET/POST/DELETE | `/api/journal` | Journal entries CRUD |
| POST | `/api/mode/toggle` | Normal ↔ News Sniper |

---

## FILE STRUCTURE

```
forex-agent/
├── main.py                     # Entry point
├── config.py                   # Pairs, sessions, scoring weights
├── backup.py                   # Daily backup (hits /api/export)
├── sync.py                     # Railway→local sync, all 4 tables
├── seed_railway.py             # One-time Railway DB seeder
├── Procfile                    # web: python main.py live
│
├── core/
│   ├── fetcher.py              # OANDA candle fetching + fetch_candles_from (historical)
│   ├── confluence.py           # Multi-TF engine
│   ├── structure.py            # Swing highs/lows, trend
│   ├── ict.py                  # OB, MSS, CHoCH, FVG
│   ├── zones.py                # S/R zones
│   ├── debate.py               # 3-call ICT bull/bear debate (NIM)
│   └── ...
│
├── filters/
│   ├── decision_layer.py       # Routes to strategy
│   ├── mode_manager.py         # Auto/manual mode detection
│   ├── news.py                 # ForexFactory news filter
│   └── ...
│
├── strategies/
│   ├── gold_strategy.py        # XAU/XAG — sweep→CHoCH→OB
│   ├── forex_strategy.py       # Hard filters
│   └── news_sniper.py          # M1 spike + CHoCH
│
├── alerts/
│   ├── scorer.py               # Bayesian P(win) + EV + grade
│   └── logger.py               # Signal logger
│
├── dashboard/
│   ├── app.py                  # Flask + all API routes
│   └── templates/dashboard.html
│
├── db/
│   └── database.py             # SQLite — all read/write helpers, 4 tables
│
├── ml/
│   ├── outcome_labeler.py      # Auto WIN/LOSS — full OANDA history, no time cap
│   ├── manual_trade_logger.py  # Monitor TP/SL, SQLite-first
│   └── trainer.py              # Base rate updater (needs 50+ signals)
│
└── logs/
    ├── trades.db               # SQLite (primary)
    ├── sync.log                # Auto sync log
    ├── backup.log              # Auto backup log
    ├── agent_signals.csv       # CSV backup
    └── manual_trades.csv       # CSV backup
```

---

## OPEN ITEMS

1. **Take button in scanner** — window._scannerSigs fix deployed. Verify works end-to-end.
2. **Vision chart spec** — chart images in debate (Phase A), training at 200+ outcomes (Phase B).

---

## RULES

**Only trade when scanner agrees with YOUR chart read. Both have to agree. Scanner-only = no trade.**
