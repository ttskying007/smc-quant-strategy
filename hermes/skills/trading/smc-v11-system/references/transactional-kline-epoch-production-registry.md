# Transactional K-line Epoch + Fail-Closed Production Registry

Use this pattern when a full-market refresh, scanner, or dashboard must never consume a partially refreshed universe or infer production status from historical report files.

## Durable architecture

```text
fetch all symbols into immutable staging epoch
→ evaluate coverage/date/freshness/alignment gates on staging
→ write PREPARING promotion journal
→ hard-link/copy production targets into rollback backup
→ promote staged files
→ atomically commit current epoch manifest LAST
→ mark journal COMMITTED
```

A file-level atomic write is not a universe-level transaction. Writing each successful symbol directly into the live K-line directory before the aggregate gate finishes is fail-open: a failed refresh leaves a mixed-date production cache.

## Recovery rule

At startup, scan promotion journals:

- `PREPARING` + current manifest does not name that epoch: restore backups and mark `ROLLED_BACK`.
- `PREPARING` + current manifest already names that epoch as `COMMITTED`: promotion succeeded; mark journal `COMMITTED` and do not roll back.
- The current manifest is the sole commit point. Scanner and daily ops must reject missing, corrupt, non-COMMITTED, or epoch-mismatched manifests.

## Consumer admission contract

A refresh is usable only when all are true:

```text
process returncode == 0
summary.gate_pass == true
summary.epoch_status == COMMITTED
summary.epoch_id is non-empty
current_manifest.status == COMMITTED
current_manifest.epoch_id == summary.epoch_id
current_manifest.market_date == summary.observed_latest_date
```

Anything else stops selector and ingest. It must not fall back to an old strategy, historical picks, or a report-file-based active version.

## Registry-bound BUY authorization

Do not stop at checking `BUY_VALID` fields on the pick itself. A stale or crafted row can carry `is_active_pick=true`, `live_guard_status=BUY_VALID`, `trade_action=BUY`, `buy_enabled=true`, and `tradable=true` while the system registry is `EMPTY_BOOK`.

Automatic ingestion must additionally require:

- registry `buy_enabled=true` and non-empty `production_strategy`;
- row strategy equals the promoted registry strategy;
- registry data epoch is valid and `COMMITTED`;
- row `data_epoch_id` equals the registry epoch and signal date equals its market date;
- `current_raw_scanner_source=true`;
- `semantic_oracle_pass=true`, `chronology_pass=true`, and `strict_t1_contract=true`.

The frontend live guard must also consult the registry before emitting `BUY_VALID`. Under `EMPTY_BOOK`, an active-looking historical row is rendered as `WATCH_ONLY_PRODUCTION_REGISTRY_BLOCKED`; durable legacy OPEN positions may remain visible for risk monitoring but cannot authorize a new buy.

## Mandatory verification

1. Hash the complete production K-line file set.
2. Run a refresh that downloads into staging and injects an aggregate gate failure.
3. Assert nonzero refresh exit, `epoch_status=REJECTED`, no current-manifest commit, and identical before/after production checksum.
4. Run a healthy full-universe refresh and verify committed manifest, market date, coverage, and scanner acceptance.
5. Simulate interrupted promotion and verify startup rollback restores the previous file.

## Explicit production registry

Do not infer the active strategy from `*_report.json` existence. Maintain one registry with:

```json
{
  "state": "EMPTY_BOOK",
  "production_strategy": null,
  "shadow_challenger": null,
  "buy_enabled": false,
  "active_buy_valid_count": 0,
  "forbidden_fallback": true,
  "data_epoch": {"status": "COMMITTED"}
}
```

Historical winners rejected by causality audits belong in `REJECTED_RESEARCH`; lineages with no causal survivor belong in `NEGATIVE_CONTROL`. Neither may occupy the production or shadow slot.

`EMPTY_BOOK` is a valid successful operational state, not a pipeline error. Daily ops should return success, ingest zero rows, and expose the same state through summary, picks, live-prices, frontend, and push surfaces.

### Post-close provider lag and display-date rule

A strict current-date coverage failure immediately after close may be a provider publication lag, not a reason to weaken the gate. Re-probe the complete universe by `provider × market × latest_date`; keep the previous committed epoch until the unchanged threshold passes. The ops/display `data_date` must come only from the committed current manifest—never from a rejected refresh summary's `latest_counts`, even when downstream scanning is already skipped. `/api/live-prices` must return explicit registry fields (`production_state`, strategy/shadow, `buy_enabled`, BUY_VALID count, forbidden fallback) alongside an empty picks list so clients do not infer state from emptiness.

## Evidence must override the roadmap

Before implementing a planned baseline or challenger, read the latest causality, independent-oracle, frozen-replay, and closure artifacts. If a planned lineage was later rejected, correct the plan instead of implementing the stale roadmap.

Once a distinct ontology has completed its single frozen replay and failed annual/epoch gates, mark it `CLOSED_NO_VARIANTS`. Do not reopen it through windows, thresholds, SL/TP, or holding-period changes. A completed research program should expose `next_ontology=null` until a genuinely different predeclared SMC ontology exists.