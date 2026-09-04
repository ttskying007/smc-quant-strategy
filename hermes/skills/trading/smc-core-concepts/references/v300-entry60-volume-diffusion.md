# V300 entry-session 60m volume diffusion audit

Date: 2026-07-03
Mode: no-write research audit. No production/frontend/watchlist writes.

## Hypothesis

After V297-V299, price-only 60m lifecycle gates still left weak months. Test whether entry-session executable 60m **volume diffusion** across market + industry + stock separates real board-fund continuation from false ACC→MAN→DIS takeovers.

## Source

- Source rows: `/root/.hermes/smc_audit/v299_strict_60m_lifecycle_no_write_20260703_141331/v299_rows.csv`
- Script: `/root/.hermes/scripts/v25/v300_entry60_volume_diffusion_audit.py`
- Summary: `/root/.hermes/smc_audit/v300_entry60_volume_diffusion_latest.json`
- Two-year guard: `/root/.hermes/smc_audit/v300_entry60_volume_diffusion_no_write_20260703_142439/v300_two_year_stability_probe.json`

## Method

For each V299 strict lifecycle candidate:

1. Use entry-date first/second/third 60m bars only.
2. Build stock context: return, close, low/high, 60m volume ratio vs previous five sessions.
3. Build market/industry context: up percentage, median return, median volume ratio, up-with-volume percentage, strong-up-with-volume percentage.
4. Require executable confirmation: stock low holds above ACC/zone low and close remains above ACC high.
5. Simulate delayed entry at k-th 60m close with daily T+1 replay.
6. Evaluate market/industry/stock volume diffusion grids; then re-mine with two-year guard.

Selectors use only entry-time fields (`confirm_k`, `mkt_up`, `ind_up`, `mkt_up_vol`, `ind_up_vol`, `stock60_vol_ratio`, `stock60_ret`, relative industry-volume lead). No `pnl`, `reason`, `exit`, MFE/MAE, or post-entry outcome fields are used for selection.

## Results

Raw V299 source:

| N | WR | Avg | 2025 WR | 2026 WR | weakest month |
|---:|---:|---:|---:|---:|---:|
| 65,387 | 50.69% | +0.73% | 57.89% | 48.50% | 202603: 30.63% |

V300 executable volume-enriched rows:

| N | WR | Avg | 2025 WR | 2026 WR | weakest month | T+1 violations |
|---:|---:|---:|---:|---:|---:|---:|
| 137,551 | 48.55% | +0.55% | 57.23% | 45.91% | 26.88% | 0 |

Best automatic high-WR pocket (not production-stable because it only covers 2026):

| Rule | N | WR | Avg | Year coverage | Min month WR | T+1 |
|---|---:|---:|---:|---|---:|---:|
| `k1_mup50_iup50_muv35_iuv20_svol1.3_sret0.0_raw` | 1,628 | 72.11% | +4.07% | 2026 only | 59.70% | 0 |

Two-year guarded best-by-stability:

| Rule | N | WR | Avg | 2025 WR | 2026 WR | Min month WR | T+1 |
|---|---:|---:|---:|---:|---:|---:|---:|
| `k2_mup65_iup65_muv20_iuv20_svol1.0_sret0.0_raw` | 3,935 | 53.04% | +1.44% | 58.50% | 51.36% | 37.28% | 0 |

Two-year guarded best-by-quality:

| Rule | N | WR | Avg | 2025 WR | 2026 WR | Min month WR | T+1 |
|---|---:|---:|---:|---:|---:|---:|---:|
| `k1_mup65_iup50_muv20_iuv20_svol1.3_sret0.0_raw` | 4,261 | 57.59% | +2.26% | 58.64% | 57.33% | 33.64% | 0 |

## Interpretation

- Entry-session volume diffusion is informative: it creates strong recent pockets and improves average PnL/SL rate in some surfaces.
- But the high-WR pocket is 2026-only and cannot be promoted.
- Under a two-year guard, volume diffusion still fails monthly stability: weak months remain around 33-37% WR.
- Therefore, **60m price + volume diffusion is still not sufficient**. It is a useful state layer, not a production-closed signal.

## Decision

Do not promote V300. Do not continue tuning only 60m market/industry volume thresholds.

Next direction must use a more granular or more causal source layer:

1. 15m / lower-timeframe takeover sequence if full historical data can be obtained.
2. Auction/opening-call and first 15m amount persistence.
3. Real sector-leading diffusion / limit-up board leadership / northbound or active funds data.
4. If no new data is available, stop this 60m-threshold branch and treat V300 as closure evidence.

## Verification

Focused ad-hoc verification passed:

- py_compile/import of V300 script
- summary no-write/source contract
- artifact row counts
- T+1 violations = 0
- selector config contains no outcome leakage fields
- two-year stability probe exists and has 424 variants

Output:

```json
{
  "status": "PASS",
  "enriched_rows": 137551,
  "best_rows": 1628,
  "two_year_variants": 424
}
```
