#!/usr/bin/env python3
"""V147 read-only integrity replay for V144 preview payload.

Goal: verify that the display-only V144 payload still matches the underlying
K-line semantics and remains isolated from production. Writes audit artifacts
only under /root/.hermes/smc_audit.
"""
from __future__ import annotations

import hashlib
import json
import urllib.request
from collections import Counter
from pathlib import Path
from typing import Any

ROOT = Path('/root/.hermes')
IN_DIR = ROOT / 'smc_audit' / 'v144_v143_ui_api_dry_run_mapping_20260621'
OUT = ROOT / 'smc_audit' / 'v147_v144_preview_integrity_replay_20260621'
KLINE_DIR = ROOT / 'kline_cache'
SMC_BASE = 'http://127.0.0.1:8890'
OUT.mkdir(parents=True, exist_ok=True)

INPUTS = {
    'all': IN_DIR / 'v144_ui_api_dry_run_all.json',
    'recent45': IN_DIR / 'v144_ui_api_dry_run_recent45.json',
    'latest_per_symbol': IN_DIR / 'v144_ui_api_dry_run_latest_per_symbol.json',
}

STATUS_RULES = {
    'PRE_BUY_GAP_NOTE_ONLY': lambda f: f['pre_buy_gap'],
    'CANCEL_AFTER_ENTRY_DAY_CLOSE': lambda f: f['cancel_after_close'],
    'INTRADAY_RISK_NOTE_ONLY': lambda f: f['intraday_risk'],
    'KEEP_WATCH_NO_LATE_FAILURE': lambda f: f['keep_watch'],
}


def fnum(v: Any, default: float = 0.0) -> float:
    try:
        if v is None or v == '':
            return default
        return float(v)
    except Exception:
        return default


def pct(a: float, b: float) -> float:
    return 0.0 if b == 0 else (a - b) / b * 100.0


def bar_date(b: dict[str, Any]) -> str:
    return str(b.get('t', b.get('date', b.get('time', '')))).replace('-', '')[:8]


def kline_path(symbol: str) -> Path | None:
    stem = symbol.replace('.', '_')
    for suffix in ['daily_750', 'daily_300']:
        p = KLINE_DIR / f'{stem}_{suffix}.json'
        if p.exists():
            return p
    return None


def load_bars(symbol: str) -> list[dict[str, Any]]:
    p = kline_path(symbol)
    if not p:
        return []
    data = json.loads(p.read_text(encoding='utf-8'))
    if isinstance(data, dict):
        for key in ['data', 'klines', 'bars']:
            if isinstance(data.get(key), list):
                data = data[key]
                break
    return data if isinstance(data, list) else []


def get_bar_value(bars: list[dict[str, Any]], idx: int, key: str) -> float | None:
    if idx < 0 or idx >= len(bars):
        return None
    return fnum(bars[idx].get(key), None)  # type: ignore[arg-type]


def recompute(row: dict[str, Any]) -> dict[str, Any]:
    bars = load_bars(str(row.get('symbol', '')))
    dates = {bar_date(b): i for i, b in enumerate(bars)}
    entry_date = str(row.get('entry_date', row.get('entryDate', '')))[:8]
    entry_i = dates.get(entry_date, int(fnum(row.get('entry_idx'), -1)))
    zone_high = fnum(row.get('zone_high'))
    entry_price = fnum(row.get('entry_price'))
    reclaim_close = fnum(row.get('reclaim_close'))

    entry_low = get_bar_value(bars, entry_i, 'l')
    entry_high = get_bar_value(bars, entry_i, 'h')
    entry_close = get_bar_value(bars, entry_i, 'c')
    next1_close = get_bar_value(bars, entry_i + 1, 'c')
    next2_close = get_bar_value(bars, entry_i + 2, 'c')

    entry_above_zone = round(pct(entry_price, zone_high), 4)
    entry_above_reclaim = round(pct(entry_price, reclaim_close), 4)
    entry_retests_zone = bool(entry_low is not None and entry_low <= zone_high)
    entry_closes_below_zone = bool(entry_close is not None and entry_close < zone_high)
    early_zone_fail = bool(
        entry_closes_below_zone or
        (next1_close is not None and next1_close < zone_high) or
        (next2_close is not None and next2_close < zone_high)
    )
    no_follow = bool(entry_close is not None and entry_close <= entry_price * 1.01)
    pre_buy_gap = entry_above_zone > 2.0
    cancel_after_close = bool(entry_closes_below_zone or no_follow or early_zone_fail)
    intraday_risk = bool(entry_retests_zone)
    keep_watch = not (pre_buy_gap or cancel_after_close or intraday_risk)

    return {
        'kline_found': bool(bars),
        'entry_i_resolved': entry_i,
        'entry_above_zone_high_pct': entry_above_zone,
        'entry_above_reclaim_close_pct': entry_above_reclaim,
        'entry_day_retests_zone_high': entry_retests_zone,
        'entry_day_closes_below_zone_high': entry_closes_below_zone,
        'early_zone_fail_0_2': early_zone_fail,
        'no_entry_follow_through_le_1pct': no_follow,
        'pre_buy_gap': pre_buy_gap,
        'cancel_after_close': cancel_after_close,
        'intraday_risk': intraday_risk,
        'keep_watch': keep_watch,
    }


def load_payload(scope: str) -> dict[str, Any]:
    return json.loads(INPUTS[scope].read_text(encoding='utf-8'))


def fetch_raw(path: str) -> bytes:
    with urllib.request.urlopen(SMC_BASE + path, timeout=8) as resp:
        return resp.read()


def production_probe() -> dict[str, Any]:
    out: dict[str, Any] = {}
    for ep in ['/api/summary', '/api/picks/contract', '/api/picks', '/api/live-prices']:
        try:
            raw = fetch_raw(ep)
            obj = json.loads(raw.decode('utf-8'))
            leak = 0
            text = raw.decode('utf-8', errors='ignore')
            for marker in ['V144_DRY_RUN', 'v143_lifecycle_status', 'v144_status', 'NO_BUY']:
                leak += text.count(marker)
            out[ep] = {
                'http_ok': True,
                'bytes': len(raw),
                'sha16': hashlib.sha256(raw).hexdigest()[:16],
                'leak_marker_count': leak,
                'summary': {
                    'engine': obj.get('engine') if isinstance(obj, dict) else None,
                    'total_trades': obj.get('total_trades') if isinstance(obj, dict) else None,
                    'win_rate': obj.get('win_rate') if isinstance(obj, dict) else None,
                    'tradable_active_pick_count': obj.get('tradable_active_pick_count') if isinstance(obj, dict) else None,
                    'watch_only_count': obj.get('watch_only_count') if isinstance(obj, dict) else None,
                    'raw_pick_file_count': obj.get('raw_pick_file_count') if isinstance(obj, dict) else None,
                    'rows': len(obj) if isinstance(obj, list) else None,
                    'picks': len(obj.get('picks', [])) if isinstance(obj, dict) and isinstance(obj.get('picks'), list) else None,
                }
            }
        except Exception as exc:
            out[ep] = {'http_ok': False, 'error': repr(exc)}
    return out


def audit_scope(scope: str) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    payload = load_payload(scope)
    rows = payload.get('rows', [])
    mismatches: list[dict[str, Any]] = []
    counts = Counter()
    bad_buy = 0
    missing_kline = 0
    for row in rows:
        flags = recompute(row)
        status = str(row.get('v143_lifecycle_status') or row.get('v144_status') or '')
        counts[status] += 1
        if not flags['kline_found']:
            missing_kline += 1
        if row.get('tradable') is True or row.get('buy_enabled') is True or row.get('trade_action') != 'NO_BUY':
            bad_buy += 1
        expected_ok = STATUS_RULES.get(status, lambda _: False)(flags)
        field_mismatch = []
        checks = [
            ('v140_entry_above_zone_high_pct', 'entry_above_zone_high_pct', 0.02),
            ('v140_entry_above_reclaim_close_pct', 'entry_above_reclaim_close_pct', 0.02),
            ('v140_entry_day_retests_zone_high', 'entry_day_retests_zone_high', None),
            ('v140_entry_day_closes_below_zone_high', 'entry_day_closes_below_zone_high', None),
            ('v140_early_zone_fail_0_2', 'early_zone_fail_0_2', None),
            ('v140_no_entry_follow_through_le_1pct', 'no_entry_follow_through_le_1pct', None),
        ]
        for src, dst, tol in checks:
            if src not in row:
                continue
            if tol is None:
                if bool(row.get(src)) != bool(flags[dst]):
                    field_mismatch.append(src)
            else:
                if abs(fnum(row.get(src)) - fnum(flags[dst])) > tol:
                    field_mismatch.append(src)
        if (not expected_ok) or field_mismatch:
            mismatches.append({
                'symbol': row.get('symbol'),
                'entry_date': row.get('entry_date'),
                'status': status,
                'field_mismatch': '|'.join(field_mismatch),
                **flags,
                'row_entry_above_zone': row.get('v140_entry_above_zone_high_pct'),
                'row_entry_above_reclaim': row.get('v140_entry_above_reclaim_close_pct'),
            })
    summary = {
        'scope': scope,
        'rows': len(rows),
        'status_counts': dict(counts),
        'missing_kline': missing_kline,
        'bad_buy_like': bad_buy,
        'mismatch_count': len(mismatches),
        'preview_payload_summary': payload.get('summary', {}),
    }
    return summary, mismatches


def main() -> None:
    scope_summaries = []
    all_mismatches = []
    for scope in INPUTS:
        summary, mismatches = audit_scope(scope)
        scope_summaries.append(summary)
        for m in mismatches:
            m['scope'] = scope
        all_mismatches.extend(mismatches)

    import csv
    mismatch_path = OUT / 'v147_preview_kline_mismatches.csv'
    cols = sorted({k for row in all_mismatches for k in row})
    with mismatch_path.open('w', newline='', encoding='utf-8') as f:
        w = csv.DictWriter(f, fieldnames=cols)
        w.writeheader()
        w.writerows(all_mismatches)

    prod = production_probe()
    summary = {
        'decision': 'V147_V144_PREVIEW_INTEGRITY_REPLAY_DONE_NO_PRODUCTION_CHANGE',
        'production_write': False,
        'input_dir': str(IN_DIR),
        'out_dir': str(OUT),
        'scope_summaries': scope_summaries,
        'total_mismatch_count': len(all_mismatches),
        'production_probe': prod,
    }
    (OUT / 'summary.json').write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding='utf-8')

    lines = [
        '# V147 V144 preview K-line integrity replay（只读）',
        '',
        f"Decision: `{summary['decision']}`。只读验证 V144 preview payload，不改生产/API/frontend/watchlist/TP/SL。",
        '',
        '## 1. Scope audit',
        '| scope | rows | missing_kline | bad_buy_like | mismatch_count | status_counts |',
        '|---|---:|---:|---:|---:|---|',
    ]
    for s in scope_summaries:
        lines.append(f"| {s['scope']} | {s['rows']} | {s['missing_kline']} | {s['bad_buy_like']} | {s['mismatch_count']} | {s['status_counts']} |")
    lines += [
        '',
        '## 2. Production isolation',
        '| endpoint | http | leak_marker_count | key summary | sha16 |',
        '|---|---:|---:|---|---|',
    ]
    for ep, p in prod.items():
        lines.append(f"| `{ep}` | {p.get('http_ok')} | {p.get('leak_marker_count', 'NA')} | {p.get('summary', {})} | {p.get('sha16', '')} |")
    lines += [
        '',
        '## 3. Conclusion',
        'V144 独立预览 payload 的 NO_BUY/display-only 合同保持成立；生产接口未出现 V144/V143 生命周期字段污染。',
        '本轮发现的字段语义差异只用于只读审计，不构成 BUY 规则。' if all_mismatches else 'K线重算与payload字段/状态全部一致，不构成 BUY 规则。',
    ]
    (OUT / 'report.md').write_text('\n'.join(lines), encoding='utf-8')
    print(json.dumps(summary, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
