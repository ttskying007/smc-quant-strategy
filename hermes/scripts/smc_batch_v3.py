#!/usr/bin/env python3
"""Full A-stock Batch Backtest — V3.2 + V2 Combo Comparison"""
import sys, os, time, json, random
from collections import Counter
from pathlib import Path

sys.path.insert(0, '/root/.hermes/skills/trading/smc-engine/scripts')
sys.path.insert(0, '/root/.hermes/scripts')

for k in ['http_proxy','https_proxy','HTTP_PROXY','HTTPS_PROXY']:
    os.environ.pop(k, None)

from smc_backtest_v2 import fetch_stock_list, fetch_klines, normalize_klines, backtest_single, compute_sharpe
from smc_engine_v3_2 import backtest_v3_2

OUT = Path('/root/.hermes/smc_opt_v3/batch_results')
OUT.mkdir(parents=True, exist_ok=True)

# ─────────── Configuration ───────────
MAX_STOCKS = 200          # 测试量级
BATCH_NAME = f"v32_batch_{MAX_STOCKS}"
BATCH_FILE = OUT / f"{BATCH_NAME}.json"
VERBOSE = False

# ─────────── Run ───────────
print(f"\n{'='*70}")
print(f"  Full A-Stock Batch: V3.2 vs V2 Combo")
print(f"  Stocks: {MAX_STOCKS} | Strategy: BOTH | SL1.5 TP2.0")
print(f"{'='*70}")

print("Loading stock list...")
all_stocks = fetch_stock_list()
stocks = [(s['symbol'], s.get('name', '')) for s in all_stocks 
          if not s.get('symbol', '').startswith('*ST')]
random.seed(42)
random.shuffle(stocks)
stocks = stocks[:MAX_STOCKS]
print(f"  {len(stocks)} stocks loaded")

results = []
start_time = time.time()
total_v2_trades = 0
total_v3_trades = 0

for idx, (code, name) in enumerate(stocks):
    try:
        t0 = time.time()
        raw = fetch_klines(code, 'daily', 500)
        bars = normalize_klines(raw)
        t1 = time.time()
        
        if len(bars) < 100:
            print(f"  [{idx+1}/{MAX_STOCKS}] {code} {name[:6]:6s} ⏭ short data ({len(bars)})")
            continue
        
        # V2 Combo
        v2r = backtest_single(code, bars, 'combo', 1.5, 2.0, False)
        v2t = v2r.get('trades', [])
        
        # V3.2
        v3t = backtest_v3_2(bars)
        
        v2n = len(v2t)
        v3n = len(v3t)
        v2w = len([t for t in v2t if t['pnl']>0])
        v3w = len([t for t in v3t if t['pnl']>0])
        
        v2_wr = v2w/v2n*100 if v2n else 0
        v3_wr = v3w/v3n*100 if v3n else 0
        
        v2_ret = sum(t['pnl'] for t in v2t)*100 if v2t else 0
        v3_ret = sum(t['pnl'] for t in v3t)*100 if v3t else 0
        
        v2_sr = compute_sharpe([t['pnl'] for t in v2t], 252) if v2t else 0
        v3_sr = compute_sharpe([t['pnl'] for t in v3t], 252) if v3t else 0
        
        total_v2_trades += v2n
        total_v3_trades += v3n
        
        delta = v3_wr - v2_wr
        marker = ''
        if delta > 20: marker = ' 🔥🔥'
        elif delta > 10: marker = ' 🔥'
        elif delta > 0: marker = ' ✓'
        elif delta < -10: marker = ' 💀'
        
        elapsed = time.time() - t0
        v3_sig_count = ', '.join(sorted(set(str(s) for t in v3t for s in t.get('signals',[])))) if v3t else '-'
        
        if v3n > 0 or v2_wr > 40 or idx % 20 == 0:
            print(f"  [{idx+1}/{MAX_STOCKS}] {code} {name[:6]:6s} | V2={v2n:>3}t WR={v2_wr:>4.1f}% | V3={v3n:>3}t WR={v3_wr:>4.1f}% Δ={delta:+.0f}%{marker} | SR={v3_sr:.1f} | {elapsed:.0f}s")
        
        results.append({
            'code': code, 'name': name,
            'v2': {'trades': v2n, 'wins': v2w, 'wr': round(v2_wr,1), 'sr': round(v2_sr,2), 'ret': round(v2_ret,2)},
            'v3': {'trades': v3n, 'wins': v3w, 'wr': round(v3_wr,1), 'sr': round(v3_sr,2), 'ret': round(v3_ret,2)},
            'delta_wr': round(delta, 1),
        })
        
    except Exception as e:
        print(f"  [{idx+1}/{MAX_STOCKS}] {code} {name[:6]:6s} ❌ {str(e)[:40]}")
        continue

# Summary
total_time = time.time() - start_time
print(f"\n{'='*70}")

v2_all_wins = sum(r['v2']['wins'] for r in results)
v2_all_trades = sum(r['v2']['trades'] for r in results)
v3_all_wins = sum(r['v3']['wins'] for r in results)
v3_all_trades = sum(r['v3']['trades'] for r in results)

v2_all_wr = v2_all_wins/v2_all_trades*100 if v2_all_trades else 0
v3_all_wr = v3_all_wins/v3_all_trades*100 if v3_all_trades else 0

v2_all_sr = sum(r['v2']['sr'] for r in results) / len(results) if results else 0
v3_all_sr = sum(r['v3']['sr'] for r in results) / len(results) if results else 0

# Distribution
v3_wr_list = [r['v3']['wr'] for r in results if r['v3']['trades'] > 0]
v3_sr_list = [r['v3']['sr'] for r in results if r['v3']['trades'] > 0]

wr_buckets = Counter()
for wr in v3_wr_list:
    b = (wr // 10) * 10
    wr_buckets[f'{b:.0f}-{b+10:.0f}%'] = wr_buckets.get(f'{b:.0f}-{b+10:.0f}%', 0) + 1

sr_positive = len([s for s in v3_sr_list if s > 0])
sr_high = len([s for s in v3_sr_list if s > 1.0])

stocks_active = len(v3_wr_list)
stocks_zero = len([r for r in results if r['v3']['trades'] == 0])

print(f"  A-STOCK BATCH: {len(results)} stocks ({stocks_active} active, {stocks_zero} zero) [{total_time/60:.1f}min]")
print()
print(f"{'─'*70}")
print(f"  AGGREGATE")
print(f"{'─'*70}")
print(f"  V2 Combo:   {v2_all_trades:>6,}t | WR={v2_all_wr:>5.1f}% | AvgSR={v2_all_sr:>5.2f}")
print(f"  V3.2 Reso:  {v3_all_trades:>6,}t | WR={v3_all_wr:>5.1f}% | AvgSR={v3_all_sr:>5.2f}")
print(f"  ΔWR:        {v3_all_wr-v2_all_wr:>+.1f}%")
print(f"  Signal ratio: {v3_all_trades/v2_all_trades*100:.1f}% of V2 total")
print()
print(f"{'─'*70}")
print(f"  DISTRIBUTION (V3.2, {stocks_active} active stocks)")
print(f"{'─'*70}")
print(f"  WR distribution:")
for bucket, count in sorted(wr_buckets.items()):
    bar = '█' * count
    pct = count / stocks_active * 100
    print(f"    {bucket:>8s}: {count:>3d} stocks {bar} {pct:.0f}%")
print(f"  SR > 0:     {sr_positive}/{stocks_active} = {sr_positive/stocks_active*100:.0f}%")
print(f"  SR > 1.0:   {sr_high}/{stocks_active} = {sr_high/stocks_active*100:.0f}%")
print()
print(f"{'─'*70}")
print(f"  TOP 10 by WR")
print(f"{'─'*70}")
sorted_by_wr = sorted([r for r in results if r['v3']['trades']>0], key=lambda r: r['v3']['wr'], reverse=True)
print(f"  {'Code':>10s} {'Name':8s} {'V2-WR':>6s} {'V3-WR':>6s} {'V3-n':>5s} {'V3-SR':>6s}")
for r in sorted_by_wr[:10]:
    print(f"  {r['code']:>10s} {r['name'][:6]:8s} {r['v2']['wr']:>5.1f}% {r['v3']['wr']:>5.1f}% {r['v3']['trades']:>4d} {r['v3']['sr']:>5.1f}")

print()
print(f"{'─'*70}")
print(f"  BOTTOM 5 by WR")
print(f"{'─'*70}")
for r in sorted_by_wr[-5:]:
    print(f"  {r['code']:>10s} {r['name'][:6]:8s} {r['v2']['wr']:>5.1f}% {r['v3']['wr']:>5.1f}% {r['v3']['trades']:>4d} {r['v3']['sr']:>5.1f}")

print(f"\n{'='*70}")
if v3_all_wr >= 80:
    print(f"  🏆 TARGET WR > 80%: ACHIEVED!")
elif v3_all_wr >= 65:
    print(f"  ✅ V3.2 WR={v3_all_wr:.1f}% — Significantly better than V2 ({v2_all_wr:.1f}%)")
    print(f"  Need {80-v3_all_wr:.0f}pp more. Next: lower score_threshold to increase signal count")
else:
    print(f"  ⚠ V3.2 WR={v3_all_wr:.1f}% — needs improvement")
print(f"{'='*70}")

# Save
with open(BATCH_FILE, 'w') as f:
    json.dump({
        'batch_name': BATCH_NAME,
        'n_stocks': len(results),
        'n_active': stocks_active,
        'v2_wr': round(v2_all_wr, 1), 'v3_wr': round(v3_all_wr, 1),
        'v2_avg_sr': round(v2_all_sr, 2), 'v3_avg_sr': round(v3_all_sr, 2),
        'results': results,
    }, f, ensure_ascii=False, indent=2)
print(f"\nSaved: {BATCH_FILE}")