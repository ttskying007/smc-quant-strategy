# Dashboard numeric contract and restart verification

## Trigger

Use when an SMC API/dashboard reads heterogeneous historical trade artifacts and returns empty responses, repeated HTTP 500s, or a Python `TypeError` while calculating summary metrics.

## Failure pattern

Historical JSON commonly serializes numeric fields such as `pnl_pct` as strings (`"4.631"`) while newer artifacts use numbers. Direct expressions such as:

```python
trade.get("pnl_pct", 0) > 0
```

can crash the summary endpoint.

## Minimal safe fix

1. Add or reuse one narrow conversion helper:

```python
def _float_or_zero(value):
    try:
        return float(value or 0)
    except (TypeError, ValueError):
        return 0.0
```

2. Apply it to every arithmetic/ordering calculation at the API boundary, e.g. winner count and average P&L. Preserve source artifact values; do not bulk-rewrite historical trade files merely to satisfy a display calculation.
3. Avoid importing a module name inside an endpoint function when that name is already module-global. A local `from pathlib import Path` makes `Path` local throughout the function and can cause `UnboundLocalError` before the import line.
4. Compile, restart the actual serving process, and call the exact failing endpoint. Source edits alone do not prove the long-running process loaded the fix.

## Acceptance checks

- `python3 -m py_compile` passes for the server module.
- Direct `/api/summary` response is valid JSON and HTTP 200.
- Response clearly distinguishes `LIVE_READY_NO_CURRENT_SIGNAL` from a server failure or historical fallback.
- No production candidate/watchlist/position artifact is mutated during dashboard-only repair.

## Relationship to data provenance

This normalizes only display-time scalar types. It must not be used to merge providers, alter OHLCV bars, or weaken source-isolation/full-market promotion gates.
