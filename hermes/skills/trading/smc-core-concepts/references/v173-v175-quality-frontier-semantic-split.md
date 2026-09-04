# V173/V175 quality frontier + semantic split lesson (2026-06-23)

Trigger: V172 is production-usable, but user asks what research direction is next and whether previous P4/P10/P11 work is actually closed.

## Acceptance boundaries used

Production default replacement requires all of:
- n >= 200
- min_year_n >= 35
- WR >= 84%
- AvgPnL >= 6.2%
- micro_profit_pct <= 1%
- all yearly WR >= 82%
- T+1 violations = 0

Research overlay only:
- n >= 150
- min_year_n >= 25
- WR >= 85%
- AvgPnL >= 6.0%
- all yearly WR >= 83%
- T+1 = 0

Anything below these is not allowed to replace production.

## V173 result

Best scalar overlay over V172:

```text
V172 + risk_pct in [3,8]
AND v132_reclaim_close_above_zone_high_pct >= 0.5
AND touch_to_reclaim_bars <= 1
```

Metrics: 169 trades / WR 86.98% / Avg +6.2193% / SL 7.10% / min_year_n 27 / all yearly WR >=85% / T+1=0.

Decision: `RESEARCH_OVERLAY_USABLE`, not production default. Scalar gates hit the coverage ceiling; do not keep endlessly adding thresholds.

Artifacts:
- `/root/.hermes/smc_audit/v173_v172_next_quality_frontier_20260623/summary.json`
- `/root/.hermes/smc_audit/v173_v172_next_quality_frontier_20260623/report.md`

## V174 P4 structure hierarchy audit

Strict classical SSL sweep -> CHOCH test on V172 showed:
- PASS only 11/247
- NO_CLASSICAL_SSL_SWEEP 158/247, yet this bucket had WR 87.34%, Avg +6.61%
- NO_CLASSICAL_CHOCH 65/247, WR 76.92%

Conclusion: the profitable production edge is not classical SSL_SWEEP_CHOCH. It is better described as `DEMAND_OB_TRUE_TAKEOVER_RECLAIM`. Do not force strict P4 classical hierarchy as a production filter; it kills or mislabels the actual edge.

Artifacts:
- `/root/.hermes/smc_audit/v174_v172_wave_structure_hierarchy_20260623/summary.json`
- `/root/.hermes/smc_audit/v174_v172_wave_structure_hierarchy_20260623/report.md`

## V175 semantic split repair

Materialized label-only production contract:
- Directory: `/root/.hermes/smc_opt_v175_semantic_split/`
- Engine: `V175_DEMAND_OB_TRUE_TAKEOVER_SEMANTIC_SPLIT`
- Metrics identical to V172: 247 / WR 83.81% / Avg +6.0493% / SL 8.91% / min_year_n 38 / T+1=0
- Primary `event_type`: `DEMAND_OB_TRUE_TAKEOVER_RECLAIM`
- Preserves old label in `original_event_type`
- Adds `semantic_contract_key`, `classical_structure_status`, `classical_sweep_choch_claim`

Frontend/API routing was patched to prefer V175 over V172. Verification:
- `/api/summary`: V175
- `/api/picks`: 26 rows, event_type all `DEMAND_OB_TRUE_TAKEOVER_RECLAIM`, 0 field missing
- `/api/live-prices`: 26 rows, 0 tradable / 26 watch-only, semantic fields present
- Browser `/`: V175, no JS errors, no `DNA UNKNOWN`, no old exact `SSL_SWEEP_CHOCH_REVERSAL` overclaim

Follow-up pitfall fixed after compaction: label-only promotion must also rewrite nested display contracts, not only top-level `event_type`/`combo_contract_key`.
- Patch `v175_semantic_split_materialize.py::enrich()` to override `combo_entry_rule`, `combo_wait_rule`, `combo_sl_rule`, `combo_tp_rule`, `combo_production_gate`, nested `combo_contract`, `smc_dna.best_event_type`, `smc_dna.effective_combo`, and row-level `dna_best_event_type`.
- Preserve old labels only in explicit provenance fields: `original_event_type`, `original_combo_contract_key`, `smc_dna.best_event_type_original`, `smc_dna.effective_combo_original`, `smc_dna.event_stats_original`.
- Also force row write flags to real production contract booleans: `production_write=True`, `frontend_write=True`, `watchlist_write=True`, `dry_run_only=False`; source V172 scanner rows may carry stale string `'False'` flags.
- Re-run script and verify both files and APIs have `bad_combo=0`, `bad_dna=0`, top-level `event_type` all `DEMAND_OB_TRUE_TAKEOVER_RECLAIM`, T+1 violations 0.
- Manual frontend refresh pitfall: `smc_unified.py` originally ignored POST JSON bodies and `/api/reselect` always used legacy `ACTIVE_VERSION` (`V88`), so the monitor button could rerun V88 instead of the V175 overlay. Fix: parse POST JSON/form body into `qs`, make `/api/reselect` accept `version/ver`, default V88+V175 artifacts to `run_version=V175`, and route V175 to `v175_semantic_split_materialize.py` with `v175_report.json` as metrics.

## Next research direction

Do not keep scalar-gate iteration unless it beats the production boundary above. Next real work is a clean two-layer generator:
1. `DEMAND_OB_TRUE_TAKEOVER_RECLAIM` production layer (current V175)
2. separate classical `SSL_SWEEP_CHOCH` research layer with strict pivot hierarchy, not mixed into production labels.
