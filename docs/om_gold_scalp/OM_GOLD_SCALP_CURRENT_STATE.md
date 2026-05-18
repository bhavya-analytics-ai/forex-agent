# OM Gold Scalp — Current State Handoff

_Last updated: 2026-05-18 | commit 252fa6b_

---

## Status: Watch-Only. Not live. No DB writes. No Slack.

---

## Phase Progress

### Phase 0 — Strategy + Tests (commit db2ddfa) ✅
- `strategies/om_gold_scalp.py` created (XAU_USD only)
- `tests/test_om_gold_scalp.py` created — 37 tests, all passing
- Key fix: `_detect_sweep()` rewritten with rolling-prior approach — each candidate bar's reference extreme is computed from `bars[:i]` only, never including the candidate itself
- Key fix: `_detect_reclaim()` open-price restriction removed
- Key fix: chase check moved before SL calculation in sweep_reclaim_long path

### Phase 1 — Multi-Strategy Runner (commits edf9fec + abb0e95) ✅
- `strategies/runner.py` created
- `run_extra_strategies(scored, confluence, pair, candles)` runs OM in parallel
- Primary `scored` is never mutated — OM returns independent dict
- `dashboard/app.py`: `_extra_store` added, `/api/signals/extra` endpoint added
- `briefing.py`: extra candidates pushed to dashboard after each scan
- Two-gate enforcement: `OM_STRATEGY_ENABLED` (global) AND `OM_GOLD_SCALP_ENABLED` (per-strategy) — both must be True for any live output
- DataFrame hotfix: `_df_to_list()` + `_normalise_candles()` in runner — production `fetch_all_timeframes()` returns DataFrames, strategy expects list-of-dicts
- Verified on Railway: OM computes state, `should_log=False`, `should_alert=False`, 0 DB rows, 0 Slack

### Momentum Gate Patch (commit 252fa6b) ✅
- `MIN_MOMENTUM_REQUIRED = 50.0` added to thresholds block
- `momentum_score` now computed **before** `ENTER_NOW` is set (was after)
- Gate enforced in all three ENTER_NOW paths:
  - `sweep_reclaim_long`
  - `failed_reclaim_continuation`
  - `range_breakdown_bearish`
- Logic:
  - `momentum_score < 50` → `entry_state = "WAIT_MOMENTUM"`, `skip_reason = "low_momentum"`
  - H1 directionally opposing entry AND `momentum_score < 35` → `entry_state = "SKIP"`, `skip_reason = "opposing_h1_low_momentum"`
  - Both pass → `momentum_gate_passed = True`, ENTER_NOW proceeds
- New audit fields on every output: `min_momentum_required` (50), `momentum_gate_passed` (bool)
- Test suite: 54/54 passing (37 original + 3 momentum gate + 14 runner)
- Deployed watch-only. No env changes. No DB writes. No Slack.

---

## Key Files

| File | Role |
|---|---|
| `strategies/om_gold_scalp.py` | Full strategy: H1 analysis → sweep/reclaim/displacement → momentum gate → ENTER_NOW |
| `strategies/runner.py` | Parallel runner, DataFrame normalisation, two-gate enforcement |
| `tests/test_om_gold_scalp.py` | 40 unit tests (37 + 3 momentum gate) |
| `tests/test_multi_strategy_runner.py` | 14 runner isolation tests |
| `reports/briefing.py` | Wires extra candidates into scan pipeline |
| `dashboard/app.py` | `_extra_store`, `/api/signals/extra` endpoint |

---

## Thresholds

| Constant | Value | Meaning |
|---|---|---|
| `MAX_SL_PTS` | 20 | SL > 20 pts → SKIP sl_too_wide |
| `SL_BUFFER_PTS` | 2 | Sweep extreme ± 2 pts |
| `MAX_CHASE_PTS` | 25 | Entry > 25 pts from zone → SKIP_CHASE |
| `TP1_MIN_PTS` | 15 | Minimum TP1 |
| `TP1_MAX_PTS` | 25 | Maximum TP1 |
| `MIN_RR` | 1.5 | Minimum risk/reward |
| `SWEEP_MIN_WICK_PTS` | 1.5 | Wick must extend 1.5 pts beyond prior swing |
| `SWEEP_MAX_BARS_AGO` | 20 | Sweep must be within last 20 M5 bars |
| `DISPLACE_MIN_MULT` | 1.5 | Displacement body >= 1.5× avg body |
| `MIN_MOMENTUM_REQUIRED` | 50 | momentum_score must reach 50 before ENTER_NOW |

---

## State Machine

```
XAU_USD only
  → H1 analysis (zone map + bias)
  → Gate 1: HTF range chop?
      yes → check fake_breakout → SKIP_INSIDE_RANGE
           → check range_breakdown → [momentum gate] → ENTER_NOW short / WAIT_MOMENTUM
           → else SKIP_CHOP
  → Gate 2: bearish sweep detected?
      no reclaim → WAIT_REACTION
      reclaim, no displacement → WAIT_HOLD
      reclaim + displacement → [momentum gate] → ENTER_NOW long / WAIT_MOMENTUM / SKIP
  → Gate 3: bullish sweep → failed reclaim?
      failed + displacement → [momentum gate] → ENTER_NOW short / WAIT_MOMENTUM / SKIP
      else → WAIT_REACTION
  → fallthrough → SKIP (no_setup)
```

---

## Momentum Score Components

| Component | Max pts | Condition |
|---|---|---|
| M5 pressure | 35 | M5 trend aligned with direction |
| Displacement strength | 25 | body/avg ratio >= 3.0× (18 for 2.0×, 10 for 1.5×) |
| M15 alignment | 25 | M15 trend aligned with direction |
| M1 placeholder | 7 | Always added (partial, future expansion) |

Total max: 92. Threshold for ENTER_NOW: 50. Hard skip (opposing H1): 35.

---

## Next Steps

1. Observe `/api/signals/extra` for 1–2 days watch-only.
2. Confirm `WAIT_MOMENTUM` entries appear instead of `ENTER_NOW` for low-momentum setups.
3. Do NOT enable `OM_GOLD_SCALP_ENABLED=true` or `OM_STRATEGY_ENABLED=true` until reviewed.
4. If output quality looks correct → next phase is live enable + DB write wiring.
5. If output looks wrong → relabel screenshots with ChatGPT-assisted annotations.

---

## v1 Setup Categories (5 of 10 implemented)

| Setup | Status |
|---|---|
| sweep_reclaim_long | ✅ |
| sweep_reclaim_short | planned |
| failed_reclaim_continuation | ✅ |
| range_breakdown_bearish | ✅ |
| range_fake_breakout_no_trade | ✅ |
| (5 more) | planned |
