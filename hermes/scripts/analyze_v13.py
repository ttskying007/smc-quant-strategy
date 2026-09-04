#!/usr/bin/env python3
"""
SMC V13 结果分析 + V14每股参数优化
====================================================
从V13全量扫描结果中:
1. 按股票/阶段/信号密度分析WR
2. 找出WR<60%的股票需要什么参数调整
3. 生成最优参数表
"""
import json
from pathlib import Path
from collections import Counter, defaultdict

# 收集所有批次结果
results_dir = Path('/root/.hermes/smc_opt_v13')
batch_files = sorted(results_dir.glob('batch_*.json'))

all_stocks = []
for f in batch_files:
    data = json.loads(f.read_text())
    all_stocks.extend(data.get('stocks', []))
    print(f"  {f.name}: {len(data.get('stocks',[]))} stocks, {data.get('summary',{}).get('total_trades',0)} trades")

print(f"\n{'='*60}")
print(f"V13 汇总 — {len(all_stocks)} 可交易股票")
print(f"{'='*60}")

if not all_stocks:
    print("No data yet - batches still running")
    exit()

# 总体统计
total_trades = sum(s['n_trades'] for s in all_stocks)
wr_list = [s['win_rate'] for s in all_stocks]
avg_wr = sum(wr_list) / len(wr_list)
avg_rr = sum(s['avg_rr'] for s in all_stocks) / len(all_stocks)

print(f"\n总交易数: {total_trades}")
print(f"平均WR: {avg_wr:.1f}%")
print(f"平均RR: {avg_rr:.2f}x")
print(f"平均PF: {sum(s['profit_factor'] for s in all_stocks)/len(all_stocks):.1f}")

# WR分布
wr_buckets = [(0,20), (20,40), (40,60), (60,70), (70,80), (80,90), (90,100)]
print(f"\nWR分布:")
for lo, hi in wr_buckets:
    cnt = sum(1 for s in all_stocks if lo <= s['win_rate'] < hi)
    if cnt > 0:
        print(f"  {lo:3d}-{hi:3d}%: {cnt:4d} stocks ({cnt/len(all_stocks)*100:.1f}%)")

# === 每股SL/TP推荐 ===
# 基于当前SL=0.5%/TP=5.0%的结果, 统计哪些股票需要不同参数
print(f"\n{'='*60}")
print(f"V14 每股参数优化建议")
print(f"{'='*60}")

# 根据WR和交易数推荐不同参数
for s in sorted(all_stocks, key=lambda x: x['win_rate']):
    symbol = s['symbol']
    wr = s['win_rate']
    n = s['n_trades']
    phase = s.get('phase', '?')
    
    # 推荐参数
    if wr >= 80:
        # 高WR: 保持当前或更激进
        rec_sl = 0.5
        rec_tp = 5.0
        reason = "高WR,保持当前"
    elif wr >= 60:
        # 中WR: 稍微调整
        if n >= 5:
            rec_sl = 0.5
            rec_tp = 5.0
            reason = "中WR,保持当前"
        else:
            rec_sl = 0.7
            rec_tp = 4.0
            reason = "交易少,保守参数"
    else:
        # 低WR: 需要调整
        if phase in ('volatile',):
            rec_sl = 1.0
            rec_tp = 3.0
            reason = "volatile阶段,宽SL"
        else:
            rec_sl = 0.3
            rec_tp = 5.0
            reason = "低WR,尝试窄SL"
    
    s['rec_sl'] = rec_sl
    s['rec_tp'] = rec_tp
    s['reason'] = reason

# 保存优化参数表
params_out = [{
    'symbol': s['symbol'], 'phase': s.get('phase','?'),
    'current_wr': s['win_rate'], 'current_n': s['n_trades'],
    'rec_sl': s['rec_sl'], 'rec_tp': s['rec_tp'],
    'reason': s['reason'],
} for s in all_stocks]

params_path = results_dir / 'v14_params.json'
Path(params_path).write_text(json.dumps(params_out, indent=2, ensure_ascii=False))
print(f"\n保存参数表: {params_path}")

# 推荐参数分布
rec_cnt = Counter((s['rec_sl'], s['rec_tp']) for s in all_stocks)
print(f"\n推荐参数分布:")
for (sl, tp), cnt in rec_cnt.most_common():
    print(f"  SL={sl}% TP={tp}%: {cnt} stocks")

# 找到最佳股票的详细信息
print(f"\n{'='*60}")
print(f"TOP 20 最佳股票 (score = WR^2 * RR * min(3, n/3))")
print(f"{'='*60}")
for s in sorted(all_stocks, key=lambda x: -(x['win_rate']**2 * x['avg_rr'] * min(3, x['n_trades']/3)))[:20]:
    score = s['win_rate']**2 * s['avg_rr'] * min(3, s['n_trades']/3)
    print(f"  {s['symbol']:12s} WR={s['win_rate']:.0f}% n={s['n_trades']:3d} "
          f"RR={s['avg_rr']:.2f}x PF={s['profit_factor']:.1f} phase={s.get('phase','?'):10s} "
          f"score={score:.0f}")

print(f"\nBOTTOM 10 (by WR, n>=3)")
for s in sorted(all_stocks, key=lambda x: x['win_rate'])[:20]:
    if s['n_trades'] >= 3:
        print(f"  {s['symbol']:12s} WR={s['win_rate']:.0f}% n={s['n_trades']:3d} "
              f"RR={s['avg_rr']:.2f}x PF={s['profit_factor']:.1f} phase={s.get('phase','?'):10s}")
