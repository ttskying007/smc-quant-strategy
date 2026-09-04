# Monitor File Isolation (2026-05-15)

## Problem

`monitor_check.py`'s `init_positions()` writes ALL picks (13,000+) to `active_positions.json` every time it runs. This overwrites any manual quality-filtered selection. Even `chmod 444` doesn't prevent root from writing.

## Root Cause

Three separate write points in `monitor_check.py`:
```python
json.dump(positions, open(POSITIONS_FILE,'w'), ...)  # lines 75, 183, 205
```

## Fix

1. **Change smc_unified.py MONITOR_POS** to read from a separate file:
```python
MONITOR_POS = OUT_DIR / 'monitor_clean.json'  # Locked clean file
```

2. **Generate `monitor_clean.json`** with quality-filtered deduped positions:
```python
# Dedup by symbol_dot, filter: gap<=3, dist -2to8%, score>=30
seen = set()
for p in picks:
    if sym_dot in seen: continue
    seen.add(sym_dot)
    # ... quality filters ...
```

3. The file separation ensures `monitor_check.py` can keep overwriting `active_positions.json` without affecting the frontend display.

## Verification

```bash
curl -s http://127.0.0.1:8890/monitor | grep -oP "当前持仓 \(\d+\)"
# Should show: 当前持仓 (151)  — NOT 12360 or 12714
```

## Key Lesson

When two processes share a data file and one is uncontrolled (cron, monitor_check), use **file separation** not file permissions. Read-only flags don't work for root.
