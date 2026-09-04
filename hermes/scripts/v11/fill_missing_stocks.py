#!/usr/bin/env python3
"""补全A股日线数据到5400只 — 东方财富列表 + 腾讯日线下载"""
import json, time, urllib.request
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor, as_completed

CACHE = Path('/root/.hermes/kline_cache')

# ═══ 1. 获取全量A股列表 (东方财富) ═══
print("Fetching A-share stock list from East Money...")
all_stocks = {}
for market, fs in [
    ('SH', 'm:1+t:2,m:1+t:23'),   # 上海主板+科创板
    ('SZ', 'm:0+t:6,m:0+t:80'),   # 深圳主板+创业板
    ('BJ', 'm:0+t:81+s:2048'),     # 北交所
]:
    page = 1
    while True:
        url = f'http://push2.eastmoney.com/api/qt/clist/get?pn={page}&pz=500&po=1&np=1&fltt=2&invt=2&fid=f3&fs={fs}&fields=f12,f14'
        try:
            req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
            resp = urllib.request.urlopen(req, timeout=15)
            data = json.loads(resp.read())
            items = data.get('data', {}).get('diff', [])
            if not items: break
            for it in items:
                code = it.get('f12', '')
                name = it.get('f14', '')
                if code and len(code) == 6:
                    all_stocks[code] = {'market': market, 'name': name, 'code': code}
            if len(items) < 500: break
            page += 1
        except Exception as e:
            print(f'  Error {market}: {e}')
            break

print(f'  Total A-share stocks: {len(all_stocks)}')

# ═══ 2. 对比现有缓存 ═══
existing = set()
for f in CACHE.glob('*_daily_300.json'):
    parts = f.stem.replace('_daily_300', '').split('_')
    if len(parts) == 2:
        existing.add(parts[0])

missing = {code: info for code, info in all_stocks.items() if code not in existing}
print(f'  Existing daily cache: {len(existing)}')
print(f'  Missing: {len(missing)}')

# ═══ 3. 下载缺失日线 (腾讯API) ═══
def download_daily(code, info):
    market = info['market']
    prefix = 'sh' if market == 'SH' else 'sz' if market == 'SZ' else 'bj'
    tc = f'{prefix}{code}'
    sym = f'{code}_{market}'
    fp = CACHE / f'{sym}_daily_300.json'
    
    if fp.exists():
        try:
            data = json.loads(fp.read_bytes())
            if len(data) >= 50: return sym, True, len(data)
        except: pass
    
    url = f'http://ifzq.gtimg.cn/appstock/app/kline/mkline?param={tc},m30,,300'
    try:
        req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
        resp = urllib.request.urlopen(req, timeout=10)
        data = json.loads(resp.read().decode('utf-8'))
        klines = data.get('data', {}).get(tc, {}).get('m30', [])
        if not klines: return sym, False, 0
        
        bars = []
        for k in klines:
            bars.append({'t': k[0], 'o': float(k[1]), 'c': float(k[2]),
                         'h': float(k[3]), 'l': float(k[4])})
        fp.write_text(json.dumps(bars))
        return sym, True, len(bars)
    except: return sym, False, 0

if missing:
    print(f'\n  Downloading {len(missing)} missing stocks...')
    ok = 0; fail = 0
    with ThreadPoolExecutor(max_workers=15) as ex:
        futures = {ex.submit(download_daily, code, info): code for code, info in missing.items()}
        for f in as_completed(futures):
            sym, success, n = f.result()
            if success: ok += 1
            else: fail += 1
            if (ok+fail) % 100 == 0:
                print(f'    Daily: {ok} ok / {fail} fail / {ok+fail} total')
    
    print(f'  Daily done: {ok} ok, {fail} fail')

# ═══ 4. 最终统计 ═══
final = len(list(CACHE.glob('*_daily_300.json')))
print(f'\n  Final daily cache: {final} stocks')
print(f'  Stock list saved to memory')
