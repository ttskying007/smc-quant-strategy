#!/usr/bin/env python3
"""Debug: trace check_60min_support logic for one stock."""
import sys, json
sys.path.insert(0, '/root/.hermes/scripts')
from v11.klines_60min import get_60min_kline
from v11.signals_v11 import detect_all_signals_v11, calc_adaptive_thresholds
from v11.adaptive_params import calc_stock_params, detect_market_phase

symbol = '000001.SZ'

# Load daily data
daily = json.loads(open(f'/root/.hermes/kline_cache/000001_SZ_daily_300.json').read())
print(f"Daily bars: {len(daily)}")
print(f"Last daily bar: {daily[-1]}")

# Load 60min
bars_60 = get_60min_kline(symbol, force_refresh=False)

# Detect 60min signals
params_60 = calc_stock_params(bars_60, symbol, tf='60min')
result = detect_all_signals_v11(bars_60, params=params_60, tf='60min')
signals_60 = result['all']
print(f"\n60min total signals: {len(signals_60)}")

# Find the last daily bar date
last_daily_t = str(daily[-1]['t'])
print(f"Last daily date: {last_daily_t}")

# Find 60min index for last daily bar
from backtest_multitf_v37 import find_60min_index_for_daily
idx_60 = find_60min_index_for_daily(last_daily_t, bars_60)
print(f"60min index for {last_daily_t}: {idx_60}")

# Window
window_start = max(0, idx_60 - 50)
print(f"Window: [{window_start}, {idx_60}]")

# Find bull signals in window
window_sigs = []
for sig in signals_60:
    sig_idx = sig.get('idx', -1)
    if window_start <= sig_idx <= idx_60:
        direction = sig.get('direction', '')
        sig_type = sig.get('type', '')
        window_sigs.append((sig_idx, sig_type, direction))
        if direction == 'bull':
            pass  # We'll print them

print(f"\nAll signals in window ({len(window_sigs)}):")
for idx, typ, dir_ in window_sigs:
    print(f"  idx={idx:4d} {typ:20s} dir={dir_}")

# Now check each type
from collections import Counter
same_dir = [t for i, t, d in window_sigs if d == 'bull']
print(f"\nBull signals in window: {len(same_dir)}")
sig_counts = Counter(same_dir)
print(f"Signal type counts: {dict(sig_counts)}")

# Score calculation
score = 0.0
fvg_c = sig_counts.get('FVG_Bull', 0)
score += min(0.5, fvg_c * 0.15)
print(f"FVG_Bull({fvg_c}) -> +{min(0.5, fvg_c * 0.15):.3f}")

sweep_c = sig_counts.get('SweepDown', 0)
score += min(0.3, sweep_c * 0.1)
print(f"SweepDown({sweep_c}) -> +{min(0.3, sweep_c * 0.1):.3f}")

ob_c = sig_counts.get('OB_Bull', 0)
score += min(0.2, ob_c * 0.08)
print(f"OB_Bull({ob_c}) -> +{min(0.2, ob_c * 0.08):.3f}")

choch_c = sig_counts.get('CHOCH_Bull', 0)
score += min(0.3, choch_c * 0.12)
print(f"CHOCH_Bull({choch_c}) -> +{min(0.3, choch_c * 0.12):.3f}")

bpr_c = sig_counts.get('BPR_Bull', 0)
score += min(0.2, bpr_c * 0.1)
print(f"BPR_Bull({bpr_c}) -> +{min(0.2, bpr_c * 0.1):.3f}")

other_bull = sum(c for t, c in sig_counts.items()
                 if t not in ('FVG_Bull', 'SweepDown', 'OB_Bull', 'CHOCH_Bull', 'BPR_Bull')
                 and 'Bull' in t)
score += min(0.15, other_bull * 0.05)
print(f"other_bull({other_bull}) -> +{min(0.15, other_bull * 0.05):.3f}")

print(f"\nTotal score: {score:.3f}")
print(f"Supported: {score >= 0.15}")
