#!/usr/bin/env python3
"""Check V38.4 JSON trade data structure"""
import json
data = json.loads(open('/root/.hermes/smc_opt_v38/backtest_v384_full.json', 'rb').read())

trades = data.get('trades', [])
print(f'Total trades in JSON: {len(trades)}')

stock_results = data.get('stock_results', [])
print(f'Stock results count: {len(stock_results)}')

if trades:
    t = trades[0]
    print(f'First trade keys: {list(t.keys())}')
    print(f'Has "symbol" key: {"symbol" in t}')
    print(f'Has "stock" key: {"stock" in t}')
elif stock_results:
    print(f'First stock keys: {list(stock_results[0].keys())}')
    if 'trades' in stock_results[0]:
        print(f'Trades in stock[0]: {len(stock_results[0]["trades"])}')
    
# Also check stock_results for entry_types structure
if stock_results:
    sr = stock_results[0]
    print(f'\nStock[0] sample:')
    print(f'  symbol: {sr.get("symbol")}')
    print(f'  entry_types: {sr.get("entry_types")}')
    print(f'  win_rate: {sr.get("win_rate")}')
    print(f'  avg_rr: {sr.get("avg_rr")}')

print(f'\nTotal file size: {len(open("/root/.hermes/smc_opt_v38/backtest_v384_full.json", "rb").read())} bytes')
