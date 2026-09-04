#!/usr/bin/env python3
"""Mass download 60min data for all 4,800 A-share stocks via Tencent API.
Uses ThreadPoolExecutor for parallel downloading (10 workers).
"""
import json, urllib.request, time, os, sys
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor, as_completed

CACHE_DIR = Path('/root/.hermes/kline_cache_60min')
CACHE_DIR.mkdir(exist_ok=True)

def symbol_to_tencent(symbol: str) -> str:
    code, exchange = symbol.replace('.', ' ').split()
    exchange = exchange.lower()
    if exchange == 'sz': return 'sz' + code
    elif exchange == 'sh': return 'sh' + code
    elif exchange == 'bj': return 'sm' + code
    return 'sz' + code

def fetch_60min_kline(symbol: str) -> list:
    fname = f"{symbol.replace('.','_')}_60min_200.json"
    fpath = CACHE_DIR / fname
    if fpath.exists():
        return [symbol, len(json.loads(fpath.read_text()))]
    
    tc = symbol_to_tencent(symbol)
    url = f'https://ifzq.gtimg.cn/appstock/app/kline/mkline?param={tc},m60,,200'
    
    for attempt in range(3):
        try:
            req = urllib.request.Request(url, headers={
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
                'Referer': 'https://gu.qq.com/',
            })
            resp = urllib.request.urlopen(req, timeout=15)
            raw = resp.read().decode('utf-8', errors='replace')
            if raw.startswith('callback'):
                raw = raw[raw.find('(')+1:raw.rfind(')')]
            data = json.loads(raw)
            sym_data = data.get('data', {})
            sym_key = None
            for k in sym_data:
                if tc in k: sym_key = k; break
            if not sym_key:
                sym_key = list(sym_data.keys())[0] if sym_data else None
            if not sym_key:
                return [symbol, 0, 'no_key']
            bars_raw = sym_data[sym_key].get('m60', [])
            if not bars_raw:
                return [symbol, 0, 'no_data']
            
            bars = []
            for b in bars_raw:
                if isinstance(b, str): continue
                try:
                    dt = str(int(b[0]))
                    year, mon, day = dt[:4], dt[4:6], dt[6:8]
                    hour, minute = dt[8:10], dt[10:12]
                    date_str = f'{year}-{mon}-{day} {hour}:{minute}:00'
                    o = float(b[1]); c = float(b[2])
                    h = float(b[3]); l_ = float(b[4])
                    v = int(float(b[5])) if b[5] else 0
                    bars.append({'date': date_str, 'o': o, 'h': h, 'l': l_, 'c': c, 'v': v, 't': int(dt)})
                except: continue
            
            bars.sort(key=lambda x: x['t'])
            fpath.write_text(json.dumps(bars))
            return [symbol, len(bars), 'ok']
        except Exception as e:
            if attempt < 2: time.sleep(1)
            else: return [symbol, 0, str(e)[:30]]

# Get stock list from daily cache
DAILY_DIR = Path('/root/.hermes/kline_cache')
symbols = sorted([f.stem.replace('_daily_300', '').replace('_', '.')
                  for f in DAILY_DIR.glob('*_daily_300.json')])
print(f"Total stocks to download: {len(symbols)}")

# Check already cached
cached = len(list(CACHE_DIR.glob('*_60min_200.json')))
print(f"Already cached: {cached}")

# Parallel download
N_WORKERS = 10
done = 0
ok = 0
fail = 0
total = len(symbols)

with ThreadPoolExecutor(max_workers=N_WORKERS) as ex:
    futures = {ex.submit(fetch_60min_kline, sym): sym for sym in symbols}
    for f in as_completed(futures):
        result = f.result()
        sym = result[0]
        if len(result) >= 3 and result[2] == 'ok':
            ok += 1
        else:
            fail += 1
        done += 1
        if done % 100 == 0 or done == total:
            print(f"  [{done}/{total}] OK={ok} FAIL={fail}")

cached_now = len(list(CACHE_DIR.glob('*_60min_200.json')))
print(f"\nDone: {done} | OK: {ok} | Fail: {fail} | Cached: {cached_now} / {total}")
