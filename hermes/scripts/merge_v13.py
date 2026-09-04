#!/usr/bin/env python3
"""Merge and analyze all V13 batches"""
import json
from pathlib import Path
from collections import Counter, defaultdict

results_dir = Path('/root/.hermes/smc_opt_v13')
batch_files = sorted(results_dir.glob('batch_*.json'))

all_trades = []
all_stocks = []

for f in batch_files:
    data = json.loads(f.read_text())
    all_stocks.extend(data.get('stocks', []))
    all_trades.extend(data.get('all_trades', []))
    s = data.get('summary', {})
    print(f"  {f.name}: {s.get('tradable',0)} stocks, {s.get('total_trades',0)} trades, WR={s.get('avg_win_rate','?')}%")

print(f"\n{'='*70}")
print(f"V13 全量4800股票汇总")
print(f"{'='*70}")

total_stocks = len(all_stocks)
total_trades = sum(s['n_trades'] for s in all_stocks)
wr_list = [s['win_rate'] for s in all_stocks]

print(f"\n总可交易股票: {total_stocks} / 4800")
print(f"总交易数: {total_trades}")
if wr_list:
    print(f"平均WR: {sum(wr_list)/len(wr_list):.1f}%")
    avg_rr = sum(s['avg_rr'] for s in all_stocks) / len(all_stocks)
    print(f"平均RR: {avg_rr:.2f}x")
    avg_pf = sum(s['profit_factor'] for s in all_stocks) / len(all_stocks)
    print(f"平均PF: {avg_pf:.1f}")

# WR分布
wr_buckets = [(0,30), (30,50), (50,60), (60,70), (70,80), (80,90), (90,100)]
print(f"\nWR分布:")
for lo, hi in wr_buckets:
    cnt = sum(1 for s in all_stocks if lo <= s['win_rate'] < hi)
    if cnt > 0:
        print(f"  {lo:3d}-{hi:3d}%: {cnt:4d} stocks ({cnt/total_stocks*100:.1f}%)")

# 阶段分布
phase_dist = Counter(s.get('phase','?') for s in all_stocks)
print(f"\n阶段分布:")
for p, cnt in phase_dist.most_common():
    wr_sub = [s['win_rate'] for s in all_stocks if s.get('phase')==p]
    avg_wr_p = sum(wr_sub)/len(wr_sub) if wr_sub else 0
    print(f"  {p:15s}: {cnt:4d} stocks avgWR={avg_wr_p:.1f}%")

# 前30佳股票 (by score: WR^2 * RR * n/5)
print(f"\nTOP 30 最佳股票:")
scored = [(s, s['win_rate']**2 * s['avg_rr'] * min(3, s['n_trades']/5)) for s in all_stocks]
scored.sort(key=lambda x: -x[1])
for s, score in scored[:30]:
    print(f"  {s['symbol']:12s} WR={s['win_rate']:.0f}% n={s['n_trades']:3d} RR={s['avg_rr']:.2f}x PF={s['profit_factor']:.0f} phase={s.get('phase','?'):10s} score={score:.0f}")

# 按WR的TOP20
print(f"\nTOP 20 (by WR, n>=5):")
top_wr = sorted([s for s in all_stocks if s['n_trades']>=5], key=lambda x: -x['win_rate'])
for s in top_wr[:20]:
    print(f"  {s['symbol']:12s} WR={s['win_rate']:.0f}% n={s['n_trades']:3d} RR={s['avg_rr']:.2f}x PF={s['profit_factor']:.0f}")

# 保存汇总数据集
merged = {
    'timestamp': '2026-05-08',
    'summary': {
        'total_scanned': 4800,
        'tradable': total_stocks,
        'total_trades': total_trades,
        'avg_win_rate': round(sum(wr_list)/len(wr_list), 1) if wr_list else 0,
        'avg_rr': round(avg_rr, 2) if wr_list else 0,
        'avg_pf': round(avg_pf, 1) if wr_list else 0,
    },
    'phase_distribution': dict(phase_dist),
    'wr_distribution': {f'{lo}-{hi}%': sum(1 for s in all_stocks if lo <= s['win_rate'] < hi)
                         for lo, hi in wr_buckets},
    'top_30': [{'symbol': s['symbol'], 'win_rate': s['win_rate'], 'n_trades': s['n_trades'],
                'avg_rr': s['avg_rr'], 'profit_factor': s['profit_factor'], 'phase': s.get('phase','')}
               for s, _ in scored[:30]],
}
outpath = results_dir / 'v13_merged_summary.json'
(Path(outpath)).write_text(json.dumps(merged, indent=2, ensure_ascii=False))
print(f"\n保存: {outpath}")
