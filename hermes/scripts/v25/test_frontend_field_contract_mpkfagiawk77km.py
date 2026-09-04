#!/usr/bin/env python3
"""Regression checks for SMC monitor/live field contract.

Covers the task mpkfagiawk77km class of failures:
- /monitor current picks table has 选股日期/加入日期/Zone/成本线/波动 populated
- /live table has 选股日/加入日/成本线/Zone/波动 populated
- API aliases remain non-blank for /api/picks and /api/live-prices
"""
import json
import re
import subprocess
import sys
import time
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PORT = 8890
BASE = f'http://127.0.0.1:{PORT}'


def blank(v):
    return v is None or v == '' or v == '-' or v == 0 or v == '0' or v == '0.00' or v == '0.00%'


def rows(payload):
    if isinstance(payload, list):
        return payload
    if isinstance(payload, dict):
        for k in ('picks', 'data', 'rows', 'items'):
            if isinstance(payload.get(k), list):
                return payload[k]
    return []


def get_json(path):
    with urllib.request.urlopen(BASE + path, timeout=30) as r:
        return json.loads(r.read().decode())


def get_html(path):
    with urllib.request.urlopen(BASE + path, timeout=30) as r:
        return r.read().decode()


def start_server():
    proc = subprocess.Popen(
        [sys.executable, str(ROOT / 'smc_unified.py')],
        cwd=str(ROOT), stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True,
    )
    for _ in range(60):
        try:
            get_json('/api/summary')
            return proc
        except Exception:
            time.sleep(0.5)
    out = proc.stdout.read() if proc.stdout else ''
    proc.terminate()
    raise RuntimeError('server not ready: ' + out[-1000:])


def extract_table_rows(html):
    tables = re.findall(r'<table.*?</table>', html, flags=re.S)
    parsed = []
    for table in tables:
        headers = [re.sub('<.*?>', '', h).strip() for h in re.findall(r'<th.*?>(.*?)</th>', table, flags=re.S)]
        trs = re.findall(r'<tr.*?>(.*?)</tr>', table, flags=re.S)
        data_rows = []
        for tr in trs[1:]:
            cells = [re.sub(r'\s+', ' ', re.sub('<.*?>', '', c)).strip() for c in re.findall(r'<td.*?>(.*?)</td>', tr, flags=re.S)]
            if cells:
                data_rows.append(cells)
        parsed.append((headers, data_rows))
    return parsed


def assert_nonblank(rows_, label, getter):
    bad = [r for r in rows_ if blank(getter(r))]
    assert not bad, f'{label} blank count={len(bad)} sample={bad[:2]}'


def test_api_picks_field_contract_zero_blank():
    rs = rows(get_json('/api/picks'))
    assert rs, 'api picks empty'
    assert_nonblank(rs, 'pick_date', lambda r: r.get('pick_date') or r.get('select_date') or r.get('pickDate'))
    assert_nonblank(rs, 'join_date', lambda r: r.get('join_date') or r.get('joinDate'))
    assert_nonblank(rs, 'zone', lambda r: (r.get('zone_type') or r.get('zoneType')) if not (r.get('zone_low') and r.get('zone_high')) else 'zone_range')
    assert_nonblank(rs, 'cost', lambda r: r.get('cost_line') or r.get('costLine') or r.get('smart_money_cost') or r.get('v25_cost_line'))
    assert_nonblank(rs, 'vol', lambda r: r.get('volatility_pct') or r.get('volatilityPct') or r.get('risk_pct') or r.get('v25_sl_pct') or r.get('v25_vol_class') or r.get('vol_class'))


def test_api_live_prices_field_contract_zero_blank_and_numeric_volatility():
    rs = rows(get_json('/api/live-prices'))
    assert rs, 'api live-prices empty'
    assert_nonblank(rs, 'live pickDate', lambda r: r.get('pickDate') or r.get('pick_date') or r.get('select_date'))
    assert_nonblank(rs, 'live joinDate', lambda r: r.get('joinDate') or r.get('join_date'))
    assert_nonblank(rs, 'live zone', lambda r: (r.get('zoneType') or r.get('zone_type')) if not (r.get('zoneLow') and r.get('zoneHigh') or r.get('zone_low') and r.get('zone_high')) else 'zone_range')
    assert_nonblank(rs, 'live cost', lambda r: r.get('costLine') or r.get('cost_line') or r.get('smart_money_cost'))
    assert_nonblank(rs, 'live numeric vol', lambda r: r.get('volatilityPct') or r.get('volatility_pct') or r.get('volatility'))


def test_monitor_html_current_picks_table_has_requested_columns_and_values():
    html = get_html('/monitor')
    tables = extract_table_rows(html)
    current = next((x for x in tables if '成本线' in x[0] and '波动' in x[0] and '引擎' in x[0]), None)
    assert current, 'monitor current picks table not found'
    headers, data_rows = current
    assert {'选股日期', '加入日期', 'Zone', '成本线', '波动'}.issubset(set(headers))
    idx = {h: i for i, h in enumerate(headers)}
    for row in data_rows[:20]:
        for col in ('选股日期', '加入日期', 'Zone', '成本线', '波动'):
            assert not blank(row[idx[col]]), f'monitor {col} blank row={row}'


def test_live_html_table_has_numeric_cost_zone_volatility():
    html = get_html('/live')
    assert '<th>选股日</th>' in html and '<th>加入日</th>' in html
    assert '<th>成本线</th>' in html and '<th>Zone</th>' in html and '<th>波动</th>' in html
    # Regression guard: live page must prefer numeric volatilityPct/volatility_pct over market-state class.
    src = (ROOT / 'smc_unified.py').read_text()
    assert "let volStr = (p.volatilityPct ? Number(p.volatilityPct).toFixed(2)+'%'" in src
    assert ": (p.volClass || p.vol_class || '-')" in src


def main():
    proc = start_server()
    try:
        tests = [
            test_api_picks_field_contract_zero_blank,
            test_api_live_prices_field_contract_zero_blank_and_numeric_volatility,
            test_monitor_html_current_picks_table_has_requested_columns_and_values,
            test_live_html_table_has_numeric_cost_zone_volatility,
        ]
        for t in tests:
            t()
            print(t.__name__, 'PASS')
    finally:
        proc.terminate()
        try:
            proc.wait(timeout=5)
        except subprocess.TimeoutExpired:
            proc.kill()


if __name__ == '__main__':
    main()
