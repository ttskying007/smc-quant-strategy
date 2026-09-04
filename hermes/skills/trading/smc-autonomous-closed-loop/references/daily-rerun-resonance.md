# Daily rerun + resonance synchronization notes

## Rerun failure pattern

Symptom:

```text
失败: 当前版本暂不支持重跑，ACTIVE_VERSION=VXX
```

Durable cause:

- `smc_unified.py` can point `ACTIVE_VERSION` to a new production version while `_api_reselect()` still has an older `engine_map`.
- Frontend summary/backtest may appear synced, but manual rerun is a separate code path and must be updated explicitly.

Required fix when promoting a new version:

1. Add `VXX` to `_api_reselect()` `engine_map` with:
   - engine path: `/root/.hermes/scripts/v25/vXX_engine.py`
   - output dir: `/root/.hermes/smc_opt_vXX`
   - prefix: `vXX`
   - engine label
2. Ensure any tuple/list branches inside `_api_reselect()` include `VXX` when they distinguish modern engines.
3. Verify with actual POST, not page load only:

```python
import urllib.request
req = urllib.request.Request('http://127.0.0.1:8890/api/reselect', data=b'', method='POST')
print(urllib.request.urlopen(req, timeout=180).read().decode()[:1000])
```

Expected:

```json
{"ok": true, "engine": "VXX_..."}
```

## Resonance blank / None signal pattern

Symptom:

```text
共振页信号为空 / None
```

Durable cause:

- `/api/resonance` historically used only `ctx_seq`.
- Later pick formats may not carry `ctx_seq`; they may carry `v59_setup_family`, `trade_role`, `zone_type`, `signal_type`, or `conf_type`.

Required fix:

- Build a signal fallback chain:

```text
ctx_seq -> seq -> detail -> v59_setup_family -> trade_role -> zone_type -> signal_type -> conf_type
```

- Add a separate `signalText` fallback such as:

```text
{family} {zone_type/signal_type} {conf_type}
```

- Treat literal strings `None` and `null` as empty.

Verification:

```python
import urllib.request, json
data = json.loads(urllib.request.urlopen('http://127.0.0.1:8890/api/resonance', timeout=30).read())
assert sum(1 for x in data if str(x.get('ctxSeq')) in ('None', '')) == 0
```

## Cron creation pattern

Use Hermes cron with the script path relative to `~/.hermes/scripts/`:

```bash
hermes cron create '0 0 * * *' \
  'Run SMC autonomous closed loop from script output; if release gate fails or metrics regress, diagnose and implement next minimal Vxx repair, audit, sync frontend/rerun support, verify APIs, no user prompts.' \
  --name 'SMC Autonomous Closed Loop V65+' \
  --deliver local \
  --skill smc-autonomous-closed-loop \
  --skill smc-v11-system \
  --script 'v25/smc_daily_closed_loop.py' \
  --workdir '/root/.hermes/scripts'
```

Pitfall:

- `hermes cron create --script` rejects absolute/home-relative script paths. Use `v25/smc_daily_closed_loop.py`, not `/root/.hermes/scripts/v25/smc_daily_closed_loop.py`.
