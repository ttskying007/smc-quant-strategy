# V91 SMC Full-Flow Solution Audit

Session date: 2026-06-13

## Trigger

Use when Lei asks to continue from exposed SMC problems and requires a full solution loop: root-cause analysis, repair, testing, backtest, review, frontend/API verification, and confirmation of both 90%+ win rate and payoff/RR requirements under the intended SMC stack:

```text
large timeframe trend -> medium timeframe signal -> small timeframe/zone entry -> smart-money liquidity target/runner
```

## Durable lesson

Do not collapse all objectives into a single metric. Split the solution into two deployable layers:

| Layer | Purpose | Gate |
|---|---|---|
| Production layer | Large enough full-market sample with 90%+ WR | V90/V86 gate + pre-entry known BSL + weak RECOVERY rejection |
| Elite MTF/RR layer | Highest quality smart-money setup and payoff | weekly bull + daily bull + zone_limit + hybrid_tight + liquidity runner |

The production layer answers “can this work at full-market scale?”; the elite layer answers “does the SMC theory improve quality when the timeframe stack is aligned?”

## Key results captured

### Production-sized candidate

Source rows: `/root/.hermes/smc_opt_v90_daily_full_market_scanner/v90_3y_v86_gate_known_bsl_rows.json`

Filter:

```python
market_state != 'RECOVERY'
or v90_recovery_substate in {
    'RECOVERY_CONFIRMED_FAST_RECLAIM',
    'RECOVERY_STABLE_HIGHER_LOW',
}
```

Result:

| Metric | Value |
|---|---:|
| n | 523 |
| WR | 90.25% |
| avg pnl | +2.6923% |
| cum pnl | +1408.08% |
| avg realized R | 2.109R |
| SL rate | 9.75% |
| T+1 violations | 0 |
| future-target violations | 0 |

This is the production-sized WR/R validation. It uses the replay source rows for realized R and augments rows with the V88/V90 frontend execution contract only for field validation.

### Elite MTF/RR candidate

Source rows: `/root/.hermes/smc_opt_v87_mtf_entry_rr_matrix/v87_matrix_rows.json`

Filter:

```text
weekly_state = BULL_CONTINUATION
AND daily_state = BULL_CONTINUATION
AND entry_mode = zone_limit
AND sl_mode = hybrid_tight
AND tp_mode = liq_then_2r_runner
```

Result:

| Metric | Value |
|---|---:|
| n | 149 |
| WR | 90.60% |
| avg pnl | +3.6088% |
| avg RR | 2.553R |
| payoff ratio | 1.5508 |
| SL rate | 6.71% |
| avg MFE | 6.0526R |

This confirms the intended SMC stack improves quality, but sample size is too small to replace the 523-row production layer. Treat it as an elite/priority ranking layer.

## Important pitfall: realized R vs contract RR

When enriching historical audit rows with frontend contract fields, do not recompute production performance from the newly attached `sl/tp/rr` fields unless the exit replay was rerun under that exact contract. In V91:

- realized WR/R comes from V90 3Y replay rows;
- frontend field audit comes from the V88/V90 contract enrichment;
- `contract_avg_rr` is a display/execution-plan metric, not the realized replay metric.

Mixing these caused a false interim “avg_realized_R below 2” reading. The fix is to preserve replay `pnl_pct/risk_pct/exit_reason` for production performance and use enriched contract fields only for release-gate field audits.

## Frontend/live API field contract lesson

`/api/live-prices` rows must expose the same flat fields expected by page/table validators, not only camelCase display fields. Required non-empty flat fields include:

```text
pick_date, join_date, engine, zone, zone_type,
cost_line, volatility, volatility_pct,
sl, tp1, rr
```

Patch pattern in `smc_unified.py::_api_live_prices`:

```python
'slPrice': round(sl_price, 2),
'sl': round(sl_price, 2),
'tpPrice': round(tp_price, 2),
'tp1': round(tp_price, 2),
'rr': round(((tp_price - entry_price) / (entry_price - sl_price)), 4)
      if tp_price and entry_price and sl_price and entry_price > sl_price
      else (float(p.get('rr') or 0) if p.get('rr') else 0),
```

Verify both `/api/picks` and `/api/live-prices`; `/api/picks` passing does not prove live rows are complete.

## Required verification sequence for this class of task

1. Run impact analysis before editing symbols when GitNexus can resolve the symbol. If the index is stale, run analyze; if analyze fails due environment setup, record that verification was attempted and proceed with a minimal edit only.
2. Reproduce field gaps using API-level audits, not only browser visual checks.
3. Generate/refresh the full-flow audit report:

```bash
cd /root/.hermes/scripts/v25
python3 v91_smc_full_flow_solution_audit.py
```

4. Run syntax and unit-style tests:

```bash
python3 -m py_compile /root/.hermes/scripts/smc_unified.py /root/.hermes/scripts/v25/v91_smc_full_flow_solution_audit.py
python3 /root/.hermes/scripts/v25/test_v87_mtf_entry_rr_matrix.py
python3 /root/.hermes/scripts/v25/test_v90_daily_full_market_scanner.py
```

5. Restart 8890 and verify API fields:

```python
# /api/picks and /api/live-prices must both have 0 missing for:
['pick_date','join_date','engine','zone','zone_type','cost_line','volatility','volatility_pct','sl','tp1','rr']
```

6. Report results as compact tables: production layer, elite MTF/RR layer, frontend/API field audit, tests, remaining limitations.

## Remaining limitation

60min entry is still not production hard-gate material unless historical 60min coverage is complete. Current best deployable proxy is `zone_limit`; use 60min only for elite ranking/diagnostics until coverage is proven complete.
