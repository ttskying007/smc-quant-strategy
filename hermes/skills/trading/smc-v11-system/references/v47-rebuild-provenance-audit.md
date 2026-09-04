# V47 rebuild/provenance audit lesson

Use this when a full-market SMC rebuild appears silent or when OB/FVG provenance audits fail after a signal-core fix.

## 1. Silent rebuild does not mean hung

`v46_1_layered_3y.py --rebuild-base` can run for ~15–20 minutes with little or no Hermes background output because progress is sparse and output is buffered:

- base rebuild prints only every 500 stock files;
- autopsy prints only every 100 trades;
- background process output may not flush until process exit.

Before killing it, verify the child Python process, not just the parent shell:

```bash
ps -p <bash_pid> -o pid,ppid,stat,etime,%cpu,%mem,rss,cmd --no-headers
pgrep -P <bash_pid> -a
ps -p <python_child_pid> -o pid,ppid,stat,etime,%cpu,%mem,rss,cmd --no-headers
```

Interpretation:

- parent bash in `S` / `do_wait` is normal;
- Python child in `R` with ~100% CPU is active;
- output files may have old mtimes while the script is in the annotate/autopsy phase.

Do not treat empty `process log` output as a stall unless the child Python process is gone, sleeping without IO/CPU for a long time, or file/process state proves no progress.

## 2. Provenance fields must be promoted, not only nested

A recurring V46/V47 failure pattern:

```text
OB_TRADE_MISSING_WAVE_TURN_LABEL
```

can occur even when the OB signal is correct, because `source_signal` contains the fields but the top-level trade contract does not.

Observed shape:

```json
{
  "zone_type": "OB",
  "wave_turn_label": null,
  "source_signal": {
    "type": "OB",
    "wave_turn_label": "LL",
    "anchor_method": "wave_turn_opposite_candle_near_HH_HL_LH_LL"
  }
}
```

Root cause:

- `v45_1_recall_repair.py` may preserve `source_signal` on setup/trade;
- `v46_1_layered_3y.py` rebuilds base via `v41.backtest_v34_setups()`;
- that merge path can keep nested `source_signal` while dropping promoted `source_signal_type`, `wave_turn_*`, `anchor_method`, and `gap_*` fields.

Required fix pattern in the rebuild loop after `backtest_v34_setups()`:

1. match each trade back to its setup using `entry_index + zone_idx + zone_type`;
2. copy `source_signal`, `source_signal_type`, `wave_turn_*`, `anchor_method`, `gap_*` from setup to trade;
3. if setup matching misses, promote the same fields from nested `trade['source_signal']`;
4. rerun `audit_v47_smc_system.py` and require `OB_TRADE_MISSING_WAVE_TURN_LABEL` to disappear.

## 3. Separate signal correctness from output-contract correctness

When an audit says OB wave-turn fields are missing, inspect both:

```python
trade.get('wave_turn_label')
(trade.get('source_signal') or {}).get('wave_turn_label')
```

If nested is populated but top-level is empty, the issue is not Pine/SMC signal definition. It is a downstream backtest/report/frontend synchronization contract bug.

## 4. Review checklist after any SMC rebuild repair

After rebuild completes:

```bash
python3 v25/audit_v47_smc_system.py
```

Minimum checks before claiming sync is fixed:

- report count equals trade file count;
- OB trades have top-level `wave_turn_label` or an accepted contract fallback;
- FVG trades have `gap_low/gap_high` or raw zone bounds;
- `entry_date`, `exit_date`, `entry_index`, `exit_index`, `entry_price`, `exit_price` are valid per K-line;
- frontend contract files are regenerated after backend output changes;
- if `TRADE_FAILURES:N` remains, split by failure type before tuning signal or exits.

## 5. RR / sold-early diagnosis from V47

A high WR does not prove the exit model is healthy. In V47 audit, the important red flags were:

```text
sold_early_rate ≈ 85.78%
avg_mfe_capture ≈ 0.087
avg_entry_zone_pos ≈ 0.99
```

Interpretation:

- entries are near the top of the zone;
- MFE exists but is not captured;
- low RR is driven by entry/SL/exit contract, not only by signal detection.

Replay-only experiment direction that improved diagnostics:

```text
zone_mid entry + structural SL
```

This reduced fake SL and sold-early symptoms in experiment, but must be productionized only after full rebuild + audit, not by directly replacing the live engine from a rough replay script.
