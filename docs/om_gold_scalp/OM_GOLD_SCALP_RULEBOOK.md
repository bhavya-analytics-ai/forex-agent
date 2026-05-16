# OM Gold Scalp — Rulebook

> Screenshot calibration log. Each example captures what Om sees, what the scanner should learn, and what label applies.
> Rules are NOT finalized from screenshots alone. Om approves each rule before it is implemented.

**Status:** Calibration in progress
**Examples collected:** 5
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

*Add next example below as Example 006*
