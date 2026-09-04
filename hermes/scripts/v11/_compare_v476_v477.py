"""V476 vs V477 详细对比 + T+1影响分析"""
import json
from pathlib import Path
from collections import Counter

V476 = json.loads((Path('/root/.hermes/smc_opt_v476/v476_full.json')).read_text())
V477 = json.loads((Path('/root/.hermes/smc_opt_v477/v477_full.json')).read_text())

print(f"{'指标':>30}  {'V476':>12}  {'V477(T+1)':>12}  {'变化':>10}")
print("-"*68)

r476 = [t['rr'] for t in V476]
r477 = [t['rr'] for t in V477]
p476 = [t['pnl_pct'] for t in V476]
p477 = [t['pnl_pct'] for t in V477]
h476 = [t['hold_bars'] for t in V476]
h477 = [t['hold_bars'] for t in V477]
w476 = sum(1 for t in V476 if t['won'])
w477 = sum(1 for t in V477 if t['won'])

print(f"    n                      {len(V476):>8}      {len(V477):>8}")
print(f"    WR                     {w476/len(V476)*100:>8.1f}%     {w477/len(V477)*100:>8.1f}%      +{w477/len(V477)*100-w476/len(V476)*100:.1f}pp")
print(f"    RR_mean                {sum(r476)/len(r476):>8.2f}x     {sum(r477)/len(r477):>8.2f}x      +{sum(r477)/len(r477)-sum(r476)/len(r476):.2f}x")
print(f"    RR_med                 {sorted(r476)[len(r476)//2]:>8.2f}x     {sorted(r477)[len(r477)//2]:>8.2f}x")
print(f"    PnL_avg                {sum(p476)/len(p476):>8.2f}%     {sum(p477)/len(p477):>8.2f}%      +{sum(p477)/len(p477)-sum(p476)/len(p476):.2f}%")
print(f"    Hold_med               {sorted(h476)[len(h476)//2]:>8.1f}        {sorted(h477)[len(h477)//2]:>8.1f}")
print(f"    Hold_mean              {sum(h476)/len(h476):>8.1f}        {sum(h477)/len(h477):>8.1f}")

# Hold分布对比
h_dist_476 = Counter(h476)
h_dist_477 = Counter(h477)
print(f"\n  Hold分布对比:")
print(f"    {'Hold':>5}  {'V476':>8}  {'V477':>8}")
for h in range(0, 11):
    print(f"    {h:>5}  {h_dist_476[h]:>8}  {h_dist_477[h]:>8}")
print(f"    {'11+':>5}  {sum(v for k,v in h_dist_476.items() if k>=11):>8}  {sum(v for k,v in h_dist_477.items() if k>=11):>8}")

# 哪些交易从跨日变跨日？v477中的同日exit统计
# 用symbol+entry_idx匹配
v476_map = {(t.get('symbol',''), t['entry_idx']): t for t in V476}
v477_map = {(t.get('symbol',''), t['entry_idx']): t for t in V477}

# 找V477中新增的跨日交易（原V476同日exit）
same_day_476_to_cross_477 = []
for key, t476 in v476_map.items():
    t477 = v477_map.get(key)
    if t477:
        # 检查V476的entry和exit是否同一天（用hold和index判断）
        ei_date = t476['entry_idx'] // 4
        xi_date = t476['exit_idx'] // 4
        if ei_date == xi_date:  # V476是同一天退出
            same_day_476_to_cross_477.append((t476, t477))

print(f"\n\n=== 同日exit交易在T+1后变化 ({len(same_day_476_to_cross_477)} 笔) ===")
if same_day_476_to_cross_477:
    orig_wins = sum(1 for a,b in same_day_476_to_cross_477 if a['won'])
    new_wins = sum(1 for a,b in same_day_476_to_cross_477 if b['won'])
    orig_pnl = sum(a['pnl_pct'] for a,b in same_day_476_to_cross_477)
    new_pnl = sum(b['pnl_pct'] for a,b in same_day_476_to_cross_477)
    orig_rr = sum(a['rr'] for a,b in same_day_476_to_cross_477) / len(same_day_476_to_cross_477)
    new_rr = sum(b['rr'] for a,b in same_day_476_to_cross_477) / len(same_day_476_to_cross_477)
    
    print(f"  原WR: {orig_wins/len(same_day_476_to_cross_477)*100:.1f}% -> 新WR: {new_wins/len(same_day_476_to_cross_477)*100:.1f}%")
    print(f"  原PnL: {orig_pnl/len(same_day_476_to_cross_477):+.2f}% -> 新PnL: {new_pnl/len(same_day_476_to_cross_477):+.2f}%")
    print(f"  原RR: {orig_rr:.2f}x -> 新RR: {new_rr:.2f}x")
    
    # 统计变化
    improved = sum(1 for a,b in same_day_476_to_cross_477 if b['pnl_pct'] > a['pnl_pct'])
    worsened = sum(1 for a,b in same_day_476_to_cross_477 if b['pnl_pct'] < a['pnl_pct'])
    same = sum(1 for a,b in same_day_476_to_cross_477 if b['pnl_pct'] == a['pnl_pct'])
    print(f"\n  改进: {improved} | 恶化: {worsened} | 持平: {same}")
    
    # 示例
    print(f"\n  示例 (first 5):")
    samples = [(a,b) for a,b in same_day_476_to_cross_477 if b['pnl_pct'] != a['pnl_pct']][:5]
    for a,b in samples:
        print(f"    {b.get('symbol','?'):10s}: {a['pnl_pct']:+.2f}% -> {b['pnl_pct']:+.2f}% (hold {a['hold_bars']}->{b['hold_bars']})")
