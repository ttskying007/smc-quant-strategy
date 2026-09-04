#!/usr/bin/env python3
"""Compare V11 vs V12 all signals on 20 stocks."""
import json, os, sys
sys.path.insert(0, '/root/.hermes/scripts/v11')

cache = '/root/.hermes/kline_cache_60min'
stocks = [f.split('_60min_200.json')[0] for f in os.listdir(cache) if f.endswith('_60min_200.json')][:20]

# Load engines
from signals_v11 import detect_all_signals_v11
from signals_v12 import detect_all_signals_v12

def load_kline(code):
    """Load kline from cache."""
    path = os.path.join(cache, f'{code}_60min_200.json')
    with open(path) as f:
        raw = json.load(f)
    return raw if isinstance(raw, list) else raw.get('data', raw.get('klines', raw))

# Signal type mapping
signal_types = ['FVG_Bull', 'FVG_Bear', 'OB_Bull', 'OB_Bear', 'Sweep',
                'CHOCH_Bull', 'CHOCH_Bear', 'BOS_Bull', 'BOS_Bear',
                'EQL_High', 'EQL_Low', 'BPR', 'IFVG_Bull', 'IFVG_Bear',
                'LiquidityVoid', 'RejectionBlock', 'FVG_Mitigated',
                'BreakerBlock', 'OTE', 'PO3']

print(f"{'Code':>8} {'Bars':>5} {'SigType':>18} {'V11':>6} {'V12':>6} {'Ratio':>7}")
print('-'*55)

# Per-signal type aggregation
sig_totals = {st: [0, 0] for st in signal_types}
stock_count = 0

for code in stocks:
    ohlcv = load_kline(code)
    r11 = detect_all_signals_v11(ohlcv)
    r12 = detect_all_signals_v12(ohlcv)
    n = len(ohlcv)

    for st in signal_types:
        c11 = len(r11.get(st, []))
        c12 = len(r12.get(st, []))
        sig_totals[st][0] += c11
        sig_totals[st][1] += c12

    stock_count += 1
    if stock_count <= 5:
        print(f"{code:>8} {n:>5} {'ALL':>18} {len(r11['all']):>6} {len(r12['all']):>6} {len(r12['all'])/max(len(r11['all']),1):>7.2f}x")

print('-'*55)
print(f"{'TOTAL':>8} {'':>5} {'':>18} {'':>6} {'':>6} {'':>7}")
print('-'*55)

for st in signal_types:
    v11, v12 = sig_totals[st]
    ratio = v12 / max(v11, 1)
    bar = '█' * int(min(30, ratio * 10))
    print(f"{'':>8} {'':>5} {st:>18} {v11:>6} {v12:>6} {ratio:>6.2f}x {bar}")

print()
total_v11 = sum(sig_totals[st][0] for st in signal_types)
total_v12 = sum(sig_totals[st][1] for st in signal_types)
print(f"Total all signals: V11={total_v11}  V12={total_v12}  ratio={total_v12/max(total_v11,1):.2f}x")
