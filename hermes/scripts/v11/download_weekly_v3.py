#!/usr/bin/env python3
"""周线补充下载 v3 — Hubble + 腾讯并行 (修复: -L跟随重定向, 降低并发)"""
import json, time, subprocess
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor, as_completed

KLINE = Path('/root/.hermes/kline_cache')

def download_weekly(symbol):
    name = symbol.replace('.', '_')
    out = KLINE / f'{name}_weekly_200.json'
    if out.exists() and out.stat().st_size > 200:
        try:
            d = json.loads(out.read_bytes())
            if isinstance(d, list) and len(d) >= 10:
                return (symbol, 'cached', len(d))
        except: pass

    code, mkt = symbol.split('.')
    tcode = f'{"sz" if mkt=="SZ" else "sh"}{code}'

    # === Source 1: Hubble ===
    try:
        r = subprocess.run([
            'curl', '-sS', '--max-time', '10',
            '-H', 'X-API-Key: 123456',
            f'http://43.167.234.49:3101/api/v2/cnstock/stocks?symbol={symbol}&interval=weekly&limit=200'
        ], capture_output=True, text=True, timeout=15)
        if r.returncode == 0:
            d = json.loads(r.stdout)
            bars = d.get('data', [])
            if len(bars) >= 10:
                result = [{'t': b.get('time',''), 'o': b['open'], 'h': b['high'],
                           'l': b['low'], 'c': b['close'], 'v': b.get('volume',0)}
                          for b in bars]
                result.sort(key=lambda x: x['t'])
                out.write_text(json.dumps(result))
                return (symbol, 'hubble', len(result))
    except: pass

    # === Source 2: 腾讯 (follow redirect) ===
    try:
        r = subprocess.run([
            'curl', '-sSL', '--max-time', '10',
            f'http://web.ifzq.gtimg.cn/appstock/app/fqkline/get?param={tcode},week,,,200,qfq'
        ], capture_output=True, text=True, timeout=15)
        if r.returncode == 0:
            d = json.loads(r.stdout)
            data = d.get('data', {}).get(tcode, {})
            bars = data.get('qfqweek', data.get('week', []))
            if bars and len(bars) >= 10:
                result = []
                for b in bars:
                    # [date, open, close, high, low, volume(千股)]
                    result.append({
                        't': b[0].replace('-', ''),
                        'o': float(b[1]),
                        'c': float(b[2]),
                        'h': float(b[3]),
                        'l': float(b[4]),
                        'v': float(b[5]) * 1000  # 千股→股
                    })
                result.sort(key=lambda x: x['t'])
                out.write_text(json.dumps(result))
                return (symbol, 'tencent', len(result))
    except: pass

    return (symbol, 'failed', 0)


def main():
    daily = sorted(KLINE.glob('*_daily_300.json'))
    all_syms = set()
    for f in daily:
        n = f.stem.replace('_daily_300', '')
        p = n.rsplit('_', 1)
        if len(p) == 2: all_syms.add(f'{p[0]}.{p[1]}')

    # Existing weekly with valid data
    existing = set()
    for f in KLINE.glob('*_weekly_200.json'):
        if f.stat().st_size > 200:
            try:
                d = json.loads(f.read_bytes())
                if isinstance(d, list) and len(d) >= 10:
                    existing.add(f.stem.replace('_weekly_200','').replace('_','.',1))
            except: pass

    missing = [s for s in all_syms if s not in existing]
    print(f"Total daily: {len(all_syms)}  Weekly have: {len(existing)}  Missing: {len(missing)}")

    if not missing:
        print("All complete!")
        return

    t0 = time.time()
    stats = {'hubble': 0, 'tencent': 0, 'cached': 0, 'failed': 0}

    # 8 workers to avoid rate limits
    with ThreadPoolExecutor(max_workers=8) as ex:
        futures = {ex.submit(download_weekly, s): s for s in missing}
        done = 0
        for f in as_completed(futures):
            sym, src, n = f.result()
            stats[src] = stats.get(src, 0) + 1
            done += 1
            if done % 200 == 0:
                e = time.time() - t0
                print(f"  [{done}/{len(missing)}] {e:.0f}s hubble={stats['hubble']} "
                      f"tencent={stats['tencent']} fail={stats['failed']}")

    e = time.time() - t0
    final = len([f for f in KLINE.glob('*_weekly_200.json') if f.stat().st_size > 200])
    print(f"\nDone: {e:.0f}s — {stats}")
    print(f"Weekly: {final}/{len(all_syms)} ({final/len(all_syms)*100:.0f}%)")

if __name__ == '__main__':
    main()
