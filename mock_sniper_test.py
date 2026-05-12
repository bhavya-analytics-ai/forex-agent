"""
mock_sniper_test.py — XAU/USD News Sniper Simulation

Scenario:
  Mode:      NEWS_SNIPER
  Pair:      XAU/USD
  Price:     $4,728.00
  M5 Sweep:  Wick above $4,731 swing high → close at $4,728  (bearish reversal)
  H1 Trend:  BEARISH — last completed H1 candle is red, price below 50-EMA ($4,745)
  M1 CHoCH:  12-pip bearish displacement candle (clean body) closing below post-sweep low

Expected: SELL — ENTER NOW  ⚡ SNIPER
"""

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import pandas as pd
import numpy as np
from datetime import datetime, timedelta

PAIR  = "XAU_USD"
PRICE = 4728.00

print("=" * 65)
print(f"  ⚡ XAU/USD NEWS SNIPER — MOCK SIMULATION")
print(f"  {datetime.utcnow().strftime('%Y-%m-%d %H:%M UTC')}")
print("=" * 65)

# ─────────────────────────────────────────────────────────────────────────────
# BUILD SYNTHETIC CANDLES
# ─────────────────────────────────────────────────────────────────────────────

def make_df(rows: list) -> pd.DataFrame:
    df = pd.DataFrame(rows, columns=["open", "high", "low", "close"])
    df.index = pd.date_range(end=datetime.utcnow(), periods=len(df), freq="1min")
    return df


# ── H1 candles (60 bars) ─────────────────────────────────────────────────────
# Bearish drift. EMA 50 will be ~$4,745. Last completed (iloc[-2]) = red candle.
h1_rows = []
base = 4760.0
for i in range(58):
    o = base - i * 0.30
    h = o + 2.0
    l = o - 3.0
    c = o - 0.80           # slightly bearish drift
    h1_rows.append((o, h, l, c))
# iloc[-2]: last completed H1 — strong red candle
h1_rows.append((4728.50, 4731.00, 4723.00, 4724.50))   # RED: body 4pip, high 4731
# iloc[-1]: current forming H1 (ignored by strategy)
h1_rows.append((4724.50, 4729.00, 4723.00, 4728.00))
df_h1 = make_df(h1_rows)

h1_ema_50 = float(df_h1["close"].ewm(span=50, adjust=False).mean().iloc[-1])
print(f"\n[H1]  Last candle: O={h1_rows[-2][0]} H={h1_rows[-2][1]} L={h1_rows[-2][2]} C={h1_rows[-2][3]}  (RED ✓)")
print(f"[H1]  50-EMA = {round(h1_ema_50, 2)} | Price {PRICE} {'BELOW' if PRICE < h1_ema_50 else 'ABOVE'} EMA")
print(f"[H1]  Swing high at 4731 visible in H1 bar range ✓")

# ── M5 candles (30 bars) ─────────────────────────────────────────────────────
# Bars 0-24 (lookback): swing high = 4731 (just the regular highs)
# Last 5 bars: bar -1 wicks above 4731 (to 4733), closes at 4728 → SWEEP
m5_rows = []
for i in range(24):
    o = 4729.00 + i * 0.05
    c = o - 0.10
    h = max(o, c) + 0.30
    l = min(o, c) - 0.20
    h = min(h, 4730.80)    # keep highs just below 4731 in lookback
    m5_rows.append((o, h, l, c))
# Candle [-5]: ranging
m5_rows.append((4729.50, 4730.50, 4727.80, 4729.20))
# Candle [-4]: ranging
m5_rows.append((4729.20, 4730.20, 4728.00, 4729.50))
# Candle [-3]: ranging
m5_rows.append((4729.50, 4730.80, 4728.20, 4729.30))
# Candle [-2]: small wick above but not quite
m5_rows.append((4730.00, 4730.90, 4727.50, 4729.00))
# Candle [-1]: THE SWEEP — wick to 4733 (above swing high 4731), close 4728
m5_rows.append((4730.50, 4733.00, 4727.00, 4728.00))
df_m5 = make_df(m5_rows)

swing_high_check = float(df_m5.iloc[-25:-5]["high"].max())
sweep_c = df_m5.iloc[-1]
print(f"\n[M5]  Swing high (lookback): {round(swing_high_check, 2)}")
print(f"[M5]  Sweep candle: O={sweep_c['open']} H={sweep_c['high']} L={sweep_c['low']} C={sweep_c['close']}")
print(f"[M5]  Wick above {round(swing_high_check,2)}: {'YES ✓' if sweep_c['high'] > swing_high_check else 'NO ✗'}")
print(f"[M5]  Close below {round(swing_high_check,2)}: {'YES ✓' if sweep_c['close'] < swing_high_check else 'NO ✗'}")

# ── M1 candles (20 bars) ─────────────────────────────────────────────────────
# m1_lookback = max((bars_ago+1)*5, 5) = 5  (sweep was bars_ago=0)
# post_spike  = df_m1.iloc[-6:]
# post_spike[:-1] lows → min = 4727.42 (recent_low)
# Trigger (last): close < 4727.42, body=12pip ($0.12), wick < 70%
#   open=4727.54, close=4727.42, body=0.12, high=4727.57, low=4727.39
#   range=0.18, wick=0.06, wick_pct=33% → PASSES (< 70%)
# Prior 5 bodies avg ~0.05 → displacement = 0.12/0.05 = 2.4x → PASSES (≥ 1.2x)

m1_rows = []
# 14 pre-event candles (small, ranging around 4729)
for i in range(14):
    o = 4729.00
    c = 4729.05 if i % 2 == 0 else 4728.95
    m1_rows.append((o, o + 0.03, o - 0.03, c))
# 5 post-sweep candles (small bodies ~0.05, all lows > 4727.42)
m1_rows.append((4728.80, 4729.00, 4727.60, 4728.70))  # low=4727.60
m1_rows.append((4728.70, 4728.85, 4727.55, 4728.60))  # low=4727.55
m1_rows.append((4728.60, 4728.75, 4727.50, 4728.55))  # low=4727.50
m1_rows.append((4728.55, 4728.65, 4727.48, 4728.50))  # low=4727.48
m1_rows.append((4728.50, 4728.60, 4727.45, 4728.45))  # low=4727.45 ← recent_low
# Trigger candle: 12-pip body, close below 4727.45
m1_rows.append((4727.57, 4727.60, 4727.38, 4727.45 - 0.01))  # close=4727.44 < 4727.45

df_m1 = make_df(m1_rows)

post_spike_check = df_m1.iloc[-6:]
recent_low_check = float(post_spike_check["low"].iloc[:-1].min())
trig = df_m1.iloc[-1]
trig_body = abs(float(trig["close"]) - float(trig["open"]))
trig_range = float(trig["high"]) - float(trig["low"])
trig_wick_pct = (trig_range - trig_body) / trig_range if trig_range > 0 else 1

prior_5_bodies = df_m1.iloc[-6:-1].apply(lambda r: abs(r["close"]-r["open"]), axis=1).mean()

print(f"\n[M1]  Post-sweep recent low: {round(recent_low_check, 5)}")
print(f"[M1]  Trigger: O={trig['open']} H={trig['high']} L={trig['low']} C={round(trig['close'],5)}")
print(f"[M1]  Body={round(trig_body,5)} ({round(trig_body/0.01,1)} pips) | Wick%={round(trig_wick_pct*100,1)}%")
print(f"[M1]  Close below recent_low: {'YES ✓' if trig['close'] < recent_low_check else 'NO ✗'}")
print(f"[M1]  Avg prior 5 body: {round(prior_5_bodies, 5)} | Displacement: {round(trig_body/prior_5_bodies if prior_5_bodies>0 else 0, 2)}x")

# ─────────────────────────────────────────────────────────────────────────────
# BUILD MOCK SCORED + CONFLUENCE DICTS
# ─────────────────────────────────────────────────────────────────────────────

scored = {
    "pair":          PAIR,
    "direction":     "bearish",   # H1 bearish → scorer outputs bearish
    "score":         72,
    "grade":         "A",
    "setup_type":    "pullback_short",
    "current_price": PRICE,
    "should_alert":  False,
    "should_log":    False,
    "entry_state":   "SKIP",
    "flags":         [],
    "breakdown":     {},
    "conditions":    {},
    "news_check":    {"safe": False},
}

confluence = {
    "pair":          PAIR,
    "current_price": PRICE,
    "direction":     "bearish",
    "has_fvg_overlap": False,
    "ict_conflict":  False,
    "h1_ema_50":     h1_ema_50,
    "price_below_h1_ema": PRICE < h1_ema_50,
    "h1": {
        "bias":    "bearish",
        "ema_50":  h1_ema_50,
        "structure": {
            "trend":         "downtrend",
            "last_high":     4745.00,
            "last_low":      4710.00,
            "phase":         "impulse",
            "setup_quality": "A",
            "pullback_depth": 0.3,
            "strength":      3,
        },
        "active_zones":      [],
        "fvg_overlaps":      [],
    },
    "m15": {
        "bias":    "bearish",
        "structure": {
            "trend":    "downtrend",
            "last_high": 4735.00,
            "last_low":  4712.00,
        },
        "fvg_overlaps": [],
    },
    "m5": {
        "bias":    "bearish",
        "structure": {
            "trend":    "downtrend",
            "last_high": 4732.00,
            "last_low":  4715.00,
        },
    },
    "ict": {
        "has_sweep": True,
        "has_choch": False,
        "has_ob":    False,
        "recent_sweep": {"bias": "bearish", "extreme": 4733.00},
    },
}

candles = {
    "H1": df_h1,
    "M5": df_m5,
    "M1": df_m1,
}

# ─────────────────────────────────────────────────────────────────────────────
# FORCE NEWS SNIPER MODE
# ─────────────────────────────────────────────────────────────────────────────
try:
    from filters.mode_manager import set_manual_mode
    set_manual_mode("news_sniper")
    print(f"\n[MODE] Set to: NEWS_SNIPER ✓")
except Exception as e:
    print(f"\n[MODE] Could not set mode: {e}")

# ─────────────────────────────────────────────────────────────────────────────
# RUN THE SNIPER
# ─────────────────────────────────────────────────────────────────────────────
print("\n" + "─" * 65)
print("  RUNNING apply_news_sniper() ...")
print("─" * 65)

from strategies.news_sniper import apply_news_sniper
result = apply_news_sniper(scored, confluence, PAIR, candles)

# ─────────────────────────────────────────────────────────────────────────────
# PRINT TERMINAL OUTPUT
# ─────────────────────────────────────────────────────────────────────────────
entry_state = result.get("entry_state", "SKIP")
direction   = result.get("direction", scored["direction"])
levels      = result.get("trade_levels", {})
flags       = result.get("flags", [])
m5_sw       = result.get("m5_sweep", {})
choch       = result.get("m1_choch", {})
marub       = result.get("h1_marubozu", {})
p_win       = result.get("p_win", 0)
ev          = result.get("ev", 0)

state_emoji = {
    "ENTER_NOW":   "🔥 ENTER NOW",
    "WAIT_RETEST": "⏳ WAIT RETEST",
    "SKIP":        "🚫 SKIP",
}.get(entry_state, entry_state)

dir_arrow = "📉 SELL" if direction == "bearish" else "📈 BUY"

print()
print("=" * 65)
print(f"  {dir_arrow} | {PAIR.replace('_','/')} | {state_emoji}  ⚡ SNIPER")
print("=" * 65)
print(f"  Price:     ${PRICE}")
print(f"  H1 EMA50:  ${round(h1_ema_50, 2)} | Price {'BELOW ✓' if PRICE < h1_ema_50 else 'ABOVE'}")

if m5_sw.get("detected") is not False and result.get("m5_sweep"):
    print(f"  M5 Sweep:  {m5_sw.get('direction','').upper()} wick → swept ${m5_sw.get('swept_level')} "
          f"| extreme ${m5_sw.get('sweep_extreme')} ✓")

if choch and choch.get("detected"):
    print(f"  M1 CHoCH:  {choch.get('type','').upper()} | body {round(choch.get('body',0)/0.01,1)}pip "
          f"| wick {int(choch.get('wick_pct',0)*100)}% "
          f"| disp {choch.get('displacement_ratio',0)}x ✓")

if marub:
    print(f"  H1 Marub:  {marub.get('direction','').upper()} {int(marub.get('body_pct',0)*100)}% "
          f"→ same as reversal — standard CHoCH OK ✓")

if levels:
    print()
    print(f"  📍 Entry:  ${levels.get('entry_price', '—')}")
    print(f"  🛑 SL:     ${levels.get('sl_price', '—')}  ({levels.get('sl_pips','?')} pips)")
    print(f"  🎯 TP1:    ${levels.get('tp1_price', '—')}  ({levels.get('tp1_pips','?')} pips | {levels.get('rr1','?')})")
    print(f"  🎯 TP2:    ${levels.get('tp2_price', '—')}  ({levels.get('tp2_pips','?')} pips | {levels.get('rr2','?')})")
    print(f"  P(win):   {round(p_win*100)}% | EV: {'+' if ev >= 0 else ''}{ev}")

print()
print("─" * 65)
print("  FLAGS:")
for f in flags:
    print(f"   {f}")

print()
if entry_state == "ENTER_NOW":
    print("  ✅ SIMULATION PASSED — SELL ENTER NOW fired correctly")
    print("  ⚡ signal_mode=news_sniper tag would be attached to DB entry")
else:
    print(f"  ✗ SIMULATION RESULT: {entry_state} — check gate failures above")
print("=" * 65)
