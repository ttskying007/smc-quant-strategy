#!/usr/bin/env python3
"""No-write source health and cross-source drift monitor for V536 raw MTF cache.

This monitor does not substitute providers inside historical raw series:
Baostock raw OHLCV remains the only 2023-2026 SH/SZ intraday writer. Sina and
Tencent are independent health/drift witnesses; their failure blocks no cache
already verified from Baostock, but is recorded for operator action.
"""
from __future__ import annotations

import gzip
import json
import subprocess
import time
from datetime import datetime
from pathlib import Path

import baostock as bs
import requests

ROOT = Path('/root/.hermes')
CACHE = ROOT / 'intraday_cache/raw_multitf_v536'
AUDIT = ROOT / 'smc_audit'
LATEST = AUDIT / 'v536_multitf_source_monitor_latest.json'
SINA = 'http://money.finance.sina.com.cn/quotes_service/api/json_v2.php/CN_MarketData.getKLineData'
PROBE = '000001.SZ'


def save(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + '.tmp')
    tmp.write_text(json.dumps(payload, ensure_ascii=False, indent=2))
    tmp.replace(path)


def bars_count(frame: str) -> int:
    path = CACHE / frame
    return len(list(path.glob('*.json.gz'))) if path.exists() else 0


def bq(freq: str, fields: str) -> dict:
    q = bs.query_history_k_data_plus('sz.000001', fields, start_date='2025-04-02', end_date='2025-04-03', frequency=freq, adjustflag='3')
    rows = []
    while q.error_code == '0' and q.next():
        rows.append(q.get_row_data())
    return {'ok': q.error_code == '0' and bool(rows), 'code': q.error_code, 'message': q.error_msg, 'rows': rows}


def sina(frame: int) -> dict:
    try:
        r = requests.get(SINA, params={'symbol': 'sz000001', 'scale': frame, 'ma': 'no', 'datalen': 10000}, headers={'User-Agent': 'Mozilla/5.0'}, timeout=25)
        rows = r.json()
        return {'ok': r.status_code == 200 and isinstance(rows, list) and bool(rows), 'http_status': r.status_code, 'rows': rows if isinstance(rows, list) else []}
    except Exception as exc:
        return {'ok': False, 'error': repr(exc), 'rows': []}


def tencent_daily() -> dict:
    url = 'http://ifzq.gtimg.cn/appstock/app/fqkline/get?param=sz000001,day,,,10,qfq'
    try:
        p = subprocess.run(['curl', '-sSL', '--max-time', '20', url], capture_output=True, text=True, timeout=30)
        data = json.loads(p.stdout)
        rows = (data.get('data', {}).get('sz000001', {}) or {}).get('qfqday') or []
        return {'ok': p.returncode == 0 and bool(rows), 'returncode': p.returncode, 'rows': rows}
    except Exception as exc:
        return {'ok': False, 'error': repr(exc), 'rows': []}


def intraday_close_by_time_bao(rows: list[list[str]]) -> dict[str, float]:
    out = {}
    for row in rows:
        if len(row) >= 6:
            key = f"{row[0]} {str(row[1])[8:12]}"
            out[key] = float(row[5])
    return out


def intraday_close_by_time_sina(rows: list[dict]) -> dict[str, float]:
    out = {}
    for row in rows:
        day = str(row.get('day') or '')
        if len(day) >= 16:
            out[f"{day[:10]} {day[11:16].replace(':', '')}"] = float(row['close'])
    return out


def compare(bao: dict, sina_rows: list[dict]) -> dict:
    left, right = intraday_close_by_time_bao(bao['rows']), intraday_close_by_time_sina(sina_rows)
    common = sorted(set(left) & set(right))
    deltas = [abs(left[k] - right[k]) for k in common]
    return {'common_bars': len(common), 'max_abs_close_delta': max(deltas) if deltas else None, 'same_raw_prices': bool(common) and max(deltas) <= 1e-8}


def main() -> None:
    started = time.time()
    login = bs.login()
    baostock_login = {'ok': login.error_code == '0', 'code': login.error_code, 'message': login.error_msg}
    if baostock_login['ok']:
        try:
            bd = bq('d', 'date,open,high,low,close,volume,amount,adjustflag')
            b60 = bq('60', 'date,time,open,high,low,close,volume,amount,adjustflag')
            b15 = bq('15', 'date,time,open,high,low,close,volume,amount,adjustflag')
        finally:
            bs.logout()
    else:
        bd = b60 = b15 = {'ok': False, 'code': login.error_code, 'message': login.error_msg, 'rows': []}
    s60, s15 = sina(60), sina(15)
    tq = tencent_daily()
    c60 = compare(b60, s60['rows']) if b60['ok'] and s60['ok'] else {'common_bars': 0, 'same_raw_prices': False}
    c15 = compare(b15, s15['rows']) if b15['ok'] and s15['ok'] else {'common_bars': 0, 'same_raw_prices': False}
    providers = {
        'baostock_login': baostock_login, 'baostock_raw_daily': bd['ok'], 'baostock_raw_m60': b60['ok'], 'baostock_raw_m15': b15['ok'],
        'sina_m60_witness': s60['ok'], 'sina_m15_witness': s15['ok'], 'tencent_daily_witness': tq['ok'],
    }
    primary_healthy = all((bd['ok'], b60['ok'], b15['ok']))
    report = {
        'version': 'V536_MULTITF_SOURCE_MONITOR_V2', 'generated_at': datetime.now().isoformat(timespec='seconds'),
        'contract': 'Provider namespaces are isolated under source_raw. Baostock is a legacy full-history source; Sina/Tencent are independently labelled partial witnesses. No cross-source bar substitution.',
        'probe_symbol': PROBE, 'cache_file_counts': {x: bars_count(x) for x in ('daily', 'weekly', 'm60', 'm15')},
        'provider_health': providers,
        'cross_source_raw_overlap': {'m60': c60, 'm15': c15},
        'primary_healthy': primary_healthy,
        'witness_healthy': all((s60['ok'], s15['ok'], tq['ok'])),
        'cache_build_allowed': primary_healthy,
        'state': 'PRIMARY_SOURCE_BLOCKED__NO_BUILD' if not primary_healthy else 'PRIMARY_SOURCE_HEALTHY',
        'elapsed_sec': round(time.time() - started, 2),
        'samples': {'baostock_daily_rows': len(bd['rows']), 'baostock_m60_rows': len(b60['rows']), 'baostock_m15_rows': len(b15['rows']), 'sina_m60_rows': len(s60['rows']), 'sina_m15_rows': len(s15['rows']), 'tencent_daily_rows': len(tq['rows'])},
    }
    stamped = AUDIT / f"v536_multitf_source_monitor_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
    save(stamped, report); save(LATEST, report)
    print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
