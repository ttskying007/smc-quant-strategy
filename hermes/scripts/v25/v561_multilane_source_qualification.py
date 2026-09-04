#!/root/.hermes/venvs/smc-source-monitor/bin/python
"""V561 outcome-blind qualification probes for genuinely new SMC information lanes.

This is intentionally NOT a strategy replay.  It checks whether a new PIT source
can legally start one later frozen ontology.  It reads no PnL/outcome artifact and
never writes scanner, watchlist, frontend, or production state.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from datetime import datetime
from io import BytesIO
from pathlib import Path
from typing import Any

import pandas as pd
import requests

ROOT = Path('/root/.hermes')
AUD = ROOT / 'smc_audit'
LATEST = AUD / 'v561_multilane_source_qualification_latest.json'
STATE = AUD / 'v561_multilane_source_qualification_state.json'
DATES = ('20240102', '20250102', '20260105')
UA = 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/122.0 Safari/537.36'


def probe_sse_margin(date: str) -> dict[str, Any]:
    params = {'isPagination': 'true', 'tabType': 'mxtype', 'detailsDate': date,
              'stockCode': '', 'beginDate': '', 'endDate': '',
              'pageHelp.pageSize': '5000', 'pageHelp.pageCount': '50',
              'pageHelp.pageNo': '1', 'pageHelp.beginPage': '1',
              'pageHelp.cacheSize': '1', 'pageHelp.endPage': '21'}
    try:
        r = requests.get('https://query.sse.com.cn/marketdata/tradedata/queryMargin.do', params=params,
                         headers={'User-Agent': UA, 'Referer': 'https://www.sse.com.cn/'}, timeout=30)
        data = r.json(); rows = data.get('result') or []
        valid = bool(rows) and all(str(x.get('opDate')) == date and x.get('stockCode') for x in rows)
        return {'date': date, 'http': r.status_code, 'rows': len(rows), 'valid_date_and_security_rows': valid, 'error': ''}
    except Exception as exc:
        return {'date': date, 'http': 0, 'rows': 0, 'valid_date_and_security_rows': False, 'error': f'{type(exc).__name__}:{exc}'}


def probe_szse_margin(date: str) -> dict[str, Any]:
    iso = f'{date[:4]}-{date[4:6]}-{date[6:]}'
    params = {'SHOWTYPE': 'xlsx', 'CATALOGID': '1837_xxpl', 'txtDate': iso,
              'tab2PAGENO': '1', 'random': '0.24279342734085696', 'TABKEY': 'tab2'}
    try:
        r = requests.get('https://www.szse.cn/api/report/ShowReport', params=params,
                         headers={'User-Agent': UA, 'Referer': 'https://www.szse.cn/disclosure/margin/margin/index.html'}, timeout=30)
        frame = pd.read_excel(BytesIO(r.content), engine='openpyxl', dtype=str)
        code_col = next((c for c in frame.columns if '证券代码' in str(c)), '')
        valid = r.status_code == 200 and len(frame) > 500 and bool(code_col) and frame[code_col].astype(str).str.contains(r'\d{6}').any()
        return {'date': date, 'http': r.status_code, 'rows': len(frame), 'valid_security_rows': bool(valid), 'error': ''}
    except Exception as exc:
        return {'date': date, 'http': 0, 'rows': 0, 'valid_security_rows': False, 'error': f'{type(exc).__name__}:{exc}'}


def probe_northbound(date: str) -> dict[str, Any]:
    # Existing V406 contract: stock-level holding records must be date-sensitive.
    params = {'reportName': 'RPT_MUTUAL_HOLD_DET',
              'columns': 'SECURITY_CODE,HOLD_DATE,HOLD_NUM,HOLD_SHARES_RATIO,HOLD_MARKET_CAPONE',
              'filter': f'(SECURITY_CODE="600519")(MARKET_CODE="001")(HOLD_DATE<=\'{date[:4]}-{date[4:6]}-{date[6:]}\')',
              'pageNumber': '1', 'pageSize': '5', 'sortColumns': 'HOLD_DATE', 'sortTypes': '-1', 'source': 'WEB', 'client': 'WEB'}
    try:
        r = requests.get('https://datacenter-web.eastmoney.com/api/data/v1/get', params=params,
                         headers={'User-Agent': UA, 'Referer': 'https://data.eastmoney.com/'}, timeout=30)
        result = r.json().get('result') or {}; rows = result.get('data') or []
        cutoff = f'{date[:4]}-{date[4:6]}-{date[6:]}'
        valid = bool(rows) and all(str(x.get('HOLD_DATE', ''))[:10] <= cutoff for x in rows)
        return {'date': date, 'http': r.status_code, 'rows': len(rows), 'valid_prior_or_same_date_rows': valid, 'error': ''}
    except Exception as exc:
        return {'date': date, 'http': 0, 'rows': 0, 'valid_prior_or_same_date_rows': False, 'error': f'{type(exc).__name__}:{exc}'}


def probe_tick() -> dict[str, Any]:
    # A real historical tick provider must vary by requested date and carry volume.
    try:
        from mootdx.quotes import Quotes
        client = Quotes.factory(market='std'); results = []
        for date in DATES:
            frame = client.transaction(symbol='600519', date=date)
            cols = list(frame.columns)
            vol = frame['volume'] if 'volume' in frame else frame.get('vol')
            fingerprint = hashlib.sha256(frame.astype(str).to_csv(index=False).encode()).hexdigest() if len(frame) else ''
            results.append({'date': date, 'rows': int(len(frame)), 'positive_volume': int((vol.astype(float) > 0).sum()) if vol is not None else 0, 'fingerprint': fingerprint, 'columns': cols})
        valid = all(x['rows'] and x['positive_volume'] for x in results) and len({x['fingerprint'] for x in results}) == len(results)
        return {'probes': results, 'date_sensitive_actual_volume': valid, 'error': ''}
    except Exception as exc:
        return {'probes': [], 'date_sensitive_actual_volume': False, 'error': f'{type(exc).__name__}:{exc}'}


def pass_all(rows: list[dict[str, Any]], flag: str, min_rows: int) -> bool:
    return len(rows) == len(DATES) and all(not r['error'] and r.get(flag) and r.get('rows', 0) >= min_rows for r in rows)


def main() -> None:
    ap = argparse.ArgumentParser(); ap.add_argument('--quiet-if-unchanged', action='store_true'); args = ap.parse_args()
    sse = [probe_sse_margin(d) for d in DATES]
    szse = [probe_szse_margin(d) for d in DATES]
    northbound = [probe_northbound(d) for d in DATES]
    tick = probe_tick()
    lanes = {
        'L1_stock_level_margin_financing': {
            'dimension': 'prior-session stock-level leveraged capital balance/buying',
            # V602 established that the official full-history source is complete,
            # while the one permitted margin-response ontology is closed. Keep
            # probing source health, but never re-queue its already-tested seed/replay.
            'status': 'SOURCE_READY__TESTED_MARGIN_ONTOLOGY_CLOSED_NO_VARIANTS' if pass_all(sse, 'valid_date_and_security_rows', 1000) and pass_all(szse, 'valid_security_rows', 500) else 'SOURCE_INCOMPLETE__NO_ONTOLOGY',
            'requirements_remaining': 'Official source health is monitored only. V569 prior-session financing-balance→SMC-response ontology is closed by V571/V602; no rebuild, seed, replay or variant is permitted.',
            'sse': sse, 'szse': szse},
        'L2_stock_connect_holdings': {
            'dimension': 'prior-date northbound stock holdings change',
            'status': 'PILOT_SOURCE_READY__FULL_HISTORY_BUILD_REQUIRED' if pass_all(northbound, 'valid_prior_or_same_date_rows', 1) else 'SOURCE_UNQUALIFIED__NO_ONTOLOGY',
            'requirements_remaining': 'Must prove publication timing, stock-universe coverage, and prior-date alignment; prior V406 failure remains authoritative until then.',
            'probes': northbound},
        'L3_historical_tick_orderflow': {
            'dimension': 'trade-direction/absorption rather than OHLC wick proxy',
            'status': 'PILOT_SOURCE_READY__FULL_HISTORY_BUILD_REQUIRED' if tick['date_sensitive_actual_volume'] else 'SOURCE_UNQUALIFIED__NO_ONTOLOGY',
            'requirements_remaining': 'Need date-sensitive actual ticks and full 2023-2026 same-source coverage aligned to daily OHLCV.',
            'probe': tick},
        'L4_etf_constituent_creation_redemption': {
            'dimension': 'PIT ETF constituent demand/supply transmission',
            'status': 'NO_VERIFIABLE_SOURCE_REGISTERED__NO_ONTOLOGY',
            'requirements_remaining': 'Require historical constituent weights, share changes, and publication/effective timestamps. Existing ETF share totals do not meet this contract.'},
        'L5_exchange_disclosure_institutional_event': {
            'dimension': 'new exchange-published institutional event, distinct from closed disclosure/block-trade branches',
            'status': 'CLOSED_UNLESS_NEW_NONOVERLAPPING_EVENT_SOURCE',
            'requirements_remaining': 'Existing announcement, LHB, block-trade, holder and disclosure branches are closed; only a non-overlapping source with publication timestamps can reopen.'},
    }
    signature = json.dumps({k: v['status'] for k, v in lanes.items()}, sort_keys=True)
    old = json.loads(STATE.read_text()) if STATE.exists() else {}
    changed = old.get('signature') != signature
    report = {'version': 'V561_MULTILANE_SOURCE_QUALIFICATION_NO_WRITE', 'generated_at': datetime.now().isoformat(timespec='seconds'),
              'research_only': True, 'production_write': False, 'frontend_write': False, 'watchlist_write': False,
              'contract': 'Source qualification only; no outcomes read; no signal/replay/selector constructed.',
              'charter': str(AUD / 'v561_multilane_research_charter.md'), 'lanes': lanes,
              'state_changed': changed, 'next_action': 'Only a PILOT_SOURCE_READY lane may advance to a separately audited full-history source build. No closed OHLCV variant is authorized.'}
    text = json.dumps(report, ensure_ascii=False, indent=2)
    LATEST.write_text(text); STATE.write_text(json.dumps({'signature': signature, 'updated_at': report['generated_at']}, ensure_ascii=False, indent=2))
    if not args.quiet_if_unchanged or changed:
        print(text)


if __name__ == '__main__':
    main()
