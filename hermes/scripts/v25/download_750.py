#!/usr/bin/env python3
"""Download 750-bar daily kline from Tencent fqkline API (~3 years)"""
import json, time, urllib.request
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor, as_completed

KLINE_DIR = Path('/root/.hermes/kline_cache')
BARS = 750
MAX_WORKERS = 30

def fetch_kline(code, market='sz'):
    m = {'sh':'sh','sz':'sz','bj':'bj'}.get(market, 'sz')
    url = f'http://web.ifzq.gtimg.cn/appstock/app/fqkline/get?param={m}{code},day,,,{BARS},qfq'
    try:
        req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
        resp = urllib.request.urlopen(req, timeout=15)
        data = json.loads(resp.read().decode('utf-8'))
        inner = data.get('data', {})
        sym_key = f'{m}{code}'
        stock = inner.get(sym_key, {})
        klines = stock.get('qfqday', stock.get('day', []))
        return klines
    except:
        return None

def save_kline(code, market, klines):
    sym = f"{code}.{market.upper()}"
    fname = sym.replace('.SH','_SH').replace('.SZ','_SZ').replace('.BJ','_BJ')
    path = KLINE_DIR / f'{fname}_daily_{BARS}.json'
    formatted = []
    for k in klines:
        if len(k) < 5: continue
        formatted.append({
            't': k[0].replace('-', ''),
            'o': float(k[1]), 'c': float(k[2]),
            'h': float(k[3]), 'l': float(k[4]),
            'v': float(k[5]) if len(k) > 5 else 0,
        })
    path.write_text(json.dumps(formatted, ensure_ascii=False))
    return len(formatted)

def main():
    codes = []
    for f in sorted(KLINE_DIR.glob('*_daily_300.json')):
        name = f.stem.replace('_daily_300', '')
        if '_SH' in name: codes.append((name.replace('_SH',''), 'sh'))
        elif '_SZ' in name: codes.append((name.replace('_SZ',''), 'sz'))
        elif '_BJ' in name: codes.append((name.replace('_BJ',''), 'bj'))
    
    print(f"Downloading {BARS} bars for {len(codes)} stocks...")
    success = 0; failed = 0
    
    with ThreadPoolExecutor(max_workers=MAX_WORKERS) as ex:
        futures = {ex.submit(fetch_kline, c, m): (c, m) for c, m in codes}
        for future in as_completed(futures):
            code, market = futures[future]
            try:
                klines = future.result()
                if klines and len(klines) > 100:
                    save_kline(code, market, klines)
                    success += 1
                else:
                    failed += 1
            except:
                failed += 1
            if (success + failed) % 500 == 0:
                print(f"  {success}/{len(codes)} OK, {failed} fail")
    
    print(f"\nDone: {success} downloaded, {failed} failed")

if __name__ == '__main__':
    main()
