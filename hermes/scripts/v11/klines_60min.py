#!/usr/bin/env python3
"""Tencent 60min K-line downloader — correct API format"""
import json, time, urllib.request
from pathlib import Path

CACHE_DIR = Path('/root/.hermes/kline_cache_60min')
CACHE_DIR.mkdir(exist_ok=True)

def get_60min_kline(symbol, count=200):
    """Download 60min K-line from Tencent ifzq API.
    Format: [date_str, open, close, high, low, volume, {}, extra]
    """
    code, market = symbol.split('.')
    prefix = 'sh' if market == 'SH' else 'sz'
    tc = f'{prefix}{code}'
    url = f'http://ifzq.gtimg.cn/appstock/app/kline/mkline?param={tc},m60,,{count}'
    
    try:
        req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
        resp = urllib.request.urlopen(req, timeout=10)
        data = json.loads(resp.read().decode('utf-8'))
        klines = data.get('data', {}).get(tc, {}).get('m60', [])
        if not klines:
            return None
        
        bars = []
        for k in klines:
            bars.append({
                't': k[0],
                'o': float(k[1]),
                'c': float(k[2]),
                'h': float(k[3]),
                'l': float(k[4]),
                'v': float(k[5]),
            })
        return bars
    except Exception as e:
        print(f"  {symbol}: {e}")
        return None

def cache_60min(symbol, count=200):
    fname = symbol.replace('.','_') + '_60min_200.json'
    fpath = CACHE_DIR / fname
    if fpath.exists():
        return json.loads(fpath.read_bytes())
    bars = get_60min_kline(symbol, count)
    if bars:
        json.dump(bars, open(fpath,'w'), ensure_ascii=False)
    return bars

if __name__ == '__main__':
    for sym in ['600519.SH', '000001.SZ']:
        bars = get_60min_kline(sym, 5)
        if bars:
            print(f"  {sym}: {len(bars)} bars")
            for b in bars[-2:]:
                print(f"    {b['t']} o={b['o']} c={b['c']}")
        else:
            print(f"  {sym}: FAIL")
