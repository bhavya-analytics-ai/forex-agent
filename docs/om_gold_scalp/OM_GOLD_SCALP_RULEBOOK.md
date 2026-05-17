# OM Gold Scalp — Rulebook

> Screenshot calibration log. Each example captures what Om sees, what the scanner should learn, and what label applies.
> Rules are NOT finalized from screenshots alone. Om approves each rule before it is implemented.

**Status:** Calibration in progress
**Examples collected:** 42 (5 × 1H context [001–005] + 8 × 15M setup [006–013] + 8 × 5M trigger [014–021] + 4 × paired 1H/5M context-execution [022–025] + 2 × paired 15M/5M news-displacement context-execution [026–027] + 2 × paired 15M/5M range-break failed-reclaim context-execution [028–029] + 2 × paired 15M/5M countertrend-green-failure context-execution [030–031] + 2 × paired 15M/5M decision-zone consolidation context-execution [032–033] + 2 × paired 15M/5M impulse-exhaustion context-execution [034–035] + 2 × paired 15M/5M HTF-range no-trade context-execution [036–037] + 2 × paired 15M/5M double-sweep reclaim long context-execution [038–039] + 2 × paired 15M/5M failed-bullish-reversal bearish-continuation context-execution [040–041] + 1 × 15M HTF-range breakdown bearish-continuation standalone context [042])
**Rules approved:** 0 (pending calibration)

---

## Metadata fields — standard format for every example

Every example must include the following fields:

| Field | Description |
|---|---|
| `example_id` | Sequential 3-digit ID |
| `screenshot_path` | Relative path from repo root |
| `timeframe` | 1H / 15M / 5M / 1M |
| `date_range_visible` | Date range readable from chart |
| `session_context` | Tokyo / London / NY / mixed |
| `news_context` | Known news events in window, or UNKNOWN |
| `move_type` | context / setup / trigger / execution |
| `Om bias` | bullish / bearish / wait / no trade |
| `Om notes` | Verbatim or paraphrased from Om |
| `zone_context` | Purple S/R zone details |
| `fvg_context` | FVG details if visible |
| `news_context_detail` | Specific events if known |
| `scanner_rule_learned` | Proposed candle/zone condition (PROPOSED until approved) |
| `code_status` | proposed / approved / rejected / implemented |

---

## How to read this file

- **Context only** — 1H examples set bias. Not direct entries.
- **Setup** — 15M/5M examples locate the trade area.
- **Trigger** — 5M/1M examples define entry candle conditions.
- **Label** is Om's verdict on the setup quality.
- **Rule learned** is the proposed scanner condition. Not live until Om approves.

---

## Core Market Structure Definitions

These definitions are the operational vocabulary used by every example below and by every PROPOSED scanner rule in this document. They are written in plain operational language so future code can map each term directly to a candle/zone condition without guessing.

Every example below uses these terms with the meanings defined here. If a definition needs to evolve, update it here first and re-validate the examples that depend on it.

---

### Annotation handling

Screenshot annotations may contain informal trader notes. The scanner must not treat informal text as direct trading logic. All examples must be interpreted through normalized audit fields and structured labels in this rulebook.

The scanner learns from structured interpretation, not raw emotional wording on screenshots.

When raw notes use informal phrases, they are mapped to normalized labels as follows. This list is the canonical translation — informal wording in any example or note refers to these structured terms, not to itself.

| Informal note | Normalized scanner label |
|---|---|
| gambling trade / gambling / risky | `low_confidence_setup` + `avoid_entry` |
| lucky trade | `low_confidence_setup` (do not generalize) |
| maybe / unsure / ??? | `confirmation_missing` → `WAIT_REACTION` or `SKIP_CHOP` |
| looks good / looks healthy / looks strong | `single_candle_strength` — not a trigger by itself |
| looks weak | `low_momentum_candle` — not invalidation by itself |
| chase trap / trap | `chase_entry` → `SKIP_CHASE` (or `liquidity_sweep_candidate` for the level) |
| countertrend attempt | `countertrend_attempt_failed` once reclaim fails |
| half-reclaim / barely held | `weak_reclaim` |
| broke and came back | `failed_breakout` / `failed_breakdown` (per direction) |
| swept the high/low | `liquidity_sweep_candidate` (becomes `sweep_reclaim_confirmed` once reclaim + hold) |
| reclaim died / could not hold | `reclaim_failed` |
| need confirmation | `structure_shift_required` / `retest_required` / `follow_through_required` |
| range not broken | `range_not_broken` + `boundary_break_required` |
| no setup here | `no_trade_zone` + `entry_invalid_without_confirmation` |
| continuation but unsure | `continuation_not_confirmed` |

Messy or unresolved examples are classified — never deleted — using one of:
- `no_trade_zone`
- `low_confidence_setup`
- `avoid_entry`
- `educational_negative_example`

An example labeled `educational_negative_example` is kept in the rulebook as a teaching case (what NOT to take), not as a valid trade.

---

**1. Liquidity sweep**
Price takes out a visible previous high/low or zone edge, then fails to continue in the sweep direction and returns back inside prior structure.
- **Bullish sweep** = price takes a visible low / support edge, then reclaims back above it.
- **Bearish sweep** = price takes a visible high / resistance edge, then rejects back below it.
- The wick beyond the level is the sweep. The close back inside is the proof.

**2. Breakout**
Price closes outside a key zone or level with displacement and does not immediately return inside.
- Requires a body close outside the level (not just a wick).
- A valid breakout requires hold + retest + follow-through.
- Without follow-through, treat as fake breakout candidate.

**3. Fake breakout**
Price breaks a level but quickly returns inside the prior range or zone.
- Treat as a sweep / trap until confirmed otherwise.
- Often the start of a reversal in the opposite direction.

**4. Reclaim**
Price loses a level (closes through it), then recovers it (closes back on the original side) and holds.
- Reclaim requires a body close back across the level AND a holding candle (next bar does not re-break).

**5. Failed reclaim**
Price attempts to recover a broken level but cannot hold it — body closes back on the broken side.
- Strong evidence for continuation in the original breakout direction.
- The failed reclaim wick + close marks the new resistance (after support break) or new support (after resistance break).

**6. Retest**
Price returns to a broken level or zone after a breakout.
- **Good retest** — holds in the new role (broken support holds as resistance / broken resistance holds as support).
- **Bad retest** — fails and re-enters the prior range. Warns of fakeout or reversal.

**7. Continuation**
Price resumes the same direction after a pullback, retest, or consolidation.
- **Bullish continuation** = higher low + retest hold + follow-through up.
- **Bearish continuation** = lower high + retest fail + follow-through down.

**8. Reversal**
Price stops continuing in the old direction and starts building opposite structure.
- One candle is never enough to call a reversal.
- **Bullish reversal** requires: sweep / reclaim OR bearish failure + break of a minor lower high + higher low + follow-through.
- **Bearish reversal** requires: sweep / rejection OR bullish failure + break of a minor higher low + lower high + follow-through.

**9. CHoCH (Change of Character)**
First warning that price behavior may be shifting.
- **Bullish CHoCH** = a bearish sequence breaks a recent lower high.
- **Bearish CHoCH** = a bullish sequence breaks a recent higher low.
- CHoCH is a warning, not an entry. Treat as `WAIT_REACTION` until BOS or retest confirms.

**10. BOS (Break of Structure)**
Stronger confirmation than CHoCH — confirms a new trend leg in the new direction.
- **Bullish BOS** = breaks the prior swing high after a higher low prints.
- **Bearish BOS** = breaks the prior swing low after a lower high prints.

**11. Range / chop**
Sideways price inside a zone with no clean direction.
- EMA flat or crossing.
- Repeated failed signals, multiple fakeouts.
- Scanner should mark `setup_action = SKIP_CHOP` (no trade) or scalp-only with explicit chop flag.

**12. Displacement**
A strong directional move with large candles and little overlap between bars.
- Displacement alone is not an entry — it must be judged together with zone context.
- A displacement candle at a HTF zone edge is a setup; the same candle mid-range is noise.

**13. Pullback**
A temporary move against the main direction.
- Useful only if it holds or fails at a meaningful zone, EMA, or structural level.
- A pullback into open air (no level) is chop, not a setup.

**14. Late entry / chase**
The signal appears after price has already moved far from the origin level or zone.
- Direction may still be correct, but the trade should be skipped if R:R is poor.
- `SKIP_CHASE` fires when entry would require an SL beyond the configured maximum or TP too close.

---

### Scanner principle — candle appearance alone is never enough

Bar color, body size, or single-candle strength is never sufficient to trigger an entry. The scanner must combine ALL of the following before arming `ENTER_NOW`:

- HTF zone context (1H / 15M map: where is price relative to the active zones?)
- Sweep / break / reclaim behavior (what did price do at the relevant level?)
- EMA / trend state (is price aligned with or against EMA 200 and recent slope?)
- Structure shift (CHoCH or BOS — has the structure actually changed?)
- Retest / follow-through (did the new direction get confirmed by a hold?)
- Risk / reward location (is the trade still worth taking given SL and TP distance?)

A green candle with `single_candle_strength` can still fail if zone context, structure, EMA, and follow-through disagree. A `low_momentum_candle` (red or otherwise) can be valid continuation if the same factors agree. The scanner reads the combination, not the appearance.

---

## Examples

---

### Example 001

| Field | Value |
|---|---|
| `example_id` | 001 |
| `screenshot_path` | `docs/om_gold_scalp/examples/001_1h_bearish_freefall_context.png` |
| `timeframe` | 1H |
| `date_range_visible` | May 2026 range visible on chart — exact dates UNKNOWN unless readable from screenshot |
| `session_context` | Mixed Tokyo / London / NY sessions visible |
| `news_context` | UNKNOWN |
| `move_type` | context |
| `Om bias` | Bearish while price remains below broken purple support |
| `label` | Bearish freefall context / broken support continuation |
| `use` | Context only — not a direct scalp entry |
| `code_status` | proposed |

**What Om sees:**
- Two purple S/R zones clearly marked:
  - Upper zone: ~4,650 (major level, tested repeatedly April–May)
  - Lower zone: ~4,560 (secondary support, also broken)
- 200 EMA (blue curve) at ~4,659 — price well below it, bearish macro bias confirmed
- Price broke below both purple zones in a sharp freefall (May 13–15)
- Both zones flipped from support → resistance
- No retest of either zone yet — price in freefall, not a clean scalp entry area
- Current price ~4,540, hanging below all structure

**Om notes:**
- This is what the H1 context looks like in a full bearish breakdown
- Both purple zones are now overhead resistance
- Would NOT scalp long here from 1H view
- Would only scalp short on a failed retest of ~4,560 or ~4,650 on lower timeframe
- Freefall candles with no consolidation = no clean entry, wait for structure

**zone_context:**

| Field | Value |
|---|---|
| `zone_low` | ~4,553 |
| `zone_high` | ~4,558 |
| `price_relation` | below / rejecting underside |
| `zone_state` | broken_support / failed_reclaim |
| `freefall_context` | true |
| `nearest_structure_distance_pts` | TBD — future candle-data implementation |
| `fvg_nearby` | true |
| `fvg_direction` | bearish |

> These values are Om screenshot labels, not live computed values yet.
> Live computation requires future candle-data implementation.

**fvg_context:**
- Not the primary focus of this screenshot — see Example 002 for FVG detail

**news_context_detail:** UNKNOWN

**scanner_rule_learned (PROPOSED — not approved):**
- If H1 price is below both identified S/R zones AND below 200 EMA → bias = bearish
- A bullish scalp is suppressed until price reclaims at least the lower zone on H1 close
- A bearish scalp is valid on failed retests of either zone from below
- No entry during active freefall — wait for consolidation candle (tight-body H1 or H1 doji near zone)
- H1 context check: `price < lower_zone AND price < ema_200` → `h1_bias = "bearish_freefall"`
- `h1_bias = bearish_freefall` → suppress bullish scalp signals entirely
- Bearish scalp allowed only at zone retest, not during open freefall

---

### Example 002

| Field | Value |
|---|---|
| `example_id` | 002 |
| `screenshot_path` | `docs/om_gold_scalp/examples/002_1h_fvg_magnet_continuation_context.png` |
| `timeframe` | 1H |
| `date_range_visible` | Apr 7 – Apr 28 range visible on chart |
| `session_context` | Mixed Tokyo / London / NY sessions visible |
| `news_context` | UNKNOWN — large impulse candles may be news-driven |
| `move_type` | context |
| `Om bias` | Continuation bias after FVG fill/rejection; bearish after support loss |
| `label` | FVG magnet / imbalance fill / continuation context / freefall after support break |
| `use` | Context only — not a direct scalp entry |
| `code_status` | proposed |

> **IMAGE FILE PENDING — Om must manually place PNG here:**
> `docs/om_gold_scalp/examples/002_1h_fvg_magnet_continuation_context.png`

**What Om sees:**
- Market leaves fair value gaps (empty/imbalanced price zones) during sharp displacement moves
- Price is drawn back to fill or mitigate those gaps before continuation
- Purple zones define major support/resistance — when broken, they become resistance
- FVG marked on chart as a magnet / reaction zone
- Om annotated: "fair value gap → fvg fillup upto any of this point, not fixed always that its gonna cover to top, but most of time manages to get more than halfway"
- Om annotated: "Market always moves in levels and fills the gap always before any big continuation, thats my theory"
- Large red impulse candle broke support → potential news-driven move
- After big displacement, price often retests FVG before next leg

**Om notes:**
- Market leaves fair value gaps / empty spaces during displacement
- Price often comes back to fill or mitigate those gaps before continuation
- FVG is a magnet and reaction area — not an automatic entry
- Purple zones define major S/R — if support breaks and no structure below, gold can freefall
- Do not chase immediately after huge displacement; wait for lower-timeframe confirmation or FVG rejection
- FVG fill is not guaranteed to top — usually covers at least halfway

**zone_context:**

| Field | Value |
|---|---|
| `upper_zone_approx` | ~4,790 (purple zone visible mid-chart) |
| `lower_zone_approx` | ~4,710 (purple zone visible lower) |
| `price_relation` | bouncing between zones / breaking below lower zone |
| `zone_state` | support → resistance flip after break |
| `freefall_context` | true — large displacement candle visible |
| `nearest_structure_distance_pts` | TBD — future candle-data implementation |

> These values are Om screenshot labels, not live computed values yet.

**fvg_context:**

| Field | Value |
|---|---|
| `fvg_present` | true |
| `fvg_direction` | mixed / depends on displacement leg |
| `fvg_low` | UNKNOWN — not precisely readable from screenshot |
| `fvg_high` | UNKNOWN — not precisely readable from screenshot |
| `price_relation_to_fvg` | fill / mitigation / rejection context |
| `fvg_age_bars` | UNKNOWN |
| `fvg_fill_pct` | UNKNOWN — Om notes "more than halfway" as typical |
| `fvg_rejection_confirmed` | proposed concept — requires lower-timeframe confirmation |

> These values are Om screenshot labels, not live computed values yet.

**news_context_detail:** UNKNOWN — large impulse candle timing suggests possible HIGH-impact event

**scanner_rule_learned (PROPOSED — not approved):**
- FVG is not an automatic entry — it is a magnet and context zone only
- FVG is a magnet/context zone — price drawn toward it, not guaranteed to fill fully
- Entry requires FVG fill/rejection + lower-timeframe momentum confirmation
- Bearish FVG rejection under broken support strengthens short bias
- Bullish FVG hold above support strengthens long bias
- After large displacement candle: wait for FVG retest on lower TF before entering scalp
- Do not enter immediately on big move — wait for structure to form at FVG level

---

---

### Example 003

| Field | Value |
|---|---|
| `example_id` | 003 |
| `screenshot_path` | `docs/om_gold_scalp/examples/003_1h_zone_flip_support_resistance.png` |
| `timeframe` | 1H |
| `date_range_visible` | Mar 13 – Apr 8 approx — exact dates UNKNOWN |
| `session_context` | Mixed Tokyo / London / NY sessions visible |
| `news_context` | UNKNOWN |
| `move_type` | context |
| `Om bias` | Depends on price relation to purple zone — above = bullish, below = bearish |
| `label` | Purple zone support/resistance flip |
| `use` | Context only — not a direct scalp entry |
| `code_status` | proposed |

> **IMAGE FILE PENDING — Om must manually place PNG here:**
> `docs/om_gold_scalp/examples/003_1h_zone_flip_support_resistance.png`

**What Om sees:**
- Purple zone acting as both support and resistance at different points in time
- When price is above the zone: zone supports from below
- When price breaks below the zone: zone flips to resistance from above
- Retest from underside + rejection = short context
- Reclaim above zone + hold = bullish recovery context

**Om notes:**
- Purple zone can act as support and resistance
- If price is above it, it can support
- If price breaks below it, it can become resistance
- Retest from underside + rejection creates short context
- Reclaim above + hold creates bullish recovery context

**zone_context:**

| Field | Value |
|---|---|
| `zone_state` | dynamic — support / resistance / broken_support / broken_resistance / retest / failed_reclaim / reclaim_success |
| `price_relation` | depends on candle position relative to zone |
| `freefall_context` | false unless break is impulsive |
| `nearest_structure_distance_pts` | TBD — future candle-data implementation |

> These values are Om screenshot labels, not live computed values yet.

**fvg_context:** Not primary focus of this example

**news_context_detail:** UNKNOWN

**scanner_rule_learned (PROPOSED — not approved):**
- Track `zone_state` dynamically across scans:
  - `support` — price above zone, zone holding from below
  - `resistance` — price below zone, zone rejecting from above
  - `broken_support` — price closed below zone after being above
  - `broken_resistance` — price closed above zone after being below
  - `retest` — price returning to zone after a break
  - `failed_reclaim` — price retested zone from below, rejected
  - `reclaim_success` — price retested zone from below, closed above and held
- Zone flip (support → resistance or reverse) is a key context signal
- `failed_reclaim` strengthens short bias; `reclaim_success` flips bias to bullish

---

### Example 004

| Field | Value |
|---|---|
| `example_id` | 004 |
| `screenshot_path` | `docs/om_gold_scalp/examples/004_1h_news_breakout_impulse_continuation.png` |
| `timeframe` | 1H |
| `date_range_visible` | Late Feb – Mar 19 approx — exact dates UNKNOWN |
| `session_context` | Mixed Tokyo / London / NY sessions visible |
| `news_context` | UNKNOWN — large impulse candle may be news-driven |
| `move_type` | context / news_impulse |
| `Om bias` | Bearish after clean support break |
| `label` | News/breakout impulse + continuation |
| `use` | Context only — not a direct scalp entry |
| `code_status` | proposed |

> **IMAGE FILE PENDING — Om must manually place PNG here:**
> `docs/om_gold_scalp/examples/004_1h_news_breakout_impulse_continuation.png`

**What Om sees:**
- Large single impulse candle breaks through purple zone cleanly
- Candle body closes and holds below the zone — not a wick poke
- No retest or consolidation — continuation bias
- If no structure below, freefall risk increases
- Possible news event driving the move (size of candle implies institutional catalyst)

**Om notes:**
- Large impulse candle through purple zone can signal news/breakout impulse
- If price closes and holds below zone, bearish continuation bias
- If no structure below, freefall risk increases
- Do not chase first impulse blindly
- Wait for FVG, pullback, retest, or lower-timeframe continuation
- News impulse creates high-alert context, not automatic entry

**zone_context:**

| Field | Value |
|---|---|
| `zone_state` | broken_support — impulsive break |
| `price_relation` | below / continuation |
| `freefall_context` | true — clean break, no structure below |
| `nearest_structure_distance_pts` | TBD — future candle-data implementation |

> These values are Om screenshot labels, not live computed values yet.

**fvg_context:**

| Field | Value |
|---|---|
| `fvg_present` | likely — large impulse candles create imbalance |
| `fvg_direction` | bearish |
| `fvg_low` | UNKNOWN |
| `fvg_high` | UNKNOWN |
| `price_relation_to_fvg` | pullback to FVG = re-entry context |
| `fvg_rejection_confirmed` | requires lower-timeframe confirmation |

> These values are Om screenshot labels, not live computed values yet.

**news_context_detail:** UNKNOWN — candle size and speed suggest HIGH-impact event possible

**scanner_rule_learned (PROPOSED — not approved):**
- Detect `breakout_impulse`: single candle body closes beyond zone by > N pts (threshold TBD)
- Detect `news_impulse`: breakout_impulse occurring within ±60 min of known HIGH-impact news window
- `news_impulse` creates high-alert context flag — not automatic entry signal
- After `news_impulse`: wait for FVG fill or lower-TF pullback before scalp entry
- Do not trade first candle of impulse — classify as context, scan for re-entry structure

---

### Example 005

| Field | Value |
|---|---|
| `example_id` | 005 |
| `screenshot_path` | `docs/om_gold_scalp/examples/005_1h_liquidity_takeout_reversal_zone.png` |
| `timeframe` | 1H |
| `date_range_visible` | Feb 8 – Mar 3 approx — exact dates UNKNOWN |
| `session_context` | Mixed Tokyo / London / NY sessions visible |
| `news_context` | UNKNOWN |
| `move_type` | context |
| `Om bias` | Watch reversal after takeout — not automatic |
| `label` | Liquidity sweep/takeout into zone + reversal risk |
| `use` | Context only — not a direct scalp entry |
| `code_status` | proposed |

> **IMAGE FILE PENDING — Om must manually place PNG here:**
> `docs/om_gold_scalp/examples/005_1h_liquidity_takeout_reversal_zone.png`

**What Om sees:**
- Previous swing highs or lows near purple zones hold resting liquidity
- Price sweeps those levels — takes the stops sitting above/below
- Sweep alone is not a reversal — continuation is also possible
- Reversal needs: sweep into zone + rejection candle + displacement away from level
- If sweep happens into zone and price fails to continue = reversal candidate

**Om notes:**
- Previous highs/lows around purple zones are liquidity
- Price can take liquidity then reverse
- Sweep/takeout alone is not enough
- Reversal needs displacement away from the swept level
- If sweep happens into zone and fails continuation, scanner should mark reversal candidate

**zone_context:**

| Field | Value |
|---|---|
| `zone_state` | retest / failed_continuation after sweep |
| `price_relation` | at zone / rejected from zone after sweep |
| `freefall_context` | false — reversal candidate context |
| `nearest_structure_distance_pts` | TBD — future candle-data implementation |

> These values are Om screenshot labels, not live computed values yet.

**fvg_context:** Not primary focus of this example — focus is on liquidity sweep mechanics

**news_context_detail:** UNKNOWN

**scanner_rule_learned (PROPOSED — not approved):**
- Add concept `liquidity_sweep`: price wick extends beyond previous swing high/low, closes back inside
- Add concept `liquidity_takeout`: price closes beyond previous swing high/low (stronger than wick sweep)
- Add concept `fakeout`: price breaks zone/level convincingly then reverses back inside
- Add concept `reversal_candidate`: liquidity_sweep OR fakeout at zone + rejection candle + displacement away
- `reversal_candidate` alone is NOT an entry — requires lower-TF momentum confirmation (see scalp trigger examples)
- Sweep/takeout must be confirmed by displacement before scanner marks tradeable signal

---

## Core OM Concepts

> Scanner-readable definitions extracted from Om's screenshot calibration.
> All concepts are PROPOSED. None are implemented in scanner code yet.
> Approval required before any concept affects scanner logic.

| Concept | Definition |
|---|---|
| `purple_zone` | Key horizontal S/R level marked by Om on H1. Defines trade context above/below. Multiple tests = stronger zone. |
| `zone_flip` | Zone changes role: support → resistance (price breaks below) or resistance → support (price breaks above and holds). |
| `failed_reclaim` | Price retests zone from underside (below), fails to close above, rejects back down. Strengthens bearish bias. |
| `reclaim_success` | Price retests zone from underside, closes above and holds on next candle. Flips bias to bullish. |
| `freefall_context` | Price below all identified zones with no structure below. No scalp long until zone reclaim. Bearish short only on retest. |
| `fvg_magnet` | Fair value gap (price imbalance) acts as a draw/target. Price tends to return toward FVG before continuation. Not an automatic entry. |
| `fvg_rejection` | Price reaches FVG area and shows rejection (wick + body away, lower-TF confirmation). Becomes scalp entry candidate with momentum confirmation. |
| `liquidity_sweep` | Price wick extends beyond previous swing high/low (stop hunt), closes back inside the level. Does not confirm reversal alone. |
| `liquidity_takeout` | Price body closes beyond previous swing high/low. Stronger than wick sweep. Can be continuation or fakeout. |
| `breakout_impulse` | Single large candle body closes decisively beyond a zone. Creates imbalance/FVG. Do not chase — wait for pullback or FVG retest. |
| `news_impulse` | `breakout_impulse` occurring within ±60 min of HIGH-impact news window. High-alert context. Wait for structure before entry. |
| `fakeout` | Price breaks zone convincingly then reverses back inside. Traps breakout traders. Often precedes strong move in opposite direction. |
| `reversal_candidate` | `liquidity_sweep` or `fakeout` at a zone + rejection candle + displacement away from level. Needs lower-TF momentum confirmation before entry. |
| `continuation_pullback` | After a strong directional move, price pulls back partially (FVG fill, zone retest, or 50% retrace) then resumes original direction. Entry on lower-TF confirmation of resumption. |

---

---

## 15M Setup Layer — Examples 006–013

> These are 15M setup-layer examples, not execution-layer examples.
> Purpose: convert Om's visual 15M trading logic into scanner-readable proposed rules.
> All scanner_rule_learned entries are PROPOSED. None affect live scanner code.

---

### Example 006

| Field | Value |
|---|---|
| `example_id` | 006 |
| `screenshot_path` | `docs/om_gold_scalp/examples/006_15m_failed_retest_bearish_continuation.png` |
| `timeframe` | 15M |
| `layer` | setup |
| `date_range_visible` | UNKNOWN — image file pending |
| `session_context` | UNKNOWN — image file pending |
| `news_context` | UNKNOWN |
| `move_type` | setup |
| `Om bias` | Bearish — failed retest confirms zone as resistance, continuation short |
| `label` | Failed retest — bearish continuation after broken support holds as resistance |
| `use` | Setup layer — confirm trigger on 5M/1M before entry |
| `code_status` | proposed |

> **IMAGE FILE PENDING — Om must manually place PNG here:**
> `docs/om_gold_scalp/examples/006_15m_failed_retest_bearish_continuation.png`

**Om notes:**
- Purple zone breaks cleanly on 15M
- Price pulls back to underside of broken zone (retest)
- Retest candle closes with rejection — wick into zone, body stays below
- Zone confirmed as resistance — failed retest = high-quality short setup
- Entry on 5M/1M rejection candle after retest, not on the 15M candle itself

**Observed setup moments:**
- Clean break below zone (body close, not wick)
- Pullback to zone underside within 3–8 candles
- Rejection candle: wick into zone, body closes below
- 15M body stays below zone after retest — `failed_reclaim` confirmed

**Scanner-readable interpretation:**
- `zone_state = underside_retest` after `broken_support`
- Rejection: candle closes below zone after touching it from below → `failed_reclaim`
- `setup_action = WAIT_RETEST` while break is fresh but no retest yet
- `setup_action = ENTER_NOW` once retest + rejection confirmed on 5M

**Proposed scanner rules (PROPOSED — not approved):**
- If `zone_state == broken_support` AND price returns within 3 pts of zone → `zone_state = underside_retest`
- If `underside_retest` AND 15M candle closes below zone → `zone_state = failed_reclaim`
- `failed_reclaim` + bearish momentum → `setup_action = ENTER_NOW`
- If break occurred > 8 candles ago without retest → `setup_action = SKIP_CHOP`

**Action labels:**
- `ENTER_NOW` — failed retest confirmed, body below zone, trigger not extended
- `WAIT_RETEST` — break confirmed but no retest yet
- `SKIP_CHASE` — price already > 25 pts below zone without retest

---

### Example 007

| Field | Value |
|---|---|
| `example_id` | 007 |
| `screenshot_path` | `docs/om_gold_scalp/examples/007_15m_bearish_continuation_into_lower_zone.png` |
| `timeframe` | 15M |
| `layer` | setup |
| `date_range_visible` | UNKNOWN — image file pending |
| `session_context` | UNKNOWN — image file pending |
| `news_context` | UNKNOWN |
| `move_type` | setup |
| `Om bias` | Bearish continuation between zones — switch to reaction as price nears lower zone |
| `label` | Bearish continuation into lower zone — zone-to-zone move, reaction mode at target |
| `use` | Setup layer — continuation valid until lower zone, then switch to WAIT_REACTION |
| `code_status` | proposed |

> **IMAGE FILE PENDING — Om must manually place PNG here:**
> `docs/om_gold_scalp/examples/007_15m_bearish_continuation_into_lower_zone.png`

**Om notes:**
- Price in bearish continuation between two purple zones
- Upper zone confirmed as resistance, lower zone is the target
- Do not re-enter short near the lower zone — price may bounce there
- Switch from continuation mode to reaction mode as price approaches lower zone
- Target is the lower purple zone, not beyond it (initially)

**Observed setup moments:**
- Price moving down from upper zone toward lower zone
- Lower zone visible on chart within 15–40 pts
- Price within 8 pts of lower zone → mode switch to reaction

**Scanner-readable interpretation:**
- `zone_state = below_zone` (upper) + `above_zone` (lower) = continuation corridor
- `nearest_zone_distance_pts` shrinking toward lower zone
- `setup_action = WAIT_REACTION` when within 8 pts of lower zone
- Target = lower zone level (15–30 pts from entry)

**Proposed scanner rules (PROPOSED — not approved):**
- Track both nearest resistance (above) and nearest support (below) purple zones
- `continuation_mode = true` while price between two zones and trending
- `setup_action = WAIT_REACTION` when `nearest_zone_distance_pts < 8` to lower zone
- `setup_action = SKIP_NEAR_ZONE` if price already inside lower zone
- Target: lower zone center ± 3 pts — do not project beyond unless zone breaks

**Action labels:**
- `ENTER_NOW` — continuation confirmed, not near lower zone, extension < 10 pts
- `WAIT_RETEST` — large impulse, extension 10–25 pts, wait for pullback
- `WAIT_REACTION` — within 8 pts of lower zone, switch to reaction mode
- `SKIP_CHASE` — extension > 25 pts from trigger

---

### Example 008

| Field | Value |
|---|---|
| `example_id` | 008 |
| `screenshot_path` | `docs/om_gold_scalp/examples/008_15m_bullish_breakout_pullback_continuation.png` |
| `timeframe` | 15M |
| `layer` | setup |
| `date_range_visible` | UNKNOWN — image file pending |
| `session_context` | UNKNOWN — image file pending |
| `news_context` | UNKNOWN |
| `move_type` | setup |
| `Om bias` | Bullish — breakout above zone, pullback holds zone as support, continuation long |
| `label` | Bullish breakout + pullback continuation — zone flips to support after break |
| `use` | Setup layer — zone becomes support after bullish break, entry on topside retest hold |
| `code_status` | proposed |

> **IMAGE FILE PENDING — Om must manually place PNG here:**
> `docs/om_gold_scalp/examples/008_15m_bullish_breakout_pullback_continuation.png`

**Om notes:**
- Price breaks above purple zone cleanly (body close above)
- Pulls back to zone from above (topside retest)
- Zone holds as support — candle closes above zone on retest
- This is the bullish mirror of the failed retest short setup
- Entry on 5M/1M bullish candle during/after topside retest hold

**Observed setup moments:**
- Clean break above zone (body close, not just wick)
- Pullback to zone from above within 3–8 candles
- Holding candle: wick into zone, body closes above → support holding
- `zone_state = topside_retest → holding_support`

**Scanner-readable interpretation:**
- `zone_state = broken_resistance` after bullish break
- `zone_state = topside_retest` on pullback to zone from above
- `zone_state = holding_support` if candle closes above zone after retest
- `setup_action = WAIT_RETEST` after break, waiting for pullback
- `setup_action = ENTER_NOW` on confirmed topside hold (5M trigger)

**Proposed scanner rules (PROPOSED — not approved):**
- If `zone_state == broken_resistance` AND price returns within 3 pts of zone from above → `zone_state = topside_retest`
- If `topside_retest` AND 15M candle closes above zone → `zone_state = holding_support`
- `holding_support` + bullish momentum → `setup_action = ENTER_NOW` for long
- If price closes below zone during topside retest → `zone_state = failed_breakout`, reassess

**Action labels:**
- `ENTER_NOW` — topside retest + zone holding confirmed, bullish momentum
- `WAIT_RETEST` — break confirmed, waiting for pullback to zone
- `SKIP_CHASE` — price already > 25 pts above zone without pullback
- `WAIT_BREAK_CONFIRMATION` — price at zone, no clear close above yet

---

### Example 009

| Field | Value |
|---|---|
| `example_id` | 009 |
| `screenshot_path` | `docs/om_gold_scalp/examples/009_15m_sweep_reclaim_reversal_zone.png` |
| `timeframe` | 15M |
| `layer` | setup |
| `date_range_visible` | UNKNOWN — image file pending |
| `session_context` | UNKNOWN — image file pending |
| `news_context` | UNKNOWN |
| `move_type` | setup |
| `Om bias` | Reversal after sweep — short bias invalidated if zone reclaimed |
| `label` | Liquidity sweep + zone reclaim — reversal candidate |
| `use` | Setup layer — sweep alone is not reversal; reclaim confirmation required |
| `code_status` | proposed |

> **IMAGE FILE PENDING — Om must manually place PNG here:**
> `docs/om_gold_scalp/examples/009_15m_sweep_reclaim_reversal_zone.png`

**Om notes:**
- Price sweeps below purple zone (wick through, takes stops)
- Immediately reclaims zone — closes back above it
- Sweep + reclaim = stop hunt confirmed, reversal candidate
- Short bias invalidated on reclaim — do not add short positions
- If reclaim holds on next candle, bias flips to bullish for at least a reaction

**Observed setup moments:**
- Wick sweep below zone (liquidity_sweep)
- Body closes back above zone on same or next candle
- `zone_state` moves from `broken_support` to `reclaimed_zone`
- Bullish momentum resumes

**Scanner-readable interpretation:**
- `liquidity_sweep` detected: wick below zone, body closes above
- `zone_state = reclaimed_zone` after sweep + body reclaim
- Short bias suppressed after reclaim
- `setup_action = WAIT_REACTION` during sweep — no entry until close confirms direction

**Proposed scanner rules (PROPOSED — not approved):**
- `liquidity_sweep = true` if candle wick extends below zone AND body closes above zone
- `zone_state = reclaimed_zone` on sweep candle closing above zone
- `reclaimed_zone` → suppress `ENTER_NOW` for short; watch for long reaction entry
- If next candle holds above zone → `setup_action = ENTER_NOW` long (momentum confirmation)
- If next candle closes back below zone → `zone_state = failed_reclaim`, short bias resumes

**Action labels:**
- `WAIT_REACTION` — sweep in progress, no entry until close confirms direction
- `ENTER_NOW` — reclaim confirmed + next candle holds (long)
- `SKIP_CHASE` — missed reclaim, price already > 25 pts above zone

---

### Example 010

| Field | Value |
|---|---|
| `example_id` | 010 |
| `screenshot_path` | `docs/om_gold_scalp/examples/010_15m_bearish_continuation_zone_to_zone.png` |
| `timeframe` | 15M |
| `layer` | setup |
| `date_range_visible` | UNKNOWN — image file pending |
| `session_context` | UNKNOWN — image file pending |
| `news_context` | UNKNOWN |
| `move_type` | setup |
| `Om bias` | Bearish — clean zone-to-zone continuation, target is next lower zone |
| `label` | Bearish zone-to-zone continuation — structured move between defined levels |
| `use` | Setup layer — entry on pullback/retest between zones, target next zone |
| `code_status` | proposed |

> **IMAGE FILE PENDING — Om must manually place PNG here:**
> `docs/om_gold_scalp/examples/010_15m_bearish_continuation_zone_to_zone.png`

**Om notes:**
- Price broke below upper zone, now moving toward lower zone
- Market moves in levels — from one purple zone to the next
- Entry: failed retest of upper zone OR pullback within the move
- Target: lower purple zone (typically 15–30 pts away)
- Do not hold past lower zone initially — close or reduce at zone

**Observed setup moments:**
- Clear break of upper zone (broken_support)
- Price moving in structured bearish continuation
- Lower zone visible within 15–40 pts as target
- No chop — clean lower highs + lower lows

**Scanner-readable interpretation:**
- `continuation_corridor = true`: price between broken upper zone and intact lower zone
- Entry at failed retest of upper zone or pullback ≤ 50% of last leg
- Target = lower zone level
- Exit or reduce at lower zone — do not assume break until confirmed

**Proposed scanner rules (PROPOSED — not approved):**
- Compute distance between upper zone (resistance) and lower zone (support)
- If `zone_to_zone_distance_pts` between 15 and 40 → valid continuation target
- Entry: `failed_reclaim` of upper zone OR `continuation_pullback` ≤ 50% retrace
- Target: lower zone level ± 3 pts
- `setup_action = WAIT_REACTION` as price nears lower zone (within 8 pts)
- Do not set target beyond lower zone unless lower zone breaks with body close

**Action labels:**
- `ENTER_NOW` — failed retest of upper zone confirmed, lower zone visible as target
- `WAIT_RETEST` — impulse extended, wait for pullback before entry
- `WAIT_REACTION` — within 8 pts of lower zone, close or reduce, not add
- `SKIP_CHASE` — price already > 25 pts from trigger without retest

---

### Example 011

| Field | Value |
|---|---|
| `example_id` | 011 |
| `screenshot_path` | `docs/om_gold_scalp/examples/011_15m_breakdown_impulse_wait_retest.png` |
| `timeframe` | 15M |
| `layer` | setup |
| `date_range_visible` | UNKNOWN — image file pending |
| `session_context` | UNKNOWN — image file pending |
| `news_context` | UNKNOWN |
| `move_type` | setup |
| `Om bias` | Bearish — breakdown impulse, but wait for retest before entering |
| `label` | Breakdown impulse — WAIT_RETEST, do not chase |
| `use` | Setup layer — impulse creates setup context, not direct entry |
| `code_status` | proposed |

> **IMAGE FILE PENDING — Om must manually place PNG here:**
> `docs/om_gold_scalp/examples/011_15m_breakdown_impulse_wait_retest.png`

**Om notes:**
- Large 15M candle breaks through zone — strong impulse
- Do not enter immediately — price is already extended
- Wait for a retest of the broken zone from below or an FVG fill
- If impulse moved > 25 pts, classify as SKIP_CHASE — wait for full retest
- Strong impulse → WAIT_RETEST, never ENTER_NOW on the impulse candle itself

**Observed setup moments:**
- Large body candle closes decisively below zone
- Impulse candle body > 20 pts
- No immediate pullback — price extended from trigger
- FVG likely left by impulse (gap in price action)

**Scanner-readable interpretation:**
- `extension_pts` computed from trigger zone to current price
- `extension_pts > 25` → `SKIP_CHASE`
- `extension_pts 10–25` → `WAIT_RETEST`
- `breakout_impulse = true` if single candle body > 20 pts
- `fvg_relation = fvg_above` (bearish: FVG left above current price)

**Proposed scanner rules (PROPOSED — not approved):**
- Detect `breakout_impulse`: 15M candle body > 20 pts through zone (threshold TBD)
- If `breakout_impulse` AND `extension_pts > 10` → override `ENTER_NOW` to `WAIT_RETEST`
- If `extension_pts > 25` → force `SKIP_CHASE`
- After `breakout_impulse`: mark FVG zone above current price as `fvg_above`
- `setup_action = WAIT_FVG_FILL` if FVG fill not yet occurred
- `setup_action = ENTER_NOW` after FVG fill + rejection confirmed

**Action labels:**
- `WAIT_RETEST` — impulse extended 10–25 pts, wait for pullback
- `SKIP_CHASE` — impulse extended > 25 pts, do not enter
- `WAIT_FVG_FILL` — FVG left by impulse, wait for price to fill it
- `ENTER_NOW` — FVG rejected, retest confirmed, extension < 10 pts

---

### Example 012

| Field | Value |
|---|---|
| `example_id` | 012 |
| `screenshot_path` | `docs/om_gold_scalp/examples/012_15m_fvg_magnet_fill_rejection.png` |
| `timeframe` | 15M |
| `layer` | setup |
| `date_range_visible` | UNKNOWN — image file pending |
| `session_context` | UNKNOWN — image file pending |
| `news_context` | UNKNOWN |
| `move_type` | setup |
| `Om bias` | Directional bias from impulse — FVG fill + rejection confirms continuation |
| `label` | FVG magnet + fill + rejection — continuation entry after imbalance mitigation |
| `use` | Setup layer — FVG touch alone not entry; rejection required |
| `code_status` | proposed |

> **IMAGE FILE PENDING — Om must manually place PNG here:**
> `docs/om_gold_scalp/examples/012_15m_fvg_magnet_fill_rejection.png`

**Om notes:**
- Impulse move leaves FVG (imbalance / empty space) behind
- Price drawn back to FVG like a magnet before continuation
- FVG touch alone is not entry — need rejection candle inside FVG
- Rejection: wick into FVG, body closes back on original side
- If price fills FVG fully and continues through → bias may shift, reassess

**Observed setup moments:**
- Displacement candle creates visible imbalance on 15M
- Price retraces into FVG zone
- Rejection candle forms: wick into FVG, body closes below FVG (bearish) or above (bullish)
- Price resumes original direction

**Scanner-readable interpretation:**
- `fvg_relation = inside_fvg` as price enters gap
- `fvg_relation = fvg_rejected` on rejection confirmation
- `fvg_relation = fvg_accepted` if price closes fully through gap (bias shift)
- `setup_action = WAIT_FVG_FILL` while price has not yet reached FVG
- `setup_action = ENTER_NOW` on `fvg_rejected` + momentum confirmation

**Proposed scanner rules (PROPOSED — not approved):**
- Detect FVG after displacement: gap between two candle bodies with no overlap
- `fvg_relation = inside_fvg` if current price within [fvg_low, fvg_high]
- `fvg_rejected`: candle enters FVG, wick into it, body closes back outside on original side
- `fvg_accepted`: candle closes fully through FVG → reassess direction
- `setup_action = WAIT_FVG_FILL` if FVG present and price not yet at it
- `setup_action = ENTER_NOW` if `fvg_rejected` + 5M momentum aligned

**Action labels:**
- `ENTER_NOW` — FVG rejection confirmed, momentum aligned
- `WAIT_FVG_FILL` — FVG present, price has not reached it
- `SKIP_CHASE` — price already > 25 pts past FVG without retracing
- `SKIP_CHOP` — price oscillating inside FVG with no clear rejection

---

### Example 013

| Field | Value |
|---|---|
| `example_id` | 013 |
| `screenshot_path` | `docs/om_gold_scalp/examples/013_15m_zone_magnet_reclaim_continuation.png` |
| `timeframe` | 15M |
| `layer` | setup |
| `date_range_visible` | UNKNOWN — image file pending |
| `session_context` | UNKNOWN — image file pending |
| `news_context` | UNKNOWN |
| `move_type` | setup |
| `Om bias` | Bullish — zone acts as magnet, price reclaims it, continuation long |
| `label` | Zone magnet + reclaim + continuation — bullish recovery after reclaim success |
| `use` | Setup layer — reclaim success flips bias; continuation entry after hold confirmed |
| `code_status` | proposed |

> **IMAGE FILE PENDING — Om must manually place PNG here:**
> `docs/om_gold_scalp/examples/013_15m_zone_magnet_reclaim_continuation.png`

**Om notes:**
- Zone acts as a magnet — price gravitates toward it even after breaking away
- Price reclaims zone from below and holds above it
- Reclaim success = bullish bias confirmed, short bias invalidated
- Enter long on first pullback after reclaim hold is confirmed
- Target: next higher purple zone

**Observed setup moments:**
- Price below zone initially (broken zone or below support)
- Zone acts as draw — price moves up toward zone
- Price closes above zone and holds on next candle
- `zone_state = reclaimed_zone`

**Scanner-readable interpretation:**
- Zone as magnet: nearest zone level is a price draw target
- `zone_state = reclaimed_zone` after close above + hold
- Short signals suppressed; long entry after hold confirmed
- `setup_action = ENTER_NOW` on pullback after reclaim hold

**Proposed scanner rules (PROPOSED — not approved):**
- If zone was previously `broken_support` AND price closes above → `zone_state = reclaimed_zone`
- `reclaimed_zone` + next candle holds above → `reclaim_confirmed = true`
- `reclaim_confirmed` → suppress all short signals for this zone
- `setup_action = ENTER_NOW` on first pullback to zone after reclaim (topside retest hold)
- If price fails to hold and closes back below → `zone_state = failed_reclaim`, short bias resumes

**Action labels:**
- `ENTER_NOW` — reclaim confirmed + pullback holds above zone (bullish)
- `WAIT_RETEST` — reclaim confirmed, waiting for first pullback to zone
- `WAIT_REACTION` — price at zone, no close confirmation yet
- `SKIP_CHASE` — price already > 25 pts above zone after reclaim without pullback

---

## 15M Setup Layer Rules — PROPOSED

> All rules below are PROPOSED. Not implemented in scanner code.
> Approval required before any rule affects scanner logic.
> Thresholds are initial estimates — subject to calibration from Om-approved examples.

---

### zone_state enum

Tracks the current relationship between price and a purple zone on 15M.

| State | Definition |
|---|---|
| `above_zone` | Price trading above zone, zone below as support |
| `below_zone` | Price trading below zone, zone above as resistance |
| `inside_zone` | Price within zone boundaries — chop or decision mode |
| `holding_support` | Price at zone from above, bouncing up — support holding |
| `rejecting_resistance` | Price at zone from below, rejecting down — resistance holding |
| `broken_support` | Price closed below zone with body conviction — support lost |
| `broken_resistance` | Price closed above zone with body conviction — resistance cleared |
| `underside_retest` | After `broken_support`, price returns to zone from below |
| `topside_retest` | After `broken_resistance`, price returns to zone from above |
| `reclaimed_zone` | Price closed above previously broken zone + held next candle |
| `failed_reclaim` | Price touched zone from below, rejected, closed back below |
| `decision_chop` | Price oscillating inside zone > 3 candles with no directional conviction |

---

### setup_action enum

The scanner's recommended action for the current 15M setup state.

| Action | Definition |
|---|---|
| `ENTER_NOW` | Setup confirmed, trigger not extended (< 10 pts), momentum aligned. Use 5M/1M for precise entry. |
| `WAIT_RETEST` | Impulse move occurred but extended 10–25 pts. Wait for pullback or zone retest. |
| `WAIT_FVG_FILL` | FVG present in path. Price has not reached it. Wait for FVG touch before evaluating entry. |
| `WAIT_REACTION` | Price approaching next purple zone (within 8 pts). Switch to reaction mode. |
| `WAIT_BREAK_CONFIRMATION` | Chop resolving or zone being tested. Wait for clear directional close. |
| `SKIP_CHASE` | Price extended > 25 pts from trigger zone. Do not enter. |
| `SKIP_CHOP` | Price oscillating inside zone with no direction. No entry until resolution. |
| `SKIP_NEAR_ZONE` | Price inside or within 5 pts of zone center with no momentum. Too close to zone for clean scalp. |

---

### chase filter

Prevents entry when price has moved too far from the trigger zone.

| Field | Value |
|---|---|
| `max_chase_pts` | 25 pts — if extension > 25 pts, force `SKIP_CHASE` |
| `wait_retest_range_pts` | 10–25 pts — downgrade `ENTER_NOW` to `WAIT_RETEST` |
| `enter_now_max_extension_pts` | 10 pts — only allow `ENTER_NOW` if extension < 10 pts |
| `extended_move_pts` | 40 pts — large impulse, freefall context, no entry |

---

### fvg_relation enum

Tracks price relationship to the most recent relevant FVG.

| State | Definition |
|---|---|
| `no_fvg` | No FVG detected in the relevant range |
| `fvg_above` | FVG exists above current price — acts as resistance / draw |
| `fvg_below` | FVG exists below current price — acts as support / draw |
| `inside_fvg` | Current price within FVG boundaries |
| `fvg_filled` | Price passed through FVG fully — no longer a magnet |
| `fvg_rejected` | Price entered FVG, rejection candle confirmed, back to original side |
| `fvg_accepted` | Price entered FVG and closed fully through — bias may shift |

---

### reaction-zone logic

When price approaches the next identified purple zone:

1. Compute `nearest_zone_distance_pts` = distance to nearest zone in scalp direction
2. If `nearest_zone_distance_pts < 8` → set `setup_action = WAIT_REACTION`
3. If `nearest_zone_distance_pts < 5` → set `setup_action = SKIP_NEAR_ZONE`
4. After price reaches zone: evaluate `zone_state` on close of next 15M candle
5. `holding_support` or `rejecting_resistance` → allow reaction entry on 5M confirmation
6. `broken_support` or `broken_resistance` → new continuation direction, reset setup

| Threshold | Value |
|---|---|
| `reaction_zone_distance_pts` | 8 pts |
| `near_zone_distance_pts` | 5 pts |

---

### continuation setup logic

For price moving between zones in a clear directional trend:

1. H1 context must confirm direction (from 1H screenshot examples 001–005)
2. 15M trend must align — lower highs + lower lows (bearish) or higher lows + higher highs (bullish)
3. Entry only on: break + retest + rejection OR FVG fill + rejection OR impulse continuation within 10 pts
4. Not extended (`extension_pts < 10` for `ENTER_NOW`, < 25 for `WAIT_RETEST`)
5. Not near next zone (`nearest_zone_distance_pts > 8`)
6. Not in chop (`decision_chop = false`)
7. Target: 15–30 pts primary, max 40 pts initially

| Threshold | Value |
|---|---|
| `ideal_target_pts` | 15–30 |
| `max_target_pts_initial` | 40 |
| `max_chase_pts` | 25 |
| `extended_move_pts` | 40 |
| `near_zone_distance_pts` | 5 |
| `reaction_zone_distance_pts` | 8 |

---

---

## 5M Trigger Layer — Examples 014–021

> These are 5M trigger-layer examples.
> Purpose: identify exact entry candle conditions, multi-setup routing, and skip/wait logic at the 5M level.
> All scanner_rule_learned entries are PROPOSED. None affect live scanner code.

---

### Example 014

| Field | Value |
|---|---|
| `example_id` | 014 |
| `screenshot_path` | `docs/om_gold_scalp/examples/014_5m_failed_reclaim_short_retest_continuation_long_reversal.png` |
| `timeframe` | 5M |
| `layer` | trigger |
| `date_range_visible` | UNKNOWN |
| `session_context` | UNKNOWN |
| `news_context` | UNKNOWN |
| `move_type` | dual — short continuation / long reversal |
| `Om bias` | Short on failed reclaim; flip long on lower zone sweep + reclaim |
| `label` | Failed reclaim short continuation → lower zone sweep → long reversal |
| `use` | Trigger layer — entry logic for both short continuation and long reversal flip |
| `code_status` | proposed |

**Om notes:**
- Price attempts to reclaim a broken zone from below — fails, closes back below
- Failed reclaim on 5M confirms short continuation — enter or add short
- Price then sweeps the lower purple zone (liquidity_sweep)
- If sweep is followed by reclaim of lower zone from below → flip to long reversal
- Two distinct setups on same chart — scanner must evaluate separately

**Observed setup moments:**
- Failed reclaim: wick into zone, body closes below → short continuation entry
- Lower zone sweep: wick below lower zone, body reclaims → long reversal setup
- Each setup has its own SL and TP

**om_zone_context:**

| Field | Value |
|---|---|
| `upper_zone_state` | broken_support → failed_reclaim (resistance confirmed) |
| `lower_zone_state` | liquidity_sweep → reclaimed_zone (support candidate) |
| `price_relation` | below upper zone / at lower zone |
| `freefall_context` | true during short phase; reversing during long phase |
| `fvg_nearby` | likely — impulse legs create imbalance |
| `fvg_direction` | bearish (short phase) → bullish (long phase) |

**trade_lifecycle:**

| Label | Description |
|---|---|
| Short entry | Failed reclaim of upper zone confirmed on 5M |
| Short SL | Above upper zone (above failed reclaim wick high) |
| Short TP | Lower zone level (15–30 pts) |
| Long flip | Lower zone sweep + reclaim confirmed on 5M |
| Long SL | Below lower zone (below sweep wick low) |
| Long TP | Back toward upper zone or next resistance (15–25 pts) |

**scanner_rule_learned (PROPOSED — not approved):**
- `failed_reclaim` on 5M + body below zone → `setup_action = ENTER_NOW` (short)
- Short SL = upper zone high + buffer (2 pts)
- After short TP hit or lower zone reached: switch evaluation to `liquidity_sweep` check
- `liquidity_sweep` at lower zone + body reclaim → flip bias to long, `setup_action = ENTER_NOW` (long)
- Scanner must not stay in short-continuation mode after lower zone sweep reclaim

**Action labels:**
- `ENTER_NOW` (short) — failed reclaim confirmed
- `ENTER_NOW` (long) — lower zone sweep + reclaim confirmed
- `WAIT_RETEST` — break confirmed but retest not yet occurred
- `SKIP_CHASE` — extended > 25 pts from trigger

---

### Example 015

| Field | Value |
|---|---|
| `example_id` | 015 |
| `screenshot_path` | `docs/om_gold_scalp/examples/015_5m_zone_reclaim_bullish_continuation_multi_tp.png` |
| `timeframe` | 5M |
| `layer` | trigger |
| `date_range_visible` | UNKNOWN |
| `session_context` | UNKNOWN |
| `news_context` | UNKNOWN |
| `move_type` | long continuation |
| `Om bias` | Bullish — zone reclaimed, hold for multiple TP levels |
| `label` | Zone reclaim bullish continuation — multi-TP structure |
| `use` | Trigger layer — entry after zone reclaim, scale out at TP1/TP2/TP3 |
| `code_status` | proposed |

**Om notes:**
- Price reclaims purple zone on 5M (closes above and holds)
- Bullish continuation — do not exit the full position at first target
- Multiple TP levels: TP1 (15 pts), TP2 (25 pts), TP3 (35–40 pts)
- Partial exit at TP1, hold runner to TP2/TP3
- Don't exit too early on a strong reclaim move — let momentum play out

**Observed setup moments:**
- Zone reclaim: 5M body closes above zone and holds
- Long entry on first pullback or confirmation candle after reclaim
- TP1 at nearest resistance (15 pts)
- TP2 at next purple zone (25 pts)
- TP3 at extended zone or session high (35–40 pts)

**om_zone_context:**

| Field | Value |
|---|---|
| `zone_state` | reclaimed_zone → holding_support |
| `price_relation` | above reclaimed zone |
| `freefall_context` | false — bullish continuation |
| `fvg_nearby` | possible below (created during break down before reclaim) |
| `fvg_direction` | bullish |

**trade_lifecycle:**

| Label | Description |
|---|---|
| Long entry | Zone reclaim + hold confirmed on 5M |
| SL | Below reclaimed zone (below zone low − 2 pts buffer) |
| TP1 | +15 pts from entry (partial exit) |
| TP2 | +25 pts from entry (partial exit) |
| TP3 | +35–40 pts from entry (runner / full close) |

**scanner_rule_learned (PROPOSED — not approved):**
- `zone_state = reclaimed_zone` + hold confirmation → `setup_action = ENTER_NOW` (long)
- Output TP1, TP2, TP3 as separate target levels based on next identified zones
- TP1 = nearest resistance (15 pts floor)
- TP2 = next purple zone above (25 pts floor)
- TP3 = extended target (capped at 40 pts initially)
- Scanner should flag multi-TP structure when zone distance supports it

**Action labels:**
- `ENTER_NOW` — reclaim + hold confirmed, momentum bullish
- `WAIT_RETEST` — reclaim occurred but no pullback hold yet
- `SKIP_CHASE` — price > 25 pts above zone without pullback

---

### Example 016

| Field | Value |
|---|---|
| `example_id` | 016 |
| `screenshot_path` | `docs/om_gold_scalp/examples/016_5m_trend_long_pullback_reentry_short_skip.png` |
| `timeframe` | 5M |
| `layer` | trigger |
| `date_range_visible` | UNKNOWN |
| `session_context` | UNKNOWN |
| `news_context` | UNKNOWN |
| `move_type` | trend long + countertrend short skip |
| `Om bias` | Bullish trend — longs on pullback valid; countertrend shorts skip unless strong confirmation |
| `label` | Trend long pullback reentry — countertrend short skip |
| `use` | Trigger layer — long reentries in trend; skip shorts against trend unless confirmed |
| `code_status` | proposed |

**Om notes:**
- Price in clear bullish trend on 5M (higher highs + higher lows)
- Pullback to zone or EMA = long reentry opportunity
- Countertrend shorts are low probability — skip unless strong rejection + displacement
- Do not force shorts just because price pulled back into zone from above
- Zone holds from above (topside retest) = long, not short

**Observed setup moments:**
- Bullish trend structure: higher highs + higher lows
- Pullback to purple zone from above (topside retest)
- Zone holds → long reentry
- No short unless: full break below zone + body close + displacement

**om_zone_context:**

| Field | Value |
|---|---|
| `zone_state` | topside_retest → holding_support |
| `price_relation` | above zone / pulling back to zone from above |
| `freefall_context` | false — bullish trend |
| `fvg_nearby` | possible below zone from prior leg |
| `fvg_direction` | bullish |

**trade_lifecycle:**

| Label | Description |
|---|---|
| Long reentry | Topside retest + zone holds on 5M |
| Long SL | Below zone low − 2 pts buffer |
| Long TP | Next resistance / previous high (15–25 pts) |
| Short skip | Price at zone but trend is bullish → skip short unless full break + displacement |

**scanner_rule_learned (PROPOSED — not approved):**
- Detect trend bias: `h1_bias = bullish` + `m15_structure = higher_highs_higher_lows`
- In bullish trend: `topside_retest` + `holding_support` → `setup_action = ENTER_NOW` (long)
- In bullish trend: short setup at zone → `setup_action = SKIP_CHOP` unless `broken_support` + displacement > 15 pts
- Countertrend short requires: full body close below zone + `breakout_impulse` flag
- Default in trending market: align with trend, skip countertrend signals

**Action labels:**
- `ENTER_NOW` (long) — topside retest holds, bullish trend confirmed
- `SKIP_CHOP` (short) — trend is bullish, countertrend short not confirmed
- `WAIT_BREAK_CONFIRMATION` — zone being tested, no clear direction yet

---

### Example 017

| Field | Value |
|---|---|
| `example_id` | 017 |
| `screenshot_path` | `docs/om_gold_scalp/examples/017_5m_range_breakdown_short_then_long_reversal.png` |
| `timeframe` | 5M |
| `layer` | trigger |
| `date_range_visible` | UNKNOWN |
| `session_context` | UNKNOWN |
| `news_context` | UNKNOWN |
| `move_type` | short breakdown → long reversal flip |
| `Om bias` | Short on range breakdown; flip long after lower sweep + reclaim |
| `label` | Range breakdown short → lower zone sweep → long reversal |
| `use` | Trigger layer — short on breakdown, flip long after sweep reclaim at lower level |
| `code_status` | proposed |

**Om notes:**
- Price ranging between two zones
- Range breaks down — short setup triggered
- Price reaches lower zone, sweeps below it (liquidity_takeout)
- Lower zone reclaimed → flip bias from short continuation to long reversal
- Scanner must exit short mode and enter long evaluation after sweep reclaim

**Observed setup moments:**
- Range breakdown: price closes below lower range boundary
- Short entry on breakdown or failed reclaim of range low
- Price sweeps below lower purple zone
- Sweep + reclaim → long reversal, short bias invalidated

**om_zone_context:**

| Field | Value |
|---|---|
| `upper_zone_state` | broken_support (range high → resistance) |
| `lower_zone_state` | liquidity_sweep → reclaimed_zone |
| `price_relation` | below range low → at lower zone |
| `freefall_context` | true during short phase |
| `fvg_nearby` | likely — created during breakdown leg |
| `fvg_direction` | bearish (short) → bullish (long flip) |

**trade_lifecycle:**

| Label | Description |
|---|---|
| Short entry | Range breakdown confirmed, body below range low |
| Short SL | Above range low (failed break invalidation) |
| Short TP | Lower purple zone level |
| Long flip | Lower zone sweep + reclaim on 5M |
| Long SL | Below sweep wick low − 2 pts |
| Long TP | Back toward range mid or range high (15–30 pts) |

**scanner_rule_learned (PROPOSED — not approved):**
- Detect range: price oscillating between zone_high and zone_low for ≥ 5 candles
- `range_breakdown = true` if 5M body closes below range low zone
- `setup_action = ENTER_NOW` (short) on range breakdown confirmation
- At lower zone: check for `liquidity_sweep` + reclaim
- `liquidity_sweep` + reclaim → suppress short continuation, evaluate long
- `setup_action = ENTER_NOW` (long) after lower zone reclaim confirmed

**Action labels:**
- `ENTER_NOW` (short) — range breakdown confirmed
- `ENTER_NOW` (long) — lower zone sweep + reclaim confirmed
- `WAIT_REACTION` — at lower zone, no sweep/reclaim confirmation yet
- `SKIP_CHASE` — extended > 25 pts from breakdown trigger

---

### Example 018

| Field | Value |
|---|---|
| `example_id` | 018 |
| `screenshot_path` | `docs/om_gold_scalp/examples/018_5m_news_breakdown_fakeout_reclaim_long_impulse.png` |
| `timeframe` | 5M |
| `layer` | trigger |
| `date_range_visible` | UNKNOWN |
| `session_context` | UNKNOWN |
| `news_context` | HIGH-impact event likely — news-style displacement visible |
| `move_type` | news impulse → fakeout → reclaim → long impulse |
| `Om bias` | Initial short bias from breakdown; flip long on strong reclaim impulse after fakeout |
| `label` | News breakdown fakeout + reclaim → long impulse |
| `use` | Trigger layer — news displacement can fake direction; strong reclaim impulse flips bias |
| `code_status` | proposed |

**Om notes:**
- News event causes large displacement candle breaking structure
- Price briefly breaks below zone — appears bearish
- But reclaim comes fast and strong (large bullish candle through zone)
- Fakeout confirmed: short bias was a trap
- Strong reclaim impulse = long bias, continuation long
- Do not fight the reclaim impulse — it is stronger than the initial breakdown

**Observed setup moments:**
- News impulse: large candle breaks zone (bearish displacement)
- `fakeout` detected: price immediately reclaims zone with equal or larger bullish candle
- Reclaim body close above zone + momentum → long entry
- `news_impulse` flag active throughout

**om_zone_context:**

| Field | Value |
|---|---|
| `zone_state` | broken_support (briefly) → reclaimed_zone (fakeout confirmed) |
| `price_relation` | above zone after reclaim |
| `freefall_context` | false — fakeout, not continuation breakdown |
| `fvg_nearby` | likely — news displacement creates imbalance |
| `fvg_direction` | bullish (after reclaim) |
| `news_impulse` | true |

**trade_lifecycle:**

| Label | Description |
|---|---|
| Initial short (avoid) | News breakdown — do not enter short on first candle |
| Fakeout confirmation | Strong reclaim candle closes above zone |
| Long entry | First pullback after reclaim or continuation of reclaim impulse |
| Long SL | Below fakeout wick low − 2 pts |
| Long TP | Next resistance (15–25 pts) |

**scanner_rule_learned (PROPOSED — not approved):**
- `news_impulse = true` if displacement occurs within ±60 min of HIGH-impact event
- On `news_impulse`: do not auto-enter short on first candle — wait for confirmation
- `fakeout = true` if price breaks zone AND reclaims within 3 candles with body close above
- `fakeout` + `reclaimed_zone` → suppress short, `setup_action = ENTER_NOW` (long)
- `news_impulse` flag should add caution period: wait 1–2 candles before entry decision

**Action labels:**
- `WAIT_BREAK_CONFIRMATION` — news impulse active, do not enter on first candle
- `ENTER_NOW` (long) — fakeout confirmed, reclaim body close above zone
- `SKIP_CHASE` — reclaim impulse already > 25 pts, wait for pullback

---

### Example 019

| Field | Value |
|---|---|
| `example_id` | 019 |
| `screenshot_path` | `docs/om_gold_scalp/examples/019_5m_multi_setup_zone_to_zone_s1_s2_l1_l2.png` |
| `timeframe` | 5M |
| `layer` | trigger |
| `date_range_visible` | UNKNOWN |
| `session_context` | UNKNOWN |
| `news_context` | UNKNOWN |
| `move_type` | multi-setup — S1, S2, L1, L2 |
| `Om bias` | Multiple directional setups on one chart — each tracked independently |
| `label` | Multi-setup zone-to-zone — S1/S2 (shorts), L1/L2 (longs), each with own SL/TP |
| `use` | Trigger layer — scanner must track multiple sequential setup opportunities |
| `code_status` | proposed |

**Om notes:**
- One chart can contain multiple valid setups in sequence
- S1: first short opportunity (break + retest)
- S2: second short opportunity (continuation or second failed reclaim)
- L1: first long opportunity (lower zone reclaim or sweep reversal)
- L2: second long opportunity (continuation of L1 or second zone reclaim)
- Each has its own entry, SL, TP — they do not share risk parameters
- Scanner must not stay locked in one setup mode after SL or TP hit

**Observed setup moments:**
- S1: first broken support + failed reclaim → short
- S2: second rejection at resistance zone → short continuation or reentry
- L1: lower zone sweep + reclaim → long reversal
- L2: long continuation after L1 TP1 hit, pullback reentry

**om_zone_context:**

| Field | Value |
|---|---|
| `upper_zone_state` | broken_support → resistance (S1/S2 context) |
| `lower_zone_state` | liquidity_sweep → reclaimed_zone (L1/L2 context) |
| `price_relation` | moves between zones across all 4 setups |
| `fvg_nearby` | likely between zones |
| `fvg_direction` | bearish (S1/S2) → bullish (L1/L2) |

**trade_lifecycle:**

| Label | Description |
|---|---|
| S1 entry | First failed reclaim of upper zone |
| S1 SL | Above upper zone high + 2 pts |
| S1 TP | Lower zone level |
| S2 entry | Second rejection at resistance (after S1 TP or S1 SL) |
| S2 SL | Above rejection wick high + 2 pts |
| S2 TP | Lower zone or new low |
| L1 entry | Lower zone sweep + reclaim confirmed |
| L1 SL | Below sweep wick low − 2 pts |
| L1 TP1 | +15 pts / L1 TP2: +25 pts |
| L2 entry | L1 TP1 hit → pullback to reclaimed lower zone → reentry long |
| L2 SL | Below lower zone − 2 pts |
| L2 TP | Next resistance (upper zone direction) |

**scanner_rule_learned (PROPOSED — not approved):**
- Scanner must track setup_sequence: `[S1, S2, L1, L2]` as independent evaluations
- After each TP/SL: reset setup_action and re-evaluate current zone_state
- `S1` and `S2` share same upper zone context but are separate entries
- `L1` and `L2` share same lower zone context but are separate entries
- Never assume previous setup is still active after TP or SL hit
- Output: up to 4 concurrent setup candidates per zone pair per scan

**Action labels:**
- `ENTER_NOW` (S1/S2) — failed reclaim / rejection at upper zone confirmed
- `ENTER_NOW` (L1) — lower zone sweep + reclaim confirmed
- `ENTER_NOW` (L2) — L1 TP hit, pullback to lower zone holds
- `WAIT_RETEST` — setup forming, retest not yet confirmed
- `SKIP_CHASE` — extended > 25 pts from trigger

---

### Example 020

| Field | Value |
|---|---|
| `example_id` | 020 |
| `screenshot_path` | `docs/om_gold_scalp/examples/020_5m_range_chop_wait_skip_level_reactions.png` |
| `timeframe` | 5M |
| `layer` | trigger |
| `date_range_visible` | UNKNOWN |
| `session_context` | UNKNOWN — session boxes visible |
| `news_context` | UNKNOWN |
| `move_type` | chop / no trade |
| `Om bias` | No trade — choppy around EMA and session boxes, no clear displacement |
| `label` | Range chop — WAIT or SKIP, no entry, level reactions only |
| `use` | Trigger layer — chop detection, suppress all entry signals |
| `code_status` | proposed |

**Om notes:**
- Price oscillating around EMA and session box boundaries
- No clear displacement in either direction
- Multiple level reactions but no follow-through
- EMA 200 acting as chop zone midpoint — not directional
- Session boxes (Tokyo/London/NY) showing range behavior
- Do not trade chop — wait for breakout of range or displacement candle

**Observed setup moments:**
- Price ranging inside session box boundaries
- No candle body closes decisively outside range
- EMA 200 flat or slightly sloping — price crossing it multiple times
- Multiple small bounces at zone levels without continuation

**om_zone_context:**

| Field | Value |
|---|---|
| `zone_state` | decision_chop — price inside zone/range with no direction |
| `price_relation` | at EMA / inside session box / at zone |
| `freefall_context` | false |
| `fvg_nearby` | possibly small FVGs but no significant imbalance |
| `fvg_direction` | mixed |

**trade_lifecycle:**

| Label | Description |
|---|---|
| All entries | SKIP or WAIT — no valid trigger |
| Condition to re-evaluate | Displacement candle breaks session box / zone with body close |

**scanner_rule_learned (PROPOSED — not approved):**
- `decision_chop = true` if: last 5 candles all within same 15 pt range AND no body outside zone
- `session_box_chop = true` if price oscillating within session high/low boundaries without breakout
- `ema_chop = true` if price crossed EMA 200 more than 3 times in last 10 candles
- Any of the above → `setup_action = SKIP_CHOP`
- Reset when: 5M body closes > 5 pts outside session box OR displacement candle > 15 pts

**Action labels:**
- `SKIP_CHOP` — price choppy inside range/session box/EMA zone
- `WAIT_BREAK_CONFIRMATION` — range tightening, watch for breakout candle
- `ENTER_NOW` — only after clear breakout body close + displacement confirmed

---

### Example 021

| Field | Value |
|---|---|
| `example_id` | 021 |
| `screenshot_path` | `docs/om_gold_scalp/examples/021_5m_bearish_breakdown_retest_continuation.png` |
| `timeframe` | 5M |
| `layer` | trigger |
| `date_range_visible` | UNKNOWN |
| `session_context` | UNKNOWN |
| `news_context` | UNKNOWN |
| `move_type` | bearish continuation — breakdown + retest |
| `Om bias` | Bearish — below EMA 200 + failed retest/reclaim + displacement = short continuation |
| `label` | Bearish breakdown retest continuation — below EMA 200, pullbacks are short opportunities |
| `use` | Trigger layer — short continuation below EMA, pullbacks = reentry not reversal |
| `code_status` | proposed |

**Om notes:**
- Price below EMA 200 on 5M — macro bearish context
- Price breaks below zone, retests zone from below (underside_retest)
- Retest fails (failed_reclaim) → short continuation confirmed
- Every pullback is a short reentry opportunity, not a reversal
- Only flip bias if price reclaims zone AND holds above EMA 200

**Observed setup moments:**
- Price below EMA 200 (bearish macro context)
- Zone breakdown: body close below zone
- Retest: price returns to zone underside
- Failed reclaim: body closes back below → short continuation
- Bearish displacement candle confirms direction

**om_zone_context:**

| Field | Value |
|---|---|
| `zone_state` | broken_support → underside_retest → failed_reclaim |
| `price_relation` | below zone / below EMA 200 |
| `freefall_context` | true — below all structure |
| `fvg_nearby` | likely above (created during breakdown) |
| `fvg_direction` | bearish |
| `ema200_relation` | below_ema200 |

**trade_lifecycle:**

| Label | Description |
|---|---|
| Short entry | Failed retest confirmed, body below zone |
| Short SL | Above zone high + 2 pts (above failed reclaim) |
| Short TP | Next lower zone or structure level (15–30 pts) |
| Pullback reentry | Pullback to zone → short reentry (not reversal) |
| Reversal condition | Only if price closes above zone AND above EMA 200 and holds |

**scanner_rule_learned (PROPOSED — not approved):**
- `below_ema200` + `failed_reclaim` + bearish displacement → `setup_action = ENTER_NOW` (short)
- Every pullback to zone while `below_ema200` → treat as short reentry opportunity, not long
- `reversal_condition = true` only if: body closes above zone AND above EMA 200 AND holds next candle
- Until `reversal_condition`, `setup_action` for long = `SKIP_CHOP` or `WAIT_BREAK_CONFIRMATION`
- Short SL = zone high + 2 pts; TP = next structure below (15–30 pts)

**Action labels:**
- `ENTER_NOW` (short) — failed retest below EMA 200 confirmed
- `WAIT_RETEST` — breakdown confirmed, no retest yet
- `SKIP_CHOP` (long) — price below EMA 200, long not valid yet
- `WAIT_BREAK_CONFIRMATION` (long) — watching for reclaim above zone + EMA 200

---

## Paired 1H / 5M Context-Execution — Examples 022–025

These four examples come in two pairs. Each pair shows the 1H context map alongside the 5M execution view of the same price action. They teach the scanner how higher-timeframe zones define magnets and bias, while 5M confirms whether to enter, wait, flip, or skip.

---

### Example 022

- **example_id:** 022
- **timeframe:** 1H
- **layer:** context
- **paired_with:** 023 (5M execution view of this same context)
- **screenshot_path:** `docs/om_gold_scalp/examples/022_1h_multi_zone_context_breakdown_sweep_reclaim_map.png`

**Om notes:**
- Multi-zone 1H map. Several HTF zones stacked above and below current price.
- Price breaks down through an upper zone, travels toward a lower support, then later sweeps and reclaims.
- 1H zones are the battlefield — they define directional magnets, not instant entries.
- A 1H zone touch is never an entry by itself; it sets the bias and target for lower-timeframe execution.

**Observed setup moments:**
- Upper zone acts as resistance / breakdown level
- Price travels through the gap toward lower zone
- Lower zone shows sweep + reclaim reaction
- 1H structure remains the magnet map — no execution decisions made at this layer

**om_zone_context:**

| Field | Value |
|---|---|
| `zone_state` | broken_resistance (upper) → magnet pull → sweep + reclaim (lower) |
| `price_relation` | between stacked HTF zones |
| `htf_zone_count` | multi (≥ 2 active zones) |
| `htf_role` | upper = resistance/broken, lower = support/magnet |
| `bias_source` | 1H zone map defines directional bias |

**scanner_rule_learned (PROPOSED — not approved):**
- 1H multi-zone state populates `htf_zone_map` audit field with each zone's price, type, and last interaction.
- 1H touches alone never set `setup_action = ENTER_NOW`. They only set bias and magnet targets for 5M.
- After 1H breakdown of an upper zone, the next lower 1H zone becomes the magnet target until proven otherwise.
- Reclaim of a broken 1H zone flips bias; failed reclaim confirms continuation toward lower magnet.

**Action labels:**
- `BIAS_ONLY` — 1H context, no entry trigger at this layer
- Pairs with Example 023 for execution

---

### Example 023

- **example_id:** 023
- **timeframe:** 5M
- **layer:** execution
- **paired_with:** 022 (1H context map for this execution)
- **screenshot_path:** `docs/om_gold_scalp/examples/023_5m_upper_zone_rejection_short_to_lower_zone_sweep_reclaim_long.png`

**Om notes:**
- 5M view of the same price action mapped on 1H (022).
- Upper-zone rejection on 5M → short continuation toward lower-zone magnet.
- Lower-zone sweep + reclaim on 5M → flip bias to long only AFTER reclaim is confirmed.
- The scanner must not flip long on first touch of the lower zone — wait for sweep + reclaim signature.

**Observed setup moments:**
- Upper zone touch + rejection candle on 5M → short entry
- Continuation pullbacks during travel = short reentries, not reversals
- Lower zone sweep (wick into zone) → not yet a long
- Reclaim candle (body closes back above sweep level) → long flip valid

**om_zone_context:**

| Field | Value |
|---|---|
| `zone_state` | upper: rejecting_resistance → lower: liquidity_sweep → reclaimed_zone |
| `price_relation` | traveling between HTF zones |
| `ema200_relation` | follows 5M EMA 200 — short while below, long after reclaim above |
| `reaction_signature` | wick into lower zone + body close back inside = reclaim confirmation |

**trade_lifecycle:**

| Label | Description |
|---|---|
| Short entry | Upper zone rejection candle on 5M |
| Short SL | Upper zone high + 2 pts |
| Short TP | Lower zone (1H magnet from 022) |
| Long entry | Lower zone sweep + reclaim candle close |
| Long SL | Below sweep wick low + 2 pts |
| Long TP | Mid-range or upper zone underside |

**scanner_rule_learned (PROPOSED — not approved):**
- `rejecting_resistance` at HTF upper zone → `setup_action = ENTER_NOW` (short) when 5M body confirms rejection.
- `liquidity_sweep` at HTF lower zone alone → `setup_action = WAIT_REACTION` (no entry yet).
- `liquidity_sweep` + `reclaimed_zone` at HTF lower zone → `setup_action = ENTER_NOW` (long flip).
- First touch of a lower zone is never an instant long — sweep + reclaim signature is required.
- Bias derives from paired 1H context (Example 022) — 5M cannot override 1H magnet direction without reclaim proof.

**Action labels:**
- `ENTER_NOW` (short) — upper zone rejection on 5M
- `WAIT_REACTION` — first touch of lower zone, no reclaim yet
- `ENTER_NOW` (long) — lower zone sweep + reclaim confirmed
- `SKIP_CHASE` — entering long mid-travel before sweep/reclaim signature

---

### Example 024

- **example_id:** 024
- **timeframe:** 1H
- **layer:** context
- **paired_with:** 025 (5M execution view of this same context)
- **screenshot_path:** `docs/om_gold_scalp/examples/024_1h_context_repeated_support1_breakdown_to_support2_magnet.png`

**Om notes:**
- 1H context showing Support 1 tested multiple times, then breaking down toward Support 2.
- A repeatedly tested support weakens. Each test absorbs buyers and exposes the zone to a clean break.
- Once Support 1 breaks AND fails to reclaim, Support 2 becomes the next 1H magnet.
- Do not long a broken support just because price returns to it — once broken, treat it as resistance until reclaimed cleanly.

**Observed setup moments:**
- Multiple 1H touches at Support 1 (3+ tests in this example)
- Eventual breakdown candle through Support 1
- Failed reclaim attempt at Support 1 from underside
- Continuation toward Support 2 magnet

**om_zone_context:**

| Field | Value |
|---|---|
| `zone_state` | Support 1: support → broken_support → underside_retest → failed_reclaim |
| `zone_tests_count` | Support 1 ≥ 3 (weakened) |
| `htf_role` | Support 1 = old support / now resistance; Support 2 = active magnet |
| `bias_source` | 1H breakdown + failed reclaim = bearish bias toward Support 2 |

**scanner_rule_learned (PROPOSED — not approved):**
- Track `zone_tests_count` per HTF zone in audit. ≥ 3 tests = `zone_strength_decay = true`.
- Once a weakened support breaks, `zone_role_flip` activates: old support becomes resistance.
- Failed reclaim at old support → set `htf_magnet` to the next lower 1H zone (Support 2).
- Repeated test count is a leading indicator of breakdown risk — do not weight first touch the same as fourth touch.

**Action labels:**
- `BIAS_ONLY` — 1H context, no entry trigger at this layer
- Pairs with Example 025 for execution

---

### Example 025

- **example_id:** 025
- **timeframe:** 5M
- **layer:** execution
- **paired_with:** 024 (1H context map for this execution)
- **screenshot_path:** `docs/om_gold_scalp/examples/025_5m_from_024_failed_reclaim_support1_short_to_support2.png`

**Om notes:**
- 5M view of the same price action mapped on 1H (024).
- After Support 1 breakdown, 5M shows failed reclaim attempt — body cannot close back above Support 1.
- Failed reclaim confirms short continuation toward Support 2.
- Do not long the return to Support 1. Once broken, it is resistance. Short on reclaim failure.

**Observed setup moments:**
- 5M breakdown candle through Support 1 (matches 1H breakdown)
- Pullback to Support 1 from underside (underside_retest)
- Reclaim attempt fails — body closes below Support 1 again
- Continuation move toward Support 2

**om_zone_context:**

| Field | Value |
|---|---|
| `zone_state` | broken_support → underside_retest → failed_reclaim |
| `price_relation` | below Support 1, traveling to Support 2 |
| `ema200_relation` | below_ema200 throughout |
| `htf_magnet` | Support 2 (from 024 context) |

**trade_lifecycle:**

| Label | Description |
|---|---|
| Short entry | Failed reclaim of Support 1 confirmed (body closes below after retest) |
| Short SL | Above Support 1 high + 2 pts (above failed reclaim wick) |
| Short TP | Support 2 (1H magnet from 024) — 15–30 pts |
| Pullback reentry | Any pullback to Support 1 underside = short reentry, not long |
| Reversal condition | Body closes above Support 1 AND holds = invalidates short setup |

**scanner_rule_learned (PROPOSED — not approved):**
- `underside_retest` + `failed_reclaim` at a recently broken HTF zone → `setup_action = ENTER_NOW` (short).
- Long entries at a recently broken support are filtered out unless `reclaimed_zone` AND `body_close_above` AND `holds_next_candle` are all true.
- Target = next lower HTF zone (Support 2) from paired 1H context.
- Pullbacks during continuation are reentries in the same direction, not reversals.

**Action labels:**
- `ENTER_NOW` (short) — failed reclaim of Support 1
- `SKIP_CHASE` (long) — touch of broken Support 1 from below without reclaim
- `WAIT_BREAK_CONFIRMATION` (long) — would require clean reclaim above Support 1 + EMA 200

---

## 1H → 5M Pair Logic — PROPOSED

Derived from Examples 022–025. These rules apply across all paired context-execution examples and govern how the scanner uses HTF context to qualify or disqualify 5M triggers.

- **1H defines zones, magnets, and major bias.** It does not generate entries.
- **5M confirms execution.** Entries fire on 5M only when the trigger aligns with 1H bias or with a clean 1H flip signal.
- **A zone touch alone is not an entry.** Touch sets attention; entry requires a confirmation signature on 5M.
- **Reclaim = possible reversal.** A clean reclaim of a broken zone (body close back inside + hold) flips bias.
- **Failed reclaim = continuation.** An underside retest that closes back through the broken side confirms continuation in the breakdown direction.
- **Repeated support tests weaken the level.** `zone_tests_count ≥ 3` raises breakdown risk and lowers the long entry priority at that zone.
- **After breakdown, old support becomes resistance** unless reclaimed cleanly. Long entries at a recently broken support are filtered out until reclaim is proven.
- **Lower HTF zone becomes magnet after failed reclaim.** Once Support 1 fails to reclaim, Support 2 (next 1H zone) becomes the active `htf_magnet` target.

**Audit fields proposed (for paired logic):**

| Field | Purpose |
|---|---|
| `htf_zone_map` | List of active 1H zones with price, type, last interaction |
| `htf_magnet` | Current directional target derived from 1H state |
| `zone_tests_count` | Per-zone touch counter (≥ 3 = weakened) |
| `zone_strength_decay` | Bool — true when repeated tests weaken the level |
| `zone_role_flip` | Bool — true when broken support is now acting as resistance |
| `paired_context_id` | Cross-reference to the 1H example backing this 5M trigger |

---

## Paired 15M / 5M News-Displacement Context-Execution — Examples 026–027

This pair shows how the scanner must read 15M as a structural map and 5M as the execution trigger when a news impulse distorts the chart. The lesson: a news displacement candle is not an entry — it is a re-bias event that must be confirmed by structure before any scalp.

---

### Example 026

- **example_id:** 026
- **timeframe:** 15M
- **layer:** context
- **paired_with:** 027 (5M execution view of this same context)
- **screenshot_path:** `docs/om_gold_scalp/examples/026_15m_sr_retest_failed_breakout_news_sweep_context.png`

**Om notes:**
- S/R band on 15M was respected by multiple touches before any directional resolution.
- Price attempted a breakout above resistance but failed to hold the higher level — body could not close and accept above.
- News / liquidity-style displacement candle pushed price down sharply, away from the band.
- Lower purple zone became the active downside magnet during the displacement.
- Later, structure changed again when price reclaimed the broken resistance and accepted above it — bias flipped from bearish back to bullish.
- The 15M layer is the map. Each phase (respect → failed breakout → displacement → reclaim) sets a different 5M execution context.

**Observed setup moments:**
- Repeated touches at the same S/R band (zone respected, accumulating tests)
- Failed breakout attempt: wick beyond resistance, body close back inside
- News/displacement candle: oversized body, range expansion in one direction
- Lower purple zone reached as displacement magnet
- Later reclaim: body close back above broken resistance + acceptance candle

**om_zone_context:**

| Field | Value |
|---|---|
| `zone_state` | sr_band: respected → failed_breakout → broken_support (post-displacement) → reclaimed_zone (later) |
| `zone_tests_count` | sr_band ≥ 3 before displacement (weakened) |
| `displacement_source` | news / liquidity (range expansion candle) |
| `htf_magnet` | lower purple zone during displacement; flips to upside on reclaim |
| `bias_source` | 15M structure — phase-dependent (bearish during displacement, bullish after reclaim) |

**scanner_rule_learned (PROPOSED — not approved):**
- 15M `zone_tests_count ≥ 3` raises breakdown probability — treat next failed breakout as a setup signal, not noise.
- `displacement_source = news` candle on 15M sets `news_impulse = true` and locks `setup_action = WAIT_REACTION` on 5M for N bars (proposed: 3 bars).
- Failed breakout = wick above resistance + body close back inside the band → bias remains range until break confirms.
- Reclaim of broken resistance + acceptance candle flips `htf_magnet` to upside and clears `news_impulse` lock.
- 15M does not generate entries on this example — it sets the phase-dependent execution context for 5M.

**Action labels:**
- `BIAS_ONLY` — 15M context, no entry trigger at this layer
- Pairs with Example 027 for execution

---

### Example 027

- **example_id:** 027
- **timeframe:** 5M
- **layer:** execution
- **paired_with:** 026 (15M context map for this execution)
- **screenshot_path:** `docs/om_gold_scalp/examples/027_5m_news_breakdown_retest_resistance_then_bullish_breakout.png`

**Om notes:**
- Do NOT enter immediately on the news displacement candle. That is `chase_entry` → `SKIP_CHASE`.
- Wait for 3-candle continuation OR structure confirmation before short scalp.
- If price retests broken support (now resistance) and cannot break back above, short scalp is valid toward lower magnet.
- If price later breaks back above resistance AND retests AND accepts, the bearish idea is invalidated — long continuation becomes valid.
- Scanner must distinguish a news impulse (one expansion candle, unconfirmed) from a structural breakdown (impulse + confirmation + failed reclaim).

**Observed setup moments:**
- News displacement candle on 5M (oversized body) — no entry yet
- 3-candle continuation in the displacement direction = first valid short trigger
- Retest of old support (now resistance) from below: wick into level, body close back below = short scalp valid
- Later: 5M reclaim of resistance + acceptance candle + retest from above that holds → long continuation trigger
- The same level acts as resistance during one phase and as support after reclaim — phase, not price, defines the scalp

**om_zone_context:**

| Field | Value |
|---|---|
| `zone_state` | broken_support → underside_retest → failed_reclaim (short phase) → reclaimed_zone → topside_retest (long phase) |
| `news_impulse` | true during displacement; cleared after structural confirmation |
| `confirmation_signal` | 3-candle continuation OR underside_retest + failed_reclaim |
| `ema200_relation` | below_ema200 during short phase; above_ema200 after reclaim |
| `paired_context_id` | 026 |

**trade_lifecycle:**

| Label | Description |
|---|---|
| News candle | Observation only — no entry |
| Short entry (phase 1) | After 3-candle continuation OR retest of old support that fails to reclaim |
| Short SL | Above failed reclaim wick + 2 pts |
| Short TP | Lower purple zone (15M magnet from 026) |
| Reclaim invalidation | Body close above old resistance + acceptance candle = exit short, no new short |
| Long entry (phase 2) | Retest of reclaimed level from above + body close holds → long scalp |
| Long SL | Below retest wick + 2 pts |
| Long TP | Next 15M structure level above |

**scanner_rule_learned (PROPOSED — not approved):**
- `news_impulse = true` locks `setup_action = WAIT_REACTION` on the first displacement candle. No `ENTER_NOW` until confirmation.
- Confirmation = `three_candle_continuation = true` OR (`underside_retest = true` AND `failed_reclaim = true`).
- On confirmation in the displacement direction → `setup_action = ENTER_NOW` (continuation scalp).
- `reclaimed_zone = true` AND `topside_retest = true` AND `body_holds_next_candle = true` → flip bias, `setup_action = ENTER_NOW` opposite direction.
- Without confirmation, treat the displacement as chop and skip — `setup_action = SKIP_CHASE`.
- A single news candle is never an entry. The scanner must wait for structural proof to separate impulse from continuation.

**Action labels:**
- `WAIT_REACTION` — news candle just printed, no confirmation yet
- `ENTER_NOW` (short) — 3-candle continuation OR failed reclaim of old support confirmed
- `SKIP_CHASE` — entering on the displacement candle itself before confirmation
- `ENTER_NOW` (long) — reclaim of resistance + topside retest + acceptance
- `BIAS_FLIP` — when reclaim invalidates the prior short phase

---

## News-Displacement Logic — PROPOSED

Derived from Examples 026–027. Applies whenever a news or liquidity-style displacement candle appears on 15M or 5M.

- **News displacement is a re-bias event, not an entry.** The first oversized candle sets attention, never `ENTER_NOW`.
- **Confirmation is required.** Either `three_candle_continuation` OR (`underside_retest` + `failed_reclaim`) must be true before an entry fires in the displacement direction.
- **Old support becomes resistance immediately after displacement breakdown** — until reclaim is proven, longs at that level are filtered out.
- **Reclaim flips bias cleanly.** Body close back above + retest from above that holds = the short phase is invalidated, long continuation becomes valid.
- **Same level, different phase, opposite scalp.** The scanner must phase-track the level, not just its price.
- **Scanner must not confuse news impulse with structural continuation.** One candle is impulse; impulse + confirmation is continuation.

**Audit fields proposed (for news-displacement logic):**

| Field | Purpose |
|---|---|
| `news_impulse` | Bool — true on detection of displacement candle |
| `three_candle_continuation` | Bool — true when 3 consecutive bars extend the displacement |
| `confirmation_signal` | Enum: `three_candle_continuation` / `failed_reclaim` / `none` |
| `displacement_source` | Enum: `news` / `liquidity` / `unknown` |
| `bias_flip_event` | Bool — true when reclaim invalidates the prior phase |

---

## Paired 15M / 5M Range-Break Failed-Reclaim Context-Execution — Examples 028–029

This pair teaches that candle appearance alone does not trigger an entry. A green candle that cannot reclaim is bearish. A red candle that holds structure is continuation. Zone behavior and follow-through — not bar color or size — decide the scalp.

---

### Example 028

- **example_id:** 028
- **timeframe:** 15M
- **layer:** context
- **paired_with:** 029 (5M execution view of this same context)
- **screenshot_path:** `docs/om_gold_scalp/examples/028_15m_range_support_break_failed_reclaim_bearish_continuation.png`

**Om notes:**
- 15M shows a range support / S-R zone that held repeatedly before resolving.
- Support eventually breaks — but the initial bearish candle alone is not the entry trigger.
- Scanner must wait for either reclaim failure or continuation confirmation on the lower timeframe before sizing the idea.
- A break candle without follow-through is a fake-break risk. Follow-through is what separates fakeout from continuation.
- After the failed reclaim, structure prints lower highs → bearish continuation confirmed.

**Observed setup moments:**
- Range support tested multiple times before resolution
- Breakdown candle through support (body close below)
- Reclaim attempt: price returns to support from below
- Reclaim fails: body close back below the broken level
- Lower-high continuation on 15M → bearish bias locked in

**om_zone_context:**

| Field | Value |
|---|---|
| `zone_state` | range_support: holding_support → broken_support → underside_retest → failed_reclaim |
| `support_hold_failed` | true |
| `reclaim_attempt` | true |
| `reclaim_failed` | true |
| `follow_through_confirmed` | true (lower-high prints after reclaim failure) |
| `htf_magnet` | next 15M structure level below |
| `bias_source` | 15M structure — bearish after failed reclaim + lower high |

**scanner_rule_learned (PROPOSED — not approved):**
- 15M `support_hold_failed = true` alone does not arm `ENTER_NOW` — only sets `setup_action = WAIT_REACTION`.
- Confirmation requires `reclaim_attempt = true` AND `reclaim_failed = true`, OR `follow_through_confirmed = true` (lower high after break).
- Without confirmation, treat the break candle as fakeout risk — `setup_action = WAIT_REACTION`.
- After confirmation, 15M sets `bias_source = bearish` and `htf_magnet` to the next lower 15M structure level for 5M execution.
- 15M does not generate entries on this example — it sets context for paired 5M trigger.

**Action labels:**
- `BIAS_ONLY` — 15M context, no entry trigger at this layer
- Pairs with Example 029 for execution

---

### Example 029

- **example_id:** 029
- **timeframe:** 5M
- **layer:** execution
- **paired_with:** 028 (15M context map for this execution)
- **screenshot_path:** `docs/om_gold_scalp/examples/029_5m_from_028_failed_reclaim_short_entry_continuation.png`

**Om notes:**
- Execution view of the 028 breakdown.
- Support fails on 5M. A green candle prints that LOOKS healthy — but it cannot reclaim or hold above the broken level.
- A red candle prints that has `low_momentum_candle` appearance — but structure remains bearish (lower high, body close below).
- Candle appearance alone is misleading. The trigger is zone behavior: did the reclaim attempt succeed, or did it fail?
- Short entry is valid only after failed reclaim or lower-high continuation — NOT on the first breakdown candle impulse.
- This is the textbook example of `candle_strength_mismatch` — bar color and body size do not match the structural reality.

**Observed setup moments:**
- 5M breakdown candle through support (matches 15M break)
- Green retest candle into broken support — body cannot close back above
- Red continuation candle — body holds below the broken level
- Structure: lower high prints on 5M → continuation entry confirmed
- Short entry on the close of the lower-high continuation candle

**om_zone_context:**

| Field | Value |
|---|---|
| `zone_state` | broken_support → underside_retest → failed_reclaim |
| `support_hold_failed` | true |
| `reclaim_attempt` | true (green candle into level) |
| `reclaim_failed` | true (body could not close above) |
| `candle_strength_mismatch` | true — green looked strong but failed structurally; red looked weak but held bias |
| `follow_through_confirmed` | true (lower high after retest failure) |
| `continuation_entry` | true |
| `htf_context_id` | 028 |
| `execution_pair_id` | 029 |
| `paired_context_id` | 028 |
| `ema200_relation` | below_ema200 |

**trade_lifecycle:**

| Label | Description |
|---|---|
| Breakdown candle | Observation only — no entry on first impulse |
| Reclaim attempt | Green retest candle into broken support |
| Failed reclaim | Body close back below broken level — confirms bearish |
| Short entry | After failed reclaim AND lower high on 5M |
| Short SL | Above failed reclaim wick / above the reclaim attempt high + 2 pts |
| Short TP | Next 15M structure level below (htf_magnet from 028) |
| Invalidation | Body close back above broken support + acceptance candle |

**scanner_rule_learned (PROPOSED — not approved):**
- 5M `setup_action = ENTER_NOW` (short) requires: `support_hold_failed = true` AND (`reclaim_failed = true` OR `follow_through_confirmed = true`).
- First breakdown candle alone → `setup_action = WAIT_REACTION`. Never enter on the impulse bar.
- `candle_strength_mismatch = true` audit flag set when bar color/size contradicts structural state — used as a calibration metric, not an entry gate.
- A reclaim attempt is judged by close, not by wick or body size. Wick above the broken level + body close below = `reclaim_failed = true`.
- `continuation_entry = true` requires a lower high after `reclaim_failed`. Until then, hold at `WAIT_REACTION`.
- Bias and target derive from paired 15M context (Example 028) — 5M cannot generate this trigger without the 15M map.

**Action labels:**
- `WAIT_REACTION` — breakdown printed, no reclaim attempt or follow-through yet
- `ENTER_NOW` (short) — failed reclaim + lower-high continuation confirmed
- `SKIP_CHASE` — entering on the first breakdown candle before confirmation
- `BIAS_FLIP` — body close back above broken support + acceptance candle = invalidate short

---

## Range-Break Failed-Reclaim Logic — PROPOSED

Derived from Examples 028–029. Applies to any range support or S-R zone that breaks down on 15M and requires 5M confirmation before entry.

- **A break candle alone is not an entry.** First breakdown bar sets attention, never `ENTER_NOW`.
- **Confirmation has two valid forms:** reclaim attempt that fails (`reclaim_failed = true`), OR follow-through that prints a lower high (`follow_through_confirmed = true`).
- **Candle color and size do not trigger.** A green retest candle that cannot reclaim is bearish. A red continuation candle that holds structure is bearish continuation.
- **The reclaim is judged by close, not by wick.** Wick into the broken level + body close below = failure.
- **15M owns context, 5M owns execution.** Bias and target come from the 15M map; entry signature comes from 5M zone behavior.
- **No entry without follow-through.** `continuation_entry = true` is the gate; until then, hold at `WAIT_REACTION`.

**Audit fields proposed (for range-break failed-reclaim logic):**

| Field | Purpose |
|---|---|
| `support_hold_failed` | Bool — true when a previously respected support breaks |
| `reclaim_attempt` | Bool — true when price returns to broken level from below |
| `reclaim_failed` | Bool — true when reclaim body close cannot hold above |
| `candle_strength_mismatch` | Bool — bar color/size contradicts structural state (calibration metric) |
| `follow_through_confirmed` | Bool — true when a lower high (or higher low) prints after the break |
| `continuation_entry` | Bool — true when all confirmation conditions for entry are met |
| `htf_context_id` | ID of the HTF example providing context (e.g. 028) |
| `execution_pair_id` | ID of the LTF example providing the trigger (e.g. 029) |

---

## Paired 15M / 5M Countertrend-Green-Failure Context-Execution — Examples 030–031

This pair teaches that green candles with `single_candle_strength` inside a bearish context are NOT bullish signals on their own. Reclaim + hold + follow-through is required to flip bias. Until then, every bullish pullback is a `countertrend_attempt_failed` candidate → continuation-short reentry opportunity, not a long.

---

### Example 030

- **example_id:** 030
- **timeframe:** 15M
- **layer:** context
- **paired_with:** 031 (5M execution view of this same context)
- **screenshot_path:** `docs/om_gold_scalp/examples/030_15m_broken_support_countertrend_green_failure_continuation.png`

**Om notes:**
- 15M shows a broken support / S-R zone where price attempts recovery with green candles that show `single_candle_strength`.
- The green candles look strong individually — but price fails to reclaim and hold above the broken support / structure.
- Red candles that follow may present as `low_momentum_candle` at first, but structure remains bearish because reclaim never succeeded (`reclaim_failed`).
- Scanner must NOT judge candle color or size alone — structural acceptance is the trigger, not bar appearance.
- Countertrend green inside bearish context = `low_confidence_setup` + `avoid_entry`. Treat as continuation reentry zone unless reclaim + hold + follow-through confirms reversal.
- Bias on 15M remains bearish throughout. The next lower 15M structure level stays as the active magnet.

**Observed setup moments:**
- Prior breakdown through 15M support → broken_support state established
- Recovery attempt: one or more green candles with `single_candle_strength` pushing into the broken level
- Reclaim attempt fails — body cannot close back above and hold
- Red follow-through prints, structure preserved as bearish (no higher high)
- Continuation toward lower 15M magnet resumes

**om_zone_context:**

| Field | Value |
|---|---|
| `zone_state` | broken_support → underside_retest → countertrend_green_attempt → reclaim_failed |
| `broken_support_context` | true (prior 15M break still active) |
| `countertrend_green_attempt` | true (green with `single_candle_strength` pushing into the broken level) |
| `reclaim_failed` | true (body close cannot hold above) |
| `bearish_context_preserved` | true (no higher high printed; structure intact) |
| `htf_magnet` | next lower 15M structure level |
| `bias_source` | 15M structure — bearish remains valid despite countertrend appearance |

**scanner_rule_learned (PROPOSED — not approved):**
- 15M `broken_support_context = true` + `countertrend_green_attempt = true` does NOT arm a long trigger by itself.
- Bias only flips when `reclaim_failed = false` AND body holds above the broken level AND follow-through prints a higher high.
- While `bearish_context_preserved = true`, every countertrend green is treated as a continuation-short reentry zone for 5M.
- The size or color of a single candle is not a structural signal — only acceptance above the broken level is.
- 15M does not generate entries on this example — it sets the context for paired 5M trigger.

**Action labels:**
- `BIAS_ONLY` — 15M context, no entry trigger at this layer
- Pairs with Example 031 for execution

---

### Example 031

- **example_id:** 031
- **timeframe:** 5M
- **layer:** execution
- **paired_with:** 030 (15M context map for this execution)
- **screenshot_path:** `docs/om_gold_scalp/examples/031_5m_from_030_failed_bullish_pullback_short_continuation.png`

**Om notes:**
- Execution view of the 030 context.
- 5M shows bullish pullback attempts with green candles that have `single_candle_strength` — but each attempt fails to reclaim and hold above the broken structure (`countertrend_attempt_failed`).
- EMA 200 and structure on 5M stay bearish throughout the recovery attempts.
- Continuation short remains the higher-probability trade. Every failed bullish pullback is a reentry short, not a reversal long.
- This is the textbook `candle_strength_mismatch`: a healthy bullish candle CAN still lose when HTF structure and zone behavior remain bearish.
- Do NOT take the long off the green candle alone. Wait for failure proof, then short the continuation.

**Observed setup moments:**
- 5M pullback prints green candles with `single_candle_strength` into the broken support / structure
- Pullback fails: body cannot close above broken level OR EMA 200 OR prior swing high
- Red continuation candle prints, structure remains bearish
- Lower-high or equal-high forms — `bullish_pullback_failed = true`
- Short entry valid on close of the failed-pullback continuation candle

**om_zone_context:**

| Field | Value |
|---|---|
| `zone_state` | broken_support → underside_retest → countertrend_green_attempt → reclaim_failed |
| `broken_support_context` | true (from 030) |
| `countertrend_green_attempt` | true (5M pullback green) |
| `reclaim_failed` | true |
| `bullish_pullback_failed` | true |
| `candle_strength_mismatch` | true — green appeared strong, structure says otherwise |
| `bearish_context_preserved` | true (no 5M higher high, below EMA 200) |
| `continuation_short_valid` | true |
| `ema200_relation` | below_ema200 |
| `htf_context_id` | 030 |
| `execution_pair_id` | 031 |
| `paired_context_id` | 030 |

**trade_lifecycle:**

| Label | Description |
|---|---|
| Countertrend green pullback | Observation only — no long entry on appearance |
| Reclaim check | Did body close hold above broken level + EMA 200? If no → reclaim_failed |
| Failed pullback confirm | Lower-high or equal-high after the green attempt |
| Short entry | Close of the failed-pullback continuation candle |
| Short SL | Above the highest pullback wick + 2 pts |
| Short TP | Next 15M structure level below (htf_magnet from 030) |
| Reversal condition | Body close above broken level + EMA 200 + higher high — invalidates short |

**scanner_rule_learned (PROPOSED — not approved):**
- 5M long entry requires ALL of: `reclaim_failed = false`, body holds above broken level, holds above EMA 200, higher high prints. Missing any → long skipped.
- 5M `setup_action = ENTER_NOW` (short) requires: `broken_support_context = true` AND `bullish_pullback_failed = true` AND `bearish_context_preserved = true`.
- `candle_strength_mismatch = true` audit flag fires whenever a pullback candle with `single_candle_strength` is followed by structural failure. Used as calibration metric only, not entry gate.
- Every countertrend green inside a bearish context becomes a `continuation_short_valid` candidate once the pullback proves it cannot reclaim.
- Bias and target derive from paired 15M context (Example 030) — 5M does not invalidate 15M bias without full reversal proof.

**Action labels:**
- `WAIT_REACTION` — countertrend green printed, no pullback failure confirmed yet
- `ENTER_NOW` (short) — bullish pullback failed + bearish context preserved
- `SKIP_CHASE` (long) — entering long on the green pullback candle alone, without reclaim proof
- `BIAS_FLIP` — reclaim succeeds + higher high prints + body holds above EMA 200

---

## Countertrend-Green-Failure Logic — PROPOSED

Derived from Examples 030–031. Applies whenever a bullish pullback appears inside an established bearish context (broken support, below EMA 200).

- **Candle color and size are not signals.** A green with `single_candle_strength` inside bearish context is a setup for a continuation short, not a long.
- **Reversal requires structural acceptance.** Reclaim + hold above broken level + hold above EMA 200 + higher high — all four must be true to flip bias.
- **Failed pullback = continuation short.** Once `bullish_pullback_failed = true` and `bearish_context_preserved = true`, the short reentry trigger arms.
- **HTF context wins ties.** When 15M says bearish and 5M prints countertrend green, the 5M trigger only fires shorts (or skips). Long requires full HTF flip.
- **`candle_strength_mismatch` is a learning metric.** It tracks how often appearance contradicts structural outcome — used to calibrate weight of bar-appearance features in scoring.
- **No long inside bearish HTF without reclaim proof.** This is the rule that prevents chasing pullbacks.

**Audit fields proposed (for countertrend-green-failure logic):**

| Field | Purpose |
|---|---|
| `broken_support_context` | Bool — true while a prior support break remains unreclaimed |
| `countertrend_green_attempt` | Bool — true on green with `single_candle_strength` into broken level inside bearish context |
| `reclaim_failed` | Bool — body cannot close and hold above broken level |
| `bullish_pullback_failed` | Bool — lower or equal high after countertrend green |
| `candle_strength_mismatch` | Bool — bar color/size contradicts structural outcome (calibration metric) |
| `bearish_context_preserved` | Bool — no higher high, structure remains bearish |
| `continuation_short_valid` | Bool — true when all confirmation conditions for short reentry are met |
| `htf_context_id` | ID of the HTF example providing context (e.g. 030) |
| `execution_pair_id` | ID of the LTF example providing the trigger (e.g. 031) |

---

## Paired 15M / 5M Decision-Zone Consolidation Context-Execution — Examples 032–033

This pair teaches that a purple HTF zone is a decision zone, not an automatic entry. Consolidation around the zone means wait. The valid trigger is either a sweep + reclaim + follow-through, OR a break + failed reclaim + continuation. Anything in between is middle-of-range risk and should be skipped.

---

### Example 032

- **example_id:** 032
- **timeframe:** 15M
- **layer:** context
- **paired_with:** 033 (5M execution view of this same context)
- **screenshot_path:** `docs/om_gold_scalp/examples/032_15m_support_resistance_consolidation_failed_hold_to_support2.png`

**Om notes:**
- 15M shows price spending time around a purple support/resistance zone.
- Consolidation and messy failed attempts cluster around the level — not a clean instant entry area.
- The zone behaves as a decision zone: price can fake below, fake above, consolidate, then later reveal direction.
- Once the upper support/resistance area cannot hold, Support 2 (lower zone) becomes the downside magnet.
- 15M does not generate entries on this example — it sets the decision context for 5M execution.

**Observed setup moments:**
- Multiple touches at the purple zone with no clean resolution (consolidation_at_zone)
- Wicks on both sides of the zone — fake breakouts and fake breakdowns
- Eventual failure to hold the zone — body close below sustained
- Support 2 magnet activates as the next downside target

**om_zone_context:**

| Field | Value |
|---|---|
| `zone_state` | purple_zone: holding_support / rejecting_resistance → decision_chop → broken_support |
| `htf_zone_type` | purple support/resistance band |
| `decision_zone` | true (consolidation + mixed reaction at zone) |
| `consolidation_at_zone` | true (multiple bars with overlap inside zone) |
| `failed_support_hold` | true (zone could not hold after consolidation) |
| `support2_magnet` | true (lower zone activates as downside target) |
| `htf_magnet` | Support 2 |
| `bias_source` | 15M — undecided during consolidation, bearish after zone fails |

**scanner_rule_learned (PROPOSED — not approved):**
- Purple HTF zone → `decision_zone = true` by default; treat as `BIAS_ONLY` until structural confirmation.
- `consolidation_at_zone = true` + no sweep/reclaim signature → `setup_action = WAIT_REACTION` for 5M.
- Valid resolution triggers are only: (a) sweep + reclaim + follow-through, OR (b) break + failed reclaim + continuation.
- When the upper zone fails to hold, `support2_magnet = true` arms and `htf_magnet` flips to the next lower zone.
- 15M does not generate entries here — it sets the gating context for paired 5M trigger.

**Action labels:**
- `BIAS_ONLY` — 15M context, no entry trigger at this layer
- Pairs with Example 033 for execution

---

### Example 033

- **example_id:** 033
- **timeframe:** 5M
- **layer:** execution
- **paired_with:** 032 (15M context map for this execution)
- **screenshot_path:** `docs/om_gold_scalp/examples/033_5m_from_032_liquidity_sweep_reclaim_then_failed_support_breakdown.png`

**Om notes:**
- Entries must be identified from level behavior — not candle appearance alone.
- First valid trigger: liquidity sweep + reclaim on the lower edge, then follow-through up = scalp long.
- Later: support breaks, attempts to reclaim, fails — bearish continuation toward Support 2.
- Middle-of-range entries between the two triggers are `low_confidence_setup` + `avoid_entry` — `middle_range_risk = true`, skip.
- The scanner must wait for one of two clean signatures (sweep+reclaim OR break+failed-reclaim). Anything else is `SKIP_CHOP` or `SKIP_CHASE`.

**Observed setup moments:**
- Liquidity sweep below the lower edge of the zone (wick takes prior low)
- Reclaim candle: body closes back above the swept level
- Follow-through bar holds above — long scalp valid
- Later: support break, body close below the zone
- Reclaim attempt fails — body cannot hold back above
- Continuation candle prints toward Support 2 magnet

**om_zone_context:**

| Field | Value |
|---|---|
| `zone_state` | liquidity_sweep → reclaimed_zone → topside_retest (phase 1) → broken_support → failed_reclaim (phase 2) |
| `liquidity_sweep_before_move` | true (phase 1 trigger) |
| `failed_support_hold` | true (phase 2 setup) |
| `failed_reclaim` | true (phase 2 confirmation) |
| `support2_magnet` | true (target for phase 2 short) |
| `middle_range_risk` | true (between phase 1 long and phase 2 short — skip zone) |
| `entry_quality` | high at sweep+reclaim and at failed-reclaim signatures; low elsewhere |
| `skip_reason` | mid_range_no_confirmation (whenever neither signature is active) |
| `ema200_relation` | depends on phase — above_ema200 during long phase, below_ema200 during short phase |
| `htf_context_id` | 032 |
| `execution_pair_id` | 033 |
| `paired_context_id` | 032 |

**trade_lifecycle:**

| Label | Description |
|---|---|
| Phase 1 long entry | Sweep below lower edge + reclaim body close + follow-through bar holds |
| Phase 1 long SL | Below sweep wick + 2 pts |
| Phase 1 long TP | Upper edge of zone or next 15M structure above (15–30 pts) |
| Middle-range zone | No entry — `SKIP_CHOP` until next clean signature |
| Phase 2 short entry | Support break + reclaim attempt + failed reclaim body close |
| Phase 2 short SL | Above failed reclaim wick + 2 pts |
| Phase 2 short TP | Support 2 (htf_magnet from 032) — 15–30 pts |
| Invalidation | Reclaim succeeds + body holds above broken support → cancel short |

**scanner_rule_learned (PROPOSED — not approved):**
- `setup_action = ENTER_NOW` (long) fires only when `liquidity_sweep_before_move = true` AND `reclaimed_zone = true` AND follow-through bar holds.
- `setup_action = ENTER_NOW` (short) fires only when `failed_support_hold = true` AND `failed_reclaim = true`.
- `middle_range_risk = true` forces `setup_action = SKIP_CHOP` regardless of candle strength or trend slope.
- `entry_quality` audit field rates each candidate trigger high / medium / low based on signature cleanness; low → skip.
- `skip_reason` audit field records the explicit reason for any skip (mid_range_no_confirmation / chase_distance / sl_too_wide / no_signature).
- Bias and target derive from paired 15M context (Example 032). Support 2 magnet is honored only after upper zone failure.

**Action labels:**
- `ENTER_NOW` (long) — sweep + reclaim + follow-through at lower edge
- `ENTER_NOW` (short) — break + failed reclaim of support
- `SKIP_CHOP` — middle-of-range, no clean signature
- `SKIP_CHASE` — entering after price has already moved most of the distance to the next level
- `WAIT_REACTION` — consolidation at the decision zone, no signature yet
- `BIAS_FLIP` — reclaim succeeds and holds, invalidating the short setup

---

## Decision-Zone Consolidation Logic — PROPOSED

Derived from Examples 032–033. Applies whenever a purple HTF zone or S/R band shows consolidation, mixed reactions, and no immediate directional resolution.

- **Purple HTF zone = decision zone, not auto entry.** Treat the zone as `BIAS_ONLY` until structural confirmation appears.
- **Consolidation means wait.** Multiple touches with overlap and no clean rejection = `WAIT_REACTION`.
- **Two valid resolution signatures, no others:**
  1. Sweep + reclaim + follow-through (entry in reclaim direction)
  2. Break + failed reclaim + continuation (entry in break direction)
- **Strong candle in the middle is noise.** A big body bar between the two signatures is `middle_range_risk = true` — skip.
- **Fast break-and-return = possible sweep / fakeout.** Body close back inside within one or two bars = treat as sweep, not breakout.
- **Failed reclaim of broken support = continuation valid.** Once the upper zone cannot hold, Support 2 becomes the active magnet.
- **Mark low-confidence conditions explicitly.** `middle_range_risk = true` and `skip_reason = mid_range_no_confirmation` (with `avoid_entry = true`) must be logged so the audit shows the scanner saw the setup and chose to skip.

**Audit fields proposed (for decision-zone consolidation logic):**

| Field | Purpose |
|---|---|
| `htf_zone_type` | Enum: purple_zone / sr_band / fvg / order_block / etc. |
| `decision_zone` | Bool — true when zone behavior is mixed (both sides reacting) |
| `consolidation_at_zone` | Bool — multiple bars overlapping inside or at the zone |
| `liquidity_sweep_before_move` | Bool — sweep signature precedes the directional move |
| `failed_support_hold` | Bool — previously respected support cannot hold after consolidation |
| `failed_reclaim` | Bool — reclaim attempt body close cannot hold (already defined; reused here) |
| `support2_magnet` | Bool — next lower HTF zone is the active downside magnet |
| `middle_range_risk` | Bool — entry would land between the two clean signatures |
| `entry_quality` | Enum: high / medium / low — based on signature cleanness |
| `skip_reason` | Enum: mid_range_no_confirmation / chase_distance / sl_too_wide / no_signature / consolidation |
| `htf_context_id` | ID of the HTF example providing context (e.g. 032) |
| `execution_pair_id` | ID of the LTF example providing the trigger (e.g. 033) |

---

## Paired 15M / 5M Impulse-Exhaustion Context-Execution — Examples 034–035

This pair teaches that a clean bullish impulse is not permission to keep buying. Once price reaches the upper liquidity / prior-high area and starts consolidating, long bias must be retired. Failed push higher after consolidation flips the read to bearish continuation, even if the bearish move is slow.

---

### Example 034

- **example_id:** 034
- **timeframe:** 15M
- **layer:** context
- **paired_with:** 035 (5M execution view of this same context)
- **screenshot_path:** `docs/om_gold_scalp/examples/034_15m_clean_bullish_impulse_exhaustion_to_bearish_continuation.png`

**Om notes:**
- 15M shows a clean bullish impulse from a low origin — valid long context while the move has room.
- The lesson is not "keep buying longs." Once price reaches the prior high / upper liquidity area, the impulse has spent its budget.
- Exhaustion signature appears: smaller bodies, more wicks, overlap → consolidation at the top.
- Once price exits the consolidation downward and fails to make a new high, bearish continuation becomes the better read.
- Bias progresses through three phases: bullish-with-room → no-trade-at-top → bearish-after-failure.

**Observed setup moments:**
- Clean bullish impulse from origin: large bodies, little overlap, EMA support
- Approach into prior high / upper liquidity area
- Exhaustion candles: smaller bodies, longer wicks, overlap
- Consolidation range printed below the prior high
- Range exit downward — fail to push higher confirmed
- Bearish continuation begins, level-by-level fill toward lower structure

**om_zone_context:**

| Field | Value |
|---|---|
| `zone_state` | impulse_origin → upper_liquidity_target → consolidation_after_impulse → failed_push_higher → bearish_continuation |
| `clean_bullish_impulse` | true (phase 1) |
| `impulse_origin` | lower 15M structure / EMA support |
| `upper_liquidity_target` | prior 15M high / upper liquidity pool |
| `top_sweep_or_exhaustion` | exhaustion (small bodies + wicks at top) |
| `consolidation_after_impulse` | true |
| `long_bias_exit` | true once consolidation prints at top |
| `failed_push_higher` | true (range exit down, no new high) |
| `bearish_continuation_after_failure` | true |
| `htf_magnet` | next lower 15M structure level once failure confirms |
| `bias_source` | 15M — phase-dependent (long → wait → short) |

**scanner_rule_learned (PROPOSED — not approved):**
- `clean_bullish_impulse = true` arms long bias ONLY while price has unobstructed room to a meaningful target.
- Approach into `upper_liquidity_target` automatically degrades long quality — `entry_quality` drops from high to low for any new long.
- `consolidation_after_impulse = true` at the top → `long_bias_exit = true`, no new longs regardless of candle strength.
- `failed_push_higher = true` (range exit downward, no new high) → flip to bearish bias for 5M execution.
- `bearish_continuation_after_failure = true` arms short-continuation triggers on 5M; target = next lower 15M magnet.
- 15M does not generate entries here — it sets the phase-dependent execution context for 5M.

**Action labels:**
- `BIAS_ONLY` — 15M context, no entry trigger at this layer
- Pairs with Example 035 for execution

---

### Example 035

- **example_id:** 035
- **timeframe:** 5M
- **layer:** execution
- **paired_with:** 034 (15M context map for this execution)
- **screenshot_path:** `docs/om_gold_scalp/examples/035_5m_from_034_bullish_impulse_sweep_then_failed_push_bearish_continuation.png`

**Om notes:**
- 5M gives a cleaner long entry earlier in the impulse — origin pullback + EMA hold + continuation candle.
- Near the top, a possible liquidity sweep prints. Long confidence must drop; watch for reversal or short scalp.
- Short scalp valid once the sweep + rejection confirms — fast trade, do not hold past failed push.
- Consolidation prints, then price fails to push higher → bearish continuation begins, slow but valid.
- Slow bearish continuation can still be tradeable if price keeps filling levels and cannot reclaim structure.
- The scanner must separate early clean-impulse longs from late chase longs. Strong green at origin = useful. Strong green into prior high / liquidity = exhaustion risk.

**Observed setup moments:**
- 5M long entry trigger: origin pullback + EMA 200 hold + continuation candle close
- Long travel through clean trend space — pullbacks are reentries
- Approach into upper liquidity — sweep wick takes prior 5M high
- Rejection candle: body closes back below swept high → short scalp window
- Short scalp closes quickly; consolidation prints
- Failed push higher: smaller and smaller bodies, no new high
- Bearish continuation: slow level-by-level fill toward lower structure
- Pullbacks during bearish continuation are short reentries, not longs

**om_zone_context:**

| Field | Value |
|---|---|
| `zone_state` | impulse_origin (long phase) → upper_liquidity_target → liquidity_sweep → rejecting_resistance → consolidation_after_impulse → failed_push_higher → bearish_continuation → slow_level_fill |
| `clean_bullish_impulse` | true (phase 1) |
| `top_sweep_or_exhaustion` | sweep + exhaustion |
| `short_scalp_valid` | true at sweep + rejection |
| `consolidation_after_impulse` | true |
| `failed_push_higher` | true |
| `bearish_continuation_after_failure` | true |
| `slow_level_fill` | true (continuation prints level-by-level, not impulsive) |
| `late_long_risk` | true for any long entry after `upper_liquidity_target` is in view |
| `entry_quality` | high for origin long and sweep-rejection short; low for chase longs after top |
| `exit_reason` | upper_liquidity_reached / consolidation_at_top / failed_push_higher (depending on phase) |
| `ema200_relation` | above_ema200 during long phase; below_ema200 once bearish continuation confirms |
| `htf_context_id` | 034 |
| `execution_pair_id` | 035 |
| `paired_context_id` | 034 |

**trade_lifecycle:**

| Label | Description |
|---|---|
| Long entry (phase 1) | Origin pullback + EMA 200 hold + continuation candle close |
| Long SL | Below pullback wick + 2 pts |
| Long TP | Upper liquidity / prior high (15–30 pts) |
| Long exit | At upper liquidity OR on first consolidation candle |
| Short scalp (phase 2) | Sweep above prior high + rejection body close back below |
| Short scalp SL | Above sweep wick + 2 pts |
| Short scalp TP | Mid-range / lower edge of consolidation (10–20 pts) |
| Consolidation phase | No new entries — `WAIT_REACTION` |
| Short continuation (phase 3) | Range exit downward + body close below lower edge |
| Continuation SL | Above last lower high + 2 pts |
| Continuation TP | Next 15M structure level (htf_magnet from 034) |
| Invalidation | New 15M high prints + body holds above prior high |

**scanner_rule_learned (PROPOSED — not approved):**
- 5M long `ENTER_NOW` requires: `clean_bullish_impulse = true` AND price has room to `upper_liquidity_target` AND EMA 200 hold confirmed.
- Once price enters the `upper_liquidity_target` zone, long `entry_quality` drops to low → `setup_action = SKIP_CHASE` for new longs.
- `top_sweep_or_exhaustion` + rejection close → arms `short_scalp_valid = true` for a fast scalp (exit at consolidation lower edge).
- `consolidation_after_impulse = true` → `WAIT_REACTION` for all directions until range resolves.
- `failed_push_higher = true` (range exit down, no new high) → arm short-continuation triggers.
- `slow_level_fill = true` allows continuation entries even when momentum is low (`low_momentum_candle`), provided structure remains bearish (no higher high, below EMA 200).
- `late_long_risk = true` audit flag fires whenever a long would be entered above the impulse origin without a fresh higher low — used to suppress chase entries.
- `exit_reason` audit field logs why a trade was closed or skipped: `upper_liquidity_reached` / `consolidation_at_top` / `failed_push_higher` / `chase_distance` / `mid_range_no_confirmation`.

**Action labels:**
- `ENTER_NOW` (long) — origin pullback + EMA hold + continuation candle, with room to upper target
- `SKIP_CHASE` (long) — entry near or above upper liquidity / prior high
- `ENTER_NOW` (short, scalp) — top sweep + rejection close, fast trade
- `WAIT_REACTION` — consolidation after impulse, no signature yet
- `ENTER_NOW` (short, continuation) — failed push higher + range exit down
- `BIAS_FLIP` — new HH prints + body holds above prior high, invalidates short

---

## Impulse-Exhaustion Logic — PROPOSED

Derived from Examples 034–035. Applies whenever a clean directional impulse approaches a meaningful liquidity / prior-extreme area and begins to lose momentum.

- **Clean impulse is not permission to keep buying / selling.** A bullish impulse is valid only while price has room to a target.
- **Approach into upper liquidity / prior high degrades long quality.** `entry_quality` for new longs drops to low automatically.
- **Consolidation at the top = no new longs.** `consolidation_after_impulse = true` triggers `long_bias_exit = true`, regardless of candle color/size.
- **Sweep at the top is an exhaustion signal, not an entry-up signal.** Watch for reversal or short scalp, not continuation long.
- **Failed push higher confirms bearish read.** Range exit downward + no new high = `bearish_continuation_after_failure = true`.
- **Slow bearish continuation is still valid.** If price keeps filling levels and cannot reclaim structure, short reentries remain valid even when momentum is low (`low_momentum_candle`).
- **Location-aware candle reading.** A strong green near the impulse origin is useful. The same strong green into prior high / liquidity is exhaustion risk.
- **Separate early clean-impulse entries from late chase entries.** Always log `entry_quality` and `late_long_risk` so the audit shows which type of entry was considered.

**Audit fields proposed (for impulse-exhaustion logic):**

| Field | Purpose |
|---|---|
| `clean_bullish_impulse` | Bool — true while impulse has room and structure intact |
| `impulse_origin` | Reference level/price for the start of the impulse (used for `late_long_risk` distance check) |
| `upper_liquidity_target` | Price level of the prior high / upper liquidity pool |
| `top_sweep_or_exhaustion` | Enum: `sweep` / `exhaustion` / `both` / `none` |
| `consolidation_after_impulse` | Bool — multiple bars with small bodies + overlap after impulse |
| `long_bias_exit` | Bool — true once consolidation prints at top OR sweep + rejection prints |
| `failed_push_higher` | Bool — range exit down + no new high (mirror: `failed_push_lower` for bearish impulses) |
| `bearish_continuation_after_failure` | Bool — short continuation armed after failed push higher |
| `slow_level_fill` | Bool — continuation prints level-by-level, low momentum, still valid |
| `late_long_risk` | Bool — entry would land far from impulse origin without fresh higher low |
| `short_scalp_valid` | Bool — top sweep + rejection close confirmed, fast scalp window open |
| `entry_quality` | Enum: high / medium / low — degraded automatically near liquidity targets (reused from 032–033) |
| `exit_reason` | Enum: `upper_liquidity_reached` / `consolidation_at_top` / `failed_push_higher` / `chase_distance` / `mid_range_no_confirmation` / `signature_invalidated` |
| `htf_context_id` | ID of the HTF example providing context (e.g. 034) |
| `execution_pair_id` | ID of the LTF example providing the trigger (e.g. 035) |

---

## Paired 15M / 5M HTF-Range No-Trade Context-Execution — Examples 036–037

This pair teaches no-trade behavior inside a wide HTF range. The scanner must not force longs or shorts while price is trapped inside the purple range. A clean boundary event is required: breakdown, breakout, reclaim, rejection, retest, or follow-through. Until then, the correct action is `SKIP_CHOP` with `skip_reason = inside_range_chop`.

---

### Example 036

- **example_id:** 036
- **timeframe:** 15M
- **layer:** context
- **paired_with:** 037 (5M execution view of this same context)
- **screenshot_path:** `docs/om_gold_scalp/examples/036_15m_htf_range_consolidation_no_trade_until_breakdown.png`

**Om notes:**
- 15M shows a wide purple HTF range / consolidation zone.
- Price trades inside the range repeatedly — no clean directional resolution.
- Longs from the middle or lower part of the range are low-confidence because the range itself is not broken.
- Scanner should mark this as a no-trade / wait state until price clearly breaks a boundary.
- Bearish continuation becomes valid only after range support fails WITH displacement (not a wick, not a single test).
- A single touch of the purple zone is never an entry while the range is active.

**Observed setup moments:**
- Multiple bars oscillating inside the purple range
- Tests of both upper and lower boundaries with no follow-through
- No clean displacement candle exits the range on either side
- Range remains active — `htf_range_active = true`
- A future displacement candle through a boundary would arm the breakdown/breakout context

**om_zone_context:**

| Field | Value |
|---|---|
| `zone_state` | inside_range_chop (no resolution) |
| `htf_range_active` | true |
| `htf_zone_type` | purple HTF range / consolidation band |
| `range_boundary_high` | upper edge of purple range |
| `range_boundary_low` | lower edge of purple range |
| `no_trade_zone` | true (mid-range and untested-boundary states) |
| `low_confidence_inside_range` | true for any entry attempt before boundary event |
| `boundary_break_required` | true (no entry until breakout / breakdown signature) |
| `htf_magnet` | undefined until range resolves |
| `bias_source` | 15M — undecided while range active |

**scanner_rule_learned (PROPOSED — not approved):**
- `htf_range_active = true` forces `setup_action = SKIP_CHOP` for all entries inside the range, regardless of candle strength or short-term momentum.
- `no_trade_zone = true` overrides any 5M signature that would otherwise fire — boundary event is the gate.
- A valid resolution requires ONE of: clean breakout above `range_boundary_high` + retest hold, OR clean breakdown below `range_boundary_low` + displacement + failed reclaim.
- `low_confidence_inside_range = true` automatically degrades `entry_quality` to low for any candidate trigger inside the range.
- `boundary_break_required = true` keeps the scanner in wait state until one of the two resolution signatures completes.
- 15M does not generate entries here — it locks the no-trade state until the range resolves.

**Action labels:**
- `BIAS_ONLY` — 15M context, no entry trigger at this layer
- `SKIP_CHOP` — propagated to 5M for any candidate inside the range
- Pairs with Example 037 for execution

---

### Example 037

- **example_id:** 037
- **timeframe:** 5M
- **layer:** execution
- **paired_with:** 036 (15M context map for this execution)
- **screenshot_path:** `docs/om_gold_scalp/examples/037_5m_from_036_range_chop_failed_support_wait_breakdown.png`

**Om notes:**
- 5M shows the same range/chop behavior in detail — bars oscillating inside the purple range, no clean direction.
- Failed support attempts are NOT enough by themselves. A wick into the lower edge that closes back inside is not a short trigger.
- Scanner should wait for one of: clean breakdown, retest, reclaim failure, or follow-through.
- Do NOT enter only because price touches the purple zone.
- Do NOT enter only because one candle shows `single_candle_strength` — appearance ≠ structural truth (see Definitions: candle color/size alone is never enough).
- The valid action is `execution_wait_state = true` until the 15M range resolves.

**Observed setup moments:**
- 5M bars oscillating inside the 15M range
- Wicks into lower boundary that close back inside — not breakdowns
- Strong-looking green and red candles mid-range — none are entries
- No body close beyond `range_boundary_low` with displacement
- No retest of broken boundary, no failed reclaim
- Continuation of chop, no signature → wait

**om_zone_context:**

| Field | Value |
|---|---|
| `zone_state` | inside_range_chop |
| `htf_range_active` | true (inherited from 036) |
| `no_trade_zone` | true |
| `inside_range_chop` | true |
| `low_confidence_inside_range` | true |
| `boundary_break_required` | true |
| `breakdown_confirmation_required` | true (body close below `range_boundary_low` + displacement) |
| `execution_wait_state` | true |
| `entry_quality` | low for any candidate inside the range |
| `skip_reason` | inside_range_chop |
| `ema200_relation` | mixed / flat — EMA inside the range, not directional |
| `htf_context_id` | 036 |
| `execution_pair_id` | 037 |
| `paired_context_id` | 036 |

**trade_lifecycle:**

| Label | Description |
|---|---|
| Inside range | No entry — `SKIP_CHOP` with `skip_reason = inside_range_chop` |
| Wick into boundary | Not a breakout / breakdown — body close required |
| Breakdown candidate | Body close below `range_boundary_low` + displacement → arm short context |
| Breakout candidate | Body close above `range_boundary_high` + displacement → arm long context |
| Retest after break | Hold = good retest → entry valid; fail = fakeout → skip |
| Reclaim failure | Body cannot close back inside after break → continuation short/long valid |
| Follow-through | Next bar continues the break direction → confirms entry quality |

**scanner_rule_learned (PROPOSED — not approved):**
- 5M `setup_action = SKIP_CHOP` is the default while `htf_range_active = true` AND price is inside `[range_boundary_low, range_boundary_high]`.
- `breakdown_confirmation_required = true` blocks short entry until: body close below `range_boundary_low` AND displacement candle AND (retest hold OR reclaim failure OR follow-through bar).
- Mirror rule for breakout: body close above `range_boundary_high` + displacement + (retest hold OR reclaim failure OR follow-through).
- A single touch of a boundary is never an entry — `wick_only_touch = true` keeps `execution_wait_state = true`.
- Strong candle inside the range is noise — `entry_quality = low`, `skip_reason = inside_range_chop`.
- The scanner must explicitly log `skip_reason = inside_range_chop` so the audit shows the setup was seen and intentionally skipped, not missed.
- Once a boundary event resolves the range, downstream signature rules (sweep+reclaim, break+failed-reclaim, etc.) apply normally on the breakout/breakdown side.

**Action labels:**
- `SKIP_CHOP` — inside the range, no boundary event (default state)
- `WAIT_REACTION` — boundary touch printed, awaiting confirmation
- `ENTER_NOW` (short) — only after breakdown + displacement + (retest hold / reclaim failure / follow-through)
- `ENTER_NOW` (long) — only after breakout + displacement + (retest hold / reclaim failure / follow-through)
- `SKIP_CHASE` — entering after price has already left the range and traveled most of the distance to the next level

---

## HTF-Range No-Trade Logic — PROPOSED

Derived from Examples 036–037. Applies whenever a wide HTF range / purple consolidation zone is active and price is trapped inside it.

- **HTF range active = default skip.** `htf_range_active = true` forces `SKIP_CHOP` for every candidate inside the range.
- **Single touch is never an entry.** A wick into a boundary that closes back inside is not a breakout or breakdown.
- **Resolution requires displacement + confirmation.** Body close beyond a boundary alone is not enough — need retest hold, reclaim failure, OR follow-through.
- **Candle strength inside the range is noise.** Strong green or red mid-range = low `entry_quality` = skip.
- **Skip with logged reason.** Always set `skip_reason = inside_range_chop` so the audit proves intentional inaction.
- **No magnet until resolution.** `htf_magnet` stays undefined until the range resolves on one side.
- **Once resolved, normal signature rules apply.** After breakdown / breakout + confirmation, sweep+reclaim and break+failed-reclaim rules from earlier examples take over.

**Audit fields proposed (for HTF-range no-trade logic):**

| Field | Purpose |
|---|---|
| `htf_range_active` | Bool — true while a wide HTF range / consolidation band is in effect |
| `no_trade_zone` | Bool — true for any candidate inside the active range without boundary event |
| `inside_range_chop` | Bool — true when 5M is oscillating inside the range without signature |
| `range_boundary_high` | Price level of the upper edge of the HTF range |
| `range_boundary_low` | Price level of the lower edge of the HTF range |
| `boundary_break_required` | Bool — true until a clean breakout/breakdown signature completes |
| `low_confidence_inside_range` | Bool — degrades `entry_quality` to low for inside-range candidates |
| `breakdown_confirmation_required` | Bool — gates short entry on body close + displacement + (retest / failed reclaim / follow-through) |
| `execution_wait_state` | Bool — 5M default state while range is unresolved |
| `htf_context_id` | ID of the HTF example providing context (e.g. 036) |
| `execution_pair_id` | ID of the LTF example providing the trigger (e.g. 037) |

---

## Paired 15M / 5M Double-Sweep Reclaim Long Context-Execution — Examples 038–039

This pair teaches a clean liquidity sweep + reclaim long setup. Price sweeps downside liquidity twice, fails to continue lower, reclaims the swept area, then creates bullish displacement. The sweep alone is never the entry. Entry arms only after reclaim + displacement + structure shift.

---

### Example 038

- **example_id:** 038
- **timeframe:** 15M
- **layer:** context
- **paired_with:** 039 (5M execution view of this same context)
- **screenshot_path:** `docs/om_gold_scalp/examples/038_15m_double_liquidity_sweep_reclaim_long_bias.png`

**Om notes:**
- Price makes a double liquidity sweep below prior lows — two separate tests of the downside liquidity pool.
- Downside continuation fails after both sweeps. No new low holds.
- Price reclaims back above the swept area. Body close above the swept level = reclaim confirmed.
- Bullish displacement candle prints after reclaim — large body, little overlap, confirms long bias.
- 15M read: `sweep_reclaim_long_candidate` → `long_bias_after_reclaim`.
- The double sweep is stronger evidence than a single sweep — more liquidity taken, more likely the move is exhausted.

**Observed setup moments:**
- Sweep 1: wick below prior low, body closes back above
- Sweep 2: second wick below (double sweep), body closes back above
- `reclaim_confirmed = true`: body close above the swept level holds
- Bullish displacement candle: large body, directional, little overlap
- `long_bias_after_reclaim = true` arms for 5M execution

**om_zone_context:**

| Field | Value |
|---|---|
| `zone_state` | liquidity_sweep (×2) → reclaimed_zone → bullish_displacement |
| `liquidity_sweep_count` | 2 |
| `double_sweep` | true |
| `swept_side` | bearish (downside liquidity) |
| `reclaim_confirmed` | true (body close above swept level after double sweep) |
| `reclaim_direction` | bullish |
| `bullish_displacement` | true |
| `long_bias_after_reclaim` | true |
| `sweep_alone_no_entry` | true (entry gate does not open until reclaim + displacement) |
| `htf_magnet` | next 15M structure level above (prior high / resistance) |
| `bias_source` | 15M — bearish during sweep, bullish after double-sweep reclaim + displacement |

**scanner_rule_learned (PROPOSED — not approved):**
- `liquidity_sweep_count ≥ 2` + `reclaim_confirmed = true` → `sweep_reclaim_long_candidate = true`. Stronger signal than single sweep.
- `sweep_alone_no_entry = true` keeps `setup_action = WAIT_REACTION` until both reclaim AND displacement confirm.
- `bullish_displacement = true` after `reclaim_confirmed` → `long_bias_after_reclaim = true` arms 5M execution.
- Double sweep: second wick that holds above the same level as sweep 1 = `double_sweep = true`, increases conviction weighting.
- 15M does not generate entries here — it arms the long context for 5M execution.

**Action labels:**
- `WAIT_REACTION` — during sweep phase (both sweeps), no entry yet
- `BIAS_ONLY` — 15M context after reclaim + displacement confirms, arms 5M
- Pairs with Example 039 for execution

---

### Example 039

- **example_id:** 039
- **timeframe:** 5M
- **layer:** execution
- **paired_with:** 038 (15M context map for this execution)
- **screenshot_path:** `docs/om_gold_scalp/examples/039_5m_from_038_double_sweep_reclaim_long_trigger.png`

**Om notes:**
- 5M shows the full sequence: sweep 1 → sweep 2 → reclaim → bullish displacement → long trigger.
- Do NOT enter while price is still below the swept level. That is `entry_invalid_without_confirmation`.
- Do NOT enter from the sweep alone — the sweep is the setup, not the entry.
- Confirmation comes from reclaim (body close back above the swept level) AND displacement (large directional candle).
- Valid long trigger fires on the first pullback/retest after displacement that holds above the reclaim level, or on the displacement close itself if strong enough.
- `structure_shift_after_sweep = true` when a higher low prints above the swept level after reclaim.

**Observed setup moments:**
- 5M sweep 1: wick below prior low, close back above
- 5M sweep 2: second wick below, close back above (same or slightly lower wick)
- `reclaim_confirmed = true` on 5M: body close above swept level holds for 1+ bars
- Bullish displacement candle on 5M: body > prior 3-bar average, little overlap
- `structure_shift_after_sweep = true`: higher low prints above swept level
- Long entry: displacement close OR first retest of reclaim level that holds
- SL: below sweep 2 wick low + 2 pts

**om_zone_context:**

| Field | Value |
|---|---|
| `zone_state` | liquidity_sweep (×2) → reclaimed_zone → bullish_displacement → long_trigger |
| `liquidity_sweep_count` | 2 |
| `double_sweep` | true |
| `swept_side` | bearish (downside) |
| `reclaim_confirmed` | true |
| `reclaim_direction` | bullish |
| `bullish_displacement` | true |
| `structure_shift_after_sweep` | true (higher low above swept level) |
| `long_bias_after_reclaim` | true (inherited from 038) |
| `long_trigger_after_reclaim` | true |
| `entry_after_reclaim_only` | true |
| `sweep_alone_no_entry` | true |
| `entry_quality` | high (double sweep + reclaim + displacement = strong confluence) |
| `ema200_relation` | price reclaims above EMA 200 during displacement confirms alignment |
| `htf_context_id` | 038 |
| `execution_pair_id` | 039 |
| `paired_context_id` | 038 |

**trade_lifecycle:**

| Label | Description |
|---|---|
| Sweep 1 | Observation only — `WAIT_REACTION`, no entry |
| Sweep 2 | Observation only — `WAIT_REACTION`, `double_sweep = true` noted |
| Reclaim candidate | Body close above swept level — watch for hold |
| Reclaim confirmed | Holding candle above swept level — `long_trigger_after_reclaim` arms |
| Long entry | Displacement close OR retest of reclaim level that holds |
| Long SL | Below sweep 2 wick low + 2 pts |
| Long TP | Next 15M structure level / prior high (15–30 pts from entry) |
| Invalidation | Body closes back below swept level after reclaim attempt — `reclaim_failed`, cancel long |

**scanner_rule_learned (PROPOSED — not approved):**
- `setup_action = WAIT_REACTION` during all sweep bars regardless of wick size or candle appearance.
- `setup_action = ENTER_NOW` (long) requires ALL of: `double_sweep = true` (or `liquidity_sweep_count ≥ 1`) AND `reclaim_confirmed = true` AND `bullish_displacement = true`.
- `entry_after_reclaim_only = true` blocks any long entry until reclaim body close is confirmed — no exceptions.
- `structure_shift_after_sweep = true` (higher low above swept level) adds conviction weight — upgrade `entry_quality` from medium to high.
- `sweep_alone_no_entry = true` is always set during sweep bars — audit field prevents entry_state from arming too early.
- Reclaim failure after the second sweep (`reclaim_failed = true`) cancels the long setup entirely — price back below swept level = `low_confidence_setup`, reassess.
- `double_sweep` carries higher conviction than single sweep — scanner may reduce required displacement threshold for entry when `double_sweep = true`.

**Action labels:**
- `WAIT_REACTION` — sweep 1, sweep 2 (no entry during sweep phase)
- `WAIT_REACTION` → `ENTER_NOW` (long) — reclaim confirmed + displacement printed
- `SKIP_CHASE` — entering long after price has already traveled far above the reclaim level
- `low_confidence_setup` — if reclaim fails after double sweep (unusual, still possible)

---

## Double-Sweep Reclaim Logic — PROPOSED

Derived from Examples 038–039. Applies to any liquidity sweep sequence (single or double) on any timeframe where price takes a prior extreme, fails to continue, and reclaims.

- **Sweep is the setup, not the entry.** `sweep_alone_no_entry = true` is always active during the sweep bar(s).
- **Double sweep increases conviction.** Two wicks into the same liquidity pool with no continuation = stronger exhaustion signal than a single sweep.
- **Reclaim is the gate.** Entry does not arm until body close above (bullish) or below (bearish) the swept level holds for at least one confirming bar.
- **Displacement is the trigger.** After reclaim holds, a displacement candle in the reclaim direction confirms `long_bias_after_reclaim` / `short_bias_after_reclaim`.
- **Structure shift adds weight.** A higher low (bullish) or lower high (bearish) after reclaim = `structure_shift_after_sweep = true` → upgrade `entry_quality`.
- **Reclaim failure cancels the setup.** If body closes back through the swept level after initial reclaim, `reclaim_failed = true` → cancel the entry, reassess.
- **SL is always anchored to the sweep extreme.** SL below sweep 2 low (bullish) or above sweep 2 high (bearish) + 2 pts buffer.

**Audit fields proposed (for double-sweep reclaim logic):**

| Field | Purpose |
|---|---|
| `liquidity_sweep_count` | Int — number of sweeps into the same liquidity level (1 or 2+) |
| `double_sweep` | Bool — true when `liquidity_sweep_count ≥ 2` at the same level |
| `swept_side` | Enum: `bearish` (downside swept) / `bullish` (upside swept) |
| `reclaim_confirmed` | Bool — body close back across swept level + hold (reused from earlier definitions) |
| `reclaim_direction` | Enum: `bullish` / `bearish` |
| `bullish_displacement` | Bool — large directional body candle in bullish direction after reclaim |
| `structure_shift_after_sweep` | Bool — higher low (bullish) or lower high (bearish) prints after reclaim |
| `long_bias_after_reclaim` | Bool — true when `swept_side = bearish` AND `reclaim_confirmed = true` AND `bullish_displacement = true` |
| `long_trigger_after_reclaim` | Bool — true when `long_bias_after_reclaim` AND 5M entry signature confirmed |
| `entry_after_reclaim_only` | Bool — gates all entries; prevents entry before reclaim confirmation |
| `sweep_alone_no_entry` | Bool — always true during sweep bars; forces `WAIT_REACTION` |

---

## Paired 15M / 5M Failed-Bullish-Reversal Bearish-Continuation Context-Execution — Examples 040–041

This pair teaches that a sweep candidate is not automatically bullish. A bullish reversal requires reclaim + structure hold. If reclaim fails and bearish displacement follows, the scanner must flip to bearish continuation. The mirror of the double-sweep reclaim long (038–039) — here the reclaim attempt collapses, not succeeds.

---

### Example 040

- **example_id:** 040
- **timeframe:** 15M
- **layer:** context
- **paired_with:** 041 (5M execution view of this same context)
- **screenshot_path:** `docs/om_gold_scalp/examples/040_15m_sweep_candidate_reclaim_failed_bearish_continuation.png`

**Om notes:**
- Price sweeps downside liquidity — initially reads as a sweep candidate for a bullish reversal.
- Bullish reversal attempt begins: price pushes back up toward the swept level.
- The attempt fails. Price cannot sustain the recovery — reclaim does not hold.
- Bearish displacement follows the failed reclaim — strong directional candle in the bearish direction.
- Bearish continuation becomes valid. This is not a clean long setup after reclaim failure.
- Key distinction from 038: in 038 the reclaim held and displacement was bullish; here reclaim failed and displacement was bearish.

**Observed setup moments:**
- Sweep candidate: wick into downside liquidity pool
- Bullish recovery attempt: price pushes back up, some green bars
- Reclaim attempt fails: body close cannot hold above the swept level (`reclaim_failed = true`)
- Bearish displacement candle prints: large bearish body, breaks back below structure
- Bearish continuation armed: lower high forms, continuation toward lower structure

**om_zone_context:**

| Field | Value |
|---|---|
| `zone_state` | liquidity_sweep → reclaim_attempt → reclaim_failed → bearish_displacement → bearish_continuation |
| `sweep_candidate` | true (downside sweep appeared initially bullish) |
| `reclaim_attempt` | true (bullish recovery attempted) |
| `reclaim_failed` | true (body close cannot hold above swept level) |
| `failed_bullish_reversal` | true |
| `bearish_displacement_after_failed_reclaim` | true |
| `bearish_continuation_valid` | true |
| `avoid_long_reason` | reclaim_failed + bearish_displacement_after_failed_reclaim |
| `htf_magnet` | next lower 15M structure level |
| `bias_source` | 15M — initially sweep candidate, flips bearish after reclaim failure + displacement |

**scanner_rule_learned (PROPOSED — not approved):**
- `sweep_candidate = true` alone does not arm long bias. Long bias requires `reclaim_confirmed = true` (see 038–039).
- If `reclaim_attempt = true` AND `reclaim_failed = true` → `failed_bullish_reversal = true`. Cancel any pending long setup.
- `bearish_displacement_after_failed_reclaim = true` → flip to `bearish_continuation_valid = true`. Short triggers now arm on 5M.
- `avoid_long_reason = reclaim_failed` suppresses any new long entries until price demonstrates a fresh reclaim structure.
- 15M does not generate entries here — it flips the bias from potential-long to confirmed-bearish for 5M execution.

**Action labels:**
- `WAIT_REACTION` — sweep candidate printed, reclaim attempt in progress
- `low_confidence_setup` — green candles during failed reclaim phase (appearance ≠ structural truth)
- `BIAS_ONLY` (bearish) — after `failed_bullish_reversal` + `bearish_displacement` confirm
- Pairs with Example 041 for execution

---

### Example 041

- **example_id:** 041
- **timeframe:** 5M
- **layer:** execution
- **paired_with:** 040 (15M context map for this execution)
- **screenshot_path:** `docs/om_gold_scalp/examples/041_5m_from_040_reclaim_failed_short_continuation_trigger.png`

**Om notes:**
- 5M execution view of the same context shown in 040.
- Failed reclaim and failed bullish continuation are visible at 5M resolution.
- Bearish continuation short trigger fires only after the reclaim failure is confirmed visible — not from the sweep alone.
- Avoid entering long just because price bounced or printed green candles during the reclaim attempt.
- Green candles during a failed reclaim phase = `single_candle_strength` without structural support = `countertrend_attempt_failed`.

**Observed setup moments:**
- 5M sweep candidate: wick into downside liquidity
- 5M reclaim attempt: green candles push back toward swept level
- `reclaim_failed = true` on 5M: body close cannot hold above swept level for 2+ bars
- Bearish displacement on 5M: large bearish body breaks below prior 5M low
- `failed_bullish_reversal = true` confirmed on 5M
- Short trigger: bearish displacement close OR lower-high retest that fails to push above

**om_zone_context:**

| Field | Value |
|---|---|
| `zone_state` | sweep_candidate → reclaim_attempt → reclaim_failed → bearish_displacement → bearish_continuation |
| `sweep_candidate` | true |
| `reclaim_attempt` | true |
| `reclaim_failed` | true |
| `failed_bullish_reversal` | true |
| `bearish_displacement_after_failed_reclaim` | true |
| `bearish_continuation_valid` | true |
| `avoid_long_reason` | reclaim_failed + bearish_displacement_after_failed_reclaim |
| `candle_strength_mismatch` | true (green bars during reclaim attempt had `single_candle_strength` but no structural support) |
| `entry_quality` | high for short after confirmed failure; low for any long during reclaim attempt |
| `ema200_relation` | below_ema200 when bearish continuation fires |
| `htf_context_id` | 040 |
| `execution_pair_id` | 041 |
| `paired_context_id` | 040 |

**trade_lifecycle:**

| Label | Description |
|---|---|
| Sweep candidate | `WAIT_REACTION` — possible sweep but reclaim not yet attempted |
| Reclaim attempt (green bars) | `WAIT_REACTION` — do not long; `avoid_long_reason` active |
| Reclaim failure confirmed | `reclaim_failed = true` — cancel any long thesis |
| Bearish displacement | Confirms `failed_bullish_reversal` — short trigger arms |
| Short entry | Bearish displacement close OR lower-high retest that cannot push above |
| Short SL | Above failed reclaim wick high + 2 pts |
| Short TP | Next 15M structure level below (htf_magnet from 040) — 15–30 pts |
| Invalidation | Body close back above the reclaim level AND holds → reassess; reclaim may have succeeded |

**scanner_rule_learned (PROPOSED — not approved):**
- 5M `setup_action = WAIT_REACTION` during sweep and entire reclaim-attempt phase regardless of green candle count or size.
- `avoid_long_reason` field is set as soon as `sweep_candidate = true` — long only arms if `reclaim_confirmed = true` (038 path); stays blocked if `reclaim_failed = true` (this path).
- `setup_action = ENTER_NOW` (short) fires after ALL of: `reclaim_failed = true` AND `bearish_displacement_after_failed_reclaim = true` AND `bearish_continuation_valid = true`.
- `candle_strength_mismatch = true` logged for every green bar during the failed reclaim phase — calibration metric for how often appearance misled.
- The failed reclaim short is the mirror of the double-sweep reclaim long (038–039): same anatomy, opposite outcome. Scanner must check reclaim success/failure before assigning direction.
- SL is always above the failed reclaim wick + 2 pts — the highest point price reached during the failed recovery.

**Action labels:**
- `WAIT_REACTION` — sweep candidate and reclaim attempt phase (both)
- `avoid_entry` (long) — green candles during failed reclaim = `low_confidence_setup`
- `ENTER_NOW` (short) — after `failed_bullish_reversal` + bearish displacement confirmed
- `SKIP_CHASE` — entering short after price has already traveled far below the failed reclaim level
- `BIAS_FLIP` — only if body closes back above failed reclaim level and holds (then reassess from scratch)

---

## Failed-Bullish-Reversal Bearish-Continuation Logic — PROPOSED

Derived from Examples 040–041. This is the failure-mode mirror of Examples 038–039 (double-sweep reclaim long). Applies when a sweep candidate fails to complete the reclaim and instead produces bearish displacement.

- **Sweep candidate ≠ bullish confirmation.** A wick into downside liquidity does not arm long bias without reclaim + hold.
- **Reclaim attempt with green bars = still waiting.** Green candles during recovery are `single_candle_strength` without structural proof — `WAIT_REACTION` stays active.
- **Reclaim failure flips bias.** `reclaim_failed = true` cancels all long setups; `failed_bullish_reversal = true` arms bearish context.
- **Bearish displacement after failed reclaim = short trigger arms.** `bearish_displacement_after_failed_reclaim = true` combined with `bearish_continuation_valid = true` allows 5M short entry.
- **SL anchored to the failed reclaim high.** The highest point during the recovery attempt + 2 pts is always the SL for the short.
- **Mirror the double-sweep reclaim logic.** Same anatomy (sweep → reclaim attempt → displacement) — outcome depends on whether reclaim succeeds (038 path) or fails (040 path). Scanner checks reclaim outcome before assigning direction.

**Audit fields proposed (for failed-bullish-reversal bearish-continuation logic):**

| Field | Purpose |
|---|---|
| `sweep_candidate` | Bool — price swept downside liquidity; bullish reversal possible but not confirmed |
| `reclaim_attempt` | Bool — price is pushing back toward the swept level (already defined; reused) |
| `reclaim_failed` | Bool — body close cannot hold above swept level (already defined; reused) |
| `failed_bullish_reversal` | Bool — `reclaim_attempt = true` AND `reclaim_failed = true` together |
| `bearish_displacement_after_failed_reclaim` | Bool — large bearish displacement candle follows the failed reclaim |
| `bearish_continuation_valid` | Bool — all confirmation conditions for bearish continuation are met |
| `avoid_long_reason` | Enum: `reclaim_failed` / `bearish_displacement_after_failed_reclaim` / `no_reclaim_hold` |

---

## 15M HTF Range Breakdown Bearish Continuation — Example 042

Standalone 15M context example. Teaches that internal moves inside a wide HTF range are not trade signals. Bearish continuation only becomes valid after the range low breaks, price accepts below it, and follow-through confirms.

---

### Example 042

- **example_id:** 042
- **timeframe:** 15M
- **layer:** context
- **paired_with:** none (standalone context example — no 5M execution pair yet)
- **screenshot_path:** `docs/om_gold_scalp/examples/042_htf_range_low_break_retest_hold_bearish_continuation_15m.png`
- **setup_type:** `htf_range_breakdown_bearish_continuation`

**Om notes:**
- A large purple box marks the HTF range / consolidation zone.
- Price spends a significant amount of time inside the range — multiple bars, both sides tested.
- Internal pushes up and down inside the range are not valid entries (`avoid_entry` / `no_trade_zone`).
- Fake pushes inside the range: any strong-looking candle inside the purple box is `low_confidence_setup`.
- Bearish continuation is NOT valid while price is inside the range.
- Bearish continuation becomes valid only after three sequential conditions are met:
  1. Range low breaks — body close below the purple box lower boundary.
  2. Price accepts and holds below the broken range low — retest of range low from below holds as resistance.
  3. Follow-through continues bearish — next bars extend lower, no reclaim back inside range.
- Failure condition: price reclaims back inside the purple range → bearish setup invalidated, reassess.

**Observed setup moments:**
- Multiple bars inside the purple HTF range — `htf_range_active = true`, `no_trade_zone = true`
- Internal bearish pushes: rejected, not followed through — `avoid_short_before_break = true`
- Internal bullish pushes: rejected, not followed through — `avoid_long_inside_range = true`
- Range low breaks: body close below lower boundary of the purple box
- Retest of range low from below: holds as resistance — `range_retest_held_below = true`
- Follow-through bearish candles: `bearish_continuation_valid = true`

**om_zone_context:**

| Field | Value |
|---|---|
| `htf_context` | range_consolidation |
| `range_state` | active_until_break (inside range) → broken (after range low body close) |
| `htf_range_active` | true while inside range |
| `no_trade_zone` | true while price is inside the purple range |
| `internal_pushes` | avoid_entry (both directions while inside range) |
| `avoid_short_before_break` | true — bearish moves inside range are not continuation |
| `avoid_long_inside_range` | true — bullish moves inside range are not reversal |
| `range_low_broken` | true (body close below lower boundary) |
| `range_retest_held_below` | true (retest of broken range low as resistance) |
| `confirmation_signal` | range_low_break_and_hold_below |
| `bearish_continuation_valid` | true only after break + retest hold + follow-through |
| `execution_bias` | short_after_confirmation |
| `failure_condition` | price_reclaims_back_inside_range |
| `htf_zone_type` | purple HTF consolidation range |

**scanner_rule_learned (PROPOSED — not approved):**
- While `htf_range_active = true`: all candidates inside the range → `setup_action = SKIP_CHOP`, `no_trade_zone = true`, `internal_pushes = avoid_entry`.
- `avoid_short_before_break = true` explicitly blocks all short entries until `range_low_broken = true`.
- `avoid_long_inside_range = true` explicitly blocks all long entries while range is active.
- `range_low_broken = true` requires a body close below the range lower boundary (wick alone = `boundary_break_required` still active).
- `range_retest_held_below = true` requires: price returns to range low from below AND body close stays below the range boundary.
- `confirmation_signal = range_low_break_and_hold_below` arms `bearish_continuation_valid = true` for short execution.
- `failure_condition = price_reclaims_back_inside_range`: if body closes back inside the purple range → cancel short setup, `bearish_continuation_valid = false`, reassess from scratch.
- Internal moves inside the range, however strong they appear (`single_candle_strength`), are always `low_confidence_setup` + `avoid_entry`.

**Action labels:**
- `SKIP_CHOP` — inside range, any direction
- `no_trade_zone` — while `htf_range_active = true`
- `avoid_entry` — all internal pushes regardless of candle size/color
- `WAIT_REACTION` — range low broken, watching for retest
- `ENTER_NOW` (short) — after `range_retest_held_below = true` + follow-through bar
- `SKIP_CHASE` — entering short far below range after price has already traveled most of the distance
- `BIAS_FLIP` — body reclaims back inside range → invalidate short, restart analysis

---

*Add next example below as Example 043*

**Next planned batch:**
- TBD by Om
