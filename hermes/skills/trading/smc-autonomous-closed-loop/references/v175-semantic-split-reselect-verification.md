# V175 semantic split + manual rerun verification pattern (2026-06-23)

## Trigger
After V175 was promoted as a label-only semantic split over V172/V175 artifacts, the frontend/API needed verification beyond aggregate metrics. The key risk was stale nested labels or manual rerun routing silently falling back to an older active engine.

## Durable lesson
When a production version is a semantic/label repair rather than a new economic model, verify both:

1. **Top-level API contract** — `/api/summary`, `/api/picks`, `/api/live-prices`, `/api/resonance` report the promoted version and no `None/null` signal text.
2. **Nested display/provenance contract** — frontend display fields and nested DNA/contract fields no longer overclaim the old semantic label; the old label may only remain in explicit provenance fields.

## Required verification commands

```bash
python3 -m py_compile \
  /root/.hermes/scripts/smc_unified.py \
  /root/.hermes/scripts/v25/v175_semantic_split_materialize.py

python3 - <<'PY'
import urllib.request, json
base='http://127.0.0.1:8890'
for path in [
    '/api/summary',
    '/api/picks',
    '/api/live-prices',
    '/api/resonance',
    '/api/kline_full?symbol=688327.SH&tf=daily&ver=V175',
    '/backtest',
]:
    data = urllib.request.urlopen(base + path, timeout=20).read(2000)
    print(path, 'OK', len(data), data[:120].decode('utf-8','ignore').replace('\n',' '))
req = urllib.request.Request(
    base + '/api/reselect',
    data=b'{"version":"V175"}',
    headers={'Content-Type':'application/json'},
    method='POST',
)
data = urllib.request.urlopen(req, timeout=30).read(2000)
print('/api/reselect V175', data[:300].decode('utf-8','ignore'))
PY
```

## Acceptance checks

- `/api/summary.version == V175`.
- `/api/picks` rows use `event_type == DEMAND_OB_TRUE_TAKEOVER_RECLAIM`.
- `/api/live-prices.total` matches the visible pick universe; market closed is allowed but must not erase rows.
- `/api/resonance` has zero empty/`None`/`null` `ctxSeq` values.
- `POST /api/reselect {"version":"V175"}` returns `ok=true` and writes a history file for V175, not V88/V102 fallback.
- K-line and backtest pages return 200 OK for the promoted version.

## Pitfall
Do not treat a label-only promotion as complete after `ACTIVE_VERSION` changes. Manual reselect may still ignore POST JSON and use the legacy default unless `/api/reselect` parses the body and routes the version explicitly.
