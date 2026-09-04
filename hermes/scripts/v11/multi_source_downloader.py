#!/usr/bin/env python3
"""
多源并行周线/60min数据下载器
================================
Sources:
  1. Hubble API (primary, weekly + daily)
  2. 东方财富 (fallback weekly)
  3. 腾讯ifzq (60min)
  4. 东方财富 (daily fallback)

下载: 缺失的3711周线 + 285个60min
并行: 15 workers
"""
import json, time, sys
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor, as_completed
import urllib.request
import urllib.error

KLINE = Path('/root/.hermes/kline_cache')
HUBBLE_BASE = 'http://43.167.234.49:3101'
HUBBLE_KEY = '123456'

# ====== 符号转换 ======
def sym_to_eastmoney(symbol):
    """000001.SZ -> 0.000001, 600519.SH -> 1.600519"""
    code, mkt = symbol.split('.')
    prefix = '0' if mkt == 'SZ' else '1'
    return f'{prefix}.{code}'

def sym_to_tencent(symbol):
    """000001.SZ -> sz000001, 600519.SH -> sh600519"""
    code, mkt = symbol.split('.')
    prefix = 'sz' if mkt == 'SZ' else 'sh'
    return f'{prefix}{code}'

# ====== Source 1: Hubble weekly ======
def fetch_hubble_weekly(symbol):
    try:
        url = f'{HUBBLE_BASE}/api/v2/cnstock/stocks?symbol={symbol}&interval=weekly&limit=200'
        req = urllib.request.Request(url)
        req.add_header('X-API-Key', HUBBLE_KEY)
        req.add_header('Content-Type', 'application/json')
        resp = urllib.request.urlopen(req, timeout=15)
        data = json.loads(resp.read())
        bars = data.get('data', [])
        if bars:
            result = [{'t': b.get('time',''), 'o': b['open'], 'h': b['high'],
                        'l': b['low'], 'c': b['close'], 'v': b.get('volume',0)}
                      for b in bars]
            result.sort(key=lambda x: x['t'])
            return result
    except Exception as e:
        pass
    return None

# ====== Source 2: 东方财富 weekly ======
def fetch_eastmoney_weekly(symbol):
    try:
        secid = sym_to_eastmoney(symbol)
        url = (f'https://push2his.eastmoney.com/api/qt/stock/kline/get?'
               f'secid={secid}&klt=102&fqt=1&lmt=200&'
               f'fields1=f1,f2&fields2=f51,f52,f53,f54,f55,f56&end=20500101')
        resp = urllib.request.urlopen(url, timeout=15)
        data = json.loads(resp.read())
        klines = data.get('data', {}).get('klines', [])
        if klines:
            result = []
            for k in klines:
                parts = k.split(',')
                # date,open,close,high,low,volume — Eastmoney format
                if len(parts) >= 6:
                    result.append({
                        't': parts[0].replace('-', ''),
                        'o': float(parts[1]),
                        'c': float(parts[2]),
                        'h': float(parts[3]),
                        'l': float(parts[4]),
                        'v': float(parts[5]) * 100  # 手→股
                    })
            result.sort(key=lambda x: x['t'])
            return result
    except Exception:
        pass
    return None

# ====== Source 3: 腾讯 60min ======
def fetch_tencent_60min(symbol):
    try:
        tcode = sym_to_tencent(symbol)
        url = (f'http://ifzq.gtimg.cn/appstock/app/kline/mkline?'
               f'param={tcode},m60,,200')
        resp = urllib.request.urlopen(url, timeout=15)
        data = json.loads(resp.read())
        day_data = data.get('data', {}).get(tcode, {}).get('m60', [])
        if day_data:
            result = [{'t': d[0], 'o': float(d[1]), 'c': float(d[2]),
                        'h': float(d[3]), 'l': float(d[4]), 'v': float(d[5])}
                      for d in day_data]
            return result
    except Exception:
        pass
    return None

# ====== 下载单个周线 (多源fallback) ======
def download_weekly(symbol):
    # Skip if already exists and valid
    path = KLINE / f'{symbol}_weekly_200.json'
    if path.exists():
        try:
            existing = json.loads(path.read_bytes())
            if isinstance(existing, list) and len(existing) >= 10:
                return (symbol, 'cached', len(existing))
        except:
            pass

    # Try Hubble first
    bars = fetch_hubble_weekly(symbol)
    if bars and len(bars) >= 10:
        path.write_text(json.dumps(bars))
        return (symbol, 'hubble', len(bars))
    
    # Fallback to Eastmoney
    bars = fetch_eastmoney_weekly(symbol)
    if bars and len(bars) >= 10:
        path.write_text(json.dumps(bars))
        return (symbol, 'eastmoney', len(bars))
    
    return (symbol, 'failed', 0)

# ====== 下载单个60min ======
def download_60min(symbol):
    path = KLINE / f'{symbol}_60min_500.json'
    if path.exists():
        try:
            existing = json.loads(path.read_bytes())
            if isinstance(existing, list) and len(existing) >= 20:
                return (symbol, 'cached', len(existing))
        except:
            pass

    bars = fetch_tencent_60min(symbol)
    if bars and len(bars) >= 20:
        path.write_text(json.dumps(bars))
        return (symbol, 'tencent', len(bars))
    
    return (symbol, 'failed', 0)

# ====== MAIN ======
def main():
    # Gather all symbols
    daily_files = sorted(KLINE.glob('*_daily_300.json'))
    all_symbols = [f.stem.replace('_daily_300', '') for f in daily_files]
    
    # Find missing
    existing_weekly = {f.stem.replace('_weekly_200', '') for f in KLINE.glob('*_weekly_200.json')}
    existing_60min = {f.stem.replace('_60min_500', '') for f in KLINE.glob('*_60min_500.json')}
    
    missing_weekly = [s for s in all_symbols if s not in existing_weekly]
    missing_60min = [s for s in all_symbols if s not in existing_60min]
    
    print(f"Total daily: {len(all_symbols)}")
    print(f"Weekly: have {len(existing_weekly)}, missing {len(missing_weekly)}")
    print(f"60min:  have {len(existing_60min)}, missing {len(missing_60min)}")
    
    # ====== Phase 1: Download missing weekly ======
    if missing_weekly:
        print(f"\n{'='*60}")
        print(f"Phase 1: Downloading {len(missing_weekly)} weekly files (15 workers)...")
        print(f"{'='*60}")
        
        stats = {'hubble': 0, 'eastmoney': 0, 'failed': 0}
        t0 = time.time()
        
        with ThreadPoolExecutor(max_workers=15) as ex:
            futures = {ex.submit(download_weekly, s): s for s in missing_weekly}
            done = 0
            for f in as_completed(futures):
                sym, source, n_bars = f.result()
                stats[source] = stats.get(source, 0) + 1
                done += 1
                if done % 500 == 0 or source == 'failed':
                    elapsed = time.time() - t0
                    print(f"  [{done}/{len(missing_weekly)}] {elapsed:.0f}s "
                          f"hubble={stats.get('hubble',0)} eastmoney={stats.get('eastmoney',0)} "
                          f"failed={stats.get('failed',0)}")
        
        elapsed = time.time() - t0
        print(f"\n  Weekly done: {elapsed:.0f}s — {stats}")
    
    # ====== Phase 2: Download missing 60min ======
    if missing_60min:
        print(f"\n{'='*60}")
        print(f"Phase 2: Downloading {len(missing_60min)} 60min files (15 workers)...")
        print(f"{'='*60}")
        
        stats = {'tencent': 0, 'cached': 0, 'failed': 0}
        t0 = time.time()
        
        with ThreadPoolExecutor(max_workers=15) as ex:
            futures = {ex.submit(download_60min, s): s for s in missing_60min}
            done = 0
            for f in as_completed(futures):
                sym, source, n_bars = f.result()
                stats[source] = stats.get(source, 0) + 1
                done += 1
                if done % 100 == 0 or source == 'failed':
                    elapsed = time.time() - t0
                    print(f"  [{done}/{len(missing_60min)}] {elapsed:.0f}s "
                          f"tencent={stats.get('tencent',0)} failed={stats.get('failed',0)}")
        
        elapsed = time.time() - t0
        print(f"\n  60min done: {elapsed:.0f}s — {stats}")
    
    # ====== Final tally ======
    final_weekly = len(list(KLINE.glob('*_weekly_200.json')))
    final_60min = len(list(KLINE.glob('*_60min_500.json')))
    
    print(f"\n{'='*60}")
    print(f"FINAL COVERAGE:")
    print(f"  Daily:  {len(all_symbols)}")
    print(f"  Weekly: {final_weekly} ({final_weekly/len(all_symbols)*100:.0f}%)")
    print(f"  60min:  {final_60min} ({final_60min/len(all_symbols)*100:.0f}%)")
    print(f"{'='*60}")

if __name__ == '__main__':
    main()
