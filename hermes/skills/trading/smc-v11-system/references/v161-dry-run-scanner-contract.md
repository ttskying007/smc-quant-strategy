# V161 dry-run scanner contract（2026-06-22）

## Trigger

Use this when a research/backtest rule such as V158/V160 looks promotable, but before discussing production promotion. The task is to prove the rule can be evaluated by the real daily scanner at scan time.

## Hard rule

Do **not** promote or wire production until the dry-run scanner contract is clean. The scanner contract must prove:

1. Input rows come from the real daily scanner stream, not historical backtest/chosen-row artifacts.
2. Required selector fields are available at scanner time.
3. No post-entry outcome fields are used by the selector: no `pnl`, `exit_*`, `won`, `MAE/MFE`, realized hold/result fields, or versioned post-outcome columns.
4. Current/recent candidate scope is audited separately from historical/all rows.
5. Production/frontend/watchlist files remain untouched.

## V161 pattern

Reference implementation:

- Script: `/root/.hermes/scripts/v25/v161_dry_run_scanner_contract.py`
- Output: `/root/.hermes/smc_audit/v161_dry_run_scanner_contract_20260622/`
- Scanner source: `/root/.hermes/smc_opt_v90_daily_full_market_scanner/v128_parallel_shadow_candidates.json`

Execution sequence:

```bash
cd /root/.hermes/scripts/v25
python3 v90_daily_full_market_scanner.py
python3 v161_dry_run_scanner_contract.py
python3 -m py_compile /root/.hermes/scripts/v25/v161_dry_run_scanner_contract.py
```

## Contract fields used for V158/V160

Core scanner-time fields:

- `symbol`, `poi_source`, `combo_family`, `event_type`
- `event_date`, `zone_date`, `entry_date`
- `zone_low`, `zone_high`, `touch_idx`, `reclaim_idx`, `entry_idx`, `entry_price`
- `risk_pct`, `v85_zone_width_pct`, `market_state`
- `reclaim_close_above_zone_pct`, `reclaim_close_pos`, `touch_to_reclaim_bars`, `entry_chase_above_zone_pct`
- Recomputed from kline before decision: `v132_reclaim_bull_body_pct`, `v132_reclaim_close_pos_pct`, `v132_reclaim_class`, `v132_true_takeover_1/2/3_strict`, hold/no-break/pullback fields.

Optional, not selector-blocking for V158/V160:

- `source_gap_atr`, `source_mid_body_atr` — present for FVG/OB+FVG but legitimately absent for `DEMAND_OB`; do not fail the V158/V160 core contract on these if the chosen rule does not use them.

## Scope interpretation

Audit `recent45` and `v160_buy_recent45` as the promotion-relevant scanner contract. Historical/all rows may include stale edge rows with insufficient post-reclaim confirmation bars; report them but do not let them obscure the current scanner contract.

V161 actual result:

| scope | rows | ready | decision_available | outcome_leak | missing_nonzero |
|---|---:|---|---:|---:|---:|
| all | 39013 | False | 39001 | 0 | 11 |
| recent45 | 2633 | True | 2633 | 0 | 0 |
| v160_buy_recent45 | 1726 | True | 1726 | 0 | 0 |

## Production gate interpretation

V161 being clean only means scanner-time field availability is proven. It does **not** overrule stability gates.

For the V158/V160 session:

- V161 dry-run scanner contract: clean for recent45 / V160 BUY recent45.
- V160 stability: still non-robust due to a bad month.
- Final decision: `NO_PRODUCTION_PROMOTION`; next work is stability hardening / weak-month attribution, not wiring production.

## Pitfalls

- Do not use `v158_chosen_rows.csv` or `v160_chosen_rows.csv` as scanner inputs; those are historical research outputs.
- Do not include outcome fields in dry-run selector logic even if present in nearby CSVs.
- Do not treat `all` historical missing edge rows as equivalent to current scanner failure; separate `all`, `recent45`, and `buy_recent45`.
- Do not promote just because field contract is clean; stability/monthly robustness remains an independent gate.
