#!/usr/bin/env python3
"""V11.6 全量批次合并+分析"""
import json, sys
from pathlib import Path
from collections import Counter

OUTPUT_DIR = Path('/root/.hermes/smc_opt_v11')
BATCH_PATTERN = 'v116_batch_{}_{}.json'

BATCHES = [
    (0, 500), (500, 1000), (1000, 1500), (1500, 2000), (2000, 2500),
    (2500, 3000), (3000, 3500), (3500, 4000), (4000, 4500), (4500, 4800),
]

all_stocks = []
total_trades = 0
total_wr_weighted = 0

for start, end in BATCHES:
    fname = BATCH_PATTERN.format(start, end)
    fpath = OUTPUT_DIR / fname
    if not fpath.exists():
        print(f"MISS: {fname}")
        continue
    data = json.loads(fpath.read_text())
    stocks = data.get('stocks', [])
    summary = data.get('summary', {})
    all_stocks.extend(stocks)
    total_trades += summary.get('total_trades', 0)
    print(f"  {fname}: {len(stocks)} tradable, {summary.get('total_trades',0)} trades, "
          f"WR={summary.get('win_rate',0)}%, RR={summary.get('avg_rr',0)}x, "
          f"swing={summary.get('swing_pct',0)}%")

n_stocks = len(all_stocks)
tradable_stocks = [s for s in all_stocks if s.get('trades', 0) >= 3]
n_tradable = len(tradable_stocks)

# 加权平均
if total_trades > 0:
    avg_wr = sum(s['win_rate'] * s['trades'] for s in tradable_stocks) / sum(s['trades'] for s in tradable_stocks)
    avg_rr = sum(s['avg_rr'] * s['trades'] for s in tradable_stocks) / sum(s['trades'] for s in tradable_stocks)
    avg_pnl = sum(s['avg_pnl'] * s['trades'] for s in tradable_stocks) / sum(s['trades'] for s in tradable_stocks)
    swing_total = sum(s.get('swing_count', 0) for s in tradable_stocks)
    swing_pct = swing_total / total_trades * 100
    all_trades_total = sum(s['trades'] for s in tradable_stocks)
else:
    avg_wr = avg_rr = avg_pnl = swing_pct = 0
    all_trades_total = 0

# WR分布
wr_dist = Counter()
for s in tradable_stocks:
    wr = s['win_rate']
    if wr >= 95: wr_dist['95-100%'] += 1
    elif wr >= 90: wr_dist['90-95%'] += 1
    elif wr >= 80: wr_dist['80-90%'] += 1
    elif wr >= 70: wr_dist['70-80%'] += 1
    elif wr >= 60: wr_dist['60-70%'] += 1
    elif wr >= 50: wr_dist['50-60%'] += 1
    else: wr_dist['<50%'] += 1

# 阶段分布
phase_dist = Counter(s.get('phase', '?') for s in tradable_stocks)

# swing使用率分布
swing_dist = Counter()
for s in tradable_stocks:
    sw = s.get('swing_pct', 0)
    if sw >= 80: swing_dist['80-100%'] += 1
    elif sw >= 60: swing_dist['60-80%'] += 1
    elif sw >= 40: swing_dist['40-60%'] += 1
    elif sw >= 20: swing_dist['20-40%'] += 1
    elif sw > 0: swing_dist['0-20%'] += 1
    else: swing_dist['0%'] += 1

print(f"\n{'='*80}")
print(f"V11.6 全量4800汇总")
print(f"{'='*80}")
print(f"\n总含数据: {n_stocks}")
print(f"可交易(>=3笔): {n_tradable}")
print(f"总交易数: {all_trades_total}")
print(f"平均WR: {avg_wr:.1f}%")
print(f"平均RR: {avg_rr:.2f}x")
print(f"平均P&L: {avg_pnl:+.2f}%")
print(f"摆动SL/TP使用率: {swing_pct:.1f}%")
print(f"\nWR分布:")
for k, v in sorted(wr_dist.items()):
    bar = '█' * (v * 80 // max(wr_dist.values(), default=1))
    print(f"  {k:10s}: {v:4d} {bar}")
print(f"\n阶段分布:")
for k, v in sorted(phase_dist.items(), key=lambda x: x[1], reverse=True):
    bar = '█' * (v * 80 // max(phase_dist.values(), default=1))
    print(f"  {k:15s}: {v:4d} {bar}")
print(f"\n摆动SL使用率分布:")
for k, v in sorted(swing_dist.items(), key=lambda x: x[1], reverse=True):
    bar = '█' * (v * 80 // max(swing_dist.values(), default=1))
    print(f"  {k:10s}: {v:4d} {bar}")

# TOP 30
print(f"\nTOP 30 (by WR, n>=5):")
top = sorted([s for s in tradable_stocks if s['trades'] >= 5], 
             key=lambda x: x['win_rate'], reverse=True)[:30]
for s in top:
    print(f"  {s['symbol']:12s} WR={s['win_rate']:.0f}% n={s['trades']:2d} "
          f"RR={s['avg_rr']:.1f}x PF={s['profit_factor']:.1f} "
          f"swing={s.get('swing_pct',0):.0f}% phase={s.get('phase','?')}")

# 保存
output = {
    'timestamp': '2026-05-08T21:20',
    'config': {'version': 'V11.6_full'},
    'summary': {
        'stocks_with_data': n_stocks,
        'tradable': n_tradable,
        'total_trades': all_trades_total,
        'win_rate': round(avg_wr, 1),
        'avg_rr': round(avg_rr, 2),
        'avg_pnl': round(avg_pnl, 2),
        'swing_pct': round(swing_pct, 1),
        'swing_total': swing_total,
    },
    'wr_dist': dict(wr_dist),
    'phase_dist': dict(phase_dist),
    'swing_dist': dict(swing_dist),
    'stocks': tradable_stocks,
}
outpath = OUTPUT_DIR / 'v116_merged_summary.json'
outpath.write_text(json.dumps(output, ensure_ascii=False, indent=2, default=str))
print(f"\n保存: {outpath}")
