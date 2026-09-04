#!/usr/bin/env python3
"""Fetch one independently labelled Sina intraday witness cache; never substitutes bars."""
from __future__ import annotations

import argparse
import gzip
import json
from datetime import datetime
from pathlib import Path

import requests

ROOT = Path('/root/.hermes')
OUT = ROOT / 'intraday_cache/raw_multitf_v536/source_raw/sina'
AUDIT = ROOT / 'smc_audit'
URL = 'http://money.finance.sina.com.cn/quotes_service/api/json_v2.php/CN_MarketData.getKLineData'


def atomic_gzip(path: Path, rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_suffix(path.suffix + '.tmp')
    with gzip.open(temp, 'wt', encoding='utf-8') as handle:
        json.dump(rows, handle, ensure_ascii=False, separators=(',', ':'))
    temp.replace(path)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument('--symbol', default='000001.SZ')
    parser.add_argument('--frames', nargs='+', type=int, default=[15, 60])
    args = parser.parse_args()
    code, market = args.symbol.split('.')
    sina_symbol = ('sh' if market == 'SH' else 'sz') + code
    result = {'version': 'V536_SINA_SOURCE_LOCAL_PROBE_V1', 'generated_at': datetime.now().isoformat(timespec='seconds'), 'research_only': True, 'production_write': False, 'symbol': args.symbol, 'source': 'sina', 'frames': {}}
    for minutes in args.frames:
        response = requests.get(URL, params={'symbol': sina_symbol, 'scale': minutes, 'ma': 'no', 'datalen': 10000}, headers={'User-Agent': 'Mozilla/5.0'}, timeout=30)
        raw = response.json()
        if response.status_code != 200 or not isinstance(raw, list) or not raw:
            raise RuntimeError(f'sina_{minutes}m_unavailable status={response.status_code}')
        bars = []
        for row in raw:
            stamp = str(row['day'])
            date, clock = stamp[:10].replace('-', ''), stamp[11:16].replace(':', '')
            bars.append({'t': f'{date}{clock}00', 'd': date, 'o': float(row['open']), 'h': float(row['high']), 'l': float(row['low']), 'c': float(row['close']), 'v': float(row['volume']), 'source': 'sina', 'adjustment': 'provider_undocumented_no_cross_source_assumption', 'requested_range': {'datalen': 10000, 'frame_minutes': minutes}, 'received_range': {'start': raw[0]['day'], 'end': raw[-1]['day']}, 'provider_timestamp': stamp, 'coverage_audit': 'PARTIAL_RANGE_UNPROMOTED', 'cross_source_validation': 'PENDING_INDEPENDENT_OVERLAP_AUDIT', 'source_kind': 'provider_raw', 'provenance_schema': 'V536_SOURCE_ISOLATED_BAR_V1'})
        frame = f'm{minutes}'
        path = OUT / frame / f'{code}_{market}_{frame}.json.gz'
        atomic_gzip(path, bars)
        result['frames'][frame] = {'bars': len(bars), 'received_start': raw[0]['day'], 'received_end': raw[-1]['day'], 'path': str(path), 'eligible_for_full_market_research': False}
    stamp = datetime.now().strftime('%Y%m%d_%H%M%S')
    for path in (AUDIT / f'v536_sina_source_probe_{stamp}.json', AUDIT / 'v536_sina_source_probe_latest.json'):
        temp = path.with_suffix('.tmp'); temp.write_text(json.dumps(result, ensure_ascii=False, indent=2)); temp.replace(path)
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
