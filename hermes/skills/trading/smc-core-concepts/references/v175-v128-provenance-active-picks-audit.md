# V175 / V128 provenance + active-picks audit lesson

Use this when validating V175 semantic-split artifacts against V128 parallel shadow scanner data, especially after the scanner has been regenerated.

## Core distinction

- `v128_parallel_shadow_candidates.json` is scanner/candidate-source data. It is large, outcome-free, and uses original event labels such as `SSL_SWEEP_CHOCH_REVERSAL` / `BOS_CONTINUATION`.
- `v175_trades.json` is V172 economics plus a V175 semantic label repair. It changes the production-facing event label to `DEMAND_OB_TRUE_TAKEOVER_RECLAIM` and preserves the old label in `original_event_type`.
- Therefore V175 will **not** match V128 by `event_type`; use `original_event_type` for source lineage checks.

## Correct lineage matching

For V175 rows, match back to V128/V161/V164/V167/V172 source lineage with:

```text
symbol + entry_date + original_event_type + poi_source
```

Do not use:

```text
symbol + entry_date + event_type + poi_source
```

because V175 intentionally rewrites `event_type` to `DEMAND_OB_TRUE_TAKEOVER_RECLAIM`.

Optional stricter checks:

- Add `entry_idx` when comparing V175 to V172/V167 materialized trade rows.
- Use rounded `zone_low/zone_high` only as a secondary check; regenerated scanner snapshots can shift zones/entry by a few bars/prices.

## Snapshot-staleness pitfall

If current V128 has a newer mtime than V175 artifacts, apparent mismatches may mean the scanner was regenerated after V175 was materialized, not that V175 is corrupt.

Audit sequence:

1. Record mtimes and row counts for V128, V161, V164, V167, V172, V175 artifacts.
2. Compare V175 historical trades against the V172 artifact it actually inherited from.
3. Separately recompute current active candidates from the latest V128 using the V161→V164→V167→V172 gate chain in memory/read-only mode.
4. If current V128-derived active count differs from `v175_active_picks.json`, conclude **active-picks materialization is stale**, not that the historical V175 backtest is invalid.

## Active-picks pollution checks

For `/api/picks?version=V175` active candidates, require:

- `event_type == DEMAND_OB_TRUE_TAKEOVER_RECLAIM`
- `original_event_type` preserved
- `pick_scope == ACTIVE_CANDIDATE`
- `is_active_pick == True`
- no completed-trade pollution: no completed `exit_date`, no `TP/SL/GAP_SL/TIME` exit reason, no realized `hold_bars`, no realized MAE/MFE/RR

For `/api/live-prices?version=V175`, `exit_reason=HOLDING`, `hold_bars=0`, and live `pnl_pct` are live-monitor state, not historical-trade pollution.

## Read-only current-candidate recompute pattern

When only diagnosing, do not patch production files. Recompute in memory from current V128:

```python
from v161_dry_run_scanner_contract import build_row, kline_path, load_json
from v164_corrected_scanner_dry_run import enrich_v164
from v167_exact_scanner_dry_run import rule_pass as v167_rule_pass
from v172_v167_high_quality_gate import gate as v172_gate

# Build V161/V164 features from current V128 + kline cache,
# then filter recent45 -> V164 -> V167 -> V172.
```

Expected interpretation:

- V175 historical trade metrics stay tied to the frozen V172/V175 artifacts.
- Active picks should be rematerialized only after confirming the latest V128-derived gate output.
- A strategy/code change is not justified by active-pick staleness alone; first rerun the materialization chain and recheck API contracts.
