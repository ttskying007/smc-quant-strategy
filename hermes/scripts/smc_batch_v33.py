#!/usr/bin/env python3
"""V3.3 Final Batch — 200 stocks with mixed strategy"""
import sys, os, time, json, random
from collections import Counter
from pathlib import Path
sys.path.insert(0, '/root/.hermes/skills/trading/smc-engine/scripts')
sys.path.insert(0, '/root/.hermes/scripts')
for k in ['http_proxy','https_proxy','HTTP_PROXY','HTTPS_PROXY']:
    os.environ.pop(k, None)
from smc_backtest_v2 import fetch_stock_list, fetch_klines, normalize_klines, backtest_single, compute_sharpe
from smc_engine_v3_3 import backtest_v3_3

OUT = Path('/root/.hermes/smc_opt_v3/batch_results')
OUT.mkdir(parents=True, exist_ok=True)

MAX_STOCKS = 200
print(f"\n{'='*70}")
print(f"  V3.3 Full Batch — {MAX_STOCKS} stocks")
print(f"  Modes: total + strict")
print(f"{'='*70}")

print("Loading stocks...")
all_s = fetch_stock_list()
stocks = [(s['symbol'],s.get('name','')) for s in all_s if not s.get('symbol','').startswith('*ST')]
random.seed(42); random.shuffle(stocks); stocks = stocks[:MAX_STOCKS]
print(f"  {len(stocks)} stocks")

start = time.time()
results = []

for idx, (code, name) in enumerate(stocks):
    try:
        bars = normalize_klines(fetch_klines(code, 'daily', 500))
        if len(bars) < 100:
            continue
        
        v2r = backtest_single(code, bars, 'combo', 1.5, 2.0, False)
        v2t = v2r.get('trades',[])
        
        v33t = backtest_v3_3(bars, 'total')
        v33s = backtest_v3_3(bars, 'strict')
        
        def calc_wr(t):
            n = len(t); w = len([x for x in t if x['pnl']>0])
            return w/n*100 if n else 0, n, compute_sharpe([x['pnl'] for x in t],252) if t else 0
        
        v2wr, v2n, v2sr = calc_wr(v2t)
        v33wr, v33n, v33sr = calc_wr(v33t)
        v33_swr, v33_sn, v33_ssr = calc_wr(v33s)
        
        results.append({
            'code':code,'name':name,
            'v2':{'n':v2n,'wr':round(v2wr,1),'sr':round(v2sr,2)},
            'v33_total':{'n':v33n,'wr':round(v33wr,1),'sr':round(v33sr,2)},
            'v33_strict':{'n':v33_sn,'wr':round(v33_swr,1),'sr':round(v33_ssr,2)},
        })
        
        if idx % 20 == 0:
            print(f"  [{idx+1}/{MAX_STOCKS}] {code} {name[:6]:6s}")
    except Exception as e:
        print(f"  [{idx+1}/{MAX_STOCKS}] {code}: {str(e)[:30]}")

total = time.time()-start

# Aggregate
v2_t = sum(r['v2']['n'] for r in results)
v2_w = sum(r['v2']['n']*r['v2']['wr']/100 for r in results)
v33_t = sum(r['v33_total']['n'] for r in results)
v33_w = sum(r['v33_total']['n']*r['v33_total']['wr']/100 for r in results)
v33s_t = sum(r['v33_strict']['n'] for r in results)
v33s_w = sum(r['v33_strict']['n']*r['v33_strict']['wr']/100 for r in results)

v2_wr_all = v2_w/v2_t*100 if v2_t else 0
v33_wr_all = v33_w/v33_t*100 if v33_t else 0
v33s_wr_all = v33s_w/v33s_t*100 if v33s_t else 0

# Active stocks
v33_active = len([r for r in results if r['v33_total']['n']>0])
v33s_active = len([r for r in results if r['v33_strict']['n']>0])
v2_active = len([r for r in results if r['v2']['n']>0])

# WR distribution
wr_buckets = Counter()
for r in results:
    if r['v33_total']['n']>0:
        b = (r['v33_total']['wr']//10)*10
        wr_buckets[f'{b:.0f}-{b+10:.0f}%'] += 1

print(f"\n{'='*70}")
print(f"  FINAL — {MAX_STOCKS} stocks [{total/60:.1f}min]")
print(f"{'='*70}")
print(f"  V2:       {v2_t:>5,}t WR={v2_wr_all:>5.1f}% | active={v2_active}")
print(f"  V3.3 tot: {v33_t:>5,}t WR={v33_wr_all:>5.1f}% | active={v33_active} | mul={v33_t/max(1,v2_t)*100:.0f}%")
print(f"  V3.3 str: {v33s_t:>5,}t WR={v33s_wr_all:>5.1f}% | active={v33s_active}")
print()
print(f"  WR Distribution (V3.3 total):")
for b, cnt in sorted(wr_buckets.items()):
    bar = '█' * cnt
    print(f"    {b:>8s}: {cnt:>3d} {bar} {cnt/v33_active*100:.0f}%")
print()
if v33_wr_all >= 65:
    print(f"  ✅ V3.3 WR={v33_wr_all:.1f}% >= 65% threshold")
elif v33_wr_all >= 60:
    print(f"  ✅ V3.3 WR={v33_wr_all:.1f}% — Good! Need {80-v33_wr_all:.0f}pp more")
else:
    print(f"  ⚠ V3.3 WR={v33_wr_all:.1f}% — room for improvement")
print(f"  Signal: {v33_t} vs {v2_t} = {v33_t/max(1,v2_t)*100:.1f}% of V2 volume")
print(f"{'='*70}")

with open(OUT/'v33_batch_200.json','w') as f:
    json.dump({'stocks':len(results),'v33_wr':v33_wr_all,'v33_n':v33_t,
               'v33s_wr':v33s_wr_all,'v33s_n':v33s_t,
               'v2_wr':v2_wr_all,'v2_n':v2_t,'results':results},
              f, ensure_ascii=False, indent=2)
print(f"Saved: {OUT/'v33_batch_200.json'}")