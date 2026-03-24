# Forex Scanner v4 — ICT Edition

Price action scanner for OANDA practice account.
Top-down analysis: H1 structure → M15 confirm → M5/M1 trigger.
ICT/Smart Money concepts built in.

**Current status: Paper trading. H1 trend detection working correctly.
Pullback vs reversal detection added. Breakout detection added.
Do NOT trust signals blindly yet — validate against chart before every trade.**

---

## Pairs
USD_JPY, GBP_JPY, EUR_JPY, CHF_JPY, CAD_JPY, NZD_JPY,
GBP_USD, EUR_USD, EUR_GBP, XAU_USD, XAG_USD

## Sessions
Tokyo (00:00–06:00 UTC), London (07:00–12:00 UTC), New York (13:00–22:00 UTC)

---

## What Was Fixed (v3 → v4)

### Core Logic Fixes
- **H1 trend detection** — was reading only 4 swing points (too short). Now uses 6 swings
  with recency weighting. H1 candle count increased from 200 → 400 so scanner sees full
  trend history, not just recent 2 weeks.
- **Zone override removed** — zones used to flip direction (resistance = bearish always).
  Now zones only CONFIRM the trend, never override it. Zone vs trend conflict is flagged
  as a warning instead.
- **H1 is the boss** — weighted vote system: H1 = 2 votes, M15 = 1, M5 = 1.
  Lower TFs can no longer override H1 by themselves.
- **ICT MSS wired into direction** — MSS/ChoCH detection now actually affects the final
  direction signal. Before it was decorative tags that did nothing.
- **ChoCH fix** — was firing on every candle because it just checked if price was above
  any recent high. Now correctly detects a FRESH break only (prev close below, current
  close above the level).
- **Premium/Discount fix** — now uses the most recent paired swing high+low from the same
  leg. Before it used independent highs and lows which gave wrong ranges (especially gold).
- **Gold pip size fix** — was 0.1, now correctly 0.01. Was causing SL/TP to be 10x too
  wide on all gold signals.
- **ICT conflict penalty** — if MSS says bullish but signal is bearish, score gets -30
  penalty. Before this was just a cosmetic badge that did nothing.
- **Signal stability** — signals lock for 15 pips before re-evaluating. Stops the 30s
  flip-flop where signal changes every refresh.

### Pullback vs Reversal (NEW)
The most important fix. Previously M15/M5 going bearish inside an H1 uptrend
would flip the signal to BEARISH. That's wrong — it's just a pullback.

**New rule: H1 trend is LAW. Only H1 MSS can change it.**

- H1 uptrend + M15/M5 bearish + no H1 MSS = **PULLBACK** → signal stays BULLISH,
  flagged as entry opportunity
- H1 uptrend + H1 MSS fires bearish = **REVERSAL** → signal flips BEARISH
- H1 trend memory persists across scan cycles — doesn't reset every 30s

### Breakout Detection (NEW)
Two-stage alert system for breakout setups:

- **Stage 1** — M15 impulse candle 2x+ ATR breaks recent swing structure.
  Alert fires: "BREAKOUT FIRING — watch for retest or enter M1 aggressive"
- **Stage 2** — Price pulls back to FVG left by impulse candle.
  Alert fires: "BREAKOUT RETEST — price at FVG, enter now"

Breakout overrides H1 trend only during killzones (institutional moves).
Outside killzones: flagged as WATCH only.

### News Filter (NEW)
- ForexFactory JSON feed (free, no API key needed)
- HIGH impact news: blocks signals 60 min before, 30 min after
- MEDIUM impact: caution flag only, doesn't block
- Post-news spike detection: flags ICT reversal opportunity after news candle
- News countdown ticker on dashboard

### Dashboard Redesign (NEW)
- Blue/navy professional theme, much easier to read
- News ticker at top with countdown to next high-impact event
- Red banner when news within 30 mins
- Bigger clearer BULL/BEAR direction display
- Color-coded rows by grade (A+ = green, A = blue, B = yellow, C = orange)
- Session timer in header
- ICT CONFLICT badge on signals that contradict MSS/ChoCH
- Setup type column shows: PULLBACK LONG/SHORT, BREAKOUT ▲/▼, BO RETEST, REVERSAL

---

## Setup Types (what the dashboard shows)

| Setup | Meaning | Action |
|-------|---------|--------|
| ↩ PULLBACK LONG | M15/M5 retracing in H1 uptrend | Wait for M5 rejection candle, enter long |
| ↩ PULLBACK SHORT | M15/M5 retracing in H1 downtrend | Wait for M5 rejection candle, enter short |
| 🚀 BREAKOUT ▲/▼ | Stage 1 — M15 impulse broke structure | Watch for FVG retest OR enter M1 aggressive |
| ⚡ BO RETEST | Stage 2 — price back at FVG/OB | Enter now, SL below FVG |
| 🔄 REVERSAL | H1 MSS confirmed, trend changing | High conviction, enter on M5 confirmation |
| sr flip | S/R flip zone | Standard zone setup |
| zone tap | Price at key zone | Standard zone setup |

---

## Alert Grades

| Grade | Meaning | Action |
|-------|---------|--------|
| A+ | Zone + structure + candle + ICT all aligned | Strong entry |
| A  | Solid confluence, 1 element missing | Take if chart looks right |
| B  | Watch only, missing confirmation | Wait |
| C  | Conflicting or weak signals | Skip |

**Score is capped at 95 — 100% confidence doesn't exist in trading.**

---

## Score Breakdown

| Component | Max Points | What It Checks |
|-----------|-----------|----------------|
| Zone | 25 | H1 zone quality and touches |
| TF Confluence | 25 | H1 + M15 + M5 weighted vote |
| Pattern | 20 | M5 candle (pin bar, engulf, etc) |
| Session | 15 | Right session for this pair |
| News | 10 | No high-impact news nearby |
| Quality Bonus | +15 | Pullback in confirmed trend |
| Pullback Bonus | +8 | Clean pullback entry in strong H1 trend |
| Breakout Bonus | +4 to +12 | Breakout strength (retest = highest) |
| MSS Reversal Bonus | +15 | H1 MSS confirmed |
| FVG Bonus | +10 | Fair value gap at zone |
| ICT Bonus | +30 | OB, MSS, ChoCH, sweep, premium/discount |

**Penalties:**
- Pattern conflict: -25
- No zone: -12
- M5 consolidating: -15
- ICT conflict (MSS contradicts signal): -30
- Counter-trend (against strong H1): -20

---

## ICT Concepts

| Concept | What It Means |
|---------|--------------|
| Order Block (OB) | Last bearish candle before bullish impulse (and vice versa) |
| Breaker Block | OB that got broken, now flipped polarity |
| Liquidity Sweep | Wick above swing high closes back below = stops taken |
| MSS | Market Structure Shift — trend officially changing (H1 MSS = highest signal) |
| ChoCH | Change of Character — first break of short-term high/low, precedes MSS |
| FVG | Fair Value Gap — imbalance left by impulse candle, price often retests it |
| Premium Zone | Price above 60% of current swing range — sell bias |
| Discount Zone | Price below 40% of current swing range — buy bias |

---

## Killzones

Outside killzones: score dampened 50%, breakouts flagged WATCH only.

| Killzone | UTC | Best Pairs |
|----------|-----|-----------|
| Asian | 01:00–05:00 | JPY pairs |
| London Open | 07:00–10:00 | GBP/EUR pairs |
| NY Open | 12:00–15:00 | Gold, USD pairs |
| London Close | 15:00–17:00 | GBP/EUR reversals |

---

## How To Run

### One-time scan
```bash
python main.py scan
```

### Live mode (background polling every 5 mins)
```bash
python main.py live
```

### Stream mode (real-time tick feed)
```bash
python main.py stream
```

### Pre-session briefings
```bash
python main.py briefing tokyo
python main.py briefing london
python main.py briefing new_york
```

### Auto-scheduler
```bash
python scheduler.py
```

### Log a trade you took
```bash
python main.py took GBP_JPY short
python main.py took XAU_USD long
```
**Important:** Run this in a new terminal tab — don't stop the scanner.
Wait for the scanner to log a signal first (few mins), then run this.

### Performance stats
```bash
python main.py stats
```

---

## Dashboard
```
http://localhost:5000
```
- Blue/navy theme, easy to read
- News ticker top with countdown
- Color coded rows by grade
- Click any row for Entry / SL / TP1 / TP2
- ICT CONFLICT badge = do not trade
- Refreshes every 30s

---

## Paper Trading Status

Currently paper trading to validate signals. Trust level:
- ✅ H1 trend detection — working correctly
- ✅ ICT conflict detection — working, blocks bad signals
- ✅ News blocking — working via ForexFactory
- 🔧 M15/M5 entry timing — improving, needs more validation
- 🔧 Breakout detection — newly added, needs live testing
- 🔧 ML pipeline — needs 50+ clean signals before training

**Rule: Only trade when scanner agrees with YOUR chart read.
Never trade scanner-only signals until trust is established.**

---

## ML Pipeline

### Auto-labeling
15 minutes after every signal, system checks price and labels WIN/LOSS/NEUTRAL.

### Manual backfill
```bash
python -m ml.outcome_labeler backfill
```

### Train model (after 50+ signals)
```bash
python -m ml.trainer
```

### Performance report
```bash
python -m ml.trainer report
```

---

## Known Issues / Still To Fix
- ML outcome labeler timezone warning (harmless, doesn't stop scanner)
- M1 aggressive breakout entry not fully implemented yet
- Stream mode breakout detection needs testing in live market

---

## File Structure

```
forex-agent/
├── config.py               # Pairs, sessions, scoring weights (H1: 400 candles)
├── main.py                 # Entry point — all run modes
├── scheduler.py            # Auto-briefing scheduler
├── .env                    # API keys (never commit)
├── core/
│   ├── confluence.py       # Multi-TF engine (pullback/breakout/reversal logic)
│   ├── fetcher.py          # OANDA candle fetching (gold pip fixed: 0.01)
│   ├── ict.py              # ICT concepts (ChoCH fixed, P/D range fixed)
│   ├── streamer.py         # Live tick streaming
│   ├── structure.py        # Market structure (6 swings, recency weighted)
│   ├── zones.py            # S/R and supply/demand zones (ATR-based)
│   ├── candles.py          # Candlestick pattern detection
│   └── fvg.py              # Fair value gap detection
├── alerts/
│   ├── scorer.py           # Signal scoring (ICT conflict penalty, setup bonuses)
│   ├── logger.py           # CSV signal logger
│   └── slack.py            # Slack alerts
├── filters/
│   ├── killzones.py        # ICT killzone filter
│   ├── news.py             # ForexFactory news (HIGH block, MEDIUM warn)
│   └── session.py          # Session detection
├── reports/
│   └── briefing.py         # Pre-session briefings
├── dashboard/
│   ├── app.py              # Flask dashboard (news wired in)
│   └── templates/
│       └── dashboard.html  # Blue/navy UI with news ticker
├── ml/
│   ├── outcome_labeler.py  # Auto WIN/LOSS labeler
│   └── trainer.py          # Model trainer
└── logs/
    ├── signals.csv         # Fresh log (started clean after v4 fixes)
    ├── signals_backup.csv  # Old data from v3 (before fixes, don't train on this)
    └── app.log             # App logs
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
SLACK_WEBHOOK_URL=your_webhook

# 3. Create logs folder
mkdir logs

# 4. Test
python main.py scan

# 5. Run
python main.py stream
```