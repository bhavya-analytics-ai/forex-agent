# Forex Scanner v3 — ICT Edition

Price action scanner for OANDA practice account.
Top-down analysis: H1 structure → M15 confirm → M5/M1 trigger.
ICT/Smart Money concepts built in.

---

## Pairs
USD_JPY, GBP_JPY, EUR_JPY, CHF_JPY, CAD_JPY, NZD_JPY,
GBP_USD, EUR_USD, EUR_GBP, XAU_USD, XAG_USD

## Sessions
Tokyo (00:00–06:00 UTC), London (07:00–12:00 UTC), New York (13:00–22:00 UTC)

---

## Setup

### 1. Install dependencies
```bash
pip install flask scikit-learn oandapyV20 requests pandas python-dotenv
```

### 2. Create your .env file
Create a file called `.env` in the project root:
```
OANDA_API_KEY=your_api_key_here
OANDA_ACCOUNT_ID=your_account_id_here
OANDA_ENVIRONMENT=practice
SLACK_WEBHOOK_URL=your_slack_webhook_here
```

Get your OANDA API key from: https://www.oanda.com/demo-account/tpa/personal_token
Get your Slack webhook from: https://api.slack.com/messaging/webhooks

### 3. Create logs folder
```bash
mkdir logs
```

---

## How To Run

### One-time scan (test everything works)
```bash
python main.py scan
```
Scans all 11 pairs once, prints results to terminal. Good for testing.

---

### Live mode (background polling)
```bash
python main.py live
```
Scans every 5 minutes. Sends A/A+ alerts to Slack.
Dashboard updates at http://localhost:5000

Custom interval (e.g. every 60 seconds):
```bash
python main.py live 60
```

---

### Stream mode (real-time, you're watching)
```bash
python main.py stream
```
Connects to OANDA live tick feed.
Fires alert the moment MSS or ChoCH prints on M1 close.
Shows candle countdown in terminal.
Dashboard live at http://localhost:5000

---

### Pre-session briefings
```bash
python main.py briefing tokyo
python main.py briefing london
python main.py briefing new_york
```
Scans all pairs, shows top setups + news warnings for that session.
Also sends to Slack if webhook is configured.

---

### Auto-scheduler (runs briefings automatically)
```bash
python scheduler.py
```
Leave this running in background.
Fires briefing 30 minutes before each session open automatically.
Sessions watched: Tokyo, London, New York.

---

### Mark a trade you took
```bash
python main.py took GBP_JPY short
python main.py took XAU_USD long
```
Stamps that signal as `taken=true` in the CSV log.
Used by ML model to learn what setups you personally pull the trigger on.

---

### Performance stats
```bash
python main.py stats
```
Shows win rate, avg pips, breakdown by pair and setup type.

---

## Dashboard

Open in browser after running `stream` or `live`:
```
http://localhost:5000
```

- Shows all 11 pairs, all grades, color coded
- Auto-refreshes every 30 seconds
- Click any row to see flags and warnings
- Slack only gets A+ and A alerts
- Dashboard shows everything

---

## Alert Grades

| Grade | Meaning | Action |
|-------|---------|--------|
| A+ | Zone + structure + candle + ICT all aligned | Strong entry |
| A  | Solid confluence, 1 element missing | Take if chart looks right |
| B  | Watch only, missing confirmation | Wait |
| C  | Conflicting or weak signals | Skip |

---

## Score Breakdown (max 100)

| Component | Max Points | What It Checks |
|-----------|-----------|----------------|
| Zone | 25 | H1 zone quality and touches |
| TF Confluence | 25 | H1 + M15 + M5 agreement |
| Pattern | 20 | M5 candle (pin bar, engulf, etc) |
| Session | 15 | Right session for this pair |
| News | 10 | No high-impact news nearby |
| Quality Bonus | +15 | Pullback in confirmed trend |
| FVG Bonus | +10 | Fair value gap at zone |
| ICT Bonus | +30 | OB, MSS, ChoCH, sweep, premium/discount |

---

## ICT Concepts

| Concept | What It Means |
|---------|--------------|
| Order Block (OB) | Last bearish candle before bullish impulse (and vice versa) |
| Breaker Block | OB that got broken, now flipped polarity |
| Liquidity Sweep | Wick above swing high closes back below = stops taken |
| MSS | Market Structure Shift — trend officially changing |
| ChoCH | Change of Character — first break of short-term high/low, precedes MSS |
| Premium Zone | Price above 60% of range — sell bias |
| Discount Zone | Price below 40% of range — buy bias |

---

## Killzones

Outside killzones the scanner stays quiet unless A+ setup.

| Killzone | UTC | Best Pairs |
|----------|-----|-----------|
| Asian | 01:00–05:00 | JPY pairs |
| London Open | 07:00–10:00 | GBP/EUR pairs |
| NY Open | 12:00–15:00 | Gold, USD pairs |
| London Close | 15:00–17:00 | GBP/EUR reversals |

---

## ML Pipeline

### Auto-labeling (runs automatically)
15 minutes after every signal fires, the system checks price and labels it WIN/LOSS/NEUTRAL automatically. No input needed.

### Manual backfill
```bash
python -m ml.outcome_labeler backfill
```
Labels all historical signals in your CSV against price data.

### Train model (after 50+ signals)
```bash
python -m ml.trainer
```
Trains on your signal history. Re-weights the scorer based on what actually works for YOUR pairs and sessions.

### Performance report only
```bash
python -m ml.trainer report
```

---

## File Structure

```
forex-agent/
├── config.py               # Pairs, sessions, scoring weights
├── main.py                 # Entry point — all run modes
├── scheduler.py            # Auto-briefing scheduler
├── .env                    # Your API keys (never commit this)
├── core/
│   ├── confluence.py       # Multi-TF confluence engine
│   ├── fetcher.py          # OANDA candle fetching
│   ├── ict.py              # ICT/Smart Money concepts
│   ├── streamer.py         # Live tick streaming
│   ├── structure.py        # Market structure analysis
│   ├── zones.py            # S/R and supply/demand zones
│   ├── candles.py          # Candlestick pattern detection
│   └── fvg.py              # Fair value gap detection
├── alerts/
│   ├── scorer.py           # Signal scoring engine
│   ├── logger.py           # CSV signal logger
│   └── slack.py            # Slack alerts
├── filters/
│   ├── killzones.py        # ICT killzone filter
│   ├── news.py             # ForexFactory news filter
│   └── session.py          # Session detection
├── reports/
│   └── briefing.py         # Pre-session briefings
├── dashboard/
│   ├── app.py              # Flask web dashboard
│   └── templates/
│       └── dashboard.html  # Dashboard UI
├── ml/
│   ├── outcome_labeler.py  # Auto WIN/LOSS labeler
│   └── trainer.py          # Model trainer
└── logs/
    ├── signals.csv         # Every signal logged here
    └── app.log             # App logs
```

---

## Trading Style This Scanner Is Built For

- Price action only, no indicators
- Top-down: H1 structure → M15 confirm → M5/M1 trigger
- Entry: rejection candle AT a H1 zone, after MSS or ChoCH
- Best setups: SR flip + liquidity sweep + OB + pullback in confirmed trend
- Hold: flexible — scalp impulse (10-15 min) OR ride trend for hours
- Avoids: high-impact news, outside killzones
- Every alert shows both scalp target and swing target

---

## Quick Start (first time)

```bash
# 1. Install
pip install flask scikit-learn oandapyV20 requests pandas python-dotenv

# 2. Create .env with your keys

# 3. Create logs folder
mkdir logs

# 4. Test it works
python main.py scan

# 5. Run live
python main.py stream
```