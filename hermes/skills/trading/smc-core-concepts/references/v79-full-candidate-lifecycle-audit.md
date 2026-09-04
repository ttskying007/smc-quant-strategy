# V79 Full-Candidate SMC Lifecycle Audit

Use this reference when SMC iteration has improved metrics by filtering a selected subset but the user points out the core smart-money tracking is still not solved.

## Durable lesson

Do not treat `FVG -> OB`, `OB anchored to sweep origin`, or a single-stock POI touch as sufficient smart-money tracking. The signal layer must explicitly model the lifecycle:

1. **Trend regime**: up-continuation, down-reversal-required, recovery/transition, range/transition.
2. **SMC event**: SSL sweep + CHOCH/MSS reversal, or BOS/CHOCH/MSS continuation.
3. **Demand POI**: OB / smart-money demand zone created by the event, not a naked FVG midpoint.
4. **Entry location**: price pulls back to POI and reclaims it; distinguish valid reclaim from pre-entry POI close-break.
5. **Exit semantics**: BSL/TP hit, POI close-break, trend HL damage, or ordinary POI retest.

This addresses the user's correction: the core problem is not fields, T+1, TP/SL, or an OB anchor tweak; it is failure to track the actual smart-money lifecycle.

## Workflow rule

When validating a new lifecycle/gate layer, first backfill it onto the **full candidate layer**, not just the latest selected subset. A subset can create a false sense of progress by raising WR while destroying yearly coverage.

Required report buckets:

| Bucket | Purpose |
|---|---|
| full candidate baseline | Verify scope is not a pre-filtered subset. |
| lifecycle-valid | Shows whether trend/event/POI/entry semantics actually exist. |
| candidate gate original exit | Shows entry quality before exit repair. |
| candidate gate semantic/env exit | Shows exit repair impact. |
| yearly coverage | Reject versions with missing years, especially 2024. |
| lifecycle reject reason | Identifies whether failures are missing event, POI mismatch, or no reclaim. |
| exit semantics | Separates POI close-break, trend damage, BSL hit, normal retest. |

## V79 concrete audit result

Scope: V71/V73 full candidate layer, 9,931 trades.

| Layer | n | WR | avg | SL | cum |
|---|---:|---:|---:|---:|---:|
| V71/V73 full candidates | 9,931 | 55.15% | +0.1437% | 44.78% | +1427.48 |
| V79 lifecycle-valid | 3,802 | 60.42% | +0.5013% | 39.51% | +1905.85 |
| V79 candidate gate, original exit | 132 | 77.27% | +1.6361% | 22.73% | +215.97 |
| V79 candidate gate + environment exit | 132 | 78.03% | +1.9121% | 8.33% | +252.39 |

Yearly result for V79 candidate gate + environment exit:

| Year | n | WR | avg | SL | env exit | cum |
|---|---:|---:|---:|---:|---:|---:|
| 2023 | 18 | 88.89% | +2.5042% | 11.11% | 0.00% | +45.08 |
| 2024 | 6 | 66.67% | +1.7812% | 0.00% | 66.67% | +10.69 |
| 2025 | 88 | 78.41% | +2.0084% | 5.68% | 27.27% | +176.74 |
| 2026 | 20 | 70.00% | +0.9944% | 20.00% | 15.00% | +19.89 |

Decision: V79 is a correct architectural step but **not production-ready** because 2024 coverage remains too low. Do not promote just because aggregate WR looks good.

## Implementation pitfalls found

- If auditing full candidates, recompute `v74_core_gate` and `setup_story_v74`; do not assume V73 rows already contain V74 fields.
- Prefer 750-bar kline cache when available; 300-bar files can misalign older `entry_idx` / `confirm_bar` indices and falsely report missing lifecycle events.
- For V77/V78 gates on full candidates, attach V76 environment history and enrich V77 stock pre-entry features before calling `passes_v77_gate` / `passes_v78_gate`.
- A narrow lifecycle detector that only checks `confirm_bar` can under-detect events; compare against existing `stock_last_event` and inspect reject buckets before concluding the logic is invalid.
- Environment exits must still respect T+1: only evaluate exits after entry day.

## Files from the session

- `/root/.hermes/scripts/v25/v78_smc_lifecycle_state_machine.py` — lifecycle primitives.
- `/root/.hermes/scripts/v25/test_v78_smc_lifecycle_state_machine.py` — 5 TDD tests covering continuation, reversal, POI close-break, HL damage, and BSL TP.
- `/root/.hermes/scripts/v25/v79_full_lifecycle_audit.py` — full candidate-layer backfill/audit.
- `/root/.hermes/smc_opt_v79_full_lifecycle_audit/v79_report.json` — structured report.
- `/root/.hermes/smc_opt_v79_full_lifecycle_audit/v79_report.md` — table report.

## Next valid direction

Continue from V79 lifecycle-valid candidates. Do not simply tighten gates. Diagnose:

1. 2024 lifecycle-valid winners vs losers.
2. 2024 candidates filtered out by V79 but profitable after semantic exit.
3. Whether missing coverage is due to event detection, POI matching, or environment hysteresis over-filtering.
4. Whether reversal and continuation stories need separate yearly gates rather than one combined threshold.
