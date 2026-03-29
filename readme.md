# Forex Scanner v5 — ICT Edition

Price action scanner for OANDA practice account.
Top-down analysis: H1 structure → M15 confirm → M5/M1 trigger.
ICT/Smart Money concepts + execution decision layer built in.

**Status: Paper trading. Core logic validated. Execution layer active.
Do NOT trade scanner-only signals — always validate against your chart first.**

---

## What's New in v5

v4 told you direction. v5 tells you **when and how to enter**.

Added on top of v4 (nothing broken):
- `filters/decision_layer.py` — hard filters, TP/SL override, gold mode, early entry
- `core/liquidity.py` — structure-based SL/TP using real swing levels
- Breakout pressure + acceptance confirmation (catches consolidation before the move)
- Gold-specific execution path (separate logic, doesn't affect other pairs)
- Early entry mode (fires before M5 confirmation when pressure is building)
- News panel fix — ForexFactory date format was breaking parsing, fixed

---

## Architecture

```
OANDA API
    ↓
core/fetcher.py        — candle data (H1/M15/M5/M1)
    ↓
core/confluence.py     — multi-TF engine, pullback/breakout/reversal detection
core/structure.py      — swing highs/lows, trend strength
core/ict.py            — OB, MSS, ChoCH, FVG, premium/discount
core/zones.py          — S/R zones (ATR-based)
    ↓
alerts/scorer.py       — scoring (0–95), grading (A+/A/B/C)
    ↓
filters/decision_layer.py  — execution filters + TP/SL override  ← NEW
    ↓
dashboard/app.py       — Flask dashboard at localhost:5000
alerts/slack.py        — Slack alerts
alerts/logger.py       — CSV signal log
```

---

## Pairs

```
USD_JPY  GBP_JPY  EUR_JPY  CHF_JPY  CAD_JPY  NZD_JPY
GBP_USD  EUR_USD  EUR_GBP
XAU_USD  XAG_USD
```

## Sessions

| Session | UTC | Best Pairs |
|---------|-----|-----------|
| Tokyo | 00:00–06:00 | JPY pairs |
| London | 07:00–12:00 | GBP/EUR |
| New York | 13:00–22:00 | Gold, USD |

---

## Decision Layer (v5)

Applied after scoring, before output. Hard filters first, then TP/SL, then entry mode.

### Hard Filters (blocks trade entirely)
| Filter | Condition |
|--------|-----------|
| Mid-range | Price 40–60% of HTF range AND weak structure |
| HTF zone | Strong opposing zone within ATR×0.5 (dynamic) |
| TF conflict | H1/M15/M5 biases not aligned (skipped for pullbacks) |
| Choppy | Ranging + strength 1 |
| Multi-conflict | 2+ mismatches (trend + zone + sweep) |
| RR < 1.0 | TP doesn't justify SL |

Momentum override: if breakout ATR ratio ≥ 1.5, mid-range and HTF zone filters skipped.

### TP/SL Override
- **SL**: M5 swing → M15 swing → OB edge → ATR fallback. Capped at ATR×2.
- **TP1**: Nearest liquidity ≥ ATR×0.5 away with RR ≥ 1.5. Closest always wins.
- **TP2**: Next real level after TP1. Not a fixed multiplier.

### Decision Priority
1. Decision layer filters
2. RR validity (≥ 1.5)
3. Setup type validity
4. Score — info only, does NOT block trades

A Grade C setup that passes filters + RR check shows as **"VALID SETUP — lower confidence"** instead of SKIP.

### Early Entry Mode
Fires when full M5 confirmation is absent but pressure is building.

Conditions:
- H1 aligned with direction (mandatory)
- M15 OR M5 OR momentum (any one sufficient)
- Not choppy (strength ≥ 2 or non-ranging phase)
- No strong conflict
- Not extreme premium/discount (> 85% or < 15%)

Output: `early_entry = True`, `entry_type = "anticipation"`, ⚡ EARLY badge on dashboard.
Grade unchanged — early entry is timing info, not quality info.

---

## Gold Mode (XAU_USD only)

Completely separate execution path inside decision layer. Other pairs unaffected.

### Trend
Dual lookback using H1 structure:
- Long-term: dominant trend (6 swings)
- Short-term: current phase (trending / pullback / ranging)
- If both agree → `trend_strength = "strong"`

### Zone Classification
Zones reclassified relative to H1 trend direction (not just price position).

### Breakout Pipeline
| Stage | Condition | Action |
|-------|-----------|--------|
| Breakout pressure | Compression near level (small bodies, tightening range) | Mark `breakout_preparation` |
| Early breakout | ATR expansion OR consecutive candles | Aggressive entry allowed |
| Breakout confirmed | Price holds above/below level, no return inside | Upgrade setup |
| Breakout failed | Price returns inside level | Warn fakeout, revert to reaction |

Breakout strength = `ATR_ratio × consecutive_candles`

| Strength | Action |
|----------|--------|
| HIGH | Immediate entry if: near level + confirmed/early + close in top 70% |
| MEDIUM | Wait for 1 confirmation candle |
| LOW | Skip continuation trade |

### Gold SL (Adaptive)
- **Normal mode**: M5 swing → M15 swing → OB → ATR×1.0
- **Momentum mode**: Skip M5 (too tight) → M15 → OB → ATR×1.5 + ATR×0.3 buffer
- Cap: ATR×2 always

### Gold TP
- TP1: Nearest valid liquidity (distance ≥ ATR×0.5, RR ≥ 1.2). Closest wins — far H1 swing can't beat a closer M15 level.
- TP2: Next real level after TP1. Not a fixed multiplier.

### Sanity Warnings (warn only, never block)
- Target unrealistically far vs structure range
- Late entry — move already largely happened
- Price mid-range with no breakout
- Weak or transitioning trend
- Multiple conflicting signals

---

## Setup Types

| Setup | Meaning | Action |
|-------|---------|--------|
| ↩ PULLBACK LONG/SHORT | M15/M5 retracing in H1 trend | Wait for M5 rejection, enter with trend |
| 🚀 BREAKOUT ▲/▼ | M15 impulse breaks structure | Watch for FVG retest or M1 aggressive |
| ⚡ BO RETEST | Price back at FVG after breakout | Enter now, SL below FVG |
| ⚡ BREAKOUT PRESSURE | Consolidation at key level | Prepare, watch for expansion |
| ⚡ EARLY BREAKOUT | ATR expansion candle detected | Aggressive entry, pre-confirmation |
| 🔄 REVERSAL | H1 MSS confirmed | High conviction, enter on M5 confirm |
| sr flip / zone tap | S/R zone setup | Standard zone entry |

---

## Grading

| Grade | Score | Meaning | Action |
|-------|-------|---------|--------|
| A+ | 82+ | Full alignment — zone + structure + candle | Strong entry |
| A | 68+ | Solid confluence, 1 element missing | Take if chart agrees |
| B | 54+ | Watch only, missing confirmation | Wait |
| C | <54 | Weak or conflicting | Skip — unless DL overrides |

**Score capped at 95. 100% confidence doesn't exist.**
A+ capped to A outside killzones.

---

## Score Breakdown

| Component | Max | What It Checks |
|-----------|-----|----------------|
| Zone | 25 | H1 zone quality and touches |
| TF Confluence | 25 | H1 + M15 + M5 weighted vote |
| Pattern | 20 | M5 candle (pin bar, engulf, etc) |
| Session | 15 | Correct session for pair |
| News | 10 | No high-impact news nearby |
| Quality Bonus | +15 | Pullback in confirmed trend |
| Pullback Bonus | +8 | Clean pullback entry |
| Breakout Bonus | +4 to +12 | Breakout strength |
| MSS Reversal | +15 | H1 MSS confirmed |
| FVG Bonus | +10 | Fair value gap at zone |
| ICT Bonus | +30 | OB, MSS, ChoCH, sweep, P/D zone |

**Penalties**: Pattern conflict −25 | No zone −12 | M5 consolidating −15 | ICT conflict −30 | Counter-trend −20

---

## ICT Concepts

| Concept | Meaning |
|---------|---------|
| OB | Last bearish candle before bullish impulse (and vice versa) |
| Breaker Block | OB that got broken, now flipped polarity |
| Liquidity Sweep | Wick above swing high closes back below = stops taken |
| MSS | Market Structure Shift — H1 MSS = trend officially changing |
| ChoCH | Change of Character — first break of short-term structure |
| FVG | Fair Value Gap — imbalance left by impulse, price retests it |
| Premium | Price above 60% of range — sell bias |
| Discount | Price below 40% of range — buy bias |

---

## Killzones

Outside killzones: score dampened 50%, breakouts flagged WATCH only.

| Killzone | UTC | Best Pairs |
|----------|-----|-----------|
| Asian | 01:00–05:00 | JPY pairs |
| London Open | 07:00–10:00 | GBP/EUR |
| NY Open | 12:00–15:00 | Gold, USD |
| London Close | 15:00–17:00 | GBP/EUR reversals |

---

## News Filter

Source: ForexFactory JSON (free, no API key).

| Impact | Action |
|--------|--------|
| HIGH | Block signals 60 min before, 30 min after |
| MEDIUM | Caution flag, don't block |
| Post-news | Flag for ICT spike reversal setup |

---

## How To Run

```bash
# One-time scan
python main.py scan

# Live mode (poll every 5 min + dashboard)
python main.py live

# Live mode custom interval
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

# Auto-scheduler (briefings at session open)
python scheduler.py
```

## Dashboard

```
http://localhost:5000
```

- Blue/navy theme
- News ticker with countdown
- Color-coded rows by grade
- ⚡ EARLY badge for early entry setups
- Click any row for Entry / SL / TP1 / TP2
- ICT CONFLICT badge = do not trade
- Refreshes every 30s

---

## File Structure

```
forex-agent/
├── main.py                 # Entry point — all run modes
├── config.py               # Pairs, sessions, scoring weights
├── scheduler.py            # Auto-briefing scheduler
│
├── core/
│   ├── confluence.py       # Multi-TF engine (pullback/breakout/reversal)
│   ├── fetcher.py          # OANDA candle fetching
│   ├── ict.py              # ICT concepts
│   ├── structure.py        # Market structure (6 swings, recency weighted)
│   ├── zones.py            # S/R zones (ATR-based)
│   ├── candles.py          # Candlestick pattern detection
│   ├── fvg.py              # Fair value gap detection
│   ├── streamer.py         # Live tick streaming
│   └── liquidity.py        # Structure-based SL/TP ← NEW (v5)
│
├── filters/
│   ├── decision_layer.py   # Execution filters + gold mode + early entry ← NEW (v5)
│   ├── killzones.py        # ICT killzone filter
│   ├── news.py             # ForexFactory news filter
│   └── session.py          # Session detection
│
├── alerts/
│   ├── scorer.py           # Signal scoring
│   ├── logger.py           # CSV signal logger
│   └── slack.py            # Slack alerts
│
├── dashboard/
│   ├── app.py              # Flask dashboard
│   └── templates/
│       └── dashboard.html  # Blue/navy UI
│
├── reports/
│   └── briefing.py         # Pre-session briefings + scan pipeline
│
├── ml/
│   ├── outcome_labeler.py  # Auto WIN/LOSS labeler
│   └── trainer.py          # Model trainer (needs 50+ signals)
│
└── logs/
    ├── signals.csv         # Clean signal log (v5+)
    └── app.log
```

---

## Paper Trading Status

| Component | Status |
|-----------|--------|
| H1 trend detection | ✅ Working |
| ICT conflict detection | ✅ Working |
| News blocking | ✅ Working |
| Decision layer filters | ✅ Working |
| Gold execution mode | ✅ Working |
| Early entry mode | ✅ Working |
| M15/M5 entry timing | 🔧 Improving |
| Breakout retest detection | 🔧 Needs live testing |
| ML pipeline | 🔧 Needs 50+ clean signals |

**Rule: Only trade when scanner agrees with YOUR chart read. Never trade scanner-only.**

---

## ML Pipeline

```bash
# Auto-label outcomes (runs automatically every scan cycle)
python -m ml.outcome_labeler backfill

# Train model (after 50+ labeled signals)
python -m ml.trainer

# Performance report
python -m ml.trainer report
```

---

## Quick Start

```bash
# 1. Install
pip install flask scikit-learn oandapyV20 requests pandas python-dotenv

# 2. Create .env
OANDA_API_KEY=your_key
OANDA_ACCOUNT_ID=your_account
OANDA_ENVIRONMENT=practice
SLACK_WEBHOOK_URL=your_webhook  # optional

# 3. Test
python main.py scan

# 4. Run
python main.py live
```
