# Causal production rebuild and valid empty-book closure

Use this reference when converting a historically strong SMC result package into a current full-market production scanner, or when a requested roadmap assumes a baseline/challenger is valid before causality has been re-audited.

## Evidence-first roadmap correction

A roadmap is subordinate to causal evidence. Before implementing “rebuild baseline X” or “promote survivor Y”:

1. Audit the historical selector’s required confirmation fields.
2. Materialize `entry_idx - required_confirmation_idx` for every selected row.
3. Verify all source/event/POI/touch/reclaim/hold indices exist.
4. Check whether the source artifact was actually production-approved or only shadow/research.
5. If entry precedes required confirmation, reject the historical advantage and rewrite the roadmap. Do not preserve the requested version label by silently changing entry semantics.

A cancelled implementation task is the correct outcome when its prerequisite is disproved.

## Transactional market-data plane

Never refresh the live cache file-by-file and let a scanner observe a mixed epoch.

- Download every symbol into a staging epoch.
- Gate request coverage, dominant latest-market-date coverage, freshness, date regression/future dates, and fallback-source price alignment.
- Write a `PREPARING` promotion journal.
- Promote staged files, then atomically commit one current-epoch manifest as the final commit point.
- Recover interrupted promotions on startup.
- Before the daily close, exclude the incomplete current daily bar.
- A failed gate deletes/rejects staging and stops selector, scanner, and ingest; the prior committed epoch remains intact.

## Single production registry

Use one registry as the only execution authorization source. Report-file existence, active-looking metadata, historical picks, and shadow rows must never imply buy permission.

A row may become `BUY_VALID` only when all are true:

- committed and valid data epoch;
- explicitly promoted production strategy;
- current raw scanner source;
- signal date equals committed market date;
- independent semantic oracle passed;
- chronology passed and entry follows every required confirmation;
- strict T+1 contract;
- complete entry/zone/SL/target/provenance fields;
- no outcome/exit/PnL/MFE/MAE pollution;
- registry and row both explicitly authorize `BUY` and `tradable=true`.

Otherwise remain WATCH_ONLY or `EMPTY_BOOK`. Do not backfill yesterday’s candidates or historical winners to avoid zero picks.

## One-ontology research protocol

For a genuinely different SMC narrative:

1. Pre-register source event, POI, lifecycle, eligible entry, invalidation, liquidity target, one execution contract, promotion gate, and `search_count=1`.
2. Run an outcome-free full-market generator.
3. Independently reimplement the semantic oracle; require identity mismatch=0, chronology failures=0, duplicate failures=0, and outcome leakage=0.
4. Run exactly one frozen, gap-aware, conservative-collision, strict-T+1 replay.
5. Require aggregate, every-year, and chronological-epoch gates.
6. If it fails, mark `CLOSED_NO_VARIANTS`; do not rescue it with windows, thresholds, SL/TP, or holding-period variants.
7. Only a passing ontology may receive a current raw shadow scanner; shadow remains NO_BUY until a separate current-smoke and production review pass.

## Production closure versus strategy success

A fully correct outcome may be:

```json
{
  "state": "EMPTY_BOOK",
  "production_strategy": null,
  "shadow_challenger": null,
  "buy_enabled": false,
  "active_buy_valid_count": 0,
  "forbidden_fallback": true,
  "next_ontology": null
}
```

This proves the data/control/execution system is safe; it does not claim an economically successful strategy exists.

## Required final verification bundle

Persist one machine-readable closure artifact containing:

- direct regression-test and syntax-check results;
- refresh requested/success/failed counts, current-date coverage, epoch ID/status;
- registry state, production strategy, shadow challenger, buy flag, BUY_VALID count, fallback flag;
- HTTP status and row counts for summary, picks, and live-prices;
- browser dashboard/monitor counts and JavaScript error count;
- explicit invariants for empty-book, no historical fallback, committed epoch, and strict T+1.

Separate conclusions into: operationally proven, economically failed/closed, and not yet defined. Never describe `EMPTY_BOOK` as a failure merely because the user originally wanted rapid profitability.