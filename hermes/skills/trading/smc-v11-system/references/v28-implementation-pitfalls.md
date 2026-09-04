# V28 Implementation Pitfalls & Techniques

## 1. f-string backslash prohibition (Python 3.12+)
**Symptom:** `SyntaxError: f-string expression part cannot include a backslash`
**Root cause:** Inside f-string `{}` expressions, backslash escapes like `{\"green\" if ... else \"red\"}` are illegal in Python 3.12+.
**Fix:** Pre-compute conditional values into variables before the f-string, or use helper functions that return the strings. Never write conditional expressions with escaped quotes inside f-string braces.

```python
# WRONG (Python 3.12+):
html = f'<td class="{"green" if wr > 55 else "red"}">{wr}%</td>'

# RIGHT:
wr_cls = 'green' if wr > 55 else 'red'
html = f'<td class="{wr_cls}">{wr}%</td>'
```

## 2. Import path: load_klines lives in scan wrapper, not core
`smc_core_v27.py` exports signal detection functions (compute_metrics, detect_all_signals_v27, etc.) but NOT data-loading utilities.
`v27_full_scan.py` defines `load_klines()`, `find_kline_files()`, `symbol_from_filename()`.
When building a new scan wrapper (e.g. v28_full_scan.py), import `v27_full_scan as base` and call `base.load_klines()`.

## 3. smc_unified.py regex function replacement
When replacing a large function in smc_unified.py (2530+ lines), the patch tool may struggle with exact matching.
**Reliable pattern:**
1. Write the fixed function to a temp file
2. Use `re.sub(r'(def old_func\(\):.*?)(\n\ndef next_func\(\):)', fixed.strip() + r'\n\n\2', content, flags=re.DOTALL)`
3. The DOTALL flag makes `.` match newlines so `.*?` captures the entire old function body
4. Always verify syntax with `compile()` after replacement

## 4. Duplicate function definitions from regex replacement
If the regex replacement leaves an empty old function signature (e.g. `def build_docs():\n\n\n\ndef build_docs():`), use patch with unique context from surrounding lines to remove the stale copy. Empty function bodies between two `def` statements are a common artifact.

## 5. Stdout buffering in long-running scans
Python stdout is line-buffered to terminals but fully-buffered when piped. Background processes started via terminal(background=True) may show no output for minutes.
**Fix:** Use `flush=True` in print statements AND check output files periodically via `ls -lt` to confirm progress. The process CPU usage (`ps -p PID -o pcpu`) is the best liveness indicator.

## 6. replace_all=true for bulk nav updates
smc_unified.py has 13 identical nav bar `<span class="brand">🚀 SMC V27</span>` strings across different page builders. Use `replace_all=true` to update all at once instead of finding each one.

## 7. Frontend restart pattern
```bash
pkill -f 'python3 smc_unified.py'
# Then start fresh:
terminal(background=True, command='cd /root/.hermes/scripts && python3 smc_unified.py')
# Verify:
sleep 2 && ss -tlnp | grep 8890 && curl -s localhost:8890/api/summary
```
Never use `&` in foreground terminal commands — Hermes blocks it. Use `terminal(background=true)` for server processes.
