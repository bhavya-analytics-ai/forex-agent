# OM Gold Scalp — Rulebook

> Screenshot calibration log. Each example captures what Om sees, what the scanner should learn, and what label applies.
> Rules are NOT finalized from screenshots alone. Om approves each rule before it is implemented.

**Status:** Calibration in progress
**Examples collected:** 13 (5 × 1H context + 8 × 15M setup, examples 006–013)
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

*Add next example below as Example 014*
