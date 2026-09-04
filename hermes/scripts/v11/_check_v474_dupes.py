#!/usr/bin/env python3
"""Check V474 for same-time different-price trades (signal redundancy)."""
import json
from collections import defaultdict

with open('/root/.hermes/smc_opt_v474/v45_full.json') as f:
    trades = json.load(f)

groups = defaultdict(list)
for t in trades:
    # trades don't have symbol in v45_full format, group by entry_idx instead
    key = (t['confirmed_at'], t.get('direction', 'bull'))
    groups[key].append(t)

dupes = {k: v for k, v in groups.items() if len(v) > 1}
print(f'Total trades: {len(trades)}')
print(f'Unique (time, dir) groups: {len(groups)}')
print(f'Groups with 2+ trades: {len(dupes)}')

multi = [(len(v), k) for k, v in dupes.items()]
multi.sort(reverse=True)

same_price = 0
diff_price = 0
print()
print('--- Top 20 duplicate groups ---')
for count, key in multi[:20]:
    v = dupes[key]
    prices = [round(t['entry_price'], 4) for t in v]
    unique_prices = set(prices)
    entry_idxs = [t['entry_idx'] for t in v]
    pnls = [f'{t["pnl_pct"]:+.2f}%' for t in v]
    if len(unique_prices) == 1:
        label = f'same={unique_prices.pop():.4f}'
        same_price += 1
    else:
        label = f'DIFF: {sorted(unique_prices)}'
        diff_price += 1
    print(f'  {count}x @ entry_idx={entry_idxs} | {label} | P&L={pnls}')

print(f'\nSame-price duplicates: {same_price}')
print(f'Different-price duplicates: {diff_price}')
print(f'Diff-price ratio: {diff_price/max(1,len(dupes))*100:.1f}% of all duplicate groups')
