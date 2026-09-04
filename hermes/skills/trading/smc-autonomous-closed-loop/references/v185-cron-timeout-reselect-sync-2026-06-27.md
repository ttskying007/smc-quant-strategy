# V185 cron timeout + reselect sync recovery (2026-06-27)

## Trigger
Daily cron wrapper reported:

```text
Script timed out after 120s: /root/.hermes/scripts/v25/smc_daily_closed_loop.py
```

User required verification that the run reports V185, rematerializes V185 production artifacts, and keeps frontend/API/watchlist/report 口径一致. Mutations were allowed only for an obvious field-sync bug.

## Recovery pattern

1. Treat the 120s timeout as incomplete observation, not strategy failure.
2. Check for still-running children before rerun:
   - `smc_daily_closed_loop.py`
   - `smc_daily_ops.py`
   - `v185_daily_rematerialize.py`
3. If no child is alive and no dated closed-loop report exists, rerun the real wrapper as a Hermes-tracked background process; do not use `--help` because this wrapper may execute the job anyway.
4. Wait/poll long enough for completion; the successful wrapper output was:

```json
{"ok": true, "version": "V185", "out": "/root/.hermes/smc_daily_closed_loop/20260627_v185_closed_loop.json", "pass": true, "wr": 86.23}
```

## Verified V185 contract

Dated report:

```text
/root/.hermes/smc_daily_closed_loop/20260627_v185_closed_loop.json
```

Production artifacts:

```text
/root/.hermes/smc_opt_v185_combined_production_candidate/v185_report.json
/root/.hermes/smc_opt_v185_combined_production_candidate/v185_picks.json
/root/.hermes/smc_opt_v185_combined_production_candidate/v185_active_picks.json
/root/.hermes/smc_opt_v185_combined_production_candidate/v185_trades.json
/root/.hermes/smc_audit/v185_daily_rematerialize_latest.json
```

Expected V185 report fields:

- `version`: `V185`
- `engine`: `V185_COMBINED_V175_PLUS_TRUE_TAKEOVER_CHILD`
- `decision`: `V185_DAILY_REMATERIALIZE_PASS`
- `production_write`: `true`
- `frontend_write`: `true`
- `watchlist_write`: `true`
- active picks: `6`
- trades: `334`
- WR: `86.23`
- avg PnL: `6.5628`
- same-day exit violations: `0`

## Field-sync bug and minimal fix

Initial API smoke found:

```text
POST /api/reselect {"version":"V185"}
=> {"ok": false, "error": "当前版本暂不支持重跑，version=V185, ACTIVE_VERSION=V88"}
```

This is an allowed minimal field-sync fix because the frontend summary/report already served V185 while `_api_reselect` could not rerun V185.

Patch `/root/.hermes/scripts/smc_unified.py` in `_api_reselect`:

- add `V185` to `engine_map`:

```python
'V185': (
    '/root/.hermes/scripts/v25/v185_daily_rematerialize.py',
    '/root/.hermes/smc_opt_v185_combined_production_candidate',
    'v185',
    'V185_COMBINED_V175_PLUS_TRUE_TAKEOVER_CHILD',
),
```

- when `ACTIVE_VERSION == 'V88'`, prefer V185 if `V185_DIR / 'v185_report.json'` exists before falling back to V175.
- include `V185` in the no-argument rematerialize/rerun tuple list.
- use `v185_report.json` as metrics path just like V175 uses `v175_report.json`.

## Verification commands

Compile:

```bash
python3 -m py_compile \
  /root/.hermes/scripts/smc_unified.py \
  /root/.hermes/scripts/v25/v185_daily_rematerialize.py \
  /root/.hermes/scripts/v25/smc_daily_closed_loop.py
```

Restart 8890 only after confirming it is safe to align live frontend with current disk state:

```bash
pid=$(ss -ltnp 'sport = :8890' 2>/dev/null | sed -n '2p' | grep -o 'pid=[0-9]*' | cut -d= -f2)
[ -n "$pid" ] && kill "$pid"
cd /root/.hermes/scripts && python3 smc_unified.py
```

Smoke endpoints:

```text
GET  /api/summary                         -> version=V185, engine=V185_COMBINED_V175_PLUS_TRUE_TAKEOVER_CHILD
GET  /api/autopsy/closed-loop             -> 200
GET  /api/picks                           -> 6 rows
GET  /api/live-prices                     -> 6 picks; market-closed notice is OK outside trading hours
GET  /api/resonance                       -> 6 rows; empty/None ctxSeq count must be 0
GET  /api/kline_full?symbol=300349.SZ&tf=daily&ver=V185 -> version=V185
POST /api/reselect {"version":"V185"}     -> ok=true, version=V185
```

## Provider-refresh caveat

Ops log may show Tencent/data-provider refresh drift:

```text
requested=4905, ok=0, failed=4905
Expecting value: line 1 column 1 (char 0)
```

Do not mutate strategy logic for this. Report it as an upstream empty/non-JSON response unless actual cache/latest-date completeness gate fails. Avoid repeated refresh loops that worsen provider throttling.
