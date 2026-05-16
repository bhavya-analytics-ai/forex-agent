# OM Gold Scalp — Rulebook

> Screenshot calibration log. Each example captures what Om sees, what the scanner should learn, and what label applies.
> Rules are NOT finalized from screenshots alone. Om approves each rule before it is implemented.

**Status:** Calibration in progress
**Examples collected:** 27 (5 × 1H context [001–005] + 8 × 15M setup [006–013] + 8 × 5M trigger [014–021] + 4 × paired 1H/5M context-execution [022–025] + 2 × paired 15M/5M news-displacement context-execution [026–027])
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
- Do NOT enter immediately on the news displacement candle. That is the chase trap.
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

*Add next example below as Example 028*

**Next planned batch:**
- 028 / 029 = 15M sweep reclaim → 5M long
- 030 / 031 = 15M chop / EMA conflict → 5M skip
