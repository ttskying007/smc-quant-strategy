# V186-V188 Baostock 60m replay and child-engine closure

Date: 2026-06-26

## Trigger
Use when continuing post-V175 research after daily OHLCV/fresh-generator attempts fail and considering historical 60min execution as a qualitative new information layer.

## Fixed gates

V175 execution replacement usable only if all pass:
- executable non-leaking rule;
- T+1 violations = 0;
- `n >= 247`, `min_year_n >= 38`;
- `WR >= 84%`, `AvgPnL >= 6.2%`;
- `all_year_WR_min >= 82%`;
- `micro_profit_pct <= 1%`;
- shadow-only until pass.

V167-leftover child engine usable only if all pass:
- 100% non-overlap vs V175;
- `n >= 120`, `min_year_n >= 20`;
- `WR >= 86%`, `AvgPnL >= 6.5%`;
- `all_year_WR_min >= 83%`;
- `micro_profit_pct <= 1%`;
- T+1 violations = 0.

## Environment

Baostock was not installed in system Python due PEP668 externally-managed environment. Created temporary venv:
- `/tmp/smc_baostock_venv`
- installed `baostock pandas`
- verified `bs.login()` and 60m query success.

## V186 — V175 Baostock 60m replay

Script: `/tmp/v186_baostock_60m_v175.py`
Artifact: `/root/.hermes/smc_audit/v186_baostock_60m_v175_replay_20260626_093237/`

Scope:
- V175 trades only (`247/247` fetched, missing=0).
- Exit eligible only after entry date (strict T+1).
- Tested base RR and simple lock/close-fail variants.

Result: `NO_PRODUCTION_PASS`.

Best/near-frontier variants:
- `rr2p5`: `n=247`, `WR=85.02%`, `Avg=6.7520%`, `min_year_n=38`, `all_year_WR_min=82.98%`, `micro=2.43%`, T+1=0. Fails only micro gate.
- `rr2p5_lock03_1r_abs2`: `WR=86.23%`, `Avg=6.6615%`, `yearMin=82.98%`, `micro=1.62%`, T+1=0. Fails micro gate.
- `rr2p5_closefail`: `WR=88.66%`, `Avg=6.4482%`, `yearMin=86.25%`, `micro=5.26%`, T+1=0. Fails micro gate.
- `base_rr1p5`: `WR=85.43%`, `Avg=6.1129%`, `micro=1.62%`. Fails Avg and micro.

Interpretation:
- Historical 60m is a real new execution layer and improves V175 economics, but every variant still fails `micro<=1%` or Avg.
- Do not promote by weakening the micro-profit gate.

## V187 — 60m horizon / micro-extension grid

Script: `/tmp/v187_60m_horizon.py`
Artifact: `/root/.hermes/smc_audit/v187_baostock_60m_horizon_micro_resolution_20260626_093457/`

Scope:
- V175 `247/247` fetched, missing=0.
- Fetched to `entry_date + 110 calendar days` instead of original V175 exit date.
- Tested RR 2.0/2.5/3.0, 40/60/80 60m-bar horizons, lock variants, and executable micro-extension rule.

Result: `NO_PRODUCTION_PASS`.

Key findings:
- Micro can be reduced below 1% by extending/using higher RR, but WR/year stability collapses.
- High Avg examples fail WR/year gate:
  - `rr3.0_b80_ext20`: `WR=71.26%`, `Avg=8.0212%`, `yearMin=61.70%`, `micro=0.40%`.
  - `rr2.5_b40_ext20`: `WR=76.52%`, `Avg=6.9572%`, `yearMin=68.42%`, `micro=0.81%`.
- Balanced high-WR variants from V186 still fail micro.

Interpretation:
- V175 60m execution has a hard trade-off: reduce micro → lose WR/year stability; preserve WR/year → micro remains too high.
- Execution-layer-only upgrade remains closed under fixed gates.

## V188 — V167 leftover child with Baostock 60m

Script: `/tmp/v188_60m_v167_leftover.py`
Artifact: `/root/.hermes/smc_audit/v188_baostock_60m_v167_leftover_child_20260626_093641/`

Scope:
- Source: `/root/.hermes/smc_opt_v167_exact_scanner_gate/v167_trades.json`.
- Excluded all V175 overlap by `symbol + entry_date`.
- Pool `546`, fetched `546/546`, missing=0.
- Tested RR 1.5/2.0/2.5/3.0, 40/60/80 bars, lock variants.

Result: `NO_CHILD_PASS`.

Best variants:
- `rr3.0_b80_lock03_abs2`: `n=546`, `WR=68.50%`, `Avg=5.3961%`, `min_year=42`, `yearMin=59.46%`, `micro=0.73%`, T+1=0.
- `rr2.5_b80`: `WR=71.25%`, `Avg=5.1897%`, `yearMin=64.86%`, `micro=0.73%`, T+1=0.
- `rr2.5_b40_lock03_abs2`: `WR=76.56%`, `Avg=4.9205%`, `yearMin=73.81%`, `micro=3.11%`, T+1=0.

Interpretation:
- 60m execution improves V167 leftover average but does not solve signal-quality/year-stability enough for a child engine.
- V167 leftovers remain closed as production/research child supply.

## Consolidated decision after V188

Closed under current gates:
1. Daily OHLCV fresh generators (V183-V185).
2. V175 60m exit replay as production upgrade (V186-V187).
3. V167 leftover child engine even with historical 60m execution (V188).

V175 remains production baseline. The only near-frontier is V186 `rr2p5`/`rr2p5_lock03_abs2`, but it fails micro-profit gate. It is research-only, not production.

## Next direction

Do not continue threshold/exit-layer loops on V175/V167.

The next qualitative change must be candidate-creation-time intraday semantics, not exit replay:
- build or cache historical 60m bars for broader candidate generation before entry;
- generate candidates from 60m structure (intraday sweep/reclaim/CHOCH inside the daily POI), then evaluate daily/60m exits;
- or introduce genuinely new pre-entry data: historical sector flow, auction/order-flow, limit-up queue, announcements/fundamentals.

Until candidate-creation-time intraday or new exogenous pre-entry data exists, no new production-grade engine has been found.