#!/usr/bin/env python3
"""Check per-stock per-signal duplicates in V13 fallback."""
import json
from collections import defaultdict
from pathlib import Path

# Load V474 stock-level results
stocks_file = '/root/.hermes/smc_opt_v474/v45_full_stocks.json'
stocks = json.loads(Path(stocks_file).read_bytes())

print(f'Stocks with trades: {len(stocks)}')

total_dup_stocks = 0
total_dup_trades = 0
dup_ratios = []

for sym, data in stocks.items():
    trades = data.get('trades', [])
    if not trades:
        continue
    
    # Group trades by entry_idx (candle position)
    by_idx = defaultdict(list)
    for t in trades:
        by_idx[t['entry_idx']].append(t)
    
    # Find duplicate entry_idx
    dupes = {k: v for k, v in by_idx.items() if len(v) > 1}
    
    if dupes:
        total_dup_stocks += 1
        dup_count = sum(len(v) for v in dupes.values())
        total_dup_trades += dup_count
        
        if len(dup_ratios) < 20:
            prices_info = []
            for idx, td in sorted(dupes.items()):
                prices = set(round(t['entry_price'],4) for t in td)
                directions = set(t.get('direction','?') for t in td)
                prices_str = f'same={list(prices)[0]}' if len(prices)==1 else f'DIFF:{sorted(prices)[:5]}...'
                prices_info.append(f'  idx={idx}: {len(td)}x dir={directions} {prices_str}')
            
            all_dup_trades = sum(len(v) for v in dupes.values())
            ratio = all_dup_trades / len(trades) * 100
            dup_ratios.append((ratio, sym, all_dup_trades, len(trades), prices_info))

dup_ratios.sort(reverse=True)

print(f'Stocks with duplicate entry_idx trades: {total_dup_stocks}/{len(stocks)} ({total_dup_stocks/len(stocks)*100:.1f}%)')
print(f'Total duplicate trades: {total_dup_trades}')
print(f'Total all trades: {sum(len(s.get("trades",[])) for s in stocks.values())}')
print()

print('--- Top 20 stocks by duplicate ratio ---')
for ratio, sym, dup, total, prices in dup_ratios[:20]:
    print(f'{sym}: {dup}/{total} trades dup ({ratio:.1f}%)')
    for p in prices[:4]:
        print(f'  {p}')
    if len(prices) > 4:
        print(f'  ... +{len(prices)-4} more entry_idx groups')
    print()
