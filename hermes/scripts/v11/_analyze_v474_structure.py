#!/usr/bin/env python3
"""Analyze V474 trade structure and find real duplicate patterns."""
import json
from collections import defaultdict

T = '/root/.hermes/smc_opt_v474/v45_full.json'
with open(T) as f:
    trades = json.load(f)

t = trades[0]
print('Trade keys:', list(t.keys()))
print('Sample trade:', {k:v for k,v in t.items() if k not in ['stop_info','tp_info']})
print()

# Look at the raw data
confirmed_counts = defaultdict(int)
for tr in trades:
    confirmed_counts[tr['confirmed_at']] += 1

print(f'Unique confirmed_at values: {len(confirmed_counts)}')
print(f'Total trades: {len(trades)}')
print()

# Show the "busiest" confirmed_at values
busy = sorted(confirmed_counts.items(), key=lambda x: -x[1])[:10]
print('--- Top 10 busiest confirmed_at values ---')
for ca, cnt in busy:
    samples = [tr for tr in trades if tr['confirmed_at'] == ca][:3]
    prices = set(tr['entry_price'] for tr in trades if tr['confirmed_at'] == ca)
    entry_idxs = set(tr['entry_idx'] for tr in trades if tr['confirmed_at'] == ca)
    msg = f'  confirmed_at={ca}: {cnt} trades, {len(prices)} unique prices, {len(entry_idxs)} unique entry_idx'
    print(msg)
    for s in samples:
        msg2 = f'    entry_idx={s["entry_idx"]} price={s["entry_price"]:.4f} pnl={s["pnl_pct"]:+.2f}%'
        print(msg2)

print()
print('--- Check: is confirmed_at the stock index or a timestamp? ---')
print(f'type: {type(trades[0]["confirmed_at"])}')
first10 = [t['confirmed_at'] for t in trades[:10]]
print(f'first 10: {first10}')
all_ca = [t['confirmed_at'] for t in trades]
print(f'range: {min(all_ca)} to {max(all_ca)}')

# If confirmed_at is a stock index (0-4551), then cross-stock duplicates are expected
# The real question: does the SAME stock have multiple trades at the SAME entry_idx?
# Without symbol in the flat file, I need to check the engine output
print()
print('--- Trade entry_idx distribution ---')
idx_counts = defaultdict(int)
for tr in trades:
    idx_counts[tr['entry_idx']] += 1
busy_idx = sorted(idx_counts.items(), key=lambda x: -x[1])[:10]
for idx, cnt in busy_idx:
    prices = set(tr['entry_price'] for tr in trades if tr['entry_idx'] == idx)
    print(f'  entry_idx={idx}: {cnt} trades, {len(prices)} unique prices')
