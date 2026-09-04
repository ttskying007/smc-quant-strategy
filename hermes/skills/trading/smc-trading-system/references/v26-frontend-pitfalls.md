# V26 Frontend Data Sync — Pitfalls & Fixes

## Pitfall 1: Monitor SL/TP Shows 0% / ?
**Root cause**: Monitor page reads `sl_initial_pct` and `tp_tiers` (V24 fields), but V26 picks use `v25_sl_pct` and `v25_tp_tiers` (dict format).
**Fix**: Prefer V25 fields with fallback:
```python
if 'v25_sl_pct' in p: sl = p.get('v25_sl_pct', 0)
else: sl = p.get('sl_initial_pct', 0)
```
**tp_tiers format handling**: V25 uses `[{'price':7.78, 'pct':3.5, 'type':'TP1', 'alloc':0.5}]` (list of dicts), not strings or simple lists. Must check `isinstance(first, dict)`.

## Pitfall 2: Monitor Shows All Historical Picks (4855 picks)
**Root cause**: Picks saved by `v26_engine` matched by symbol only — one stock with 9 historical entries → all 9 saved.
**Fix**: Deduplicate per symbol, keep only most recent `entry_date`:
```python
sym_best = {}
for p in filtered:
    if sym in trade_symbols:
        if sym not in sym_best or p['entry_date'] > sym_best[sym]['entry_date']:
            sym_best[sym] = p
```

## Pitfall 3: Monitor Shows 120-Day History (4855 → 994 → 165)
**User complaint**: "选股不能是120天以内，太久了，无法跟踪，选股每天选的，应该是每天的股票"
**Fix**: Filter monitor to today only (or last trading day):
```python
now = datetime.now()
days_back = 1
if now.weekday() >= 5: days_back = now.weekday() - 4
cutoff = (now - timedelta(days=days_back)).strftime('%Y%m%d')
recent_picks = [p for p in picks if str(p.get('entry_date','')) >= cutoff]
```

## Pitfall 4: Engine Overwrites Enriched Picks
**Root cause**: Engine saves picks from pre-filter stage (no SL/TP enrichment), overwriting daily_scan's enriched picks.
**Fix**: After engine runs, re-run enrichment on all picks:
```python
for p in picks:
    if p.get('v25_sl_pct', 0) < 0.1 or not p.get('regime'):
        # Load klines → compute_sltp(p, klines) → p.update(enriched_data)
```

## Pitfall 5: RANGE State Produces Garbage SL (2989%)
**Root cause**: RANGE state has `sl_atr_mult: 999` (to force skip in engine), but enrichment function used these params directly → `sl = dz_low - atr * 999` → absurd values.
**Fix**: Fallback RANGE to TREND_UP params in enrichment:
```python
if state in ('RANGE', 'UNDEFINED'):
    state = 'TREND_UP'
params = STATE_PARAMS.get(state, STATE_PARAMS['TREND_UP'])
```

## Pitfall 6: Live Page Buy Date Disappeared
**Root cause**: `entryDate` field was in API response but not rendered in HTML table.
**Fix**: Add `<th>买入日</th>` to header and `<td>entryDateStr</td>` to row. Must escape `{` → `{{` in Python f-string JavaScript blocks.
