#!/usr/bin/env python3
"""Run 200-stock test for V13 param tuning. Called by _v13_tune.py"""
import sys, json, time
from pathlib import Path
sys.path.insert(0, '/root/.hermes/scripts/v11')

# Get first 200 symbols from the v474 engine
v474 = __import__('v474_engine')
symbols = v474.load_symbols()[:200]  # first 200

from v11.v474_engine import load_ohlcv, calc_stock_params_v45, evaluate_v45_entry, backtest_stock_v45
# Re-import signal detection to pick up patched params
from v11.signals_v12 import detect_all_signals_v13_60min

trades_all = []
stocks_ok = 0

for sym in symbols:
    ohlcv = load_ohlcv(sym)
    if not ohlcv or len(ohlcv) < 60:
        continue
    n = len(ohlcv)
    stock_params = calc_stock_params_v45(ohlcv, sym)
    base_params = {'fvg_min_width': None, 'sweep_lookback': 12}
    
    signals_result = detect_all_signals_v13_60min(ohlcv, params=base_params, tf='60min')
    all_signals = signals_result.get('all', [])
    
    if not all_signals or len(all_signals) < 3:
        continue
    
    # Count OB count for coverage tracking
    ob_count = sum(1 for s in all_signals if 'OB' in str(s.get('type','') if isinstance(s,dict) else getattr(s,'type','')))
    
    trades, used_bars = [], set()
    direction = 'bull'
    
    for sig in all_signals:
        sig_idx = sig.get('idx', 0) if isinstance(sig, dict) else getattr(sig, 'idx', 0)
        sig_type = sig.get('type', '') if isinstance(sig, dict) else getattr(sig, 'type', '')
        
        if sig_type not in v474.TRADE_SIGNAL_TYPES:
            continue
        if 'OB' not in sig_type:
            continue
        if sig_idx < 40 or sig_idx >= n - 10:
            continue
        
        sigs_up_to = [s for s in all_signals if (s.get('idx',0) if isinstance(s,dict) else s.idx) <= sig_idx]
        result = evaluate_v45_entry(all_signals, sigs_up_to, sig, ohlcv, n,
                                     direction, base_params, stock_params)
        if result:
            if result['entry_idx'] in used_bars:
                continue
            used_bars.add(result['entry_idx'])
            trades.append(result)
    
    if len(trades) >= 2:
        stocks_ok += 1
        trades_all.extend(trades)

n = len(trades_all)
if n:
    wins = sum(1 for t in trades_all if t['won'])
    wr = wins / n * 100
    wp = sum(t['pnl_pct'] for t in trades_all if t['won'])
    lp = abs(sum(t['pnl_pct'] for t in trades_all if not t['won']))
    pf = wp / lp if lp > 0 else 999
    rr = sum(t['rr'] for t in trades_all) / n
    pnl = sum(t['pnl_pct'] for t in trades_all) / n
    print(f"Stocks: {stocks_ok}/200 | Trades: {n} | WR: {wr:.1f}% | RR: {rr:.2f}x | PF: {pf:.0f} | P&L: {pnl:+.2f}%")
else:
    print(f"Stocks: 0/200 | Trades: 0 | WR: 0.0% | RR: 0.00x | PF: 0 | P&L: +0.00%")
