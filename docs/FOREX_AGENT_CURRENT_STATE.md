# Forex Agent — Current State Handoff

_Last updated: 2026-05-18 | commit 252fa6b_

---

## Production Safety State

- Weekend/session guard deployed and enforced.
- Bad-run rows (May 15–18) archived and excluded from performance stats.
- Legacy pre-OM fake/open rows archived and excluded.
- Active unresolved fake signals cleaned.
- Legacy live DB writes and Slack blocked unless explicitly enabled.
- No live OM signals yet — all OM output is watch-only.

---

## Strategy Architecture

Original scanner (legacy_forex, legacy_gold) stays unchanged.
News sniper stays as a separate mode.
OM Gold Scalp is a parallel extra strategy — not a replacement.

**Scan pipeline per pair:**
1. Fetch candles once (`fetch_all_timeframes`)
2. Build shared confluence once (`check_confluence`)
3. Run legacy scorer → `scored` dict (primary)
4. Run `strategies/runner.run_extra_strategies()` in parallel → list of extra candidate dicts
5. Each extra candidate is fully independent — primary `scored` is never mutated

**Signal modes (must stay distinct everywhere):**

| signal_mode | owner |
|---|---|
| legacy_forex | original forex scanner |
| legacy_gold | original gold scanner |
| news_sniper | news_sniper module |
| om_gold_scalp | strategies/om_gold_scalp.py |

- Dashboard may show a combined view but source `signal_mode` must always be visible.
- Performance stats must be separated by `signal_mode`.
- Extra candidates are stored in `_extra_store` (keyed `pair|signal_mode`), separate from `_signal_store`.
- `/api/signals/extra` endpoint reads only `_extra_store` — `/api/signals` is untouched.

---

## Kill Switches

All default **false**. Both gates must be True for DB writes and Slack.

| Env Var | Scope |
|---|---|
| `OM_STRATEGY_ENABLED` / `GLOBAL_SCANNER_ENABLED` | Global master — if false, no DB writes, no Slack for any strategy |
| `LEGACY_FOREX_ENABLED` | Legacy forex scanner |
| `LEGACY_GOLD_ENABLED` | Legacy gold scanner |
| `NEWS_SNIPER_ENABLED` | News sniper |
| `OM_GOLD_SCALP_ENABLED` | OM Gold Scalp strategy |

- Global false → zero DB writes, zero Slack, across all strategies.
- Per-strategy false → that strategy runs state machine but output is watch-only.

---

## Commit History

| Commit | Description |
|---|---|
| db2ddfa | Phase 0: om_gold_scalp.py + 37 tests, all passing |
| edf9fec | Phase 1: multi-strategy runner, /api/signals/extra, OM wired watch-only |
| abb0e95 | Phase 1 hotfix: DataFrame → list-of-dicts normalisation in runner |
| 252fa6b | Momentum gate: MIN_MOMENTUM_REQUIRED=50, audit fields, 54 tests pass |

---

## Next Steps

1. Watch-only observation for 1–2 days — inspect `/api/signals/extra` output.
2. Verify low-momentum setups now appear as `WAIT_MOMENTUM` (not `ENTER_NOW`).
3. If OM output looks wrong, relabel screenshots with ChatGPT-assisted annotations.
4. Do NOT enable OM live yet.
5. Do NOT enable DB writes or Slack until reviewed.

---

## Known Caution

OM produced `ENTER_NOW` with `momentum_score=29` before the 252fa6b patch.
That is fixed. Gate: momentum < 50 → `WAIT_MOMENTUM`. Opposing H1 + momentum < 35 → hard `SKIP`.
Still need live verification that `/api/signals/extra` reflects this correctly.
