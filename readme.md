# FOREX AGENT — ICT DECISION ENGINE
### Personal trading scanner built on ICT/Smart Money Concepts

---

## GIT LOG

```
901fbb2 merge: v6 worktree — Bayesian scorer, news sniper, strategy silos
283f711 feat: v6 — Bayesian scorer, news sniper mode, strategy silos
fafd657 feat: v5 execution layer — decision layer, gold mode, early entry
c4b30d3 yeah
be047a1 remove .DS_Store
431b8ae Inside local
20f7196 24 Mar 12.26pm push
244b7e0 Latest update mar 23 8.48
26e4146 updated run.md
13d6262 Gold nd jpy breakout not good
```

**Status: Paper trading. Core logic validated. Do NOT trade scanner-only signals — always validate against your chart first.**

---

## WHAT WE ARE BUILDING

A personal trading decision engine that reads market data, applies ICT/Smart Money logic top-down, and tells you exactly whether to enter now, wait, or skip — with probability and expected value attached to every signal.

Not a bot. Not a black box. A scanner that thinks the way an ICT trader thinks.

Three jobs in one system:
1. **Multi-timeframe confluence engine** — H1 structure → M15 confirm → M5/M1 trigger, every scan
2. **Bayesian decision layer** — P(win) + EV math, two separate likelihood tables, auto-routes to correct strategy
3. **News sniper mode** — detects post-news spikes, M1 wick sweep + CHoCH sequence, separate silo that never bleeds into normal mode

---

## HOW THE SYSTEM WORKS

Each scan cycle does this, in order:

**Step 1 — Fetch candles (OANDA API)**
- Pulls H1, M15, M5, M1 for every pair
- 100–200 candles per timeframe depending on lookback needs

**Step 2 — Multi-TF confluence engine**
- H1: market structure, swing highs/lows, bias direction
- M15: confirms or denies H1 bias
- M5/M1: entry timing
- Detects 3 setup types: pullback, breakout, reversal

**Step 3 — ICT concept detection**
- Order Blocks (OB) — last bearish candle before bullish impulse, vice versa
- Fair Value Gaps (FVG) — imbalance left by impulse move
- Liquidity sweeps — wick above swing high that closes back below (stops taken)
- Market Structure Shift (MSS) — H1 officially changes trend
- Change of Character (CHoCH) — first break of short-term structure
- Premium/Discount zones — where price sits in the larger range

**Step 4 — Mode detection (auto or manual)**
- Checks ForexFactory: HIGH impact news within 15 minutes?
- YES → news sniper mode activates automatically
- NO → normal mode (gold strategy or forex strategy)
- Dashboard toggle lets you override manually anytime

**Step 5 — Bayesian scorer**
- Takes all confluence signals as conditions
- Computes P(win) using Bayesian posterior: `P(W|conditions) = P(conditions|W) × P(W) / P(conditions)`
- Computes Expected Value: `EV = P(win) × RR − P(loss)`
- Uses STANDARD_LIKELIHOODS in normal mode, NEWS_LIKELIHOODS in news sniper
- The two tables never mix — mode_manager controls which one gets passed to the scorer

**Step 6 — Strategy router**

*Normal mode:*
- Gold pairs (XAU, XAG) → gold_strategy (ICT sniper sequence: sweep → CHoCH → OB entry)
- All other pairs → forex_strategy (hard filters: mid-range, HTF zone, TF conflict, choppy, RR)

*News sniper mode:*
- All pairs → news_sniper (M1 spike → wick sweep → M1 CHoCH → spike extreme SL → opposing liquidity TP)

**Step 7 — Output**
- One of 3 entry states: `ENTER_NOW`, `WAIT_RETEST`, `SKIP`
- Trade levels: entry, SL, TP1, TP2
- P(win) %, EV, Grade (A+/A/B/C — human-readable fallback)
- Flags explaining exactly why the decision was made
- Dashboard updated, Slack alert fired (if ENTER_NOW + grade A or better)

---

## THE TWO MODES

### NORMAL MODE

Runs when no HIGH impact news is nearby. Two strategy paths:

**Gold strategy (XAU_USD, XAG_USD)**

ICT sniper sequence, in order:
1. Liquidity sweep detected (wick beyond swing high/low, closes back inside)
2. CHoCH fires in opposite direction after the sweep
3. Price pulls back into OB or FVG zone
4. If all 3 confirmed → ENTER_NOW
5. If sweep + CHoCH confirmed but no zone yet → WAIT_RETEST
6. Missing sweep → SKIP

SL logic:
- M5 swing extreme → M15 swing → OB edge → ATR×1.5 fallback
- Capped at ATR×2 always
- XAU floor: $15. XAG floor: $0.80

TP logic:
- Nearest opposing liquidity with RR ≥ 1.2
- Deduped within ATR×0.3 (not 3 levels that are basically the same price)
- TP2: next real level after TP1 — not a fixed multiplier

**Forex strategy (all other pairs)**

Hard filters, checked in order:
| Filter | Condition | Result |
|--------|-----------|--------|
| Mid-range | Price 40–60% of HTF range, weak structure | SKIP |
| HTF zone | Strong opposing zone within ATR×0.5 | SKIP |
| TF conflict | H1/M15/M5 biases don't align | SKIP |
| Choppy | Ranging + structure strength = 1 | SKIP |
| Multi-conflict | 2+ mismatches (trend + zone + sweep) | SKIP |
| RR < 1.2 | TP doesn't justify the SL | SKIP |

Momentum override: if breakout ATR ratio ≥ 1.3, mid-range and HTF zone filters are skipped.

---

### NEWS SNIPER MODE

Auto-activates 15 minutes before HIGH impact ForexFactory events (and stays active 5 minutes post-event).
Manual toggle available on dashboard.

ICT news sequence — all 3 must happen, in order:

```
HIGH IMPACT NEWS FIRES
        ↓
M1 SPIKE CANDLE  (≥1.5x ATR, ≥30% wick)
        ↓
WICK SWEEPS SWING HIGH/LOW  (liquidity grab — stops taken)
        ↓
M1 CHoCH IN OPPOSITE DIRECTION  (institutional reversal confirmed)
        ↓
ENTER NOW
```

SL: spike extreme + small buffer (institutional stops sit exactly at the extreme)
TP: nearest opposing swing with RR ≥ 1.5

State machine:
- Spike detected, CHoCH not yet → `WAIT_RETEST`
- Spike + CHoCH confirmed, RR ≥ 1.5 → `ENTER_NOW`
- No spike, or spike bias ≠ signal direction, or RR too low → `SKIP`

**The silo is strict.** NEWS_LIKELIHOODS only used in news sniper mode. Normal mode Bayesian table never runs during news sniper. Different timeframes, different logic, different likelihood table — zero bleed.

---

## BAYESIAN SCORING

Old system: stacked bonuses and penalties → total score → grade. Problem: 30 points from ICT + 25 from zone + penalty −20 → number that doesn't mean anything about probability.

New system: every condition updates a probability.

```
Base rate P(W) = 0.45  (45% win rate assumption, conservative)

For each condition (sweep, CHoCH, FVG, zone, trend aligned, news safe...):
  if condition is true:  P(W) × sensitivity
  if condition is false: P(W) × (1 - sensitivity)

Final P(win) → Expected Value = P(win) × RR − P(loss)
```

Two tables:
- `STANDARD_LIKELIHOODS` — used in normal mode, trained on pullback/breakout/reversal setups
- `NEWS_LIKELIHOODS` — used in news sniper mode, weighted toward spike + sweep + CHoCH confirmations

Once 50+ labeled outcomes exist in signals.csv, base rates auto-update from real results. System gets smarter the more it runs.

Grades still show (A+/A/B/C) as human-readable shorthand. Grade never overrides the entry state — the strategy decides ENTER/WAIT/SKIP, not the score.

---

## SETUP TYPES

| Setup | What it means | Entry signal |
|-------|--------------|-------------|
| ↩ PULLBACK LONG/SHORT | M15/M5 retracing in H1 trend | M5 rejection at OB/FVG in trend direction |
| 🚀 BREAKOUT ▲/▼ | M15 impulse breaks structure | FVG retest or M1 aggressive |
| ⚡ BO RETEST | Price back at FVG after breakout | Enter now, SL below FVG |
| ⚡ BREAKOUT PRESSURE | Consolidation at key level | Watch for expansion |
| 🔄 REVERSAL | H1 MSS confirmed | M5 confirm in new direction |
| 💥 NEWS SNIPER | Post-news spike + M1 CHoCH | Enter now, SL at spike extreme |

---

## ICT CONCEPTS

| Concept | What it is |
|---------|-----------|
| OB (Order Block) | Last bearish candle before a bullish impulse (or vice versa). Institutional entry zone. |
| FVG (Fair Value Gap) | Gap between candle 1 and candle 3 of a 3-candle impulse move. Price comes back to fill it. |
| Liquidity Sweep | Wick pierces swing high/low, then closes back inside. Stops taken, reversal likely. |
| MSS (Market Structure Shift) | H1 breaks a key swing in the opposite direction. Trend officially changing. |
| CHoCH (Change of Character) | First short-term structure break against the trend. Early warning of reversal. |
| Breaker Block | OB that got broken — now flipped polarity. Former support becomes resistance. |
| Premium zone | Price above 60–70% of the H1 range. Sell bias, not a place to buy. |
| Discount zone | Price below 30–40% of the H1 range. Buy bias, not a place to sell. |

---

## PAIRS AND SESSIONS

**Pairs:**
```
XAU_USD  XAG_USD
GBP_USD  EUR_USD  EUR_GBP
USD_JPY  GBP_JPY  EUR_JPY  CHF_JPY  CAD_JPY  NZD_JPY
```

**Sessions and killzones:**
| Session | UTC | Best pairs |
|---------|-----|-----------|
| Asian KZ | 01:00–05:00 | JPY pairs |
| London Open KZ | 07:00–10:00 | GBP, EUR |
| NY Open KZ | 12:00–15:00 | Gold, USD |
| London Close KZ | 15:00–17:00 | GBP/EUR reversals |

Outside killzones: score dampened, A+ capped to A, breakouts flagged WATCH only.

---

## NEWS FILTER

Source: ForexFactory JSON feed (free, no API key required).

| Impact | Action |
|--------|--------|
| HIGH | Hard block 60 min before, 30 min after. OR — switches to news sniper mode. |
| MEDIUM | Caution flag on signal. Does not block. |
| Post-news spike detected | Flag for ICT spike reversal setup. News sniper evaluates. |

Dashboard shows a live news ticker with countdown to next HIGH event. News panel shows upcoming events and which pairs are affected.

---

## DASHBOARD

```
http://localhost:5000
```

- Navy/blue dark theme
- Signals sorted: A+ first, then by score within each grade
- Color-coded rows by grade
- Live news ticker at top with countdown
- ⚡ EARLY badge — early entry timing (pressure building, not full confirm)
- ICT CONFLICT badge — do not trade this signal
- 🔴 NEWS SNIPER ACTIVE banner — pulsing red when news mode is on
- Click any row → Entry / SL / TP1 / TP2 / P(win) / EV breakdown
- Mode toggle button — switch between Normal and News Sniper manually
- Refreshes every 30 seconds

---

## HOW TO RUN

```bash
# Single scan
python main.py scan

# Live mode — scans every 5 min + dashboard
python main.py live

# Live mode with custom interval (seconds)
python main.py live 60

# Real-time tick feed
python main.py stream

# Pre-session briefings
python main.py briefing tokyo
python main.py briefing london
python main.py briefing new_york

# Log a trade you took
python main.py took GBP_JPY short

# Performance stats
python main.py stats

# Auto-scheduler (briefings at session open automatically)
python scheduler.py
```

---

## FILE STRUCTURE

```
forex-agent/
├── main.py                     # Entry point — all run modes
├── config.py                   # Pairs, sessions, scoring weights
├── scheduler.py                # Auto-briefing scheduler
│
├── core/
│   ├── fetcher.py              # OANDA candle fetching (H1/M15/M5/M1)
│   ├── confluence.py           # Multi-TF engine (pullback/breakout/reversal)
│   ├── structure.py            # Swing highs/lows, trend, recency-weighted vote
│   ├── ict.py                  # OB, MSS, CHoCH, FVG, premium/discount
│   ├── zones.py                # S/R zones (ATR-based)
│   ├── candles.py              # Candlestick pattern detection
│   ├── fvg.py                  # Fair Value Gap detection
│   ├── liquidity.py            # Structure-based SL/TP anchor points
│   └── streamer.py             # Live tick streaming
│
├── filters/
│   ├── decision_layer.py       # Thin orchestrator — routes to gold or forex strategy
│   ├── mode_manager.py         # Auto/manual mode detection — news sniper vs normal
│   ├── killzones.py            # ICT killzone filter
│   ├── news.py                 # ForexFactory news filter
│   └── session.py              # Session detection
│
├── strategies/
│   ├── gold_strategy.py        # XAU/XAG — ICT sniper sequence (sweep→CHoCH→OB)
│   ├── forex_strategy.py       # All other pairs — hard filters + RR check
│   └── news_sniper.py          # News mode only — M1 spike + CHoCH sequence
│
├── alerts/
│   ├── scorer.py               # Bayesian scorer — P(win), EV, grade
│   ├── logger.py               # CSV signal logger
│   └── slack.py                # Slack alerts
│
├── dashboard/
│   ├── app.py                  # Flask dashboard + API routes
│   └── templates/
│       └── dashboard.html      # Navy/blue UI
│
├── reports/
│   └── briefing.py             # Pre-session briefings + scan pipeline
│
├── ml/
│   ├── outcome_labeler.py      # Auto WIN/LOSS labeler
│   └── trainer.py              # Base rate updater (needs 50+ signals)
│
└── logs/
    ├── signals.csv             # Clean signal log (v5+)
    └── app.log
```

---

## TECH STACK

| What | Tool | Cost |
|------|------|------|
| Market data | OANDA API (practice) | Free |
| News data | ForexFactory JSON | Free |
| Backend | Python + Flask | Free |
| Dashboard | HTML/JS (localhost:5000) | Free |
| Alerts | Slack webhooks | Free |
| Signal log | CSV (signals.csv) | Free |
| ML (future) | scikit-learn | Free |

Total running cost: **$0/month** (OANDA practice account, no paid APIs).

---

## WHAT'S DONE

### Phase 1 — Bug fixes (core logic)
- ✅ Swing lookback reduced (was too large, missing near-term structure)
- ✅ Weighted vote bug fixed (was weighting the wrong candle)
- ✅ Signal lock made pair-aware (gold = 200 pip threshold, forex = 20 pip)
- ✅ Breakout threshold corrected (1.8x → 1.3x ATR)
- ✅ Pullback detection cleaned up (M15 against H1 only, removed noisy M5 check)
- ✅ M1 candles already in fetcher — confirmed no changes needed

### Phase 2 — Architecture cleanup
- ✅ decision_layer.py collapsed from 1164 lines → 22-line orchestrator
- ✅ gold_strategy.py — clean ICT sniper sequence (~280 lines)
- ✅ forex_strategy.py — hard filters extracted and isolated (~190 lines)
- ✅ Sweep → CHoCH now linked sequence (previously detected independently, not connected)
- ✅ Early entry flag moved to info-only (never changes entry state)
- ✅ SL capped at ATR×2, ATR floors added for gold

### Phase 3 — Bayesian scorer + news sniper mode
- ✅ Bayesian scorer replacing stacked bonus system
- ✅ P(win) + EV on every signal
- ✅ STANDARD_LIKELIHOODS vs NEWS_LIKELIHOODS — strict silo, never mix
- ✅ Auto base rate update at 50+ labeled signals (ml/ pipeline)
- ✅ news_sniper.py — M1 spike + wick sweep + M1 CHoCH sequence
- ✅ mode_manager.py — auto-detect + manual override, thread-safe
- ✅ Dashboard news panel bug fixed (panel_events missing from /api/signals)
- ✅ Dashboard mode banner (NEWS SNIPER ACTIVE red pulse)
- ✅ /api/mode GET + /api/mode/toggle POST endpoints
- ✅ Same 3 entry states across all strategies: ENTER_NOW / WAIT_RETEST / SKIP

---

## WHAT'S NEXT

1. **Phase 4 — Unicorn Model** — FVG + Breaker Block detection (high confluence, easy money if the sequence fires)
2. **Phase 5 — Retest entries** — detect when price comes back to an already-confirmed OB after ENTER_NOW was missed
3. **Phase 6 — ML base rates** — clean the signal log, auto-label win/loss, let the Bayesian priors update from real results. Needs 50+ signals first.
4. **Merge to main** — worktree testing complete, merge stoic-swanson → main
5. **Product prep** — clean config, multi-account support, onboarding doc for other ICT traders

---

## QUICK START

```bash
# 1. Install dependencies
pip install flask scikit-learn oandapyV20 requests pandas python-dotenv

# 2. Create .env file
OANDA_API_KEY=your_key
OANDA_ACCOUNT_ID=your_account
OANDA_ENVIRONMENT=practice
SLACK_WEBHOOK_URL=your_webhook  # optional

# 3. Test one scan
python main.py scan

# 4. Run live
python main.py live
# Dashboard at http://localhost:5000
```

---

## PAPER TRADING RULE

**Only trade when the scanner agrees with YOUR chart read.**

Scanner tells you: probability, RR, entry state.
Your chart tells you: does this actually look right right now?

Both have to agree. Scanner-only signals are not a reason to trade.
