#!/usr/bin/env python3
"""多源并行周线下载器 v2 — subprocess+curl (解决SSL/redirect问题)"""
import json, time, subprocess, sys
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor, as_completed

KLINE = Path('/root/.hermes/kline_cache')
HUBBLE_URL = 'http://43.167.234.49:3101/api/v2/cnstock/stocks'
KEY = '123456'

def sym_to_secid(symbol):
    """600519.SH -> 1.600519, 000001.SZ -> 0.000001"""
    code, mkt = symbol.split('.')
    prefix = '0' if mkt == 'SZ' else '1'
    return f'{prefix}.{code}'

def download_weekly(symbol):
    name = symbol.replace('.', '_')
    out = KLINE / f'{name}_weekly_200.json'
    
    # Skip if already exists with valid data
    if out.exists():
        try:
            existing = json.loads(out.read_bytes())
            if isinstance(existing, list) and len(existing) >= 10:
                return (symbol, 'cached', len(existing))
        except:
            pass
    
    # === Source 1: Hubble ===
    try:
        cmd = [
            'curl', '-sS', '--max-time', '15',
            '-H', f'X-API-Key: {KEY}',
            '-H', 'Content-Type: application/json',
            f'{HUBBLE_URL}?symbol={symbol}&interval=weekly&limit=200'
        ]
        resp = subprocess.run(cmd, capture_output=True, text=True, timeout=20)
        if resp.returncode == 0 and resp.stdout.strip():
            data = json.loads(resp.stdout)
            bars = data.get('data', [])
            if bars and len(bars) >= 10:
                result = [{'t': b.get('time',''), 'o': b['open'], 'h': b['high'],
                           'l': b['low'], 'c': b['close'], 'v': b.get('volume',0)}
                          for b in bars]
                result.sort(key=lambda x: x['t'])
                out.write_text(json.dumps(result))
                return (symbol, 'hubble', len(result))
    except Exception:
        pass
    
    # === Source 2: 东方财富 ===
    try:
        secid = sym_to_secid(symbol)
        em_url = (f'https://push2his.eastmoney.com/api/qt/stock/kline/get?'
                  f'secid={secid}&klt=102&fqt=1&lmt=200&'
                  f'fields1=f1,f2&fields2=f51,f52,f53,f54,f55,f56&end=20500101')
        cmd = ['curl', '-sS', '--max-time', '15', em_url]
        resp = subprocess.run(cmd, capture_output=True, text=True, timeout=20)
        if resp.returncode == 0 and resp.stdout.strip():
            data = json.loads(resp.stdout)
            klines = data.get('data', {}).get('klines', [])
            if klines and len(klines) >= 10:
                result = []
                for k in klines:
                    parts = k.split(',')
                    if len(parts) >= 6:
                        result.append({
                            't': parts[0].replace('-', ''),
                            'o': float(parts[1]),
                            'c': float(parts[2]),
                            'h': float(parts[3]),
                            'l': float(parts[4]),
                            'v': float(parts[5]) * 100
                        })
                result.sort(key=lambda x: x['t'])
                out.write_text(json.dumps(result))
                return (symbol, 'eastmoney', len(result))
    except Exception:
        pass
    
    return (symbol, 'failed', 0)


def main():
    # Find all daily symbols
    daily_files = sorted(KLINE.glob('*_daily_300.json'))
    all_symbols = set()
    for f in daily_files:
        name = f.stem.replace('_daily_300', '')
        # name = 000001_SZ
        parts = name.rsplit('_', 1)
        if len(parts) == 2:
            symbol = f'{parts[0]}.{parts[1]}'
            all_symbols.add(symbol)
    
    existing = {f.stem.replace('_weekly_200','').replace('_','.',1) 
                for f in KLINE.glob('*_weekly_200.json')
                if f.stat().st_size > 200}
    
    missing = [s for s in all_symbols if s not in existing]
    
    print(f"Daily: {len(all_symbols)} | Weekly have: {len(existing)} | Missing: {len(missing)}")
    
    if not missing:
        print("All weekly data complete!")
        return
    
    print(f"\nDownloading {len(missing)} weekly with 20 workers...")
    
    stats = {'hubble': 0, 'eastmoney': 0, 'cached': 0, 'failed': 0}
    t0 = time.time()
    
    with ThreadPoolExecutor(max_workers=20) as ex:
        futures = {ex.submit(download_weekly, s): s for s in missing}
        done = 0
        for f in as_completed(futures):
            sym, source, n = f.result()
            stats[source] = stats.get(source, 0) + 1
            done += 1
            if done % 200 == 0 or source == 'failed':
                elapsed = time.time() - t0
                rate = done / max(elapsed, 0.1)
                print(f"  [{done}/{len(missing)}] {elapsed:.0f}s ({rate:.0f}/s) "
                      f"hubble={stats['hubble']} em={stats['eastmoney']} fail={stats['failed']}")
    
    elapsed = time.time() - t0
    final = len(list(KLINE.glob('*_weekly_200.json')))
    print(f"\nDone: {elapsed:.0f}s — {stats}")
    print(f"Weekly total: {final} ({final/len(all_symbols)*100:.0f}%)")

if __name__ == '__main__':
    main()
