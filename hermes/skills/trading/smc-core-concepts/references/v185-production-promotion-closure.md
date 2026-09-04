# V185 production promotion closure

Date: 2026-06-26

## Trigger

Use when continuing SMC research after V175/V180-V182. This captures the later V185 qualitative improvement and frontend/API promotion steps.

## Result

V185 produced a real production-gate improvement over V175 by combining:

- V175 baseline semantic-split engine; and
- a non-overlapping true-takeover runner child.

Formal rule:

```text
V167 excluded non-overlap
AND v132_bull_count_3 >= 3
AND risk_pct >= 3.0133
AND v132_reclaim_body_range_pct >= 50
Execution: p50_time10_after_entry
```

Selector leak fields: none. Overlap with V175: 0. Same-day/T+1 violations: 0.

Metrics:

| pool | n | WR | Avg | minYear | yearWRmin | micro | T+1 |
|---|---:|---:|---:|---:|---:|---:|---:|
| V175 baseline | 247 | 83.81 | 6.0493 | 38 | 81.71 | 1.21 | 0 |
| V185 child | 87 | 93.10 | 8.0206 | 3 | 82.35 | 0.00 | 0 |
| Combined | 334 | 86.23 | 6.5628 | 41 | 82.81 | 0.90 | 0 |

Combined yearly WR:

```json
{"2023": 82.81, "2024": 87.2, "2025": 86.54, "2026": 87.8}
```

## Artifacts

Formal audit:

```text
/root/.hermes/smc_audit/v185_formal_candidate_v175_plus_child_20260626_001218/
```

Current dry-run/readiness:

```text
/root/.hermes/smc_audit/v203_v185_formal_readiness_current_dryrun_20260626_064312/
```

Shadow materialization:

```text
/root/.hermes/smc_audit/v204_v185_shadow_materialization_no_write_20260626_064406/
```

Endpoint mapping smoke:

```text
/root/.hermes/smc_audit/v205_v185_shadow_endpoint_mapping_smoke_20260626_085805/
```

Promoted production candidate artifact directory:

```text
/root/.hermes/smc_opt_v185_combined_production_candidate/
```

Files:

- `v185_trades.json/csv`
- `v185_active_picks.json/csv`
- `v185_picks.json`
- `v185_report.json`

## Frontend/API routing patch

`/root/.hermes/scripts/smc_unified.py` was minimally patched to prefer V185 over V175 when `ACTIVE_VERSION == 'V88'`:

- `V185_DIR = /root/.hermes/smc_opt_v185_combined_production_candidate`
- `_promoted_contract_dir()` prefers V185 report.
- `_active_pick_mtime()` watches `v185_active_picks.json`.
- `_v88_latest_market_date()` includes `v185_report.json`.
- `_merge_v90_daily_picks()` prefers `v185_active_picks.json`.
- `_merge_v91_shadow_picks()` respects V185 precedence.
- `_v100_production_rows()` accepts `production_eligible_v185`.
- `_promoted_trade_file()` prefers `v185_trades.json`.
- `_refresh_cache()` treats V185 as a promoted production file.
- `get_version_trades('V185')`, `get_version_picks('V185')`, and `_active_version_paths('V185')` were added.
- `reload_metrics()` prefers `v185_report.json`.
- `_api_live_prices()` numeric parsing was hardened for string `risk_pct/sl/tp1` fields.
- `_api_summary()` numeric parsing was hardened for string `pnl_pct` and V185 metrics.

GitNexus impact note:

- `reload_metrics` impact was HIGH: direct callers `build_backtest`, `build_analysis`, `build_autopsy`, `build_docs`; indirect route/API handlers.
- Several underscore helper symbols were not found by the current GitNexus index; py_compile and endpoint smoke tests were used as verification.
- `gitnexus detect-changes` failed because `/root` is not a git repository, so it could not map a git diff.

## Verified endpoints after patch

After restart of `smc_unified.py` on port 8890:

```text
/api/summary
  version=V185
  engine=V185_COMBINED_V175_PLUS_TRUE_TAKEOVER_CHILD
  total_trades=334
  win_rate=86.2
  avg_pnl=6.56
  total_pnl=2191.97

/api/picks?version=V185
  rows=6
  old event labels=0
  completed-trade pollution=0
  event_type=DEMAND_OB_TRUE_TAKEOVER_RUNNER_CHILD
  production/frontend/watchlist flags=True

/api/picks
  rows=6, routed to V185

/api/live-prices?version=V185 and /api/live-prices
  rows=6
  old event labels=0
  live rows were WATCH_ONLY because current last prices were not near entry; this is live guard behavior, not historical pollution.
```

## Interpretation

V185 is the first post-V175 path in this sequence that passed the predefined combined production gate. V183/V184 raw-Kline fresh generators failed and should not be promoted. The next research direction is no longer generic filtering or exit overlays; it is:

1. keep V185 as the promoted baseline;
2. monitor the 6 active candidates with live guard semantics;
3. continue new-supply research only if it can beat V185 combined metrics without overlap, leakage, T+1 violations, or micro-profit pollution.
