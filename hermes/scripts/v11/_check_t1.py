"""分析V476交易的当日买卖情况（A股T+1检查）"""
import json
from pathlib import Path
from collections import Counter

CACHE_DIR = Path('/root/.hermes/kline_cache_60min')
V476_TRADES = Path('/root/.hermes/smc_opt_v476/v476_full.json')

# 1. 先看60min数据格式
d = json.loads((CACHE_DIR / '000001_SZ_60min_200.json').read_text())
print(f"000001.SZ: {len(d)} bars")
print(f"Keys: {list(d[0].keys())}")
print(f"First 3 bars:")
for b in d[:3]:
    print(f"  {b}")
print()

# 2. 看是否有date/t字段可以判断交易日
# 如果没日期字段，需要从数据推断
# 假设每个交易日有4根60min bar (9:30,10:30,11:30/13:00,14:00)
# 但实际上A股只有4根60min bar: 9:30-10:30, 10:30-11:30, 13:00-14:00, 14:00-15:00

has_date = 'date' in d[0] or 't' in d[0]
print(f"Has date field: {has_date}")
if has_date:
    date_field = 'date' if 'date' in d[0] else 't'
    print(f"Date field: {date_field}")
    print(f"Sample dates:")
    seen_dates = set()
    for b in d:
        seen_dates.add(b.get(date_field, '?'))
    print(f"  {sorted(seen_dates)[:10]}")

# 3. 看V476交易中entry和exit是否在同一天
trades = json.loads(V476_TRADES.read_text())
print(f"\nV476 total trades: {len(trades)}")

# 如果数据没有日期字段，我们可以按连续bar推断：每4根bar = 1天
# entry_idx和exit_idx的差值
same_bar = sum(1 for t in trades if t['hold_bars'] == 0)
same_or_next_bar = sum(1 for t in trades if t['hold_bars'] <= 1)
hold_dist = Counter(t['hold_bars'] for t in trades)

print(f"\nHold bars distribution:")
for h in sorted(hold_dist):
    sub = [t for t in trades if t['hold_bars'] == h]
    won = sum(1 for t in sub if t['won'])
    rr = sum(t['rr'] for t in sub) / len(sub)
    pnl = sum(t['pnl_pct'] for t in sub) / len(sub)
    print(f"  hold={h:3d}: n={len(sub):5d} WR={won/len(sub)*100:.1f}% RR={rr:.2f}x PnL={pnl:+.2f}%")

# 按bar差值推断同一交易日 (每4根60min=1天)
# 从entry_bar算起，同一天最多4根bar，但entry可能在任意位置
# 所以同一天 <= 4 - (entry_bar % 4) ？不对，entry_bar是全局索引
# 更准确：同一天的exit_idx - entry_idx <= 3 (最多剩3根当日bar)
# 但这是近似，因为entry可能在第一根(0)或最后一根(3)

print(f"\n--- T+1 检查 ---")
# 简单模型：假设entry_bar % 4 是当天第几根60min
# 当日可卖出的最大bar数量 = 3 - (entry_bar % 4) + 1 = 4 - entry_bar%4
# hold=0: entry和退出在同一根bar (根本不可能)
# hold=1且在第一根bar入场: 可卖出(第2根)，但entry在最后1根也不行

# 保守估计：hold_bars <= 1 的大部分可能当日买卖
# hold_bars == 0: 100%当日
# hold_bars == 1: 如果entry在当天第1-2根，exit在第2-3根，仍在同一天
# hold_bars == 1 且 entry_bar%4 <= 2: 可能同一天
# hold_bars == 2: 如果entry在当天第1根，exit在第3根，仍在同一天

very_likely_same_day = sum(1 for t in trades if t['hold_bars'] == 0)
likely_same_day = sum(1 for t in trades if t['hold_bars'] <= 1 and (t['entry_idx'] % 4) <= 2)
maybe_same_day = sum(1 for t in trades if t['hold_bars'] <= 2 and (t['entry_idx'] % 4) <= 0)

print(f"\n  hold=0 (绝对当日): {very_likely_same_day}")
print(f"  hold<=1 + entry_idx%4<=2: {likely_same_day}")
print(f"  hold<=2 + entry_idx%4<=0: {maybe_same_day}")

# 更精确：看每笔交易的entry_idx和exit_idx是否跨天
# 交易日分割: bar 0-3 = day0, bar 4-7 = day1, ...
same_day = 0
same_day_details = []
for t in trades:
    entry_day = t['entry_idx'] // 4
    exit_day = t['exit_idx'] // 4
    if entry_day == exit_day:
        same_day += 1
        same_day_details.append(t)

print(f"\n  精确跨天检查 (4bar=1day):")
print(f"  同日exit: {same_day}/{len(trades)} ({same_day/len(trades)*100:.1f}%)")
print(f"  跨日exit: {len(trades)-same_day}/{len(trades)} ({(len(trades)-same_day)/len(trades)*100:.1f}%)")

# 分析这些同日交易的质量
if same_day_details:
    same_won = sum(1 for t in same_day_details if t['won'])
    same_rr = sum(t['rr'] for t in same_day_details) / len(same_day_details)
    same_pnl = sum(t['pnl_pct'] for t in same_day_details) / len(same_day_details)
    print(f"\n  同日交易质量:")
    print(f"    n={same_day}, WR={same_won/same_day*100:.1f}%, RR={same_rr:.2f}x, PnL={same_pnl:+.2f}%")
    
    # 细分
    for h in range(4):
        sub = [t for t in same_day_details if t['hold_bars'] == h]
        if sub:
            sub_won = sum(1 for t in sub if t['won'])
            sub_rr = sum(t['rr'] for t in sub) / len(sub)
            sub_pnl = sum(t['pnl_pct'] for t in sub) / len(sub)
            print(f"    hold={h}: n={len(sub)}, WR={sub_won/len(sub)*100:.1f}%, RR={sub_rr:.2f}x, PnL={sub_pnl:+.2f}%")

# 同样分析V467
V467_TRADES = Path('/root/.hermes/smc_opt_v467/v467_full_trades.json')
if V467_TRADES.exists():
    t467 = json.loads(V467_TRADES.read_text())
    same_467 = sum(1 for t in t467 if (t['entry_idx'] // 4) == (t['exit_idx'] // 4))
    print(f"\n  V467同日exit: {same_467}/{len(t467)} ({same_467/len(t467)*100:.1f}%)")
