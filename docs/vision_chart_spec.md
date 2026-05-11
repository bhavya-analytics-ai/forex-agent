# Vision Chart Integration — Spec for Future Session

## What This Is

Two-phase plan:
1. **Phase A (build now):** Auto-capture H1/M15/M5/M1 chart images from OANDA data when a signal fires or debate runs. Feed them to a NIM vision model as part of the debate — "here's what the chart actually looks like."
2. **Phase B (train later):** Once 200+ labeled outcomes collected, use stored chart images as training features for a pattern-recognition model.

---

## Phase A — Chart Images in Debate

### What to build

`core/chart_capture.py` — renders OANDA candle data as a chart image (PNG) using matplotlib/mplfinance. Returns base64-encoded image.

**Input:** signal dict from DB (has pair, timestamp_utc, direction, entry_price, sl_price, tp1_price)

**Output:** 4 images — H1 (last 50 candles), M15 (last 50), M5 (last 30), M1 (last 30)

Each image includes:
- Candlestick chart
- Horizontal lines: entry (white), SL (red), TP1 (green)
- OB zone shaded if h1_zone_high/low available
- Title: pair + direction + grade + timestamp

### Vision model call

Add a 4th call to `core/debate.py` after the judge verdict:

```python
# Call 4 (optional, only if NIM_API_KEY set and images captured successfully)
# Send H1 + M15 images to vision model
# Prompt: "You are an ICT chart analyst. The bull/bear debate reached verdict X.
#          Look at the H1 and M15 charts. Does the price action confirm or deny the verdict?
#          Flag anything the text debate missed."
# Model: nvidia/llama-3.2-90b-vision-instruct (NIM vision model)
# Returns: {"visual_confirm": "AGREE/DISAGREE/PARTIAL", "observation": "one sentence"}
```

Dashboard shows this below the debate result as:
```
👁 Visual: AGREE — H1 OB respected, M15 shows clean higher-low structure
```

### Files to create/modify
- `core/chart_capture.py` — NEW
- `core/debate.py` — add optional call 4
- `dashboard/app.py` — `/api/debate_signal` passes images if capture succeeds
- `dashboard/templates/dashboard.html` — show visual_confirm in debate card
- `requirements.txt` — add `mplfinance>=0.12.10b0`

---

## Phase B — Store Charts for Training

### Schema addition (add to db/database.py)

```sql
CREATE TABLE IF NOT EXISTS chart_snapshots (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    signal_id     TEXT,
    captured_at   TEXT,
    timeframe     TEXT,   -- H1, M15, M5, M1
    image_b64     TEXT,   -- base64 PNG
    candle_count  INTEGER,
    FOREIGN KEY (signal_id) REFERENCES agent_signals(signal_id)
);
```

Store snapshots at signal fire time. Link to `agent_signals.signal_id`.

When outcome is later marked WIN/LOSS, the chart snapshot + outcome = one labeled training example.

### Training data format (Phase B, 200+ outcomes)

Each row: `{signal_id, pair, direction, grade, score, h1_trend, session, killzone, news_safe, outcome, h1_image_b64, m15_image_b64}`

Feed to a fine-tuned vision classifier or use as context for a vision LLM that outputs a confidence score.

---

## What You Need Before Phase B Makes Sense

- **200+ labeled outcomes** (currently at ~27, need ~173 more)
- **Chart snapshots stored from now** — start capturing at signal fire time even before training
- **Consistent labeling** — W/L only, no NEUTRAL in training set

---

## NIM Vision Model

`nvidia/llama-3.2-90b-vision-instruct` — available on NIM, OpenAI-compatible, same API key.

Test call:
```python
from openai import OpenAI
client = OpenAI(base_url="https://integrate.api.nvidia.com/v1", api_key=NIM_API_KEY)
resp = client.chat.completions.create(
    model="nvidia/llama-3.2-90b-vision-instruct",
    messages=[{
        "role": "user",
        "content": [
            {"type": "text", "text": "Describe the market structure in this chart."},
            {"type": "image_url", "image_url": {"url": f"data:image/png;base64,{image_b64}"}}
        ]
    }],
    max_tokens=200
)
```

---

## Dependencies to add

```
mplfinance>=0.12.10b0   # chart rendering
matplotlib>=3.7.0       # already likely installed
```

---

## Priority Order

1. Build `chart_capture.py` first — test locally that it renders correctly
2. Wire into `/api/debate_signal` as optional (non-fatal if capture fails)
3. Add `chart_snapshots` table migration
4. Start capturing + storing on every agent signal (background, non-blocking)
5. Phase B training only after 200+ labeled outcomes

---

## Key constraint

Chart capture runs on Railway — must use OANDA API (already available), not TradingView screenshots. mplfinance renders from raw OANDA candle data. No browser automation needed.
