# V85 BEAR_RISK reversal candidate suppression

## Trigger
Use this when `/monitor` or `/live` shows no current-month SMC candidates even though raw reversal events exist in the latest month.

## Root cause pattern
`v81_contextual_smc_generator.generate_candidates()` can produce valid `DOWN_REVERSAL_SSL_SWEEP_CHOCH_PULLBACK_TO_POI_RECLAIM` rows in `BEAR_RISK` market state, but `v85_mixed_accumulation_generator.generate_v85_candidates()` can silently drop them if V85 only promotes:

- `UP_CONTINUATION_BOS_PULLBACK_TO_POI_RECLAIM`, or
- `MIXED_ACCUMULATION_HOLD_ABOVE_POI`

Observed failure mode: a month where the environment table marks every recent day as `BEAR_RISK`. V81 finds many SSL→CHOCH reversal candidates, but V85 passes almost none to V90/V91, causing the frontend to look as if the entire month has no candidates.

## Diagnostic drill-down
Run a layered count, not just aggregate scanner output:

1. Latest K-line date distribution.
2. Environment-state distribution for the current month.
3. V81 raw events by month/event type.
4. V81 valid POI + entry candidates.
5. V85 promoted candidates by `v85_path`.
6. V90/V91 contract rows and reject reasons.
7. Frontend `/api/picks` and `/api/live-prices` field contract.

Useful probe pattern:

```python
# Pseudocode skeleton
for symbol, ks in all_kline_files:
    for idx in recent_month_bars:
        context = classify_context(ks, idx, env_by_date[date])
        event = detect_event(ks, idx, context)
        poi = locate_poi(ks, event, env)
        entry = locate_entry(ks, poi, idx)
    v85_rows = generate_v85_candidates(symbol, ks, env_by_date)
```

If raw V81 current-month reversal rows exist but V85 current-month rows are missing, inspect promotion conditions.

## Fix pattern
Promote BEAR_RISK reversal rows in `generate_v85_candidates()` when all are true:

```python
nr.get('story') == 'DOWN_REVERSAL_SSL_SWEEP_CHOCH_PULLBACK_TO_POI_RECLAIM'
nr.get('market_state') == 'BEAR_RISK'
nr.get('v83_takeover_type') == 'HOLD_ABOVE_POI'
```

Set:

```python
nr['v85_path'] = 'BEAR_RISK_SSL_CHOCH_HOLD_ABOVE_POI'
by_key[(nr.get('event_date'), nr.get('entry_date'))] = nr
```

## Frontend filter lesson
Do not require `pick_date == latest_market_date`. SMC candidates can remain active several trading days after signal/pick. For current candidates, filter scanner rows by latest market **month** via `pick_date` or `join_date`, while still excluding historical V88 backtest rows.

## Regression checks

```bash
python3 /root/.hermes/scripts/v25/test_v85_bear_risk_reversal_candidates.py
python3 /root/.hermes/scripts/v25/v90_daily_full_market_scanner.py
python3 /root/.hermes/scripts/v25/v91_shadow_zone_entry_scanner.py
python3 /root/.hermes/scripts/v25/test_v88_current_picks_contract.py
python3 /root/.hermes/scripts/v25/test_frontend_field_contract_mpkfagiawk77km.py
```

Expected shape after a repaired BEAR_RISK month:

| Surface | Expected |
|---|---:|
| V90 recent active | non-zero |
| V91 recent active | non-zero |
| `/api/picks` current-month rows | non-zero |
| field blanks | 0 |
| T+1 violations | 0 |
