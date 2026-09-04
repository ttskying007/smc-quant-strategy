"""V477 深度分析：SL设计、入场质量、持仓时间、止盈设计、仓位策略"""
import json, sys, math
from collections import Counter, defaultdict

with open('/root/.hermes/smc_opt_v477/v477_full.json') as f:
    trades = json.load(f)

n = len(trades)
print(f"总交易数: {n}")

# ============================================================
# 1. SL设计逻辑 — SL位置是否合理？
# ============================================================
print("\n" + "="*60)
print("【1】SL设计逻辑 — 各SL类型的距离和效果")
print("="*60)

# 所有交易都用 adaptive SL (100%)
sl_pcts = [t['sl_pct'] for t in trades]
sl_min, sl_max = min(sl_pcts), max(sl_pcts)
sl_mean = sum(sl_pcts) / n
# median
sl_pcts_sorted = sorted(sl_pcts)
sl_med = sl_pcts_sorted[n//2]
print(f"  SL距离: 均值={sl_mean:.2f}%, 中位={sl_med:.2f}%, 范围=[{sl_min:.2f}%, {sl_max:.2f}%]")

# 按距离分档
buckets = [(0, 0.1), (0.1, 0.15), (0.15, 0.2), (0.2, 0.25), (0.25, 0.3), (0.3, 0.5), (0.5, 1.0), (1.0, 999)]
for lo, hi in buckets:
    subset = [t for t in trades if lo <= t['sl_pct'] < hi]
    if not subset: continue
    wr = sum(1 for t in subset if t['won']) / len(subset) * 100
    rr = sum(t['rr'] for t in subset) / len(subset)
    r_med = sorted([t['rr'] for t in subset])[len(subset)//2]
    print(f"  SL [{lo:.2f}%, {hi:.2f}%): n={len(subset):4d}, WR={wr:.1f}%, RRmean={rr:.2f}x, RRmed={r_med:.2f}x")

# 关键问题：SL距离 vs TP距离的关系
print("\n  SL vs TP 距离对比:")
tp_pcts = [t['tp_pct'] for t in trades]
tp_mean, tp_med = sum(tp_pcts)/n, sorted(tp_pcts)[n//2]
print(f"  SL(中位)={sl_med:.2f}%, TP(中位)={tp_med:.2f}%, Ratio(TP/SL)={tp_med/sl_med:.1f}x")

# SL与持仓时间的关系
print("\n  SL距离 vs 持仓时间:")
for hold in range(1, 12):
    subset = [t for t in trades if t['hold_bars'] == hold]
    if not subset: continue
    avg_sl = sum(t['sl_pct'] for t in subset) / len(subset)
    wr = sum(1 for t in subset if t['won']) / len(subset) * 100
    rr = sum(t['rr'] for t in subset) / len(subset)
    print(f"  Hold={hold}bars: n={len(subset):4d}, avgSL={avg_sl:.3f}%, WR={wr:.1f}%, RR={rr:.2f}x")

# ============================================================
# 2. 持仓时间分析
# ============================================================
print("\n" + "="*60)
print("【2】持仓时间分布 — 系统到底是scalp还是swing？")
print("="*60)

hold_dist = Counter(t['hold_bars'] for t in trades)
for h in sorted(hold_dist):
    pct = hold_dist[h] / n * 100
    wr = sum(1 for t in trades if t['hold_bars'] == h and t['won']) / (hold_dist[h] or 1) * 100
    rr = sum(t['rr'] for t in trades if t['hold_bars'] == h) / (hold_dist[h] or 1)
    print(f"  {h:2d} bars: {hold_dist[h]:4d} ({pct:5.1f}%) | WR={wr:.1f}% | RR={rr:.2f}x")

# 交易日的换算 (60min=4bars/日)
print(f"\n  持仓中位: {sorted(t['hold_bars'] for t in trades)[n//2]} bars = {sorted(t['hold_bars'] for t in trades)[n//2]/4:.1f} 交易日")
print(f"  持仓均值: {sum(t['hold_bars'] for t in trades)/n:.1f} bars = {sum(t['hold_bars'] for t in trades)/n/4:.1f} 交易日")

# 持仓2-4天的盈亏特征
for bars_range_name, lo, hi in [("1-2",1,3), ("2-4",3,6), ("5+",6,999)]:
    subset = [t for t in trades if lo <= t['hold_bars'] < hi]
    if not subset: continue
    wr = sum(1 for t in subset if t['won']) / len(subset) * 100
    rr = sum(t['rr'] for t in subset) / len(subset)
    avg_pnl = sum(t['pnl_pct'] for t in subset) / len(subset)
    print(f"  {bars_range_name}日: n={len(subset):4d}, WR={wr:.1f}%, RR={rr:.2f}x, avgP&L={avg_pnl:+.2f}%")

# ============================================================
# 3. 入场价格质量 — 入场后价格方向
# ============================================================
print("\n" + "="*60)
print("【3】入场价格质量 — 入场后是否立即面对不利方向？")
print("="*60)

# 计算平均盈利/亏损入场后的走势
won_entry_bars = [t['hold_bars'] for t in trades if t['won']]
lost_entry_bars = [t['hold_bars'] for t in trades if not t['won']]
print(f"  盈利交易平均hold: {sum(won_entry_bars)/len(won_entry_bars):.1f} bars" if won_entry_bars else "  无盈利交易")
print(f"  亏损交易平均hold: {sum(lost_entry_bars)/len(lost_entry_bars):.1f} bars" if lost_entry_bars else "  无亏损交易")

# 入场后盈亏比分布
early_win = sum(1 for t in trades if t['won'] and t['hold_bars'] <= 3)
early_lose = sum(1 for t in trades if not t['won'] and t['hold_bars'] <= 3)
late_win = sum(1 for t in trades if t['won'] and t['hold_bars'] > 3)
late_lose = sum(1 for t in trades if not t['won'] and t['hold_bars'] > 3)
print(f"  早期exit(<=3bars): {early_win+early_lose}笔, WR={early_win/(early_win+early_lose)*100:.1f}%" if (early_win+early_lose)>0 else "")
print(f"  晚期exit(>3bars): {late_win+late_lose}笔, WR={late_win/(late_win+late_lose)*100:.1f}%" if (late_win+late_lose)>0 else "")

# ============================================================
# 4. 止盈设计分析
# ============================================================
print("\n" + "="*60)
print("【4】止盈设计分析 — TP位置和时间")
print("="*60)

tp_types = Counter(t['tp_type'] for t in trades)
print(f"  TP类型分布:")
for tp_t, cnt in tp_types.most_common():
    pct = cnt / n * 100
    subset = [t for t in trades if t['tp_type'] == tp_t]
    wr = sum(1 for t in subset if t['won']) / len(subset) * 100
    rr = sum(t['rr'] for t in subset) / len(subset)
    print(f"    {tp_t}: {cnt:4d} ({pct:.1f}%) | WR={wr:.1f}% | RR={rr:.2f}x")

# TP距离分布
tp_dist = Counter(round(t['tp_pct']/2)*2 for t in trades)
print(f"\n  TP距离分布 (按2%分档):")
for tp in sorted(tp_dist):
    if tp_dist[tp] < 10: continue
    subset = [t for t in trades if round(t['tp_pct']/2)*2 == tp]
    wr = sum(1 for t in subset if t['won']) / len(subset) * 100
    rr = sum(t['rr'] for t in subset) / len(subset)
    print(f"    {tp}%: {tp_dist[tp]:4d}笔 | WR={wr:.1f}% | RR={rr:.2f}x")

# ============================================================
# 5. TP vs Trailing — 是否提前出场
# ============================================================
print("\n" + "="*60)
print("【5】提前出场分析 — 是否本该到TP但被截走？")
print("="*60)

# 所有交易都是 trailing exit
exit_methods = Counter(t['exit_method'] for t in trades)
print(f"  出场方式: {dict(exit_methods)}")

# POI激活占比
poi_activated = sum(1 for t in trades if t.get('poi_activated'))
poi_not = sum(1 for t in trades if not t.get('poi_activated'))
print(f"  POI激活: {poi_activated} ({poi_activated/n*100:.1f}%)")
print(f"  POI未激活: {poi_not} ({poi_not/n*100:.1f}%)")

# exit_price vs TP达到率
tp_reached = sum(1 for t in trades if t['won'])  # 盈利就说明trailing至少部分锁住了
print(f"  盈利交易(部分或完全达到TP): {tp_reached}/{n} ({tp_reached/n*100:.1f}%)")

# 盈利但hold短的 — 是否被trailing过早截走？
short_profits = [t for t in trades if t['won'] and t['hold_bars'] <= 3]
short_profit_pnl = sum(t['pnl_pct'] for t in short_profits) / len(short_profits) if short_profits else 0
print(f"  快速盈利(<=3bars): {len(short_profits)}笔, avgP&L={short_profit_pnl:.2f}%")

long_profits = [t for t in trades if t['won'] and t['hold_bars'] > 3]
long_profit_pnl = sum(t['pnl_pct'] for t in long_profits) / len(long_profits) if long_profits else 0
print(f"  慢速盈利(>3bars): {len(long_profits)}笔, avgP&L={long_profit_pnl:.2f}%")

# ============================================================
# 6. 仓位策略
# ============================================================
print("\n" + "="*60)
print("【6】仓位策略 — 当前是固定仓位吗？")
print("="*60)

# 检查是否有仓位字段
has_position_sizing = 'position_pct' in trades[0] or 'shares' in trades[0]
print(f"  交易数据中仓位字段: {'有' if has_position_sizing else '无'}")
print(f"  当前仓位策略: 固定等权 (每笔交易相同权重)")
print(f"  平均P&L = +{sum(t['pnl_pct'] for t in trades)/n:.2f}%")

# 按信号质量分档的PnL表现
print("\n  按共振分数分档 (resonance_total):")
# 提取并分析resonance分数
resonances = [t.get('resonance_total', 0) for t in trades]
res_min, res_max = min(resonances), max(resonances)
print(f"  resonance范围: [{res_min:.3f}, {res_max:.3f}]")
thresholds = [0.6, 0.65, 0.7, 0.75, 0.8, 1.0]
prev = 0
for th in thresholds:
    subset = [t for t in trades if prev <= t.get('resonance_total', 0) < th]
    if subset:
        wr = sum(1 for t in subset if t['won']) / len(subset) * 100
        rr = sum(t['rr'] for t in subset) / len(subset)
        pnl = sum(t['pnl_pct'] for t in subset) / len(subset)
        print(f"    [{prev:.2f}, {th:.2f}): n={len(subset):4d}, WR={wr:.1f}%, RR={rr:.2f}x, PnL={pnl:+.2f}%")
    prev = th

# retest vs non-retest
print("\n  重测 vs 非重测:")
for is_retest, name in [(True, "重测"), (False, "非重测")]:
    subset = [t for t in trades if t.get('is_retest') == is_retest]
    if subset:
        wr = sum(1 for t in subset if t['won']) / len(subset) * 100
        rr = sum(t['rr'] for t in subset) / len(subset)
        pnl = sum(t['pnl_pct'] for t in subset) / len(subset)
        print(f"    {name}: n={len(subset):4d}, WR={wr:.1f}%, RR={rr:.2f}x, PnL={pnl:+.2f}%")

# ============================================================
# 7. 系统性偏差识别
# ============================================================
print("\n" + "="*60)
print("【7】系统性偏差汇总")
print("="*60)

# 亏损交易详细分析
losers = [t for t in trades if not t['won']]
print(f"  亏损交易: {len(losers)}笔 ({len(losers)/n*100:.1f}%)")
avg_loss = sum(t['pnl_pct'] for t in losers) / len(losers) if losers else 0
avg_hold = sum(t['hold_bars'] for t in losers) / len(losers) if losers else 0
print(f"    平均亏损: {avg_loss:+.2f}%, 平均hold: {avg_hold:.1f} bars")
print(f"    亏损中SL距离: 均值={sum(t['sl_pct'] for t in losers)/len(losers):.3f}%")

# 亏损交易的SL距离分布
print(f"    亏损交易SL分布:")
for lo, hi in buckets:
    subset = [t for t in losers if lo <= t['sl_pct'] < hi]
    if subset:
        print(f"      SL [{lo:.2f}, {hi:.2f}): {len(subset)}笔")

# 连续亏损分析
print("\n  连续亏损统计:")
win_lose = [1 if t['won'] else 0 for t in trades]
max_consec_loss = 0
curr_loss = 0
for w in win_lose:
    if w == 0:
        curr_loss += 1
        max_consec_loss = max(max_consec_loss, curr_loss)
    else:
        curr_loss = 0
print(f"    最大连续亏损: {max_consec_loss}笔")

# 大赢家分析 (RR > 50x)
big_winners = [t for t in trades if t['won'] and t['rr'] > 50]
print(f"\n  大赢家 (RR>50x): {len(big_winners)}笔")
if big_winners:
    avg_pnl_big = sum(t['pnl_pct'] for t in big_winners) / len(big_winners)
    avg_hold_big = sum(t['hold_bars'] for t in big_winners) / len(big_winners)
    print(f"    平均P&L: {avg_pnl_big:.2f}%, 平均hold: {avg_hold_big:.1f} bars")
    total_pnl = sum(t['pnl_pct'] for t in trades)
    big_pnl = sum(t['pnl_pct'] for t in big_winners)
    print(f"    占总PnL: {big_pnl/total_pnl*100:.1f}%")

print("\n" + "="*60)
print("分析完成")
print("="*60)
