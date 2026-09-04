# Daily cron timeout verification/report pattern (2026-06-19)

## Trigger

Hermes cron reported:

```text
Script timed out after 120s: /root/.hermes/scripts/v25/smc_daily_closed_loop.py
```

This matched the known long-running daily-ops pattern: the wrapper timed out, but a child `smc_daily_ops.py` process continued and later wrote current artifacts.

## Procedure

1. **Do not immediately rerun.** First check whether a child process is still alive:

   ```bash
   ps -p <parent_or_child_pids> -o pid,ppid,etime,pcpu,pmem,stat,cmd || true
   pstree -ap <parent_pid> || true
   ps -eo pid,ppid,etime,pcpu,pmem,stat,cmd \
     | grep -E 'smc_daily_closed_loop|smc_daily_ops|daily_scan|v[0-9]+_.*(engine|audit|gate|scan)' \
     | grep -v grep
   ```

2. **If the child is alive, wait/inspect instead of starting a duplicate run.** After it exits, inspect fresh artifacts:

   ```bash
   ls -lt /root/.hermes/smc_monitor/ops_latest.json \
          /root/.hermes/smc_monitor/ops.log \
          /root/.hermes/smc_monitor/kline_refresh_latest.json
   ```

   Parse `/root/.hermes/smc_monitor/ops_latest.json` for:
   - `generated_at`, `date`, `data_date`
   - `kline_refresh.summary.requested/ok/failed/latest_counts`
   - selector/scanner `returncode`, scanned symbols, latest market date
   - field audits and T+1 violations
   - `daily_ingest.ok`, `added`, `today_pick_count`, `reason`

3. **Verify gates, not just ops completion.** Check at least:

   ```text
   /root/.hermes/smc_audit/v66_release_gate.json
   /root/.hermes/smc_audit/v66_daily_completeness_gate.json
   ```

   Report `pass`, `failed_checks`, requested/ok/failed ratios, and key quality metrics. Do not infer gate success from file existence.

4. **Smoke-test the frontend/API on :8890:**

   ```text
   GET  /api/summary
   GET  /api/autopsy/closed-loop
   GET  /api/picks
   GET  /api/kline_full?symbol=300349.SZ&tf=daily&ver=V66
   GET  /api/resonance
   POST /api/reselect {"version":"V66"}
   ```

   Also scan `/api/picks` and `/api/resonance` response text for literal `None`/`null` signal pollution. `/api/reselect` may route legacy `V66` requests through the active production engine mapping (observed as `V88_PRODUCTION_CONTRACT`); treat HTTP 200 + `ok: true` as rerun support present, but mention the mapped engine in the report.

## Reporting template

Keep the final cron report concise and factual:

```markdown
## SMC 日闭环 Cron 报告 — <timestamp>

结论：<timeout was wrapper-only / real blocker / gate failed>。

### 运行状态
- child process: <still running / ended>
- latest artifact: <path>, generated_at <time>, data_date <date>

### 数据刷新 / 扫描
- requested/ok/failed: ...
- latest market date coverage: ...
- scanner returncode: ...
- active entry window candidates: ...
- T+1 violations: ...

### Release gate / 完整性 gate
- release gate pass: ... failed_checks: ...
- completeness gate pass: ... failed_checks: ...

### 前端/API smoke
- summary/picks/resonance/kline/reselect: ...
- None/null pollution: ...

### 处理决定
- rerun: skipped/started + reason
- next action: none / fix required / manual follow-up
```

## Pitfalls

- A 120s Hermes wrapper timeout is not enough evidence to create a new Vxx or rerun; daily ops can exceed 12 minutes.
- Do not launch a second closed-loop while `smc_daily_ops.py` is still alive.
- Do not report success from old artifacts; verify mtimes/generation timestamps.
- Do not call `[SILENT]` when a timeout occurred; report the verified outcome or the blocker.
