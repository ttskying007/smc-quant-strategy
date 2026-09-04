# Daily closed-loop rerun: active-version and refresh-drift safeguards

Session lesson from 2026-06-26 SMC autonomous closed-loop recovery.

## Pattern

A 120s cron wrapper timeout can leave the real `smc_daily_ops.py` child running. After waiting for the child, the first completed ops artifact may be valid and fresh. If the dated `/root/.hermes/smc_daily_closed_loop/YYYYMMDD_vXX_closed_loop.json` is missing, running `smc_daily_closed_loop.py` once as a tracked background process can regenerate it — but the rerun may repeat provider refresh and overwrite `ops_latest.json` with a second refresh attempt.

## Safeguards

1. **Do not duplicate while child is alive.** Check process table for `smc_daily_closed_loop.py`, `smc_daily_ops.py`, daily scanner, and shadow selector children; wait for them to exit before rerunning.
2. **Snapshot/read the first successful ops log before rerun.** Preserve `smc_monitor/ops_logs/YYYYMMDD.json` facts: `kline_refresh.summary`, `daily_scan`, `daily_ingest`, `shadow_selector`, and contract summaries.
3. **If a rerun refresh reports `ok=0` / JSON empty-response errors, audit actual cache before calling completeness failed.** Count `/root/.hermes/kline_cache/*_daily_750.json` latest bars using both `date` and `t` keys. If latest-date coverage is already >=4500, treat the rerun refresh counter as provider/rate-limit drift and report the caveat honestly.
4. **Do not restart frontend blindly when live API active version differs from on-disk wrapper detection.** `smc_daily_closed_loop.py` may derive active version from `smc_unified.py` `ACTIVE_VERSION` and generate a V88 report, while the already-running API serves a later version such as V175. Restarting can downgrade the live process if on-disk paths are stale. Verify `/api/summary`, `/api/picks`, `/api/resonance`, and `POST /api/reselect {"version":"Vxxx"}` first; if live and wrapper disagree, report the drift and avoid restart until active-version mapping is aligned.
5. **Use the dated report and live API as separate facts.** The dated closed-loop report proves wrapper completion for its detected version; live `/api/summary` proves the frontend process state. Do not conflate them.

## Compact verification snippets

Cache coverage audit:

```python
from pathlib import Path
import json, collections
counts=collections.Counter(); total=bad=0
for p in Path('/root/.hermes/kline_cache').glob('*_daily_750.json'):
    total += 1
    try:
        rows = json.loads(p.read_text())
        if isinstance(rows, dict):
            rows = rows.get('data') or rows.get('rows') or []
        if not rows:
            bad += 1; continue
        last = rows[-1]
        date = (last.get('date') or last.get('t') or last.get('time')) if isinstance(last, dict) else (last[0] if isinstance(last, (list, tuple)) and last else None)
        counts[str(date)] += 1
    except Exception:
        bad += 1
print({'cache_files': total, 'bad_or_empty': bad, 'top_latest_dates': counts.most_common(12)})
```

Live/frontend drift checks:

```bash
ss -ltnp 'sport = :8890' || true
python3 - <<'PY'
import json, urllib.request
for ep in ['/api/summary','/api/picks','/api/resonance']:
    data = urllib.request.urlopen('http://127.0.0.1:8890' + ep, timeout=20).read()
    print(ep, len(data), b'Traceback' in data)
req = urllib.request.Request('http://127.0.0.1:8890/api/reselect', data=json.dumps({'version':'V175'}).encode(), headers={'Content-Type':'application/json'}, method='POST')
print(urllib.request.urlopen(req, timeout=60).read()[:500])
PY
```
