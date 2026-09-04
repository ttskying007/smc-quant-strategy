#!/usr/bin/env python3
"""深度追踪：OB边界、SL位置、ATR、entry_price 四者关系"""

import json, sys, math, os
from pathlib import Path
from collections import Counter

sys.path.insert(0, '/root/.hermes/scripts')
from v11.signals_v11 import detect_all_signals_v11

CACHE_DIR = Path('/root/.hermes/kline_cache_60min')
TRADES_FILE = Path('/root/.hermes/smc_opt_v477/v477_full.json')

# 加载交易数据
trades_data = json.loads(TRADES_FILE.read_text())
if isinstance(trades_data, dict):
    all_trades = trades_data.get('trades', [])
elif isinstance(trades_data, list):
    all_trades = trades_data
else:
    all_trades = []
print(f"总交易数: {len(all_trades)}")

# 按symbol分组
by_symbol = {}
for t in all_trades:
    sym = t.get('symbol', '')
    if sym not in by_symbol:
        by_symbol[sym] = []
    by_symbol[sym].append(t)

print(f"有交易的股票数: {len(by_symbol)}")

# ──────────────────────────────────────────────
# 【1】SL公式直接验证
# ──────────────────────────────────────────────
print("\n" + "="*80)
print("【1】SL公式验证 — 实际计算值 vs 理论最小值")
print("="*80)
sl_pcts = [t['sl_pct'] for t in all_trades]
sl_pct_counter = Counter(sl_pcts)
print(f"SL_pct分布 (前15个值):")
for val, cnt in sorted(sl_pct_counter.most_common(15)):
    print(f"  SL={val:.2f}%: {cnt}笔 ({cnt/len(all_trades)*100:.1f}%)")
    
# 0.15%占的比例
pct_015 = sum(1 for t in all_trades if t['sl_pct'] == 0.15)
print(f"\nSL=0.15% (floored): {pct_015}/{len(all_trades)} = {pct_015/len(all_trades)*100:.1f}%")

# ──────────────────────────────────────────────
# 【2】逐笔交易：OB边界 vs entry_price vs SL对比
# ──────────────────────────────────────────────
print("\n" + "="*80)
print("【2】OB边界 vs entry_price vs SL — 位置关系校验")
print("="*80)
print(f"采样前100笔交易 (按持股数排序):\n")

# 加载信号数据
def load_stock_kline(symbol):
    fname = f"{symbol.replace('.','_')}_60min_200.json"
    fpath = CACHE_DIR / fname
    if not fpath.exists():
        return None
    return json.loads(fpath.read_text())

def compute_atr(ohlcv, idx):
    if idx < 15:
        return (ohlcv[idx]['h'] - ohlcv[idx]['l']) / ohlcv[idx]['l'] * 100
    trs = []
    for i in range(max(1, idx - 14), idx + 1):
        h, l, pc = ohlcv[i]['h'], ohlcv[i]['l'], ohlcv[i-1]['c']
        trs.append(max(h - l, abs(h - pc), abs(l - pc)))
    avg_tr = sum(trs) / len(trs)
    return avg_tr / ohlcv[idx]['l'] * 100

sample_count = 0
issues = []  # 记录发现的问题

for sym, trades in sorted(by_symbol.items()):
    if sample_count >= 100:
        break
    
    ohlcv = load_stock_kline(sym)
    if not ohlcv:
        continue
    
    # 检测信号
    signals_result = detect_all_signals_v11(ohlcv, tf='60min')
    all_signals = signals_result.get('all', [])
    
    for t in sorted(trades, key=lambda x: x.get('entry_idx', 0)):
        if sample_count >= 100:
            break
        
        entry_idx = t.get('entry_idx', 0)
        sig_idx = t.get('sig_idx', entry_idx)
        entry_price = t.get('entry_price', 0)
        sl = t.get('sl', 0)
        sl_pct = t.get('sl_pct', 0.15)
        exit_price = t.get('exit_price', 0)
        hold = t.get('hold_bars', 0)
        won = t.get('won', False)
        rr = t.get('rr', 0)
        pnl = t.get('pnl_pct', 0)
        
        # 找对应的OB信号
        matching_sigs = [s for s in all_signals if s.get('type', '') == 'OB_Bull' and abs(s.get('idx', 0) - sig_idx) <= 3]
        if not matching_sigs:
            matching_sigs = [s for s in all_signals if 'OB' in s.get('type', '') and abs(s.get('idx', 0) - sig_idx) <= 3]
        
        if not matching_sigs:
            continue
        
        sig = matching_sigs[0]
        ob_lower = sig.get('lower', 0)
        ob_upper = sig.get('upper', 0)
        ob_idx = sig.get('idx', 0)
        ob_price = sig.get('price', 0)  # bar['l'] for bullish OB
        
        # ATR计算
        atr = compute_atr(ohlcv, entry_idx)
        
        # SL相对于entry的位置
        sl_distance_from_entry = (entry_price - sl) / entry_price * 100
        
        # entry相对于OB lower的位置
        if ob_lower > 0:
            entry_vs_ob_lower = (entry_price - ob_lower) / ob_lower * 100
            sl_vs_ob_lower = (sl - ob_lower) / ob_lower * 100 if ob_lower > 0 else 0
        
        atr_ratio = sl_pct / atr if atr > 0 else 0
        
        sample_count += 1
        
        # 检查异常情况
        if sl > entry_price:
            issues.append(f"{sym}: SL({sl}) > entry({entry_price}) — SL在entry之上")
        if entry_price < ob_lower * 0.99 and ob_lower > 0:
            issues.append(f"{sym}: entry({entry_price:.2f}) << OB_lower({ob_lower:.2f}) — 入场远低于OB支撑")
        if sl_pct == 0.15 and atr > 1.0:
            issues.append(f"{sym}: SL floored at 0.15%, ATR={atr:.2f}%, ratio={atr_ratio:.2f}x")
        
        # 取入入场前后K线
        start = max(0, ob_idx - 5)
        end = min(len(ohlcv), entry_idx + hold + 5)
        
        print(f"\n--- {sym} | OB_idx={ob_idx} entry_idx={entry_idx} hold={hold} | wr={'W' if won else 'L'} RR={rr:.1f}x PnL={pnl:+.2f}% ---")
        print(f"  OB: lower={ob_lower:.4f} upper={ob_upper:.4f} (区间宽度={(ob_upper-ob_lower)/ob_lower*100:.2f}%)")
        print(f"  Entry: {entry_price:.4f} (相对OB lower: {entry_vs_ob_lower:+.2f}%)")
        print(f"  SL: {sl:.4f} ({sl_pct:.2f}% below entry, 相对于OB lower: {sl_vs_ob_lower:+.2f}%)")
        print(f"  ATR(60min)={atr:.2f}% | SL/ATR={atr_ratio:.2f}x")
        
        for k in range(start, end):
            bar = ohlcv[k]
            marker = ""
            if k == ob_idx:
                marker = " <<< OB"
            elif k == entry_idx:
                marker = " <<< ENTRY"
            elif k == t.get('exit_idx', 0):
                marker = " <<< EXIT"
            print(f"  [{k:3d}] {bar['date']} O={bar['o']:.2f} H={bar['h']:.2f} L={bar['l']:.2f} C={bar['c']:.2f}{marker}")

# 报告问题
print("\n" + "="*80)
print("【3】发现的问题汇总")
print("="*80)
if issues:
    print(f"共发现 {len(issues)} 个问题:")
    for iss in sorted(set(issues)):
        print(f"  - {iss}")
else:
    print("无结构性位置异常")

# ──────────────────────────────────────────────
# 【4】全量：entry_price vs OB lower 统计
# ──────────────────────────────────────────────
print("\n" + "="*80)
print("【4】全量: entry_price vs OB lower 统计")
print("="*80)

all_entries = 0
entry_above_ob = 0
entry_at_ob = 0
entry_below_ob = 0
sl_below_ob = 0
sl_above_ob = 0

for sym, trades in sorted(by_symbol.items()):
    ohlcv = load_stock_kline(sym)
    if not ohlcv:
        continue
    signals_result = detect_all_signals_v11(ohlcv, tf='60min')
    all_signals = signals_result.get('all', [])
    
    for t in trades:
        sig_idx = t.get('sig_idx', 0)
        entry_price = t.get('entry_price', 0)
        sl = t.get('sl', 0)
        
        matching_sigs = [s for s in all_signals if 'OB' in s.get('type', '') and abs(s.get('idx', 0) - sig_idx) <= 3]
        if not matching_sigs:
            continue
        
        sig = matching_sigs[0]
        ob_lower = sig.get('lower', 0)
        
        all_entries += 1
        if ob_lower > 0 and entry_price > 0:
            diff = (entry_price - ob_lower) / ob_lower * 100
            if diff > 0.1:
                entry_above_ob += 1
            elif diff > -0.1:
                entry_at_ob += 1
            else:
                entry_below_ob += 1
            
            if sl < ob_lower:
                sl_below_ob += 1
            else:
                sl_above_ob += 1

print(f"可匹配OB的交易: {all_entries}")
if all_entries > 0:
    print(f"  入场 > OB.lower: {entry_above_ob} ({entry_above_ob/all_entries*100:.1f}%)")
    print(f"  入场 ≈ OB.lower: {entry_at_ob} ({entry_at_ob/all_entries*100:.1f}%)")
    print(f"  入场 < OB.lower: {entry_below_ob} ({entry_below_ob/all_entries*100:.1f}%)")
    print(f"  SL < OB.lower (合理): {sl_below_ob} ({sl_below_ob/all_entries*100:.1f}%)")
    print(f"  SL >= OB.lower (不合理): {sl_above_ob} ({sl_above_ob/all_entries*100:.1f}%)")

print("\n分析完成")
