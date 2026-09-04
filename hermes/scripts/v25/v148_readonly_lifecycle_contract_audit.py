#!/usr/bin/env python3
"""V148 read-only lifecycle API/display contract audit.

Verifies the V144 preview endpoint now exposes an explicit contract block,
all preview rows remain NO_BUY, and production endpoints remain isolated.
Writes only under /root/.hermes/smc_audit.
"""
from __future__ import annotations

import hashlib
import json
import urllib.request
from collections import Counter
from pathlib import Path
from typing import Any

OUT = Path('/root/.hermes/smc_audit/v148_readonly_lifecycle_contract_20260621')
OUT.mkdir(parents=True, exist_ok=True)
BASE = 'http://127.0.0.1:8890'
SCOPES = ['latest_per_symbol', 'recent45', 'all']
PROD_ENDPOINTS = ['/api/summary', '/api/picks/contract', '/api/picks', '/api/live-prices']


def fetch(path: str) -> tuple[int, bytes]:
    with urllib.request.urlopen(BASE + path, timeout=12) as r:
        return r.status, r.read()


def json_fetch(path: str) -> tuple[int, Any, bytes]:
    status, raw = fetch(path)
    return status, json.loads(raw.decode('utf-8')), raw


def audit_preview(scope: str) -> dict[str, Any]:
    status, data, raw = json_fetch('/api/v144-dry-run-preview?scope=' + scope)
    rows = data.get('rows', [])
    contract = data.get('contract', {})
    status_counts = Counter(r.get('v144_status') or r.get('lifecycle_status') or r.get('v143_lifecycle_status') or 'UNKNOWN' for r in rows)
    bad_buy = [r for r in rows if r.get('tradable') is True or r.get('buy_enabled') is True or str(r.get('trade_action') or '') != 'NO_BUY']
    failures = []
    expected_contract = {
        'shadow_only': True,
        'display_only': True,
        'production_write': False,
        'buy_enabled': False,
        'trade_action': 'NO_BUY',
        'all_rows_no_buy': True,
        'v147_checked': True,
    }
    for k, v in expected_contract.items():
        if contract.get(k) != v:
            failures.append(f'contract.{k}={contract.get(k)!r} expected {v!r}')
    if contract.get('row_count') != len(rows):
        failures.append(f"contract.row_count={contract.get('row_count')} rows={len(rows)}")
    if contract.get('bad_buy_like') != len(bad_buy):
        failures.append(f"contract.bad_buy_like={contract.get('bad_buy_like')} actual={len(bad_buy)}")
    if dict(status_counts) != contract.get('status_counts'):
        failures.append('contract.status_counts mismatch')
    if contract.get('v147_kline_mismatch_count') != 0:
        failures.append(f"v147 mismatch={contract.get('v147_kline_mismatch_count')}")
    if contract.get('v147_missing_kline') != 0:
        failures.append(f"v147 missing_kline={contract.get('v147_missing_kline')}")
    return {
        'scope': scope,
        'http': status,
        'bytes': len(raw),
        'sha16': hashlib.sha256(raw).hexdigest()[:16],
        'rows': len(rows),
        'status_counts': dict(status_counts),
        'bad_buy_like': len(bad_buy),
        'contract': contract,
        'failures': failures,
        'pass': status == 200 and not failures and len(bad_buy) == 0,
    }


def audit_page() -> dict[str, Any]:
    status, raw = fetch('/v144-preview')
    text = raw.decode('utf-8', 'replace')
    checks = {
        'has_shadow_only_text': 'shadow-only / display-only / NO_BUY' in text,
        'fetches_preview_api': '/api/v144-dry-run-preview' in text,
        'not_fetch_picks_api': "fetch('/api/picks" not in text and 'fetch("/api/picks' not in text,
        'not_fetch_live_api': "fetch('/api/live-prices" not in text and 'fetch("/api/live-prices' not in text,
    }
    return {
        'http': status,
        'bytes': len(raw),
        'sha16': hashlib.sha256(raw).hexdigest()[:16],
        'checks': checks,
        'pass': status == 200 and all(checks.values()),
    }


def audit_prod() -> dict[str, Any]:
    out: dict[str, Any] = {}
    for ep in PROD_ENDPOINTS:
        try:
            status, raw = fetch(ep)
            text = raw.decode('utf-8', 'ignore')
            leak = sum(text.count(m) for m in ['V144_DRY_RUN', 'V148_READONLY_LIFECYCLE_CONTRACT', 'v144_status', 'v143_lifecycle_status', 'NO_BUY'])
            try:
                obj = json.loads(text)
            except Exception:
                obj = None
            summary = {}
            if isinstance(obj, dict):
                summary = {
                    'engine': obj.get('engine'),
                    'total_trades': obj.get('total_trades'),
                    'win_rate': obj.get('win_rate'),
                    'tradable_active_pick_count': obj.get('tradable_active_pick_count'),
                    'watch_only_count': obj.get('watch_only_count'),
                    'raw_pick_file_count': obj.get('raw_pick_file_count'),
                    'picks': len(obj.get('picks', [])) if isinstance(obj.get('picks'), list) else None,
                }
            elif isinstance(obj, list):
                summary = {'rows': len(obj)}
            out[ep] = {
                'http': status,
                'bytes': len(raw),
                'sha16': hashlib.sha256(raw).hexdigest()[:16],
                'leak_marker_count': leak,
                'summary': summary,
                'pass': status == 200 and leak == 0,
            }
        except Exception as exc:
            out[ep] = {'pass': False, 'error': repr(exc)}
    return out


def main() -> None:
    preview = [audit_preview(s) for s in SCOPES]
    page = audit_page()
    prod = audit_prod()
    passed = all(x['pass'] for x in preview) and page['pass'] and all(x.get('pass') for x in prod.values())
    summary = {
        'decision': 'V148_READONLY_LIFECYCLE_CONTRACT_DONE_NO_PRODUCTION_CHANGE' if passed else 'V148_CONTRACT_AUDIT_FAILED',
        'production_write': False,
        'frontend_change': 'api contract metadata only; existing /v144-preview display page verified',
        'out_dir': str(OUT),
        'preview_scopes': preview,
        'page': page,
        'production_probe': prod,
        'pass': passed,
    }
    (OUT / 'summary.json').write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding='utf-8')
    lines = [
        '# V148 readonly lifecycle API/display contract audit',
        '',
        f"Decision: `{summary['decision']}`。只读补齐 `/api/v144-dry-run-preview` 合同元数据，不改生产 BUY/watchlist/TP/SL。",
        '',
        '## 1. Preview API contract',
        '| scope | rows | bad_buy_like | v147_mismatch | v147_missing_kline | status_counts | pass |',
        '|---|---:|---:|---:|---:|---|---:|',
    ]
    for x in preview:
        c = x['contract']
        lines.append(f"| {x['scope']} | {x['rows']} | {x['bad_buy_like']} | {c.get('v147_kline_mismatch_count')} | {c.get('v147_missing_kline')} | {x['status_counts']} | {x['pass']} |")
    lines += [
        '',
        '## 2. Preview page checks',
        '| check | value |',
        '|---|---:|',
    ]
    for k, v in page['checks'].items():
        lines.append(f'| {k} | {v} |')
    lines += [
        '',
        '## 3. Production isolation',
        '| endpoint | http | leak_marker_count | key summary | pass |',
        '|---|---:|---:|---|---:|',
    ]
    for ep, x in prod.items():
        lines.append(f"| `{ep}` | {x.get('http')} | {x.get('leak_marker_count')} | {x.get('summary')} | {x.get('pass')} |")
    lines += [
        '',
        '## 4. Conclusion',
        'V148 只把 V144/V147 的只读审计状态变成显式 API 合同；页面仍只消费 `/api/v144-dry-run-preview`，生产接口未出现 V144/V148/NO_BUY 污染。',
        '该合同只用于展示和审计，不能作为 production picks、morning push、自动买入或 tradable watchlist 来源。',
    ]
    (OUT / 'report.md').write_text('\n'.join(lines), encoding='utf-8')
    print(json.dumps(summary, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
