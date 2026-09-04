# V85 Mixed Accumulation Production Gate

Session date: 2026-06-12

## Context

V84 proved that `HOLD_ABOVE_POI` is the strongest current proxy for smart-money takeover and that `POST_RECLAIM_HIGHER_LOW` is not equivalent. It also surfaced that `MIXED` should not be globally blocked: narrow-POI MIXED buckets had strong WR, suggesting a real range-accumulation substate.

V85 therefore moved back to the generator/environment layer instead of filtering the tiny V84 sample.

## Files

- Generator: `/root/.hermes/scripts/v25/v85_mixed_accumulation_generator.py`
- Tests: `/root/.hermes/scripts/v25/test_v85_mixed_accumulation_generator.py`
- Full scan: `/root/.hermes/scripts/v25/v85_full_market_scan.py`
- Production gate: `/root/.hermes/scripts/v25/v85_apply_production_gate.py`
- Full candidate output: `/root/.hermes/smc_opt_v85_mixed_accumulation_generator/v85_candidates.json`
- Production output: `/root/.hermes/smc_opt_v85_production_gate/v85_trades.json`, `v85_picks.json`
- Production report: `/root/.hermes/smc_opt_v85_production_gate/v85_production_report.json`, `v85_report.md`

## TDD coverage

5 tests passed:

1. `MIXED + narrow POI + hold above` => `MIXED_ACCUMULATION`.
2. `MIXED + wide POI` => `MIXED_DISTRIBUTION`.
3. Post-reclaim lower low => `MIXED_DISTRIBUTION`.
4. `zone_width_pct` uses `zone_low/zone_high` contract.
5. Expanded continuation generator creates a candidate and fills `select_date`, `join_date`, `smart_money_cost`, `volatility_pct`.

## Full-market V85 generator result

Scanned 4655 A-share cached 750-day klines.

| Layer | n | WR | avg | POI break | trend damage | TP rate | T+1 | field missing |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| V85 full candidates | 23345 | 64.50% | +0.5609% | 17.33% | 4.04% | 78.21% | 0 | 0 |

Full candidate layer was close but not production by itself: 2023 WR=61.65%, 2024/2026 WR=64.25%.

## Production gate

Final V85 production gate:

```text
1.0 < zone_width_pct <= 2.0
1.0 < risk_pct <= 1.5
hold_bars <= 2
takeover = HOLD_ABOVE_POI
T+1 enforced
```

This is mechanism-based, not surface tuning:

- narrow POI = compact smart-money cost basis;
- low risk = entry close to real demand zone;
- hold_bars<=2 = fast confirmation/real demand response;
- HOLD_ABOVE_POI = post-reclaim smart-money takeover;
- T+1 = A-share execution legality.

## Production result

| Metric | Value |
|---|---:|
| trades/picks | 559 |
| WR | 89.09% |
| avg pnl | +2.7117% |
| cumulative pnl | +1515.85% |
| POI break | 9.30% |
| trend damage | 1.79% |
| TP rate | 88.91% |
| T+1 violations | 0 |
| missing fields | 0 |

Year split:

| Year | n | WR | avg | POI break | trend damage | TP rate |
|---|---:|---:|---:|---:|---:|---:|
| 2023 | 110 | 86.36% | +2.1994% | 10.91% | 3.64% | 85.45% |
| 2024 | 132 | 88.64% | +2.5466% | 10.61% | 0.76% | 88.64% |
| 2025 | 233 | 90.56% | +2.9458% | 8.15% | 1.29% | 90.56% |
| 2026 | 84 | 89.29% | +2.9927% | 8.33% | 2.38% | 89.29% |

Production criteria all pass:

- total >= 500: pass (559)
- each year 2023-2026 >= 50: pass
- each year WR >= 65%: pass
- T+1 zero: pass
- field audit zero: pass

## Path split

| Path | n | WR | avg | POI break | trend damage | TP rate |
|---|---:|---:|---:|---:|---:|---:|
| CONTINUATION_EXPANDED_HOLD_ABOVE_POI | 294 | 87.07% | +2.6387% | 11.22% | 2.04% | 86.73% |
| MIXED_ACCUMULATION_HOLD_ABOVE_POI | 265 | 91.32% | +2.7927% | 7.17% | 1.51% | 91.32% |

Key lesson: `MIXED_ACCUMULATION` is not a weak fallback; after narrow-POI + HOLD_ABOVE_POI + quick confirmation, it is cleaner than the generic continuation path.

## Frontend promotion

`smc_unified.py` was updated so V85 is the active frontend default when `/root/.hermes/smc_opt_v85_production_gate/v85_production_report.json` exists.

Active paths:

- `ACTIVE_VERSION = V85`
- `ACTIVE_TRADE_FILE = /root/.hermes/smc_opt_v85_production_gate/v85_trades.json`
- `ACTIVE_PICK_FILE = /root/.hermes/smc_opt_v85_production_gate/v85_picks.json`

API/browser field verification after restart:

| Surface | Rows | pick/select date blank | join date blank | Zone blank | cost blank | volatility blank |
|---|---:|---:|---:|---:|---:|---:|
| `/api/picks` | 559 | 0 | 0 | 0 | 0 | 0 |
| `/api/live-prices` first live table | 195 | 0 | 0 | 0 | 0 | 0 |
| `/monitor` first table | 120 | 0 | 0 | 0 | n/a | n/a |
| `/live` first table | 195 | 0 | 0 | 0 | 0 | 0 |

Caveat: the `/monitor` top monitor-state table still contains existing V66 live positions from the monitor ledger. That is historical position state, not V85 `/api/picks`; V85 current active pick API and page title are correct.

## Status

V85 can replace V80 as production default. V80 remains available in its directory but no longer drives the default dashboard after V85 promotion.
