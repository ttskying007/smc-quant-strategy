# Python Patching Pitfalls

## Indentation Bug from patch() on Python Code

When using the `patch` tool to replace blocks of Python code, the indentation in the
`old_string` and `new_string` must match exactly. A common failure mode:

**Symptom**: Code after a `patch` replacement has wrong indentation, creating phantom blocks
that Python parses as valid but unreachable code.

**Root cause**: The `old_string` didn't capture the full old block correctly, or the
`new_string` had different indentation than the surrounding code.

**Example from this session**:
```python
# OLD (correct):
            # Check if bar touches the zone
            if not (lo <= zone_hi and hi >= zone_lo):
                continue
            
            entry_price = cl
            # Build signal sequence from zone to entry
            zone_sigs = [...]  # 12 spaces indent

# After bad patch — phantom indentation:
            entry_price = cl
            # Build signal sequence from zone to entry
                zone_sigs = [...]  # 16 spaces — unreachable phantom block!
```

**Detection**: Code compiles (no SyntaxError) but function returns 0 results.
`importlib` or `py_compile` will say "OK" but the function logic is broken.

**Fix strategy**:
1. After any `patch` on Python code: test the function directly
2. Use `execute_code` to import and call the function, verify output
3. If output is empty/unexpected, check indentation around the patched area
4. Clean up: strip line-number prefixes with regex `re.sub(r'^\s*\d+\|', '', content, flags=re.MULTILINE)`
5. Rewrite the entire function block if indentation is corrupted

## read_file() Silent Failure Pattern

**Symptom**: `read_file(path)` returns "File not found" but `ls` confirms file exists.
Often accompanied by `similar_files: ['./Divination', './HuangjiJingshi', ...]`

**Workaround**: Use `terminal` with `grep -n 'pattern' path` and `sed -n 'start,endp' path`
to read specific sections. These always work.

**Root cause**: Unknown — possible path resolution issue with certain characters
or file sizes. Does NOT affect `write_file`, `search_files`, or `terminal`.

**Prevention**: When read_file fails twice on the same path, switch to `terminal` immediately.
Don't retry read_file more than twice.

## Indentation Corruption: patch() on if-blocks (2026-05-18)

**Symptom**: `scan_single_stock()` returns 0 picks but inline trace finds 13 entries.
`py_compile` says syntax OK — the indented code became unreachable after a `continue`.

**Root cause**: `patch()` removing an `if not (...): continue` block left subsequent code
at 16-space indent instead of 12-space. Python compiled it as dead code after `continue`.

**Detection**: Run the function directly:
```python
python3 -c "from v25.full_scan import scan_single_stock, load_daily_kline; print(len(scan_single_stock('000001.SZ', load_daily_kline('000001.SZ'))))"
# Should return >0. If 0, indentation corruption likely.
```

**Fix**: `execute_code` to read+write the entire function using `write_file`, not `patch()`.

**Prevention**: After any `patch()` on indentation-sensitive Python, run the direct function test above.

## Orphaned Template After Patch

When patching f-string templates in Python, removing the opening `return f"""` line
leaves the template content as orphaned code (not inside a string).

**Symptom**: `SyntaxError` on template content (HTML with emojis, etc.)

**Fix**: Always verify the `return f"""..."""` wrapper is intact. When replacing blocks
inside f-strings, use only the inner HTML content as old/new strings, keeping the wrapper.

## Tool Restrictions During Cron

When running in cron context, certain operations are blocked:
- `python3 -c "..."` — use `execute_code` instead
- `find -delete` — use `terminal rm <specific_path>`
- `pkill -f` — use `kill <PID>` after extracting PID from `ss`
- `curl | python3` — blocked as security risk
