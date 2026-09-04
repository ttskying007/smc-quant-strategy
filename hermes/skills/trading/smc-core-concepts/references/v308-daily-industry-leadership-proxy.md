# V308 Daily Industry Leadership Proxy Audit

## Trigger
V307 confirmed the strongest near-term branch is `industry-led opening gap + first120 15m industry leadership + candidate participation`, but the 15m cache only covers the recent 202604-202607 window. V308 tests whether **daily-only, scanner-time-safe proxies** can reproduce the industry leadership signal across the full 2023-2026 V280 chronological SMC candidate set.

## Scope
- Script: `/root/.hermes/scripts/v25/v308_daily_industry_leadership_proxy_audit.py`
- Result: `/root/.hermes/smc_audit/v308_daily_industry_leadership_proxy_latest.json`
- Safe combo probe: `/root/.hermes/smc_audit/v308_daily_industry_leadership_proxy_safe_combo_probe.json`
- Source rows: V280 full-history chronological candidates
- No production/frontend/watchlist writes.

## Leakage Guard
The first run exposed an important issue: using same-day close/low/high (`OPEN_HOLD`, drawdown, push) would be post-entry leakage for a daily-open execution contract. The script was patched to keep only **entry-open-known** fields:

- candidate stock opening gap vs previous close
- market opening gap breadth
- industry opening gap median / gap-up breadth / rank
- V280 pre-existing SMC family/regime/risk/range fields

Forbidden selector fields removed from enriched output:

- `stock_open_hold`
- `stock_gap_participate`
- `open_drawdown_pct`
- `open_push_pct`
- `open_to_close_pct`
- `day_ret_pct`

## Coverage

| Scope | Rows | Symbols | Years | T+1 violations |
|---|---:|---:|---|---:|
| V280 source | 82,400 | 4,643 | 2023-2026 | 0 |
| V308 enriched | 81,686 | 4,603 | 2023-2026 | 0 |

Baseline after daily proxy coverage:

| N | WR | Avg | 2023 | 2024 | 2025 | 2026 |
|---:|---:|---:|---:|---:|---:|---:|
| 81,686 | 45.55% | +0.48% | 34.86 | 46.01 | 51.32 | 40.23 |

## Main Results

Simple daily leadership dimensions improve the baseline but do **not** reach production quality:

| Dimension | N | WR | Avg | Year WR issue |
|---|---:|---:|---:|---|
| `mkt_gap_up>=75%` | 10,896 | 57.68% | +2.49 | 2023 41.94 / 2026 44.06 |
| `ind_gap_up>=75%` | 14,395 | 56.03% | +2.09 | 2023 41.26 / 2026 42.46 |
| `daily_leader_gap_up` | lower quality than V307 first120 | — | — | daily open alone lacks continuation proof |

Safe expanded combo mining tested 525 selector combinations while excluding post-open outcome fields. Best larger stable pockets:

| Safe Combo | N | WR | Avg | Year WR |
|---|---:|---:|---:|---|
| `RANGE_LOW_SWEEP_RECLAIM + ind_gap_up>=75 + ind_gap_ge1<45 + mkt_gap_up>=75` | 1,747 | 57.18% | +1.41 | 2023 53.80 / 2024 65.75 / 2025 56.45 / 2026 55.66 |
| `RANGE_LOW_SWEEP_RECLAIM + RNG>=25 + ind_gap_up>=75 + mkt_gap_up>=75` | 966 | 56.31% | +1.29 | 2023 55.65 / 2024 53.79 / 2025 57.52 / 2026 55.92 |
| `RANGE_LOW_SWEEP_RECLAIM + RNG15_25 + ind_gap_ge1<45 + mkt_gap_up>=75` | 935 | 56.90% | +1.47 | 2023 54.26 / 2024 73.28 / 2025 53.72 / 2026 58.40 |

These are useful diagnostic state layers but not production quality. Monthly minima remain unstable because opening-gap breadth does not prove real intraday takeover.

## Interpretation

V308 answers V307's open question:

1. **Daily open industry proxy works as a weak state layer**: market/industry gap breadth lifts V280 from 45.55% WR to mid/high-50s in broad pockets.
2. **It does not reproduce V307 first120 leadership**: the strong V307 70%+ pockets require intraday continuation/participation, not just opening gap.
3. **The safe signal is `opening breadth`, not `industry leader transmission`**: once post-open fields are removed, no daily-only proxy reaches production-level stability.
4. **RANGE_LOW_SWEEP_RECLAIM is the only family that consistently benefits** from full-history daily opening breadth; other families remain unstable.

## Closure

Do not promote V308 to production. Do not continue tuning daily opening-gap buckets alone.

Next concrete direction:

`Daily market/industry opening breadth → executable intraday continuation proof → candidate same-source POI lifecycle`

Specifically, the next iteration should test whether a scanner-time intraday module can wait for **first 15/30/60/120 minute industry continuation** after an opening-breadth state, because V308 proves daily open is insufficient while V307 proves first120 continuation is strong.

## Verification
Focused ad-hoc verifier passed:

- helper bucket boundaries
- metrics fixture
- source V280 count recomputation
- no-write artifact contract
- T+1=0
- selector field safety: no same-day high/low/close derived fields in output
- safe combo probe contract

Verifier output: `status=PASS`, V280 rows=82,400, enriched rows=81,686, T+1=0.
