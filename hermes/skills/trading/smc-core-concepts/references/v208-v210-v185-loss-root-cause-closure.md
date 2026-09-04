# V208-V210 V185 loss root-cause and refinement closure

Date: 2026-06-26

## Trigger

Use when continuing after V185 production candidate and the user asks to analyze lower-WR/losing rows and decide whether to keep iterating.

## Fixed gates used before search

New production improvement over V185 requires:
- non-leaking source-side/execution rule;
- T+1 / same-day exit violations = 0;
- `n >= 300`;
- `min_year_n >= 40`;
- `WR >= 87%`;
- `AvgPnL >= 6.8%`;
- `all_year_WR_min >= 84%`;
- `micro_profit_pct <= 1%`;
- improves both WR and AvgPnL vs V185 combined baseline.

Research-only usable requires at least:
- `n >= 260`, `min_year_n >= 35`, `WR >= 88%`, `AvgPnL >= 6.8%`, `all_year_WR_min >= 84%`, `micro <= 1%`, T+1=0.

Unusable/closed:
- outcome/realized path filters (`exit_reason`, `pnl`, `MAE/MFE`, `hold_bars`, hit flags, realized RR);
- year-only filters;
- high WR pockets with sample collapse or poor year coverage;
- execution replays that require waiting for deeper POI retouch but collapse WR/fill rate.

## Artifacts

- V208 loss/root-cause + non-leak frontier: `/root/.hermes/smc_audit/v208_v185_loss_root_cause_frontier_20260626_175542/`
- V209 source-aware refinement: `/root/.hermes/smc_audit/v209_v185_source_aware_refinement_20260626_175825/`
- V210 entry-quality replay: `/root/.hermes/smc_audit/v210_v185_entry_quality_replay_20260626_180213/`

## V185 baseline

| n | WR | AvgPnL | minYear | yearWRmin | micro | T+1 |
|---:|---:|---:|---:|---:|---:|---:|
| 334 | 86.23% | 6.5628% | 41 | 82.81% | 0.90% | 0 |

Source split:

| pool | n | WR | AvgPnL | minYear | yearWRmin | micro | SL-like |
|---|---:|---:|---:|---:|---:|---:|---:|
| V175 baseline rows | 247 | 83.81% | 6.0493% | 38 | 81.71% | 1.21% | 8.91% |
| V185 child rows | 87 | 93.10% | 8.0206% | 3 | 82.35% | 0.00% | 26.44% |
| Combined | 334 | 86.23% | 6.5628% | 41 | 82.81% | 0.90% | 13.47% |

## Loss root cause

V185 has 46 losers. Losses are not mainly from the child; the weak side remains the V175 baseline component:
- V175 rows: WR `83.81%`, Avg `6.0493%`, yearWRmin `81.71%`.
- V185 child: WR `93.10%`, Avg `8.0206%`, but low standalone coverage (`min_year_n=3`).

Loser source-side feature deltas vs winners:
- `risk_pct`: losers mean `6.6157` vs winners `5.9834`.
- `v132_reclaim_close_pos_pct`: losers mean `81.0864` vs winners `74.8787`.
- `entry_chase_above_zone_pct`: losers mean `2.7361` vs winners `2.4892`.
- `v85_zone_width_pct`: losers mean `3.2120` vs winners `2.9107`.

Interpretation: lower-WR rows are mostly high-risk / higher close-position / more chase-after-zone V175-style rows. This is an entry-quality and source-supply issue, not a generic exit problem.

## V208 non-leak scalar frontier

Best non-leak filters improved WR but failed production improvement because Avg stayed near V185 and sample/year coverage weakened:

- `risk_pct<=8.48852 AND v132_reclaim_body_range_pct<=62.3987`: `n=273`, WR `88.28%`, Avg `6.6602%`, minYear `36`, yearWRmin `86.49%`, micro `0.73%`.
- `risk_pct<=8.48852`: `n=300`, WR `87.33%`, Avg `6.5890%`, minYear `37`, yearWRmin `83.61%`, micro `0.67%`.

Decision: `V208_RESEARCH_FRONTIER_FOUND__NOT_PRODUCTION_YET`.

## V209 source-aware refinement

Keeping all V185 child rows and filtering only V175 rows produced high-WR pockets, but all collapsed sample/year coverage:

- Top example: `V175.v132_bull_count_3>=3 AND V175.v132_post_min_low_pullback_pct_3>=1.71011` → `n=120`, WR `95.00%`, Avg `8.5429%`, but minYear `4`.
- No production pass, no near-frontier pass, no research overlay pass.

Decision: `V209_NO_SOURCE_AWARE_UPGRADE__CLOSED`.

## V210 entry-quality replay

Tested waiting for deeper post-confirmation retouch (`zone_high`, `smart_money_cost`, `zone_low`) up to 1/2/3/5/8/10 bars, with strict T+1 exit replay.

Result: all variants failed badly. Best fill-rate variants had WR only ~39% and small/negative median because demanding a later zone retouch selects failed/weak setups rather than improving entry.

Decision: `V210_ENTRY_REPLAY_NO_GATE_PASS__ENTRY_CHASE_NOT_SOLE_ROOT_CAUSE`.

## Direction closure

Closed:
- simple V185 scalar filters;
- source-aware V175 pruning;
- delayed/deeper zone retouch execution;
- generic entry chase repair.

Current usable baseline remains V185 combined. To create another qualitative change, do not keep filtering V185/V175 rows. Next research must change candidate supply or add a genuinely new pre-entry information layer:

1. **new supply generator** anchored on post-reclaim takeover persistence before entry, not just inherited V167/V175 rows;
2. **sector/market participation layer** if available before entry, but not as standalone scalar filter;
3. **historical intraday candidate generation** (not just exit replay) if 60m cache coverage is sufficient;
4. otherwise stabilize V185 production/cron/live guard instead of endless research.
