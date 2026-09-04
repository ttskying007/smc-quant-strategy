"""深度分析：SL/ATR关系、具体交易案例、持仓合理性"""
import json, os, sys
import random
from collections import Counter, defaultdict
import numpy as np

# ============================
# 加载数据
# ============================
with open('/root/.hermes/smc_opt_v477/v477_full.json') as f:
    trades = json.load(f)

# 获取有交易股票列表
symbols = set(t['symbol'] for t in trades)
print(f"有交易的股票数: {len(symbols)}")
print(f"总交易数: {len(trades)}")

# ============================
# 1. 读取K线数据，计算每只股票的真实ATR
# ============================
print("\n" + "="*70)
print("【1】60min K线ATR分布 — 我们的SL相对于ATR有多小？")
print("="*70)

def calc_atr(ohlcv, period=14):
    """计算简单ATR"""
    closes = [c for _,_,_,c,_ in ohlcv]
    highs = [h for _,h,_,_,_ in ohlcv]
    lows = [l for _,l,_,_,_ in ohlcv]
    trs = []
    for i in range(1, len(ohlcv)):
        tr = max(highs[i]-lows[i], abs(highs[i]-closes[i-1]), abs(lows[i]-closes[i-1]))
        trs.append(tr)
    if len(trs) < period:
        return None
    # Simple ATR (not smoothed)
    atr = sum(trs[-period:]) / period
    # As percentage of current price
    price = closes[-1]
    return atr / price * 100 if price > 0 else None

# Sample stocks - examine K-line cache
kline_dir = '/root/.hermes/kline_cache_60min'
stock_atrs = {}
missing = 0
loaded = 0

for symbol in symbols:
    fpath = os.path.join(kline_dir, f"{symbol}.json")
    if not os.path.exists(fpath):
        # try another path
        fpath = os.path.join(kline_dir, symbol.replace('.', '_'), f"{symbol}.json")
        if not os.path.exists(fpath):
            missing += 1
            continue
    try:
        with open(fpath) as f:
            data = json.load(f)
        # data is list of [time, open, high, low, close, volume] or dict with 'date'
        if isinstance(data, list) and len(data) > 0:
            if isinstance(data[0], dict) and 'high' in data[0]:
                ohlcv = [(d.get('open',0), d.get('high',0), d.get('low',0), d.get('close',0), d.get('volume',0)) for d in data]
            elif isinstance(data[0], list) and len(data[0]) >= 5:
                ohlcv = [(d[1], d[2], d[3], d[4], d[5] if len(d) > 5 else 0) for d in data if len(d) >= 5]
            else:
                missing += 1
                continue
        else:
            missing += 1
            continue
        
        atr = calc_atr(ohlcv)
        if atr is not None:
            stock_atrs[symbol] = atr
            loaded += 1
    except Exception:
        missing += 1
        continue

print(f"  加载K线: {loaded}, 缺失: {missing}")

if stock_atrs:
    atr_values = list(stock_atrs.values())
    atr_mean = sum(atr_values) / len(atr_values)
    atr_med = sorted(atr_values)[len(atr_values)//2]
    print(f"  ATR均值: {atr_mean:.2f}%, ATR中位: {atr_med:.2f}%")
    print(f"  ATR范围: [{min(atr_values):.2f}%, {max(atr_values):.2f}%]")
    
    # ATR分档
    for th in [(0, 1), (1, 2), (2, 3), (3, 4), (4, 6), (6, 999)]:
        cnt = sum(1 for a in atr_values if th[0] <= a < th[1])
        if cnt:
            print(f"  ATR [{th[0]:.0f}%, {th[1]:.0f}%): {cnt}只 ({cnt/len(atr_values)*100:.1f}%)")

# ============================
# 2. SL vs ATR对比
# ============================
print("\n" + "="*70)
print("【2】SL vs ATR对比 — 我们的SL是ATR的多少倍？")
print("="*70)

# For each trade, look up the stock's ATR
trade_atrs = []
for t in trades:
    sym = t['symbol']
    if sym in stock_atrs:
        trade_atrs.append((stock_atrs[sym], t['sl_pct'], t['hold_bars'], t['won'], t['rr']))

print(f"  能匹配ATR的交易: {len(trade_atrs)}笔")

if trade_atrs:
    sl_atr_ratios = [s/a for a,s,_,_,_ in trade_atrs]
    ratio_mean = sum(sl_atr_ratios)/len(sl_atr_ratios)
    ratio_med = sorted(sl_atr_ratios)[len(sl_atr_ratios)//2]
    print(f"  SL/ATR比率: 均值={ratio_mean:.2f}x, 中位={ratio_med:.2f}x")
    print(f"  范围: [{min(sl_atr_ratios):.3f}x, {max(sl_atr_ratios):.3f}x]")
    
    # 按SL/ATR比率分档
    for lo, hi in [(0, 0.05), (0.05, 0.1), (0.1, 0.15), (0.15, 0.2), (0.2, 0.5), (0.5, 999)]:
        subset = [(a,s,h,w,r) for a,s,h,w,r in trade_atrs if lo <= s/a < hi]
        if subset:
            wr = sum(1 for _,_,_,w,_ in subset if w) / len(subset) * 100
            rr = sum(r for _,_,_,_,r in subset) / len(subset)
            avg_hold = sum(h for _,_,h,_,_ in subset) / len(subset)
            print(f"    SL/ATR [{lo:.2f}, {hi:.2f}): n={len(subset):4d}, WR={wr:.1f}%, RR={rr:.2f}x, hold={avg_hold:.1f}")

# ============================
# 3. 具体交易案例分析
# ============================
print("\n" + "="*70)
print("【3】具体交易案例 — 看入场/出场质量")
print("="*70)

# 分析各个symbol的交易模式
symbol_trades = defaultdict(list)
for t in trades:
    symbol_trades[t['symbol']].append(t)

# 找一些典型交易查看
print("\n  a) 大赢家 (RR>80x):")
big_wins = [t for t in trades if t['won'] and t['rr'] > 80]
for t in big_wins[:5]:
    print(f"    {t['symbol']}: entry_idx={t['entry_idx']}, hold={t['hold_bars']}, "
          f"entry={t['entry_price']}, exit={t['exit_price']}, "
          f"SL={t['sl_pct']:.2f}%, TP={t['tp_pct']:.2f}%, RR={t['rr']:.1f}x, "
          f"PnL={t['pnl_pct']:+.2f}%")

print("\n  b) 亏损交易 (最差5笔):")
losers = sorted([t for t in trades if not t['won']], key=lambda x: x['pnl_pct'])[:5]
for t in losers:
    print(f"    {t['symbol']}: entry_idx={t['entry_idx']}, hold={t['hold_bars']}, "
          f"entry={t['entry_price']}, exit={t['exit_price']}, "
          f"SL={t['sl_pct']:.2f}%, PnL={t['pnl_pct']:+.2f}%")

print("\n  c) 典型快进快出 (hold=1, 高RR):")
fast_profits = [t for t in trades if t['won'] and t['hold_bars'] == 1 and t['rr'] > 30]
for t in fast_profits[:5]:
    print(f"    {t['symbol']}: entry_price={t['entry_price']}, exit_price={t['exit_price']}, "
          f"SL={t['sl_pct']:.2f}%, RR={t['rr']:.1f}x, PnL={t['pnl_pct']:+.2f}%")

print("\n  d) 被T+1强制hold 2-4bars的典型交易:")
t1_trades = [t for t in trades if t['hold_bars'] >= 2 and t['hold_bars'] <= 4 and t['won']]
for t in random.sample(t1_trades, min(5, len(t1_trades))):
    print(f"    {t['symbol']}: hold={t['hold_bars']}, entry={t['entry_price']}, exit={t['exit_price']}, "
          f"SL={t['sl_pct']:.2f}%, RR={t['rr']:.1f}x, PnL={t['pnl_pct']:+.2f}%")

# ============================
# 4. 详细的持仓时间分析
# ============================
print("\n" + "="*70)
print("【4】持仓时间深度分析 — 1-2天是否合理？")
print("="*70)

print("\n  a) 不同hold时间的盈亏对比:")
for hold in sorted(set(t['hold_bars'] for t in trades)):
    subset = [t for t in trades if t['hold_bars'] == hold]
    if len(subset) < 5: continue  # skip small samples
    wr = sum(1 for t in subset if t['won']) / len(subset) * 100
    rr = sum(t['rr'] for t in subset) / len(subset)
    pnl = sum(t['pnl_pct'] for t in subset) / len(subset)
    rr_med = sorted([t['rr'] for t in subset])[len(subset)//2]
    print(f"    hold={hold:2d} | n={len(subset):4d} | WR={wr:5.1f}% | RRmean={rr:6.2f}x | RRmed={rr_med:6.2f}x | PnL={pnl:+.2f}%")

print("\n  b) 从1bar到4bar的PnL累积:")
for hold in range(1, 5):
    # 所有hold<=该bar的交易
    subset = [t for t in trades if t['hold_bars'] <= hold]
    wr = sum(1 for t in subset if t['won']) / len(subset) * 100
    pnl = sum(t['pnl_pct'] for t in subset) / len(subset)
    print(f"    hold<={hold}: n={len(subset):4d}, WR={wr:.1f}%, avgPnL={pnl:+.2f}%")

# 持仓1bar的vs长期持仓的RR+WR对比
print("\n  c) 短期(<=3bar) vs 中期(4-8bar) vs 长期(>8bar):")
for name, lo, hi in [("短期<=3", 1, 4), ("中期4-8", 4, 9), ("长期>8", 9, 999)]:
    subset = [t for t in trades if lo <= t['hold_bars'] < hi]
    if not subset: continue
    wr = sum(1 for t in subset if t['won']) / len(subset) * 100
    rr = sum(t['rr'] for t in subset) / len(subset)
    pnl = sum(t['pnl_pct'] for t in subset) / len(subset)
    print(f"    {name}: n={len(subset):4d} ({len(subset)/len(trades)*100:.1f}%), "
          f"WR={wr:.1f}%, RR={rr:.2f}x, PnL={pnl:+.2f}%")

# ============================
# 5. 信号正确性分析
# ============================
print("\n" + "="*70)
print("【5】信号正确性 — OB位置是否合理？")
print("="*70)

# 检查entry_type分布
entry_types = Counter(t['entry_type'] for t in trades)
print(f"  入场类型分布:")
for et, cnt in sorted(entry_types.items(), key=lambda x: -x[1]):
    subset = [t for t in trades if t['entry_type'] == et]
    wr = sum(1 for t in subset if t['won']) / len(subset) * 100
    rr = sum(t['rr'] for t in subset) / len(subset)
    print(f"    {et}: {cnt:4d} ({cnt/len(trades)*100:.1f}%) | WR={wr:.1f}% | RR={rr:.2f}x")

# 检查signal_type分布
signal_types = Counter(t['signal_type'] for t in trades)
print(f"\n  信号类型分布:")
for st, cnt in sorted(signal_types.items(), key=lambda x: -x[1]):
    subset = [t for t in trades if t['signal_type'] == st]
    wr = sum(1 for t in subset if t['won']) / len(subset) * 100
    rr = sum(t['rr'] for t in subset) / len(subset)
    print(f"    {st}: {cnt:4d} ({cnt/len(trades)*100:.1f}%) | WR={wr:.1f}% | RR={rr:.2f}x")

# ============================
# 6. 反弹vs趋势延续分析
# ============================
print("\n" + "="*70)
print("【6】反弹vs趋势延续 — 是否在正确方向入场？")
print("="*70)

# is_retest分布
retest_wr = sum(1 for t in trades if t.get('is_retest') and t['won']) / max(1, sum(1 for t in trades if t.get('is_retest'))) * 100
noret_wr = sum(1 for t in trades if not t.get('is_retest') and t['won']) / max(1, sum(1 for t in trades if not t.get('is_retest'))) * 100
retest_cnt = sum(1 for t in trades if t.get('is_retest'))
noret_cnt = sum(1 for t in trades if not t.get('is_retest'))
print(f"  重测(反弹确认): {retest_cnt}笔, WR={retest_wr:.1f}%")
print(f"  非重测(直接入场): {noret_cnt}笔, WR={noret_wr:.1f}%")

# POI激活分析
poi_wr = sum(1 for t in trades if t.get('poi_activated') and t['won']) / max(1, sum(1 for t in trades if t.get('poi_activated'))) * 100
nopoi_wr = sum(1 for t in trades if not t.get('poi_activated') and t['won']) / max(1, sum(1 for t in trades if not t.get('poi_activated'))) * 100
print(f"  POI激活: {sum(1 for t in trades if t.get('poi_activated'))}笔, WR={poi_wr:.1f}%")
print(f"  POI未激活: {sum(1 for t in trades if not t.get('poi_activated'))}笔, WR={nopoi_wr:.1f}%")

print("\n" + "="*70)
print("分析完成")
print("="*70)