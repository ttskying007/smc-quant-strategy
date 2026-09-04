# Intraday data and causality closure (V367–V371)

Use this when a daily SMC research branch is exhausted and the next hypothesis needs 60-minute confirmation.

## Decision hierarchy

1. Do **not** keep mining daily scalar gates after strict daily sequence, broader supply, exits, and independent OOS have failed.
2. Before building an MTF generator, prove historical intraday coverage at the exact intended universe and dates.
3. Compare each symbol’s intraday dates against its available daily dates—not against a blanket all-years expectation, because IPO/listing history differs.
4. Treat a source as usable only when each expected trading day has the expected A-share 60-minute slots and valid OHLCV.
5. Only after source coverage passes: build cache → generate causal 60m POI lifecycle → next-bar executable entry → full-market daily T+1 replay → independent semantic and leakage audit.

## Strict coverage contract

For each eligible SH/SZ symbol and each daily-cache date in the analysis range:

- exactly four 60m bars;
- expected slots: `10:30`, `11:30`, `14:00`, `15:00` (Baostock raw suffixes `103000000`, `113000000`, `140000000`, `150000000`);
- no missing expected daily dates;
- report unexpected dates separately;
- preserve per-symbol/year coverage, failures, and data-source query status;
- a source failure means **no MTF performance or production claim**.

## Provider-session pitfall

Validate connection/session behavior with a small sample before full-universe execution. If concurrent provider logins yield authentication-state, network-receive, or broken-worker errors, rerun the same probe serially; use the verified serial session model as the audit default. Do not label the data missing based on a concurrency-induced failure. A successful serial probe proves only provider-session stability, never full-universe coverage.

## Probe-to-universe escalation rule

A small serial probe is only a provider feasibility check. It may verify login stability, year-chunk behavior, valid A-share slots, and a source’s ability to return older bars, but it **must not** unlock QFQ alignment, an MTF generator, or any performance claim.

Before downstream work, run the strict coverage audit across the full intended universe (normally `>=4000` eligible SH/SZ symbols), preferably as a tracked background job because serial provider sessions are the verified safe mode. Treat a report with a small `universe_symbols` count as `PREFLIGHT_ONLY`, even if every sampled symbol/year passes. The required full gate is:

- zero query failures;
- zero expected-date or slot failures;
- each symbol compared with its own daily-date availability;
- explicit full-universe count persisted in the latest report.

Only then may QFQ/raw price alignment begin.

## Mandatory future-data audit for delayed confirmations

Any feature such as `takeover_2`, `takeover_3`, `bull_count_3`, post-reclaim hold, or post-reclaim pullback is unknown before those future bars close.

The valid chain is:

`event → POI → touch → reclaim → delayed confirmation bars → next executable open entry`

Never backtest an entry before its required confirmation index. Audit every row with:

- `entry_idx >= confirm_idx + 1`;
- no feature reads from a bar at or after entry except the fill/open price explicitly defined by the execution contract;
- strict A-share exit start at the next trading day (T+1);
- independent re-derivation of the confirmation indexes.

If a candidate condition reads two/three later bars while `entry_idx` is earlier, its entire associated result family is invalid evidence, including apparent OOS performance.

## Reference artifacts

- Source audit script: `/root/.hermes/scripts/v25/v371_baostock_m60_strict_coverage_audit.py`
- Causality rejection: `/root/.hermes/smc_audit/v366_v365_candidate_causality_audit_latest.json`
- Daily lifecycle/replay baseline: V357–V359 audit artifacts.
