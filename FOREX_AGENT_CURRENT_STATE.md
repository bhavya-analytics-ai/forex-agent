
# FOREX AGENT CURRENT STATE — May 2026

---

## 1. Current System Purpose

Forex Agent is a scanner and decision-support system. It is not a blind auto-trader.

It scans 11 forex and metals pairs across four timeframes (H1, M15, M5, M1), evaluates confluence using ICT/SMC concepts, grades signals, and presents them for manual review. Om decides whether to take a trade. The system does not execute orders.

**Core functions:**
- Continuous 5-min scan cycle across 11 pairs
- ICT confluence scoring: zones, structure, killzones, FVG, pattern, news clearance
- Three strategy streams: `normal` (gold_strategy / forex_strategy), `news_sniper` (XAU only), mode switchable
- Signal logging to SQLite DB and CSV — with dedup, archival, and labeling
- Dashboard (Flask) for live signal review, manual trade logging, P&L tracking, audit panel
- Slack alerts for qualifying signals
- Railway live deployment, SQLite DB as source of truth

**Operating principle:** System surfaces high-confluence setups. Om reviews. Om labels outcomes. No auto-execution at any stage.

---

## 2. Stabilization Work Completed

All items below are committed and deployed on Railway.

| Fix | Commit | Description |
|---|---|---|
| Archived spam excluded from all read paths | `e9bd0a4` | `get_recent_agent_signals`, `get_performance_summary_db`, `get_unlabeled_taken_signals` now filter `COALESCE(is_archived,0)=0`. 107 spam rows quarantined via API. |
| Forex logging restored without spam | `f486303` | Forex signals log via `should_log` flag. DB-backed 60-min fingerprint dedup prevents repeated logging. Fingerprint: `(pair, signal_mode, direction, setup_type, h1_trend)`. Gold/sniper unchanged — still require `entry_state=ENTER_NOW`. `signal_mode` now written to DB. |
| Decision trace mode | `7771d4e` | `DEBUG_DECISIONS` env var (default `false`). When enabled: one compact INFO line per pair per scan showing grade, score, entry_state, should_log, should_alert, block reason. Zero effect on trading behavior. |
| Friday/weekend market-hours guard | `6089318` | `filters/market_hours.py`. Friday 21:00–21:30 UTC: −10 pts, alerts suppressed. Friday 21:30–22:00 UTC: hard block, no log, no alert. Sunday 22:00–23:00 UTC: −15 pts, A+ alerts only. |
| Minimum quality gate | `af467c4` | `filters/quality_gate.py`. Entry pattern gate (forex A/A+ with no candle confirmation → block). Zone-direction conflict gate (strong opposing zone → block, weak → −8 pts). Minimum SL gate (XAU < 150p, XAG < 200p, forex < 5p → block). Fails open on exception. |
| Grade C metal ENTER_NOW alert suppression | `af467c4` | Gold/silver ENTER_NOW with grade C still logs (strategy conviction kept) but `should_alert=False`. No Slack noise on low-confidence entries. |
| XAU pts display fixed in dashboard | `4dfb9c9` | SL/TP labels, live P&L tracker, close modal, take-trade modal, audit panel all show `pts` not `pips` for XAU/USD. Internal pip math unchanged. |
| Breakout Slack routing fixed | `d0aca5b` | Breakout alerts use `send_sniper_alert` in news_sniper mode, `send_signal_alert` in normal mode. |
| News filter country mapping fixed | `97d18be` | ForexFactory fallback now maps ISO country codes (`US` → `USD`) matching Finnhub path. XAU/USD news blocking now reliable even when Finnhub 403s. |
| Scorer / logger integrity fixes | `f64a62d`, `f5c4f32` | Killzone safe default, EV labeled estimated, news likelihood guard, loss penalty display-only, `signal_mode` persisted, dead breakdown columns blank not fake-zero. |
| News sniper sweep quality | `7b37809` | `_WICK_PCT_MIN` filters weak sweeps. SL anchored to sweep candle close. Explicit rejection reasons logged. |

---

## 3. Current Risk Controls

**Market hours (live — `filters/market_hours.py`):**
- Friday 21:00–21:30 UTC — caution: −10 pts, all alerts suppressed
- Friday 21:30–22:00 UTC — hard block: no log, no alert for any pair
- Sunday 22:00–23:00 UTC — caution: −15 pts, A+ grade alerts only
- All other times: clean pass, no penalty

**Quality gate (live — `filters/quality_gate.py`):**
- Forex A/A+ with no candle confirmation pattern → hard block (no log, no alert)
- Forex B with no pattern → logs with `⚠️ NO PATTERN` flag
- Gold/sniper: pattern gate exempt (ICT sequence is the pattern)
- Zone-direction conflict with zone strength ≥ 40 → hard block
- Zone-direction conflict with zone strength < 40 → −8 pts penalty, flag
- Bypass: `zone_flip=True` or `setup_type` in `{sr_flip, zone_tap}`
- SL < minimum threshold → hard block (XAU: 150p, XAG: 200p, forex: 5p)

**Signal dedup (live — `alerts/logger.py`):**
- Forex: 60-min DB-backed fingerprint dedup prevents repeated same-signal spam
- Gold/sniper: in-memory cooldown per pair (unchanged)

**Grade C metal suppression (live — `reports/briefing.py`):**
- Gold/silver ENTER_NOW grade C → `should_alert=False`, still logs

---

## 4. Current Known Weaknesses

**Score saturation:**
- Multiplicative Bayesian boosts in `alerts/scorer.py` can compound past 1.0
- Score of 99/100 is currently appearing on multiple unrelated signals per scan
- Scores are not being meaningfully differentiated at the top end
- Fix designed, not implemented

**OM Gold Scalp:**
- Detailed spec finalized (see Section 5)
- Strategy file `strategies/om_gold_scalp.py` does not exist yet
- No code written

**Learning layer (Sona/Hermes):**
- Architecture discussed, not designed in detail
- No code written
- Not starting until labeled examples are collected

**Screenshot calibration:**
- **Core Market Structure Definitions layer added** to rulebook (top of file, before examples). Defines 14 operational terms: liquidity sweep, breakout, fake breakout, reclaim, failed reclaim, retest, continuation, reversal, CHoCH, BOS, range/chop, displacement, pullback, late entry/chase. Includes scanner principle: candle appearance alone is never enough — HTF zone + sweep/break/reclaim + EMA/trend + structure shift + retest/follow-through + R:R must combine before `ENTER_NOW`. All existing examples reference these definitions; future examples must reuse the same vocabulary.
- **SCREENSHOT CALIBRATION COMPLETE — 45 examples collected** (`docs/om_gold_scalp/OM_GOLD_SCALP_RULEBOOK.md`)
- Examples 001–005: 1H standalone/context examples (bearish freefall, FVG magnet, zone flip, news impulse, liquidity sweep)
- Examples 006–013: 15M setup layer (failed retest, bearish continuation into lower zone, bullish breakout pullback, sweep reclaim reversal, zone-to-zone continuation, breakdown impulse, FVG fill rejection, zone magnet reclaim)
- Examples 014–021: 5M trigger layer (failed reclaim short/long reversal, zone reclaim bullish multi-TP, trend pullback reentry, range breakdown flip, news fakeout reclaim impulse, multi-setup zone-to-zone, chop skip, bearish breakdown retest continuation) — all PROPOSED scanner rules, no code written
- Examples 022–025: paired 1H/5M context-execution examples (022+023 = multi-zone breakdown + upper rejection → lower sweep reclaim; 024+025 = repeated S1 breakdown + failed reclaim → S2 magnet). Introduces 1H → 5M pair logic and audit fields `htf_zone_map`, `htf_magnet`, `zone_tests_count`, `zone_strength_decay`, `zone_role_flip`, `paired_context_id`
- Examples 026–027: paired 15M/5M news-displacement context-execution. 026 = 15M S/R band respected → failed breakout → news displacement → lower magnet → later reclaim. 027 = 5M no-entry on news candle, wait for 3-candle continuation or failed reclaim of old support before short; reclaim + topside retest flips to long. Introduces news-displacement logic and audit fields `news_impulse`, `three_candle_continuation`, `confirmation_signal`, `displacement_source`, `bias_flip_event`
- Examples 028–029: paired 15M/5M range-break failed-reclaim context-execution. 028 = 15M range support breaks, reclaim attempt fails, lower-high continuation confirms bearish bias. 029 = 5M shows green retest candle with `single_candle_strength` that cannot reclaim (`reclaim_failed`), then `low_momentum_candle` continuation candle that holds structure — teaches `candle_strength_mismatch` (bar color/size ≠ structural truth). Introduces range-break failed-reclaim logic and audit fields `support_hold_failed`, `reclaim_attempt`, `reclaim_failed`, `candle_strength_mismatch`, `follow_through_confirmed`, `continuation_entry`, `htf_context_id`, `execution_pair_id`
- Examples 030–031: paired 15M/5M countertrend-green-failure context-execution. 030 = 15M broken support with healthy green recovery attempts that fail to reclaim and hold; bearish context preserved. 031 = 5M bullish pullbacks fail under EMA 200, every failed pullback is a continuation-short reentry, not a reversal long. Reinforces `candle_strength_mismatch` — appearance ≠ structural truth. Introduces countertrend-green-failure logic and audit fields `broken_support_context`, `countertrend_green_attempt`, `bullish_pullback_failed`, `bearish_context_preserved`, `continuation_short_valid`
- Examples 032–033: paired 15M/5M decision-zone consolidation context-execution. 032 = 15M purple zone treated as decision area; consolidation + mixed reactions until upper zone fails, then Support 2 magnet activates. 033 = 5M two clean signatures only — (a) sweep + reclaim + follow-through long, (b) break + failed-reclaim short. Middle-of-range entries explicitly marked as `low_confidence_setup` + `avoid_entry` and skipped with logged `skip_reason`. Introduces decision-zone consolidation logic and audit fields `htf_zone_type`, `decision_zone`, `consolidation_at_zone`, `liquidity_sweep_before_move`, `failed_support_hold`, `support2_magnet`, `middle_range_risk`, `entry_quality`, `skip_reason`
- Examples 034–035: paired 15M/5M impulse-exhaustion context-execution. 034 = 15M clean bullish impulse into upper liquidity, exhaustion + consolidation, range exit down = bearish read. 035 = 5M early origin long valid, then sweep + rejection short scalp at top, consolidation = no-trade, failed push higher → slow bearish continuation. Encodes location-aware candle reading: strong green at origin = useful, same strong green into prior high = exhaustion risk. Introduces impulse-exhaustion logic and audit fields `clean_bullish_impulse`, `impulse_origin`, `upper_liquidity_target`, `top_sweep_or_exhaustion`, `consolidation_after_impulse`, `long_bias_exit`, `failed_push_higher`, `bearish_continuation_after_failure`, `slow_level_fill`, `late_long_risk`, `short_scalp_valid`, `exit_reason`
- Examples 036–037: paired 15M/5M HTF-range no-trade context-execution. 036 = wide purple HTF range, price trapped inside, no clean directional resolution — scanner marks no-trade state. 037 = 5M chop inside the range, wicks into boundaries close back inside, no displacement break — explicit `SKIP_CHOP` with `skip_reason = inside_range_chop`. Resolution requires breakout/breakdown + displacement + (retest hold OR reclaim failure OR follow-through). Introduces HTF-range no-trade logic and audit fields `htf_range_active`, `no_trade_zone`, `inside_range_chop`, `range_boundary_high`, `range_boundary_low`, `boundary_break_required`, `low_confidence_inside_range`, `breakdown_confirmation_required`, `execution_wait_state`
- Examples 038–039: paired 15M/5M double-sweep reclaim long context-execution. 038 = 15M double liquidity sweep below prior lows, downside fails, reclaim + bullish displacement confirms long bias. 039 = 5M full sequence: sweep 1 → sweep 2 → reclaim → displacement → long trigger. Entry gates: `entry_after_reclaim_only = true`, `sweep_alone_no_entry = true`. Double sweep increases conviction vs single sweep. SL anchored to sweep 2 wick extreme + 2 pts. Introduces double-sweep reclaim logic and audit fields `liquidity_sweep_count`, `double_sweep`, `swept_side`, `reclaim_confirmed`, `reclaim_direction`, `bullish_displacement`, `structure_shift_after_sweep`, `long_bias_after_reclaim`, `long_trigger_after_reclaim`, `entry_after_reclaim_only`, `sweep_alone_no_entry`
- Examples 040–041: paired 15M/5M failed-bullish-reversal bearish-continuation context-execution. Mirror of 038–039 — same anatomy (sweep → reclaim attempt → displacement) but reclaim fails, bias flips bearish. 040 = 15M sweep candidate, bullish recovery collapses, `reclaim_failed = true`, bearish displacement follows. 041 = 5M green candles during failed reclaim = `single_candle_strength` without structure = `avoid_entry`; short only after `failed_bullish_reversal = true` + bearish displacement. Latest concept: scanner distinguishes sweep-with-reclaim (long) vs sweep-with-failed-reclaim (short) using the same audit anatomy. Introduces audit fields `sweep_candidate`, `failed_bullish_reversal`, `bearish_displacement_after_failed_reclaim`, `bearish_continuation_valid`, `avoid_long_reason`
- All screenshot files committed — 5M batch `9793c93`, paired 1H/5M `f2c8b34`, news-displacement `ade3127`, range-break failed-reclaim `c015638`, countertrend-green-failure `5be702b`, decision-zone consolidation `b80e6ad`, impulse-exhaustion `29e94de`, HTF-range no-trade `5d055d4`, double-sweep reclaim long `20a7878`
- Examples 042–043: paired 15M/5M HTF-range breakdown bearish-continuation. 042 = 15M context — large purple range, all internal moves `no_trade_zone` + `avoid_entry`, bearish continuation requires range low body close + retest hold + follow-through. 043 = 5M execution pair — `no_trade_zone_inside_range = true` while in range, `avoid_short_before_break = true` until 15M context confirms break, `ENTER_NOW` (short) only after `range_retest_held_below = true` + follow-through. Failure = body reclaims back inside HTF range. 042 updated from standalone to paired. Audit fields: `no_trade_zone_inside_range`, `internal_pushes`, `avoid_short_before_break`, `range_low_broken`, `range_retest_held_below`, `confirmation_signal`, `bearish_continuation_valid`, `execution_bias`, `failure_condition`, `htf_context_id`, `execution_pair_id`
- Example 044: standalone 5M range fake-breakout reclaim-failed no-trade. `educational_negative_example` — teaches what NOT to act on. Price breaks above range high, fails to hold, reclaims back inside. Neither long (failed breakout) nor short (still inside range) is valid. `scanner_action = SKIP_INSIDE_RANGE`, `entry_allowed = false` for both directions. Short gate: range low broken + hold below + follow-through. Long gate (symmetric): fresh clean breakout + hold + follow-through. Audit fields: `range_high_swept`, `breakout_failed`, `reclaim_back_inside_range`, `avoid_long_reason`, `avoid_short_reason`, `entry_allowed`, `scanner_action`, `confirmation_needed`
- Example 045: standalone 5M S/R reclaim candidate to bullish displacement. Final calibration example. Teaches progressive scanner state detection: `price_below_sr = true` → long suppressed → push back into level = `reclaim_candidate` (attention, no entry) → body close above + hold = `reclaim_confirmed` → bullish displacement = `ENTER_LONG_ALLOWED`. `scanner_state_flow: WAIT_RECLAIM → WAIT_HOLD → ENTER_LONG_ALLOWED`. Early detection design: scanner marks `reclaim_candidate` at push-back stage so it is ready to upgrade, not discovering the setup after displacement is complete. Audit fields: `key_sr_level`, `price_below_sr`, `bearish_pressure_below_sr`, `reclaim_candidate`, `reclaim_confirmed`, `hold_above_sr_required`, `bullish_displacement_after_reclaim`, `potential_long_setup`, `enter_long_only_after_confirmation`, `scanner_state_flow`

**Screenshot calibration phase: COMPLETE.**
**Next phase: rule extraction and scanner patch planning.**
- Om reviews PROPOSED rules in OM_GOLD_SCALP_RULEBOOK.md
- Approved rules extracted into scanner spec document
- `strategies/om_gold_scalp.py` written only from approved spec
- No code written from unapproved PROPOSED rules
- Core OM Concepts: zone_flip, failed_reclaim, fvg_magnet, liquidity_sweep, breakout_impulse, news_impulse, fakeout, reversal_candidate, continuation_pullback (14 total)
- 15M Setup Layer Rules section added: zone_state enum, setup_action enum, chase filter, fvg_relation enum, reaction-zone logic, continuation setup logic, proposed thresholds
- Scanner reads OHLC candle data only — no pixel/image reading
- Screenshots are needed to translate Om's visual trading logic into measurable candle rules

**Live scanner vs screenshots:**
- Current scanner cannot read screenshots
- Screenshots are for rule extraction and training data only — not live execution input
- v1 OM Gold Scalp will execute from market data, not image recognition

---

## 5. OM Gold Scalp Status

**High-level architecture — finalized:**
- Separate strategy stream from `gold_strategy` (structural) and `news_sniper` (news reversal)
- `pair = XAU_USD` — no fake pair names
- `signal_mode = om_gold_scalp`
- `dashboard_label = OM SCALP`
- File: `strategies/om_gold_scalp.py`
- Killzone: no hard gate — scoring bonus only
- News safety: penalty only (−15/−20/−10 pts depending on window) — not a hard block
- H1/EMA opposing scalp direction: −25 pts penalty. Hard SKIP only if opposing AND `momentum_score < 35`
- SL method: sweep wick extreme + 2 pt buffer, max SL = 20 pts
- TP1: 15–25 pts (min 1:1.5 RR). TP2: up to 30 pts
- `ENTER_NOW`: valid sweep + displacement ≥ 3 pts + `momentum_score ≥ 50`
- `WAIT_RETEST`: sweep confirmed, displacement not yet closed or `momentum_score` 35–49
- `SKIP`: no sweep, SL > 20 pts, H1 opposing + `momentum_score < 35`, or score < 50

**Detailed spec — finalized:**
- Momentum scoring: 4 components, weights defined, 100 pt scale
- Sweep criteria: 4 gates (M5 swing within 20 bars, wick ≥ 1.5 pts, close inside, recency ≤ 5 bars)
- Audit fields: 8 scalp-specific fields into `breakdown` JSON column
- Entry state conditions: fully defined
- Score thresholds: `should_log ≥ 50`, `should_alert ≥ 65` AND grade ≥ B

**What must happen before implementation:**
- Screenshot calibration (Section 6) must produce Om-approved examples
- Rules must be validated against real setups Om would have taken
- Implementation only begins after rulebook v1 is approved

---

## 6. Screenshot Calibration Workflow

Om will send batches of chart screenshots. Claude processes each batch and produces a table.

**Batch types:**
- **1H batch** — market context, bias, purple S/R zones, trend direction
- **15M batch** — setup location, sweep visibility, failed reclaim area
- **5M batch** — scalp trigger, displacement candle, pullback quality
- **1M batch** — execution timing, early-vs-late, confirmation candle

**Output table per image:**

| Field | Content |
|---|---|
| Image # | Sequential number |
| Timeframe | 1H / 15M / 5M / 1M |
| Take? | YES / NO / WAIT |
| Direction | Bullish / Bearish |
| Entry idea | Price level or candle |
| Invalidation | Price level that breaks the idea |
| Target idea | 15 / 20 / 25 / 30 pt level |
| What Om likely sees | Describe the visual setup |
| Scanner rule learned | What candle/zone condition maps to this |
| Label | clean scalp / missed opportunity / trash / late entry / early entry / fakeout / chop |

**Process:**
1. Claude extracts patterns from each screenshot batch
2. Om corrects or confirms Claude's read
3. Agreed patterns accumulate into Rulebook v1
4. Only after Rulebook v1 is approved does implementation begin

Claude must not finalize trading rules from screenshots alone. Om's corrections are the source of truth.

---

## 7. How Screenshots Help the Scanner

The current scanner reads OHLC candle data and computed indicators — it does not read pixels.

Screenshots serve a different purpose: translating Om's visual pattern recognition into measurable, codeable candle and zone conditions.

Examples:
- Om sees "clean sweep + displacement" → Claude maps that to: M5 wick > 1.5 pts past level, close inside, body ≥ 3 pts in scalp direction
- Om sees "choppy, avoid" → Claude maps that to: ATR ratio < threshold, no clean body directional bias
- Om labels "late entry" → that becomes a recency gate (sweep candle age > N bars = disqualified)

A future Sona/vision layer may store screenshots alongside audit JSON as training examples. v1 OM Gold Scalp will still execute from market data, not image recognition.

---

## 8. Sona / Learning Layer Status

**Not started. Future phase only.**

Goal: a learning system that reviews wins, losses, missed trades, screenshots, audit JSON, and Om's notes — and proposes threshold adjustments or rule changes.

**Constraints that will apply when built:**
- No auto-editing of live strategy files
- No autonomous trading rule changes
- All proposed changes require Om's explicit approval before implementation
- Archived and spam rows must be excluded from all training data
- Learning begins with labeled examples and trade reviews — not unsupervised threshold tuning
- Sona is advisory only: surfaces patterns, does not act

**Prerequisite:** 30+ labeled OM Gold Scalp examples collected before Sona design begins.

---

## 9. Next Execution Order

1. ✅ This checkpoint README (current step)
2. Begin screenshot calibration — Om sends batches, Claude produces analysis tables
3. Build OM Gold Scalp Rulebook v1 from Om-approved examples
4. Write OM Gold Scalp implementation plan only after Rulebook v1 approved
5. Code `strategies/om_gold_scalp.py` — separately from all other strategy files
6. Verify on paper observation (no live trades) — confirm ENTER_NOW fires correctly, dedup holds, dashboard label correct
7. Design Sona learning capture layer around collected examples and labeled outcomes
8. Score saturation fix — separate engineering task, does not block any of the above

---

## 10. Claude Operating Rules Going Forward

Claude must:
- Ask what phase we are in before writing any code
- Never mix OM Gold Scalp logic with Sona design unless Om explicitly asks
- Never implement strategy logic from assumptions — wait for Om-approved examples
- Always list exact files that will be touched before editing
- Always run syntax check and tests after any code change
- Always show `git diff` before committing
- Never deploy without Om's explicit approval
- Treat Om's screenshot labels as source of truth for scalp rule calibration
- Keep `gold_strategy.py` and `news_sniper.py` untouched unless explicitly instructed
- Keep all 3 strategy streams (`normal`, `news_sniper`, `om_gold_scalp`) fully isolated from each other

---

*Last updated: 2026-05-16*
*Quality gate live: af467c4*
*Market hours guard live: 6089318*
*Dedup/lifecycle live: f486303*
*5M trigger layer examples committed: 9793c93*