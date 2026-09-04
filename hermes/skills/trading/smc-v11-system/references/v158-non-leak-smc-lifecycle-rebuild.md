# V158 Non-leak SMC lifecycle rebuild (2026-06-22)

Use this reference when continuing V154/V157 lifecycle work.

## Context

V157 showed weak 2024 months were dominated by post-entry zone death and early/PRE_BUY_GAP entries, but market breadth and future zone death are not allowed as production selectors.

V158 rebuilt the lifecycle gate using only non-leaking SMC inputs:

- No market breadth.
- No future/post-entry zone-death selector.
- Inputs limited to V132 reclaim/hold quality, V141 pre-buy price-gap availability/lifecycle metadata, and buy-decision price/chase fields.
- T+1 remains mandatory.

## Script and artifacts

- Script: `/root/.hermes/scripts/v25/v158_non_leak_smc_lifecycle_rebuild.py`
- Output: `/root/.hermes/smc_audit/v158_non_leak_smc_lifecycle_rebuild_20260622/`
- Key files: `summary.json`, `report.md`, `v158_rule_search.csv`, `v158_chosen_rows.csv`, `v158_watch_only_rejected_rows.csv`, `v158_bucket_metrics.csv`

## Chosen rule

```text
TT2_SECOND_CONFIRM_OR_CHASE_LE_3
+
NONSTRICT_RECLAIM_BODY_LE_86_6
```

Semantics:

1. TRUE_TAKEOVER_2 must either have strict secondary confirmation (`v132_true_takeover_3_strict`) or low entry chase (`entry_chase_above_zone_pct <= 3`).
2. Non-strict takeovers with blow-off reclaim bodies (`v132_reclaim_bull_body_pct > 86.6124`) are downgraded to `WATCH_ONLY`.
3. Full `PRE_BUY_GAP_NOTE_ONLY` ban is rejected: it destroys yearly coverage. V158 keeps PBG only when the TT2/chase/body quality rule passes.

## Verified metrics

| version | n | WR | Avg | Median | Loss | min_year_n | 2023 WR | 2024 WR | 2025 WR | 2026 WR | T+1 |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| V154 baseline | 247 | 82.59 | 3.2709 | 3.9216 | 17.41 | 35 | 87.30 | 75.00 | 90.57 | 82.86 | 0 |
| V158 chosen | 214 | 84.11 | 3.5357 | 3.9804 | 15.89 | 35 | 90.57 | 78.05 | 88.64 | 82.86 | 0 |

Release gate used in script: `n >= 200`, `min_year_n >= 35`, overall `WR >= 82`, `avg >= 3.0`, `2024 WR >= 78`, `T+1 violations == 0`.

V158 passes this research release gate but is not production-promoted yet.

## Important interpretation

- The successful rule is a lifecycle-quality rule, not market-state filtering.
- The rejected bucket is weak: 33 trades, WR 72.73, avg 1.5537, 2024 WR 57.14.
- PBG all-skip is not acceptable; PBG kept by V158 is materially stronger (114 trades, WR 83.33, 2024 WR 79.55) than PBG rejected (32 trades, WR 71.88, 2024 WR 57.14).

## Next required closure before production

Do not directly promote from research CSV. Required next steps:

1. Implement same rule in scanner/backtest source, not as CSV post-filter.
2. Full-market same-source rerun.
3. Produce current watchlist from latest K-lines, not historical trades.
4. Verify `/api/picks`, `/api/live-prices`, `/api/summary`, K-line BUY/SL/TP markers, and frontend reload behavior.
5. Run T+1 and field-contract audits before changing default production version.
