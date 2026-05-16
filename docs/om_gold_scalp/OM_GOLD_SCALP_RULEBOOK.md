# OM Gold Scalp — Rulebook

> Screenshot calibration log. Each example captures what Om sees, what the scanner should learn, and what label applies.
> Rules are NOT finalized from screenshots alone. Om approves each rule before it is implemented.

**Status:** Calibration in progress
**Examples collected:** 1
**Rules approved:** 0 (pending calibration)

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
| **Image** | `examples/001_1h_bearish_freefall_context.png` |
| **Timeframe** | 1H |
| **Date** | 2026-05-15 (approx. 22:29 UTC-4) |
| **Pair** | XAU/USD |
| **Price at screenshot** | ~4,540.58 |
| **Direction** | Bearish |
| **Label** | Bearish freefall context / broken support continuation |
| **Use** | Context only — not a direct scalp entry |

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

**Rule learned (PROPOSED — not approved):**
- If H1 price is below both identified S/R zones AND below 200 EMA → bias = bearish
- A bullish scalp is suppressed until price reclaims at least the lower zone on H1 close
- A bearish scalp is valid on failed retests of either zone from below
- No entry during active freefall — wait for consolidation candle (tight-body H1 or H1 doji near zone)

**Scanner implication (PROPOSED):**
- H1 context check: `price < lower_zone AND price < ema_200` → `h1_bias = "bearish_freefall"`
- `h1_bias = bearish_freefall` → suppress bullish scalp signals entirely
- Bearish scalp allowed only at zone retest, not during open freefall

**om_zone_context:**

> These values are Om screenshot labels, not live computed values yet.
> Live computation requires future candle-data implementation.

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

**Status:** Proposed. Awaiting Om approval before adding to spec.

---

*Add next example below as Example 002*
