# V285 Stock-DNA Temporal Selector Audit

## Trigger

Use this reference when SMC research shows "trade count is too low" and the next hypothesis is that every stock should have many opportunities if SMC primitives are correct, so the bottleneck may be chronological combo selection, parameters, or per-stock DNA.

## Session result

V285 tested per-stock DNA walk-forward selection on top of V280 multi-family chronological SMC events.

Artifacts:
- Script: `/root/.hermes/scripts/v25/v285_v280_stock_dna_walkforward.py`
- Summary: `/root/.hermes/smc_audit/v285_v280_stock_dna_walkforward_latest.json`
- Selected rows: `v285_selected_rows.csv` under the timestamped V285 audit directory
- No-write: production/frontend/watchlist all false

## Key findings

Raw chronological opportunities were not scarce:

| Scope | Trades | Symbols | Per-stock | WR | Avg |
|---|---:|---:|---:|---:|---:|
| 2023-2026 V280 raw | 82,400 | 4,643 | 17.75 | 45.54% | +0.48% |
| 2024-2026 test | 70,556 | 4,643 | 15.20 | 47.33% | +0.68% |

Per-stock opportunity density: P25=13, P50=17, P75=22, P90=26, P95=29, max=55.

Therefore "few trades" is not a primitive/opportunity problem. It is caused by quality gates and production selectors filtering a large but unstable opportunity pool.

## Per-stock DNA result

Historical per-symbol selection did not generalize reliably:

| Selector | N | WR | Avg | 2024 WR | 2025 WR | 2026 WR |
|---|---:|---:|---:|---:|---:|---:|
| stock_dna loose | 6,681 | 47.31% | +0.54% | 48.68% | 50.10% | 39.87% |
| stock_dna balanced | 4,674 | 47.00% | +0.44% | 37.61% | 51.47% | 40.17% |
| stock_dna strict | 1,921 | 45.45% | +0.22% | - | 52.10% | 40.59% |
| stock_dna pnl | 5,120 | 47.38% | +0.49% | 39.17% | 51.81% | 40.52% |

Lesson: per-stock DNA alone is not stable enough. It can fit 2025 and still fail in 2026. Do not promote a per-stock historical selector without regime validation.

## Family-level diagnosis

Large-volume families all degraded in 2026:

| Family | N | WR | Avg | 2024 | 2025 | 2026 |
|---|---:|---:|---:|---:|---:|---:|
| ABSORB_SSL_FAST_MSS | 37,187 | 48.64% | +0.93% | 49.21 | 51.33 | 39.74 |
| UP_CONT_BOS_OB | 12,394 | 46.22% | +0.42% | 43.03 | 50.92 | 41.08 |
| RANGE_LOW_SWEEP_RECLAIM | 14,145 | 45.84% | +0.40% | 41.16 | 51.56 | 39.66 |
| REV_SSL_CHOCH_OB | 6,830 | 45.31% | +0.31% | 39.83 | 51.37 | 41.44 |

This indicates a parent market/industry regime problem rather than a single combo or single-stock personality problem.

## Durable workflow rule

When trade count seems too low:

1. First measure raw primitive and chronological opportunity density per stock.
2. If raw opportunities are plentiful, do not keep relaxing production gates blindly.
3. Test multiple SMC story families separately: reversal, continuation, range sweep/reclaim, fast absorption.
4. Run walk-forward selection, not in-sample selection.
5. If per-stock DNA fails out-of-sample, escalate to parent selectors:
   - market regime
   - industry participation
   - breadth/euphoria state
   - previous-day market/industry return
   - current year/regime drift
6. Treat high-WR low-N pockets as research candidates only unless they pass year-by-year stability and current-scanner evaluability.

## Practical conclusion

For future V286+ work, the next promising architecture is:

`Market/Industry Regime -> SMC Story Family -> Stock DNA/Parameter Pocket -> Entry/Exit Contract`

Not:

`Stock DNA -> Fixed historical best family`

and not:

`One fixed chronological combo for every stock and every regime`.
