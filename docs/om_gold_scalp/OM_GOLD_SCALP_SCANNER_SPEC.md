# OM Gold Scalp — Scanner Implementation Spec

> Extracted from 45 screenshot calibration examples in `OM_GOLD_SCALP_RULEBOOK.md`.
> All rules marked PROPOSED here. Om must approve section by section before any code is written.
> No code exists yet. This spec is the bridge between the rulebook and `strategies/om_gold_scalp.py`.

**Status:** Draft — awaiting Om approval
**Source:** `docs/om_gold_scalp/OM_GOLD_SCALP_RULEBOOK.md` (45 examples, calibration complete)
**Target file:** `strategies/om_gold_scalp.py` (does not exist yet)
**Signal mode:** `om_gold_scalp`
**Pair:** `XAU_USD` only

---

## 1. Setup Categories

Ten distinct setup categories extracted from the 45 examples. Each maps to a named `setup_type` field in the audit output. The scanner evaluates all categories per scan and returns the highest-confidence one that passes the entry gate.

| # | setup_type | Direction | Core condition |
|---|---|---|---|
| 1 | `sweep_reclaim_long` | Long | Liquidity sweep downside + reclaim confirmed + bullish displacement |
| 2 | `sweep_reclaim_short` | Short | Liquidity sweep upside + rejection + bearish displacement |
| 3 | `failed_reclaim_continuation` | With prior breakout | Reclaim attempt fails → continuation in breakout direction |
| 4 | `range_breakdown_bearish` | Short | HTF range low breaks + retest holds below + follow-through |
| 5 | `range_breakout_bullish` | Long | HTF range high breaks + retest holds above + follow-through |
| 6 | `htf_range_no_trade` | None | Price inside HTF range, no clean boundary event |
| 7 | `news_displacement_continuation` | With displacement | News impulse + 3-candle continuation OR failed reclaim |
| 8 | `impulse_exhaustion_reversal` | Against prior impulse | Impulse into liquidity target + consolidation + failed push |
| 9 | `sr_reclaim_candidate` | Long or Short | Price pushes back into key S/R; progressive state detection |
| 10 | `range_fake_breakout_no_trade` | None | Breakout above/below range that reclaims back inside |

**Educational negative examples** (from rulebook): scenarios where the scanner explicitly fires `SKIP_*` with a logged `skip_reason`. The scanner must log these, not just silently pass. Examples 044, parts of 032–033, 036–037.

---

## 2. Scanner State Flow

The scanner uses a **progressive state machine** per scan cycle, not a binary signal. Each setup progresses through these states in order — skipping states is not permitted.

### Global state machine

```
SKIP_CHOP           — inside HTF range or chop, no boundary event
WAIT_REACTION       — boundary touch or setup beginning, watching
WAIT_RECLAIM        — price below/above S/R, waiting for push back
WAIT_HOLD           — reclaim body close printed, waiting for hold bar
ENTER_LONG_ALLOWED  — all conditions met for long
ENTER_SHORT_ALLOWED — all conditions met for short
SKIP_CHASE          — direction correct but entry is too far from zone
```

### Per-setup state flows

**Sweep + reclaim (long):**
`WAIT_REACTION` (sweep printing) → `WAIT_HOLD` (reclaim body close) → `ENTER_LONG_ALLOWED` (displacement + structure shift)

**Failed reclaim (continuation short):**
`WAIT_REACTION` (sweep candidate / bounce printing) → `WAIT_REACTION` (reclaim attempt in progress) → `ENTER_SHORT_ALLOWED` (reclaim fails + bearish displacement)

**HTF range no-trade:**
`SKIP_CHOP` (default while inside range) → `WAIT_REACTION` (range boundary broken) → `WAIT_HOLD` (retest of broken boundary) → `ENTER_*_ALLOWED` (hold confirmed + follow-through)

**S/R reclaim candidate (progressive):**
`WAIT_RECLAIM` (price below S/R) → `WAIT_HOLD` (body close above S/R) → `ENTER_LONG_ALLOWED` (hold bar + displacement)

**News displacement:**
`WAIT_REACTION` (news candle printed — no entry) → `WAIT_REACTION` (waiting for 3-candle continuation OR failed reclaim) → `ENTER_*_ALLOWED` (confirmation complete)

**Impulse exhaustion:**
Long bias active → `WAIT_REACTION` (approach into upper liquidity) → `WAIT_REACTION` (consolidation at top) → `ENTER_SHORT_ALLOWED` (failed push higher + displacement down)

---

## 3. Decision Tree — Entry State Assignment

The scanner returns one of four top-level entry states per scan. These map directly to the existing `entry_state` field used by the rest of the system.

```
ENTER_NOW     ← maps to ENTER_LONG_ALLOWED or ENTER_SHORT_ALLOWED
WAIT_RETEST   ← maps to WAIT_REACTION or WAIT_HOLD
SKIP          ← maps to SKIP_CHOP, no_trade_zone, or no setup
SKIP_CHASE    ← direction correct but entry too far from zone
```

### Full decision logic (in evaluation order)

```
1. Is htf_range_active = true AND price inside [range_boundary_low, range_boundary_high]?
   → SKIP (SKIP_CHOP, skip_reason = inside_range_chop)

2. Is no_trade_zone = true (fake breakout returned inside range)?
   → SKIP (SKIP_CHOP, skip_reason = inside_range_chop OR fake_breakout_no_trade)

3. Is news_impulse = true AND confirmation_signal = none?
   → WAIT_RETEST (WAIT_REACTION, awaiting 3-candle continuation or failed reclaim)

4. Is consolidation_after_impulse = true AND long_bias_exit = true?
   → WAIT_RETEST (WAIT_REACTION, awaiting range resolution)

5. Is reclaim_candidate = true AND reclaim_confirmed = false?
   → WAIT_RETEST (WAIT_RECLAIM)

6. Is reclaim_confirmed = true AND (bullish_displacement = false AND bearish_displacement = false)?
   → WAIT_RETEST (WAIT_HOLD — hold confirmed, waiting for displacement)

7. Is failed_bullish_reversal = true AND bearish_displacement_after_failed_reclaim = true?
   → ENTER_NOW (short) — if entry distance within max_chase_pts

8. Is sweep_reclaim_confirmed (single or double) = true AND bullish_displacement = true?
   → ENTER_NOW (long) — if entry distance within max_chase_pts

9. Is range_low_broken = true AND range_retest_held_below = true AND bearish_follow_through = true?
   → ENTER_NOW (short) — if entry distance within max_chase_pts

10. Is range_high_broken = true AND range_retest_held_above = true AND bullish_follow_through = true?
    → ENTER_NOW (long) — if entry distance within max_chase_pts

11. Is entry_distance > max_chase_pts?
    → SKIP_CHASE (direction may be correct but R:R is poor)

12. No conditions above met:
    → SKIP (no_setup)
```

---

## 4. Required Audit Fields

All fields below must be written to the `breakdown` JSON column in `agent_signals` for every OM Gold Scalp signal (including skips). The scanner cannot skip-log a signal without writing `skip_reason`.

### Zone context
| Field | Type | Source |
|---|---|---|
| `htf_zone_map` | list | 1H zone detection |
| `htf_magnet` | float | Active 1H target level |
| `zone_state` | enum | See Section 6 |
| `htf_zone_type` | enum | purple_zone / sr_band / fvg / order_block |
| `decision_zone` | bool | Mixed reactions at zone |
| `key_sr_level` | bool | Zone is key S/R |

### Range state
| Field | Type | Source |
|---|---|---|
| `htf_range_active` | bool | Wide range detection |
| `range_boundary_high` | float | Upper range edge |
| `range_boundary_low` | float | Lower range edge |
| `no_trade_zone` | bool | Inside range flag |
| `inside_range_chop` | bool | Price oscillating inside |
| `range_high_swept` | bool | Fake breakout above range |
| `breakout_failed` | bool | Breakout body close failed |
| `reclaim_back_inside_range` | bool | Returned inside after breakout |
| `range_low_broken` | bool | Body close below range |
| `range_retest_held_below` | bool | Retest holds as resistance |
| `boundary_break_required` | bool | Gate still open |

### Sweep state
| Field | Type | Source |
|---|---|---|
| `liquidity_sweep_count` | int | Number of sweeps at same level |
| `double_sweep` | bool | ≥ 2 sweeps at same level |
| `swept_side` | enum | bearish / bullish |
| `sweep_candidate` | bool | Sweep seen, outcome pending |
| `sweep_alone_no_entry` | bool | Always true during sweep bar |
| `entry_after_reclaim_only` | bool | Gate enforcement |

### Reclaim state
| Field | Type | Source |
|---|---|---|
| `reclaim_candidate` | bool | Push back into level, no body close yet |
| `reclaim_attempt` | bool | Actively pushing through level |
| `reclaim_confirmed` | bool | Body close + hold above/below |
| `reclaim_failed` | bool | Body close could not hold |
| `reclaim_direction` | enum | bullish / bearish |
| `hold_above_sr_required` | bool | Gate: hold bar must print |
| `weak_reclaim` | bool | Partial close, not clean |

### Displacement + structure
| Field | Type | Source |
|---|---|---|
| `bullish_displacement` | bool | Large bullish body after reclaim |
| `bearish_displacement_after_failed_reclaim` | bool | Large bearish body after failed reclaim |
| `structure_shift_after_sweep` | bool | Higher low / lower high post-sweep |
| `three_candle_continuation` | bool | 3 consecutive bars extend displacement |
| `follow_through_confirmed` | bool | Next bar extends in setup direction |
| `failed_push_higher` | bool | Consolidation range exit down, no new high |
| `failed_push_lower` | bool | Mirror for bearish impulses |
| `slow_level_fill` | bool | Continuation is low-momentum but valid |

### Reversal / continuation classification
| Field | Type | Source |
|---|---|---|
| `failed_bullish_reversal` | bool | Reclaim attempt + reclaim failed together |
| `bearish_continuation_valid` | bool | All short conditions met |
| `bullish_continuation_valid` | bool | All long conditions met |
| `long_bias_after_reclaim` | bool | Swept bearish + reclaim confirmed + displacement |
| `long_trigger_after_reclaim` | bool | Full 5M long trigger armed |
| `broken_support_context` | bool | Prior support break still active |
| `countertrend_green_attempt` | bool | Green bar into broken level in bearish context |
| `bullish_pullback_failed` | bool | Countertrend green + lower/equal high |
| `bearish_context_preserved` | bool | No higher high, below EMA 200 |
| `continuation_short_valid` | bool | Short continuation entry armed |

### Impulse exhaustion
| Field | Type | Source |
|---|---|---|
| `clean_bullish_impulse` | bool | Impulse has room and structure |
| `impulse_origin` | float | Start level of impulse |
| `upper_liquidity_target` | float | Prior high / upper pool |
| `top_sweep_or_exhaustion` | enum | sweep / exhaustion / both / none |
| `consolidation_after_impulse` | bool | Small bodies + overlap at top |
| `long_bias_exit` | bool | Long bias retired at top |
| `late_long_risk` | bool | Entry far from origin |

### News / displacement
| Field | Type | Source |
|---|---|---|
| `news_impulse` | bool | Displacement candle detected |
| `displacement_source` | enum | news / liquidity / unknown |
| `confirmation_signal` | enum | three_candle_continuation / failed_reclaim / none |
| `bias_flip_event` | bool | Reclaim invalidates prior phase |

### Decision zone
| Field | Type | Source |
|---|---|---|
| `consolidation_at_zone` | bool | Multiple bars overlapping at zone |
| `liquidity_sweep_before_move` | bool | Sweep precedes directional move |
| `failed_support_hold` | bool | Previously respected support broke |
| `support2_magnet` | bool | Next lower HTF zone is active target |
| `middle_range_risk` | bool | Entry between two clean signatures |

### Entry quality + skip classification
| Field | Type | Source |
|---|---|---|
| `entry_quality` | enum | high / medium / low |
| `entry_allowed` | bool | Master gate field |
| `skip_reason` | enum | See Section 10 |
| `avoid_long_reason` | enum | reclaim_failed / failed_breakout_back_inside_range / no_reclaim_hold |
| `avoid_short_reason` | enum | still_inside_range_until_low_break_hold |
| `candle_strength_mismatch` | bool | Calibration: appearance ≠ structure |
| `scanner_state_flow` | string | Human-readable progression |
| `exit_reason` | enum | Why a trade was/should be closed |
| `htf_context_id` | int | Paired context example reference |
| `execution_pair_id` | string | e.g. "042_043" |
| `paired_context_id` | int | LTF → HTF cross-reference |

### Support/resistance zone tests
| Field | Type | Source |
|---|---|---|
| `zone_tests_count` | int | Touch count at zone |
| `zone_strength_decay` | bool | ≥ 3 tests = weakened |
| `zone_role_flip` | bool | Old support now resistance |
| `support_hold_failed` | bool | Prior respected support broke |
| `continuation_entry` | bool | All confirmation conditions met |

### S/R reclaim candidate (progressive)
| Field | Type | Source |
|---|---|---|
| `price_below_sr` | bool | Below level, long suppressed |
| `bearish_pressure_below_sr` | bool | Bearish bias below level |
| `potential_long_setup` | bool | Watching for reclaim |
| `enter_long_only_after_confirmation` | bool | Gate enforcement |

---

## 5. Timeframe Role Definitions

### 1H — Zone map and bias layer

**Purpose:** Define the battlefield. Set directional magnets. Never generate entries.

**What 1H computes:**
- Active S/R zones and purple HTF zones (type, price, strength, test count)
- `htf_zone_map` — ordered list of all active zones
- `htf_magnet` — current directional target (next meaningful level in bias direction)
- `zone_state` per active zone (see Section 6)
- HTF trend direction (bearish / bullish / chop)
- Whether price is inside an HTF range (`htf_range_active`)
- `zone_tests_count` per zone (≥ 3 = `zone_strength_decay = true`)
- `zone_role_flip` when broken support is now acting as resistance

**1H outputs to 15M:** bias direction, htf_magnet, active zones, htf_range state

**1H never:** generates `ENTER_NOW`, sets trade levels, fires alerts

### 15M — Setup location and context layer

**Purpose:** Confirm whether a valid setup is forming in the right location. Narrow the 1H bias to a specific area. Never trigger entries directly.

**What 15M computes:**
- Zone state at 15M resolution (is price near the 1H zone? Inside it? Breaking it?)
- `decision_zone` — mixed reactions at zone (consolidation, both sides tested)
- `consolidation_at_zone` — multiple bars overlapping inside the zone
- `htf_range_active` at 15M if a 15M-scale range is visible
- `failed_support_hold` / `support2_magnet` (range-break context)
- Setup classification: sweep candidate, reclaim attempt, impulse, exhaustion, chop
- `news_impulse` detection on 15M (displacement candle)
- `top_sweep_or_exhaustion` (impulse near prior high)
- `long_bias_exit` (consolidation at top armed)

**15M outputs to 5M:** setup_type candidate, zone_state, htf_magnet, range state, confirmation gates

**15M never:** generates `ENTER_NOW`, sets trade levels

### 5M — Trigger and execution layer

**Purpose:** Identify the precise entry candle. Apply confirmation gates. Arm `ENTER_NOW` only when all conditions from 1H + 15M + 5M align.

**What 5M computes:**
- Sweep detection: wick beyond level, body close back inside (`reclaim_candidate`)
- Reclaim confirmation: body close + hold bar (`reclaim_confirmed`)
- Displacement detection: body size, overlap, directionality
- Failed reclaim: body close back through level (`reclaim_failed`)
- `structure_shift_after_sweep`: higher low or lower high after reclaim
- `three_candle_continuation` after news displacement
- `range_retest_held_below/above`
- Entry state assignment (ENTER_NOW / WAIT_RETEST / SKIP / SKIP_CHASE)
- Trade levels: entry price, SL (sweep extreme + 2 pts), TP1 (15–25 pts), TP2 (up to 30 pts)
- `momentum_score` (4-component, 0–100 scale — see Section 5 notes below)
- EMA 200 relation (`above_ema200` / `below_ema200`)

**5M outputs:** entry_state, trade_levels, all audit fields, signal for logging gate

**Trade level method:**
- **Entry:** displacement candle close OR retest hold candle close (whichever fires the state gate)
- **SL:** sweep wick extreme (most extreme point of sweep) + 2 pts buffer. Hard max: 20 pts. If SL > 20 pts → SKIP.
- **TP1:** min 1:1.5 RR, target 15–25 pts
- **TP2:** up to 30 pts, only if 1H magnet is in that range
- **Minimum SL:** 150 pips (= 1.50 pts for XAU at pip_size 0.01). Enforced by existing quality gate.

**Momentum score components (PROPOSED — weights to be calibrated):**
- M5 pressure (trend alignment): 35 pts
- Displacement strength (body size vs ATR): 25 pts
- M1 alignment (optional): 25 pts
- M1 EMA slope: 15 pts

### 1M — Optional precision execution layer

**Purpose:** Tighten entry timing after 5M trigger is armed. Not required for signal to log. Used when Om wants to wait for the cleanest possible candle close within a 5M-triggered setup.

**What 1M adds (optional):**
- Confirmation candle: does the 1M candle close confirm the direction?
- Early vs late: is the 1M entry still near the reclaim level or already displaced?
- `recency_gate`: sweep candle age on 1M — if > 5 bars old, flag as potentially late

**1M never:** overrides a 5M signal, generates signals independently

---

## 6. Zone State Enum

Used in `zone_state` audit field. One value per active zone per scan.

| Value | Meaning |
|---|---|
| `above_zone` | Price above the zone, zone is support below |
| `below_zone` | Price below the zone, zone is resistance above |
| `inside_zone` | Price body inside the zone |
| `holding_support` | Price repeatedly holding above zone lower edge |
| `rejecting_resistance` | Price repeatedly rejecting at zone upper edge |
| `broken_support` | Body close below zone; support no longer holding |
| `broken_resistance` | Body close above zone; resistance no longer holding |
| `underside_retest` | Price returned to broken support from below |
| `topside_retest` | Price returned to broken resistance from above |
| `reclaimed_zone` | Body close back inside/above after break + hold |
| `failed_reclaim` | Retest body close could not hold; continuation direction confirmed |
| `decision_chop` | Mixed tests on both sides, no directional resolution |
| `inside_range_chop` | HTF range active; price oscillating inside |
| `liquidity_sweep` | Wick took prior extreme; body returned inside |

---

## 7. Setup Action Enum

Returned as `setup_action` or maps to `entry_state`.

| Value | Entry state maps to | Meaning |
|---|---|---|
| `ENTER_NOW` | `ENTER_NOW` | All conditions met; entry armed |
| `WAIT_RETEST` | `WAIT_RETEST` | Partial confirmation; watching |
| `WAIT_RECLAIM` | `WAIT_RETEST` | Price below/above S/R; push back expected |
| `WAIT_HOLD` | `WAIT_RETEST` | Reclaim body close printed; waiting for hold bar |
| `WAIT_REACTION` | `WAIT_RETEST` | Boundary event or sweep; watching for outcome |
| `SKIP_CHOP` | `SKIP` | Inside range/chop, no signature |
| `SKIP_CHASE` | `SKIP` | Direction correct but entry too far from origin |
| `SKIP_INSIDE_RANGE` | `SKIP` | Fake breakout returned inside range; both sides blocked |

---

## 8. News / Displacement Handling

**Detection (on 15M and 5M):**
- A news/displacement candle is identified by: body size > 2× recent average body size AND occurs within 30 min of a HIGH-impact news event (cross-referenced with existing `filters/news.py` events).
- If news proximity cannot be determined: classify as `displacement_source = liquidity`, not `news`.

**State on detection:**
- `news_impulse = true` → `setup_action = WAIT_REACTION`
- `ENTER_NOW` is blocked on the displacement candle itself, regardless of size or direction.

**Confirmation options (both valid):**
1. `three_candle_continuation = true` — 3 consecutive bars extending the displacement without a close against the direction
2. `failed_reclaim = true` — price retests prior level from the new side and body close fails to re-enter → continuation short/long valid

**Bias flip:**
- If price reclaims back across the displacement origin AND holds: `bias_flip_event = true`, prior displacement bias cancelled.
- This is the same reclaim logic applied to the displacement level.

**Penalty approach (matches existing spec):**
- News window penalties apply to scoring (−15 to −20 pts) but are not hard blocks for om_gold_scalp, unlike other strategy streams.
- The `news_impulse` confirmation gate is the primary safety mechanism.

---

## 9. No-Trade / Range / Chop Handling

### HTF range active (`htf_range_active = true`)

**Default state:** `SKIP_CHOP`, `skip_reason = inside_range_chop`

**Override conditions (two valid resolution paths only):**

Path 1 — Breakdown:
```
range_low_broken = true          (body close below range_boundary_low)
→ WAIT_REACTION
→ range_retest_held_below = true (retest of range low holds as resistance)
→ WAIT_HOLD
→ bearish_follow_through = true  (next bar extends lower)
→ ENTER_NOW (short)
```

Path 2 — Breakout:
```
range_high_broken = true         (body close above range_boundary_high)
→ WAIT_REACTION
→ range_retest_held_above = true (retest of range high holds as support)
→ WAIT_HOLD
→ bullish_follow_through = true  (next bar extends higher)
→ ENTER_NOW (long)
```

**Fake breakout handling:**
- Breakout above/below range + body returns inside within 1–2 bars: `breakout_failed = true`, `reclaim_back_inside_range = true`
- Result: `scanner_action = SKIP_INSIDE_RANGE`, `entry_allowed = false` for BOTH directions
- `avoid_long_reason = failed_breakout_back_inside_range`
- `avoid_short_reason = still_inside_range_until_low_break_hold`

### Middle-of-range risk

- Entry between two clean zone signatures: `middle_range_risk = true`
- Logged as `skip_reason = mid_range_no_confirmation`, not silently dropped.
- `entry_quality = low` auto-assigned.

### Decision zone / consolidation

- `decision_zone = true` + `consolidation_at_zone = true` → `WAIT_REACTION`
- No entry until one of the two clean signatures fires: sweep+reclaim+follow-through OR break+failed-reclaim+continuation.

### Chase filter

- `max_chase_pts = 25` — if entry would be more than 25 pts from the origin level or zone: `SKIP_CHASE`
- `reaction_zone_distance_pts = 8` — retest must be within 8 pts of the broken level to count as a retest
- `near_zone_distance_pts = 5` — price within 5 pts of zone edge: `SKIP_NEAR_ZONE` (not the right time to enter, too close without reaction)

---

## 10. Skip Reason Enum

Every SKIP must include a `skip_reason`. The scanner never drops a signal silently.

| skip_reason | When applied |
|---|---|
| `inside_range_chop` | `htf_range_active = true` + price inside bounds |
| `fake_breakout_no_trade` | Breakout failed + reclaim back inside range |
| `mid_range_no_confirmation` | Entry between two zone signatures |
| `news_impulse_no_confirmation` | News candle printed; waiting for continuation |
| `consolidation_no_signature` | Decision zone + consolidation, no resolution |
| `reclaim_not_confirmed` | Push back into level but no body close hold |
| `chase_distance` | Entry > `max_chase_pts` from origin |
| `sl_too_wide` | SL > 20 pts max (also caught by quality gate) |
| `no_sweep_signature` | No sweep detected at any active zone |
| `impulse_exhaustion_wait` | Impulse at top; consolidation phase, no entry |
| `avoid_long_failed_breakout` | Long blocked after breakout failed + inside range |
| `avoid_short_inside_range` | Short blocked; still inside range, low not broken |
| `no_setup` | No conditions match any category |

---

## 11. Files Likely Needing Changes

Listed in the order they would be touched during implementation. No changes made yet.

| File | Change type | Reason |
|---|---|---|
| `strategies/om_gold_scalp.py` | **CREATE** | New strategy stream — does not exist |
| `filters/mode_manager.py` | **MODIFY** | Route `om_gold_scalp` mode to new strategy file |
| `alerts/scorer.py` | **MODIFY** | Add momentum_score computation for om_gold_scalp; keep isolated from other streams |
| `alerts/logger.py` | **MODIFY** | Add `om_gold_scalp` to dedup fingerprint handling; add `signal_mode` filter |
| `db/database.py` | **MODIFY** | Confirm `breakdown` JSON column can store all new audit fields; add migration if needed |
| `reports/briefing.py` | **MODIFY** | Extend logging gate: om_gold_scalp uses `entry_state == ENTER_NOW` gate (same as gold_strategy) |
| `dashboard/app.py` | **MODIFY** | Add `OM SCALP` label display; ensure audit panel shows om_gold_scalp-specific breakdown fields |
| `dashboard/templates/dashboard.html` | **MODIFY** | Render `OM SCALP` signal cards with pts (not pips) labels |
| `config.py` | **MODIFY** | Add `OM_GOLD_SCALP_MODE` env var kill switch; add thresholds (`max_chase_pts`, `max_sl_pts`, etc.) |
| `filters/quality_gate.py` | **CHECK** | Confirm XAU min SL gate (150p) still applies; om_gold_scalp uses its own max SL (20 pts = 2000 pips) gate internally |
| `tests/` | **CREATE** | New test file: `tests/test_om_gold_scalp.py` — see Section 12 |

**Isolation rule (from operating principles):**
`om_gold_scalp.py` must never import from `gold_strategy.py` or `news_sniper.py`. All logic is self-contained. The only shared code is candle primitives from `core/`.

---

## 12. Tests Needed Before Implementation

All tests must exist and pass **before** `strategies/om_gold_scalp.py` is wired into the scan loop.

### Unit tests (`tests/test_om_gold_scalp.py`)

| Test | What it proves |
|---|---|
| `test_sweep_reclaim_long_enter_now` | Double sweep + reclaim + displacement → `ENTER_NOW`, direction=long |
| `test_sweep_alone_no_entry` | Sweep bar printed, no reclaim yet → `WAIT_RETEST` |
| `test_failed_reclaim_short` | Reclaim attempt + reclaim failed + bearish displacement → `ENTER_NOW`, direction=short |
| `test_htf_range_skip_chop` | Price inside range boundaries → `SKIP`, skip_reason=`inside_range_chop` |
| `test_range_breakdown_enter_now` | Range low broken + retest hold + follow-through → `ENTER_NOW`, direction=short |
| `test_range_fake_breakout_skip` | Breakout above range + reclaim back inside → `SKIP_INSIDE_RANGE`, entry_allowed=false |
| `test_news_impulse_no_entry` | News candle + no confirmation → `WAIT_RETEST` |
| `test_news_3_candle_confirmation` | News candle + 3-candle continuation → `ENTER_NOW` |
| `test_impulse_exhaustion_long_exit` | Impulse to upper liquidity + consolidation → `long_bias_exit=true`, no new longs |
| `test_sl_too_wide_skip` | Sweep extreme + 2 pts buffer > 20 pts → `SKIP`, skip_reason=`sl_too_wide` |
| `test_chase_distance_skip` | Entry > 25 pts from origin zone → `SKIP_CHASE` |
| `test_skip_reason_always_logged` | Any SKIP must include non-empty `skip_reason` field |
| `test_momentum_score_range` | Momentum score always between 0 and 100 |
| `test_audit_fields_present` | Every signal (including SKIP) has all required audit fields in breakdown JSON |
| `test_om_scalp_isolated_from_gold_strategy` | `om_gold_scalp.py` has no imports from `gold_strategy.py` or `news_sniper.py` |
| `test_signal_mode_written_to_db` | Logged signal has `signal_mode = om_gold_scalp` in DB row |

### Integration tests

| Test | What it proves |
|---|---|
| `test_scan_pair_xauusd_om_scalp_mode` | Full `scan_pair` call with om_gold_scalp mode active returns valid scored dict |
| `test_dedup_fingerprint_om_scalp` | Duplicate om_gold_scalp signal within 60 min is deduped by logger |
| `test_dashboard_label_om_scalp` | Dashboard signal card shows `OM SCALP` label, not `GOLD` or `SNIPER` |
| `test_quality_gate_still_fires` | Existing quality gate (min SL 150p) still applies to om_gold_scalp signals |

---

## 13. Thresholds Summary

All values are PROPOSED. Om must approve before implementation.

| Parameter | Value | Source |
|---|---|---|
| `max_sl_pts` | 20 pts | Spec (SL > 20 pts → SKIP) |
| `min_sl_pips` | 150 pips (XAU) | Existing quality gate |
| `tp1_min_pts` | 15 pts | Spec |
| `tp1_max_pts` | 25 pts | Spec |
| `tp2_max_pts` | 30 pts | Spec |
| `min_rr` | 1.5 | Spec (TP1 / SL ≥ 1.5) |
| `sl_buffer_pts` | 2 pts | Spec (sweep extreme + 2) |
| `max_chase_pts` | 25 pts | Chase filter |
| `reaction_zone_distance_pts` | 8 pts | Retest must be within this |
| `near_zone_distance_pts` | 5 pts | SKIP_NEAR_ZONE threshold |
| `should_log_min_score` | 50 | Spec |
| `should_alert_min_score` | 65 | Spec (AND grade ≥ B) |
| `enter_now_min_momentum` | 50 | Spec (`momentum_score ≥ 50`) |
| `wait_retest_momentum_range` | 35–49 | Spec |
| `sweep_min_wick_pts` | 1.5 pts | Spec |
| `sweep_max_bars_ago` | 20 bars (M5) | Spec |
| `sweep_recency_max_bars` | 5 bars | Spec (sweep candle age) |
| `displacement_min_body_multiple` | 1.5× | PROPOSED (vs 3-bar avg body) |
| `news_proximity_window_min` | 30 min | Spec |

---

## 14. What This Spec Does NOT Cover

The following are out of scope for the initial implementation and will be addressed separately:

- Sona/learning layer (threshold auto-adjustment) — deferred until 30+ labeled OM scalp outcomes collected
- 1M entry timing refinement — optional, add after v1 is live and producing paper signals
- Score saturation fix in `alerts/scorer.py` — separate engineering task
- Multi-pair extension — om_gold_scalp is XAU_USD only in v1
- Backtesting framework — no historical data pipeline exists yet

---

*Spec created: 2026-05-16*
*Source: OM_GOLD_SCALP_RULEBOOK.md — 45 examples*
*Status: PROPOSED — awaiting Om approval before any code is written*
