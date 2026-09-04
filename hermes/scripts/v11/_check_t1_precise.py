"""精确T+1影响分析：用实际date字段"""
import json
from pathlib import Path
from datetime import datetime
from collections import Counter

V476_TRADES = Path('/root/.hermes/smc_opt_v476/v476_full.json')
CACHE_DIR = Path('/root/.hermes/kline_cache_60min')

trades = json.loads(V476_TRADES.read_text())

# 需要缓存每只股票的OHLCV来查找date
# 用第一个交易做示例分析
stock_trades = {}
for t in trades:
    sym = t.get('symbol', 'unknown')
    if sym not in stock_trades:
        stock_trades[sym] = []
    stock_trades[sym].append(t)

# 取前50只股票，比较index//4 vs date精确判断
date_same = 0
index_same = 0
total = 0
both_same = 0
examples = []

for sym, sts in stock_trades.items():
    fname = CACHE_DIR / f"{sym.replace('.','_')}_60min_200.json"
    if not fname.exists():
        continue
    ohlcv = json.loads(fname.read_text())
    
    for t in sts:
        total += 1
        ei, xi = t['entry_idx'], t['exit_idx']
        if ei >= len(ohlcv) or xi >= len(ohlcv):
            continue
        
        date_ei = ohlcv[ei]['date'][:10]  # YYYY-MM-DD
        date_xi = ohlcv[xi]['date'][:10]
        
        is_date_same = (date_ei == date_xi)
        is_index_same = (ei // 4) == (xi // 4)
        
        if is_date_same:
            date_same += 1
        if is_index_same:
            index_same += 1
        if is_date_same and is_index_same:
            both_same += 1
        
        if is_date_same != is_index_same and len(examples) < 5:
            examples.append({
                'symbol': sym,
                'entry_idx': ei, 'exit_idx': xi,
                'entry_date': date_ei,
                'exit_date': date_xi,
                'hold': t['hold_bars'],
                'entry_day': ohlcv[ei]['date'],
                'exit_day': ohlcv[xi]['date']
            })
        
        if total >= 2000:
            break
    if total >= 2000:
        break

print(f"分析 {total} 笔交易:")
print(f"  date精确判断同日: {date_same} ({date_same/total*100:.1f}%)")
print(f"  index//4判断同日: {index_same} ({index_same/total*100:.1f}%)")
print(f"  两者一致: {both_same} ({both_same/total*100:.1f}%)")
print(f"\n不一致示例:")
for ex in examples:
    print(f"  {ex['symbol']}: entry_idx={ex['entry_idx']}({ex['entry_day']}) -> exit_idx={ex['exit_idx']}({ex['exit_day']}), hold={ex['hold']}bar")

print(f"\n=== date精确T+1分析 (全量) ===")
print(f"date_same: {date_same}")
print(f"跨日exit: {total-date_same}")

# 模拟T+1修正：如果同一天exit，强制到下一交易日第一根bar
print(f"\n=== 模拟T+1强制跨日退出 ===")
t1_corrected = 0
t1_corrected_won = 0
t1_corrected_pnl = 0
t1_corrected_rr = 0
t1_orig_pnl = 0

sample_count = 0
for sym, sts in stock_trades.items():
    fname = CACHE_DIR / f"{sym.replace('.','_')}_60min_200.json"
    if not fname.exists():
        continue
    ohlcv = json.loads(fname.read_text())
    
    for t in sts:
        ei, xi = t['entry_idx'], t['exit_idx']
        if ei >= len(ohlcv) or xi >= len(ohlcv):
            continue
        
        date_ei = ohlcv[ei]['date'][:10]
        date_xi = ohlcv[xi]['date'][:10]
        
        if date_ei == date_xi:
            # 同一天exit → 强制到下一交易日第一根bar
            next_day_idx = None
            for j in range(xi + 1, min(xi + 8, len(ohlcv))):
                if ohlcv[j]['date'][:10] != date_ei:
                    next_day_idx = j
                    break
            
            if next_day_idx is not None:
                next_bar = ohlcv[next_day_idx]
                # 用次日开盘价退出
                new_exit_price = next_bar['o']
                entry_price = t['entry_price']
                sl_price = t['sl']
                
                new_pnl = (new_exit_price - entry_price) / entry_price * 100
                new_rr = abs(new_exit_price - entry_price) / abs(entry_price - sl_price) if entry_price != sl_price else 10
                new_won = new_exit_price > entry_price
                
                t1_corrected += 1
                t1_corrected_won += 1 if new_won else 0
                t1_corrected_pnl += new_pnl
                t1_corrected_rr += new_rr
                t1_orig_pnl += t['pnl_pct']
                
                if sample_count < 5:
                    print(f"  {sym}: entry={entry_price:.2f} orig_exit={t['exit_price']:.2f}({t['pnl_pct']:+.2f}%) -> next_open={new_exit_price:.2f}({new_pnl:+.2f}%) {'WIN' if new_won else 'LOSS'}")
                    sample_count += 1

if t1_corrected > 0:
    print(f"\nT+1修正统计 ({t1_corrected} 笔):")
    print(f"  原始平均PnL: {t1_orig_pnl/t1_corrected:+.2f}%")
    print(f"  修正后平均PnL: {t1_corrected_pnl/t1_corrected:+.2f}%")
    print(f"  修正后WR: {t1_corrected_won/t1_corrected*100:.1f}%")
    print(f"  修正后RR: {t1_corrected_rr/t1_corrected:.2f}x")
