python main.py live


# 📈 Forex Zone Scanner & Pre-Session Briefing Agent

A Python-based algorithmic trading intelligence system for forex price action traders. Scans multiple currency pairs across H1/M15/M5 timeframes, detects high-probability zone setups, and fires real-time alerts with plain-English explanations.

Built for traders who trade S/R zones and supply/demand without indicators — the system does the scanning, you do the trading.

---

## Features

- **Multi-timeframe confluence** — H1 sets direction, M15 confirms, M5 triggers entry
- **Zone detection** — S/R zones, supply/demand zones, SR flips, Fair Value Gaps
- **Smart signal grading** — A+/A/B/C grades with strict validation rules
- **Pattern detection** — engulfing, pin bar, doji, inside bar, momentum candles
- **Conflict detection** — flags when M5 candle contradicts signal direction
- **Consolidation filter** — won't alert when price is chopping on a zone
- **Session scoring** — JPY pairs weighted higher Tokyo, Gold/Silver higher NY
- **News filter** — blocks signals within 60 min of high-impact events
- **Pre-session briefings** — auto-generated before Tokyo and New York opens
- **Slack integration** — real-time alerts to your phone
- **Signal logger** — every signal logged to CSV for future ML training

---

## Pairs Covered

| Pair | Sessions |
|------|----------|
| USD/JPY | Tokyo + NY |
| GBP/JPY | Tokyo |
| EUR/JPY | Tokyo |
| XAU/USD (Gold) | New York |
| XAG/USD (Silver) | New York |

---

## Signal Scoring

| Component | Max Points |
|-----------|-----------|
| Zone strength (H1) | 25 |
| TF confluence (H1+M15+M5) | 25 |
| M5 candle pattern | 20 |
| Session context | 15 |
| News clearance | 10 |
| Setup quality bonus | +15 |
| FVG overlap bonus | +10 |

**Grade rules:**
- 🔥 **A+** — zone + structure + M5 candle all aligned, strong entry
- ✅ **A** — solid confluence, take if chart confirms
- ⚠️ **B** — watch only, missing 1+ element
- ❌ **C** — conflict or weak signals, skip

---

## Alert Output

```
=================================================================
📈 USD_JPY | BULLISH | 74/100 | ✅ Grade A
   GOOD SETUP — solid confluence, take if chart looks right to you
-----------------------------------------------------------------
📊 Trend: uptrend | Phase: pullback | Quality: A+ | Pullback: 42%
🔑 Setup: Sr Flip
📐 Score: Zone:18 TF:17 Pat:14 Sess:15 News:10 Qual:15
-----------------------------------------------------------------
📖 H1 + one lower TF bullish — good timing, wait for M5 candle
🕯️  M5 Candle: Bullish engulfing — buyers overwhelmed sellers, 1.5x size
=================================================================
```

---

## Setup

### 1. Clone & install
```bash
git clone https://github.com/bhavya-analytics-ai/forex-agent.git
cd forex-agent
conda create -n forex-agent python=3.11
conda activate forex-agent
pip install oandapyV20 pandas numpy requests python-dotenv
```

### 2. Configure
Create a `.env` file in the root directory:
```
OANDA_API_KEY=your-oanda-api-token
OANDA_ACCOUNT_ID=your-account-id
OANDA_ENVIRONMENT=practice
SLACK_WEBHOOK_URL=your-slack-webhook (optional)
```

> ⚠️ Never commit your `.env` file. It's already in `.gitignore`.

### 3. Run
```bash
# Live scanner (every 5 min)
python main.py live

# Live scanner (every 60 seconds)
python main.py live 60

# One-time scan
python main.py scan

# Pre-session briefings
python main.py briefing tokyo
python main.py briefing new_york

# Performance stats
python main.py stats

# Auto-scheduler (fires briefings before each session)
python scheduler.py
```

---

## Project Structure

```
forex-agent/
├── main.py                  # Entry point
├── scheduler.py             # Auto-scheduler for briefings
├── config.py                # Pairs, sessions, scoring config
├── core/
│   ├── fetcher.py           # OANDA API candle fetching
│   ├── zones.py             # S/R and supply/demand zone detection
│   ├── structure.py         # Market structure and trend analysis
│   ├── confluence.py        # Multi-timeframe confluence engine
│   ├── candles.py           # Candlestick pattern detection
│   └── fvg.py               # Fair Value Gap detection
├── filters/
│   ├── news.py              # Economic calendar filter
│   └── session.py           # Session detection and scoring
├── alerts/
│   ├── scorer.py            # Signal scoring and grading
│   ├── slack.py             # Slack alert formatting
│   └── logger.py            # CSV signal logger
└── reports/
    └── briefing.py          # Pre-session briefing generator
```

---

## Data Source

[OANDA](https://www.oanda.com/) practice/live account API. Free demo account available.

---

## Tech Stack

- Python 3.11
- oandapyV20
- pandas / numpy
- requests
- python-dotenv

---

## Roadmap

- [ ] Fix trend detection accuracy on H1
- [ ] Fix ForexFactory news calendar parsing
- [ ] Add D1 timeframe as extra confirmation layer
- [ ] Deploy to VPS (DigitalOcean) for 24/7 running
- [ ] Build ML layer on top of signal log CSV data
- [ ] Streamlit dashboard for visual zone display

---

## Disclaimer

This tool is for educational purposes. It does not constitute financial advice. Always do your own analysis before entering any trade.