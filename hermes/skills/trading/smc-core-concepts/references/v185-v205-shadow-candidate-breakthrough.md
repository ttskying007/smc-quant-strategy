# V185-V205 shadow candidate breakthrough

Date: 2026-06-26

## Trigger

Use when deciding post-V175 SMC research direction, especially after earlier daily-OHLCV attempts seemed exhausted. This reference supersedes older closure statements that said no daily-OHLCV improvement existed before V185 formal validation.

## Usability gates

Production-upgrade gate used here:
- non-leaking source-side selector;
- T+1/same-day exit violations = 0;
- combined engine `n >= 260`;
- `min_year_n >= 40`;
- `WR >= 84%`;
- `AvgPnL >= 6.2%`;
- `all_year_WR_min >= 82%`;
- `micro_profit_pct <= 1%`;
- no frontend/watchlist/API production writes before dry-run and endpoint mapping pass.

Research child engine alone remains not production-usable unless it also has enough year coverage (`n>=120`, `min_year_n>=20`).

## Closed/unusable paths before breakthrough

- V177 generic executable exits on V175: no improvement over V175.
- V178 TIME attribution: heterogeneous; not a single exit bug.
- V179 initial 60min coverage: insufficient for production claims.
- V180/V181 V128/V167 scalar filters: no usable child/production frontier.
- V182 runner-only on broad V181 child: improved Avg but broke WR/year stability.
- Many fresh daily candidate generators (range spring, V81 supply, absorption, accumulation, limit-up retest, peer/breadth gates, target-room mining) failed their gates.

## Breakthrough candidate

Formal candidate artifact:
- `/root/.hermes/smc_audit/v185_formal_candidate_v175_plus_child_20260626_001218/`
- Decision: `V185_COMBINED_PRODUCTION_GATE_PASS__SHADOW_ONLY`.
- Selector: `V167 excluded non-overlap AND v132_bull_count_3>=3 AND risk_pct>=3.0133 AND v132_reclaim_body_range_pct>=50`.
- Execution overlay: `V184 p50_time10_after_entry` — take 50% at TP; BE-lock remainder; close remaining at entry+10 bars if not stopped.
- Selector leak fields: `[]`.
- Overlap with V175: `0`.
- production/frontend/watchlist writes: `False`.

Metrics:
- V175 baseline: `n=247`, `WR=83.81%`, `Avg=6.0493%`, `minYear=38`, `yearWRmin=81.71%`, `micro=1.21%`, same-day=0.
- V185 child alone: `n=87`, `WR=93.10%`, `Avg=8.0206%`, `minYear=3`, `yearWRmin=82.35%`, `micro=0%`, same-day=0. Child alone fails coverage, so do not promote alone.
- Combined V175+V185 child: `n=334`, `WR=86.23%`, `Avg=6.5628%`, `minYear=41`, year WR `{2023:82.81, 2024:87.20, 2025:86.54, 2026:87.80}`, `yearWRmin=82.81%`, `micro=0.90%`, same-day=0. Combined passes the declared production-upgrade gate.

## Robustness validation

Artifact:
- `/root/.hermes/smc_audit/v186_v185_robustness_sensitivity_20260626_001356/`
- Decision: `V186_ROBUST_ENOUGH_FOR_SHADOW_PROMOTION_DESIGN`.
- Threshold sensitivity tested 49 `(risk, body)` combinations; 9 passed the combined gate.
- Passing region includes: risk/body `(2.5,48)`, `(2.5,50)`, `(3.0,48)`, `(3.0,50)`, `(3.0133,48)`, `(3.0133,50)`, `(3.25,48)`, `(3.25,50)`, `(3.5,48)`.
- Leave-one-year-out on chosen rule kept WR/Avg robust, but 2024-only exclusion produced micro `1.44%`; treat as a caution, not a blocker because full combined micro is `0.90%`.

## Independent readiness audit

Artifact:
- `/root/.hermes/smc_audit/v203_v185_formal_readiness_current_dryrun_20260626_064312/`
- Decision: `V203_V185_FORMAL_CANDIDATE_VALIDATED__PROMOTION_BRIDGE_NEXT_SHADOW_ONLY`.
- Recomputed selector over source rows: eligible=87, child_rows=87, missing=0, extra=0.
- Overlap with V175=0; selector leak fields=[]; child same-day=0; combined same-day=0.
- Current latest V128 dry-run using formal rule: recent45 formal candidates=6; latest entry date `20260616`; latest rows=3 (`300327.SZ`, `688048.SH`, `688486.SH`). No production writes.

## Shadow materialization and endpoint mapping

V204 artifact:
- `/root/.hermes/smc_audit/v204_v185_shadow_materialization_no_write_20260626_064406/`
- Decision: `V204_SHADOW_MATERIALIZATION_READY__NO_PRODUCTION_WRITE`.
- Historical shadow rows=334; active shadow rows=6.
- Active rows come from current scanner dry-run, not historical trades.
- Active old event labels=0; active outcome pollution=0; production/frontend/watchlist writes all false.

V205 artifact:
- `/root/.hermes/smc_audit/v205_v185_shadow_endpoint_mapping_smoke_20260626_085805/`
- Decision: `V205_SHADOW_ENDPOINT_MAPPING_PASS__READY_FOR_CODE_IMPACT_ANALYSIS`.
- Mock API picks rows=6; historical rows=334; missing required frontend fields=0; old event labels=0; active outcome pollution=0; write pollution=0; shadow_false=0; historical same-day exit=0; latest_entry_date=`20260616`.

## Direction

This is the first post-V175 qualitative improvement candidate. Treat it as **shadow-ready**, not yet production-mutated.

Next concrete step before any production/router patch:
1. Run GitNexus impact analysis on `smc_unified.py` routing/API symbols (required by AGENTS.md before editing).
2. Patch only a reversible `V185_SHADOW` route first, not default production.
3. Verify `/api/summary`, `/api/picks?version=V185_SHADOW`, `/api/live-prices?version=V185_SHADOW`, reload behavior, field aliases, no outcome pollution, and current active source separation.
4. Only after endpoint smoke passes should V185 be considered for default production promotion.

Do **not** continue daily scalar iteration unless this V185 shadow route fails; the current qualitative path is integration hardening, not another candidate search.