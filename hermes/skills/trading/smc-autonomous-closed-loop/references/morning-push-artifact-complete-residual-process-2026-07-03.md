# Morning push: artifact-complete residual process recovery (2026-07-03)

## Situation
A Hermes-tracked `smc_morning_push.py` run continued to appear `running` even after the morning report and ops artifacts were already written.

Observed command:

```bash
cd /root/.hermes/scripts && python3 v25/smc_morning_push.py
```

Observed process tree while apparently hung:

```text
/bin/bash -lic set +m; cd /root/.hermes/scripts && python3 v25/smc_morning_push.py
  \_ python3 v25/smc_morning_push.py
      \_ /usr/bin/python3 /root/.hermes/scripts/v25/smc_daily_ops.py
```

Key artifacts had already been updated:

```text
/root/.hermes/smc_monitor/ops_logs/YYYYMMDD.json
/root/.hermes/smc_monitor/ops_latest.json
/root/.hermes/smc_push_reports/YYYYMMDD_HHMMSS_morning_push.md
```

The generated report contained the complete morning holdings/picks content, while the parent process remained alive long enough to confuse the cron recovery path.

## Recovery pattern

1. Do **not** immediately rerun `smc_morning_push.py` while a parent/child is alive.
2. Poll/wait briefly, then inspect artifact mtimes and sizes:

```bash
stat -c '%y %s %n' \
  /root/.hermes/smc_monitor/ops_logs/YYYYMMDD.json \
  /root/.hermes/smc_monitor/ops_latest.json \
  /root/.hermes/smc_push_reports/*_morning_push.md
```

3. Read `ops_logs/YYYYMMDD.json` and verify all required stages returned `0`:
   - `kline_refresh.returncode`
   - `selector.returncode`
   - `v185_rematerialize.returncode`
   - `v231_shadow_audit.returncode`
   - `v236_shadow_audit.returncode`
   - `v246_shadow_audit.returncode`
   - `daily_ingest.ok`
4. Read the morning report and verify it includes:
   - OPEN holdings table
   - NEXT_DAY_PENDING section
   - latest trading-day picks
   - historical candidates
5. Run API smoke before declaring success:
   - `/api/summary`
   - `/api/picks`
   - `/api/live-prices`
   - `/api/monitor/state`
   - `POST /api/reselect {"version":"V185"}`
6. Compare `/api/picks` vs `/api/live-prices` live-guard status for matched symbols; require zero mismatches before reporting parity.
7. Only after artifacts and API smoke are verified, clear the residual Hermes-tracked process if it is still alive. Then verify no `smc_morning_push.py` / `smc_daily_ops.py` processes remain.

## Reporting rule
Report this as an artifact-complete recovery, not as a failed push, when:

- the report file exists and is fresh,
- ops log is fresh,
- required subprocess return codes are successful,
- API smoke and reselect pass,
- live-guard parity has zero mismatches.

Include the caveat that the process was cleaned up after completion verification.