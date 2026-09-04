# V201-V202 post-V175 target-room and 60min micro-resolution closure

Date: 2026-06-25

## Trigger
Use when continuing post-V175 SMC research after V198-V200, especially if considering V85 target-room seed expansion or 60min profit-lock micro-resolution.

## Fixed usable gates

Production upgrade remains unusable unless all hold:
- non-leaking source/execution rule;
- T+1 violations = 0;
- for V175 replacement/execution replay: `n >= 247`, `min_year_n >= 38`, `WR >= 84%`, `AvgPnL >= 6.2%`, `all_year_WR_min >= 82%`, `micro_profit_pct <= 1%`;
- for new combined engine: `combined_n >= 260`, `min_year_n >= 40`, `WR >= 84%`, `AvgPnL >= 6.2%`, `all_year_WR_min >= 82%`, `micro_profit_pct <= 1%`;
- shadow-only until pass.

Research child engine usable only if non-overlap vs V175 and `n>=120`, `min_year_n>=20`, `WR>=86%`, `AvgPnL>=6.5%`, `all_year_WR_min>=83%`, T+1=0.

## V201 — V85 target-room rule mining
Artifact: `/root/.hermes/smc_audit/v201_v85_target_room_rule_mining_20260625_212659/`

Purpose: test the only remaining daily-OHLCV seed from V186 — V85 HOLD_ABOVE_POI candidates with large liquidity target room — using only source-side/non-leaking features.

Result:
- Decision: `V201_TARGET_ROOM_NO_GATE_PASS`.
- Base non-overlap V85 target-room pool: `n=19867`, `WR=75.62%`, `Avg=1.0958%`, `all_year_WR_min=70.97%`, `micro=18.12%`, T+1=0.
- Production pass count: `0`.
- Research child pass count: `0`.
- The earlier promising tiny high-target subset did not expand into a gate-passing child engine. Target-room alone mostly increases reward room but does not solve signal quality / SL damage.

## V202 — cached Baostock 60m micro-resolution grid
Artifact: `/root/.hermes/smc_audit/v202_cached_baostock_60m_micro_resolution_20260625_213415/`

Purpose: continue from V200 near-frontier (`rr2.5_h15_lock03_1r`) and try executable non-leaking rules to reduce micro-profit pollution without weakening production gates.

Result:
- Decision: `V202_60M_MICRO_RESOLUTION_NO_PRODUCTION_PASS`.
- Baostock per-trade 60m cache succeeded: `fetch_ok=247/247`, missing=0, T+1=0.
- Production pass count: `0`.
- Best by Avg: `rr3.0_h20_lock03_if_abs2.0_tr1.5` => `n=247`, `WR=78.54%`, `Avg=8.1102%`, `all_year_WR_min=72.34%`, `micro=2.43%`, T+1=0. High Avg but year/WR fail.
- Micro-resolution variants could not reduce `micro<=1%` while also preserving `WR>=84` and yearly stability.

## Closed directions after V202
1. More scalar filtering of V128/V167/V172/V175 artifacts.
2. V85 target-room expansion from current daily candidate supply.
3. Generic V175 daily exit overlays.
4. V175 60min TP/hold/profit-lock micro-resolution.
5. Daily OHLCV-only fresh generators already tested through V183-V198 and remain closed.

## Current conclusion
V175 remains the production baseline. Under currently available daily OHLCV + V175-specific historical 60min replay, there is no new production-quality engine and no validated child engine.

Next qualitative change requires a truly new pre-entry information layer or a new supply generator with different event semantics, not another threshold search over existing artifacts. Candidate sources:
- full historical 60min data for broad candidate generation (not just V175 exit replay);
- true sector/board flow and peer confirmation data;
- auction/order-flow/limit-up queue data;
- fundamentals/news/announcement filters as ex-ante context.

Do not mutate frontend/watchlist/API until such a new shadow engine passes the fixed gates above.
