#!/usr/bin/env python3
"""V500 深度分析 — 结构TP/SL质量评估"""
import json, sys
from collections import defaultdict, Counter

trades = json.load(open('/root/.hermes/smc_opt_v500/v500_trades.json'))
print(f"加载 {len(trades)} 笔交易")

# ── 1. SL距离分布 ──
sl_distances = [t['sl_distance'] for t in trades]
buckets = Counter()
for d in sl_distances:
    if d <= 1.0: buckets['0-1%'] += 1
    elif d <= 2.0: buckets['1-2%'] += 1
    elif d <= 3.0: buckets['2-3%'] += 1
    elif d <= 4.0: buckets['3-4%'] += 1
    elif d <= 5.0: buckets['4-5%'] += 1
    elif d <= 6.0: buckets['5-6%'] += 1
    elif d <= 8.0: buckets['6-8%'] += 1
    else: buckets['8%+'] += 1

print("\n=== SL距离分布 ===")
for b in ['0-1%', '1-2%', '2-3%', '3-4%', '4-5%', '5-6%', '6-8%', '8%+']:
    cnt = buckets.get(b, 0)
    pct = cnt / len(trades) * 100
    bar = '█' * int(pct)
    print(f"  {b}: {cnt}笔 ({pct:.1f}%) {bar}")

# SL距离 × WR
print("\n=== SL距离 vs WR ===")
for b in ['0-1%', '1-2%', '2-3%', '3-4%', '4-5%', '5-6%', '6-8%', '8%+']:
    subset = [t for t in trades if (
        (b == '0-1%' and t['sl_distance'] <= 1.0) or
        (b == '1-2%' and 1.0 < t['sl_distance'] <= 2.0) or
        (b == '2-3%' and 2.0 < t['sl_distance'] <= 3.0) or
        (b == '3-4%' and 3.0 < t['sl_distance'] <= 4.0) or
        (b == '4-5%' and 4.0 < t['sl_distance'] <= 5.0) or
        (b == '5-6%' and 5.0 < t['sl_distance'] <= 6.0) or
        (b == '6-8%' and 6.0 < t['sl_distance'] <= 8.0) or
        (b == '8%+' and t['sl_distance'] > 8.0)
    )]
    if subset:
        won = sum(1 for t in subset if t['won'])
        wr = won / len(subset) * 100
        avg_pnl = sum(t['pnl_pct'] for t in subset) / len(subset)
        print(f"  {b}: {len(subset)}笔 | WR={wr:.1f}% | 均PnL={avg_pnl:.2f}%")

# ── 2. TP距离分布 ──
tp_distances = []
for t in trades:
    if t['won'] and t.get('tp_distance'):
        tp_distances.append(t['tp_distance'])

tp_buckets = Counter()
for d in tp_distances:
    if d <= 2.0: tp_buckets['0-2%'] += 1
    elif d <= 4.0: tp_buckets['2-4%'] += 1
    elif d <= 6.0: tp_buckets['4-6%'] += 1
    elif d <= 8.0: tp_buckets['6-8%'] += 1
    elif d <= 10.0: tp_buckets['8-10%'] += 1
    elif d <= 15.0: tp_buckets['10-15%'] += 1
    else: tp_buckets['15%+'] += 1

print(f"\n=== TP距离分布 (赢单, {len(tp_distances)}笔) ===")
for b in ['0-2%', '2-4%', '4-6%', '6-8%', '8-10%', '10-15%', '15%+']:
    cnt = tp_buckets.get(b, 0)
    pct = cnt / len(tp_distances) * 100
    bar = '█' * int(pct)
    print(f"  {b}: {cnt}笔 ({pct:.1f}%) {bar}")

# ── 3. 无结构SL深入分析 ──
no_sl = [t for t in trades if t['sl_source'] == 'none_fallback']
print(f"\n=== 无结构SL ({len(no_sl)}笔, {len(no_sl)/len(trades)*100:.1f}%) ===")
# 信号类型分布
sig_dist = Counter(t['signal_type'] for t in no_sl)
for sig, cnt in sig_dist.most_common():
    print(f"  {sig}: {cnt}笔 ({cnt/len(no_sl)*100:.0f}%)")
# 对无SL交易的WR
won = sum(1 for t in no_sl if t['won'])
print(f"  WR: {won}/{len(no_sl)} = {won/len(no_sl)*100:.1f}%")
avg_pnl = sum(t['pnl_pct'] for t in no_sl) / len(no_sl)
print(f"  均PnL: {avg_pnl:.2f}%")

# ── 4. SL来源 × WR ──
print("\n=== SL来源 vs WR ===")
for src in ['fvg_lower', 'swing_low', 'ob_lower', 'none_fallback']:
    subset = [t for t in trades if t['sl_source'] == src]
    if subset:
        won = sum(1 for t in subset if t['won'])
        wr = won / len(subset) * 100
        avg_sl = sum(t['sl_distance'] for t in subset) / len(subset)
        avg_pnl = sum(t['pnl_pct'] for t in subset) / len(subset)
        print(f"  {src}: {len(subset)}笔 | WR={wr:.1f}% | 均SL距离={avg_sl:.2f}% | 均PnL={avg_pnl:.2f}%")

# ── 5. TP层级近距离分析 ──
print("\n=== TP1距离 vs WR ===")
# 分析所有交易的tp1距离
tp1_data = []
for t in trades:
    tp_details = t.get('tp_details', [])
    if tp_details:
        tp1_data.append({
            'tp1_dist': tp_details[0]['dist_pct'],
            'tp1_src': tp_details[0]['source'],
            'won': t['won'],
            'tp_hit': t.get('tp_hit', 0),
        })

for d_range in [('0-2%', 0, 2), ('2-4%', 2, 4), ('4-6%', 4, 6), ('6-10%', 6, 10), ('10%+', 10, 999)]:
    subset = [d for d in tp1_data if d_range[1] <= d['tp1_dist'] < d_range[2]]
    if subset:
        won = sum(1 for d in subset if d['won'])
        wr = won / len(subset) * 100
        tp1_hit = sum(1 for d in subset if d['tp_hit'] == 1)
        tp1_hit_pct = tp1_hit / len(subset) * 100
        print(f"  TP1={d_range[0]}: {len(subset)}笔 | WR={wr:.1f}% | TP1命中率={tp1_hit_pct:.1f}%")

# ── 6. 前3层TP累加命中率 ──
tp_hits = Counter()
for t in trades:
    if t['won']:
        tp_hits[t.get('tp_hit', 0)] += 1

total_won = sum(1 for t in trades if t['won'])
print(f"\n=== TP层级累加命中 ({total_won}赢) ===")
cum = 0
for level in range(1, 11):
    cum += tp_hits.get(level, 0)
    print(f"  TP1-{level}: {cum}/{total_won} = {cum/total_won*100:.1f}%")

# ── 7. 信号强度 vs WR ──
print("\n=== 信号强度 vs WR ===")
for sr in [('弱(<3)', 0, 3), ('中(3-5)', 3, 5), ('强(5-7)', 5, 7), ('极强(7+)', 7, 99)]:
    subset = [t for t in trades if sr[1] <= t['signal_strength'] < sr[2]]
    if subset:
        won = sum(1 for t in subset if t['won'])
        wr = won / len(subset) * 100
        avg_pnl = sum(t['pnl_pct'] for t in subset) / len(subset)
        print(f"  {sr[0]}: {len(subset)}笔 | WR={wr:.1f}% | 均PnL={avg_pnl:.2f}%")

# ── 8. 信号置信度 vs WR ──
print("\n=== 信号置信度 vs WR ===")
for cr in [('<0.4', 0, 0.4), ('0.4-0.5', 0.4, 0.5), ('0.5-0.6', 0.5, 0.6), ('0.6-0.7', 0.6, 0.7), ('0.7+', 0.7, 1.0)]:
    subset = [t for t in trades if cr[1] <= t['signal_confidence'] < cr[2]]
    if subset:
        won = sum(1 for t in subset if t['won'])
        wr = won / len(subset) * 100
        avg_pnl = sum(t['pnl_pct'] for t in subset) / len(subset)
        print(f"  {cr[0]}: {len(subset)}笔 | WR={wr:.1f}% | 均PnL={avg_pnl:.2f}%")

print()
