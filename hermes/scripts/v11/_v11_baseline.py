"""Run V467 (V11) on first 200 stocks for baseline comparison."""
import sys, json
sys.path.insert(0, '/root/.hermes/scripts')
from pathlib import Path
CACHE = Path('/root/.hermes/kline_cache_60min')
files = sorted(CACHE.glob('*_60min_200.json'))[:200]
SYMBOLS = [f.stem.replace('_60min_200','').replace('_','.') for f in files]

from v11.v467_engine import load_ohlcv, calc_stock_params_v45, evaluate_v45_entry, TRADE_SIGNAL_TYPES
from v11.signals_v11 import detect_all_signals_v11

trades_all, stocks_ok = [], 0
for sym in SYMBOLS:
    ohlcv = load_ohlcv(sym)
    if not ohlcv or len(ohlcv) < 60: continue
    n = len(ohlcv)
    stock_params = calc_stock_params_v45(ohlcv, sym)
    base_params = {'fvg_min_width': None, 'sweep_lookback': 12}
    sr = detect_all_signals_v11(ohlcv, params=base_params, tf='60min')
    all_sigs = sr.get('all', [])
    if not all_sigs or len(all_sigs) < 3: continue
    trades, used = [], set()
    for sig in all_sigs:
        si = sig.get('idx', 0) if isinstance(sig, dict) else getattr(sig, 'idx', 0)
        st = sig.get('type', '') if isinstance(sig, dict) else getattr(sig, 'type', '')
        if st not in TRADE_SIGNAL_TYPES: continue
        if 'OB' not in st: continue
        if si < 40 or si >= n - 10: continue
        su = [s for s in all_sigs if (s.get('idx',0) if isinstance(s,dict) else s.idx) <= si]
        r = evaluate_v45_entry(all_sigs, su, sig, ohlcv, n, 'bull', base_params, stock_params)
        if r:
            if r['entry_idx'] in used: continue
            used.add(r['entry_idx'])
            trades.append(r)
    if len(trades) >= 2:
        stocks_ok += 1
        trades_all.extend(trades)

n = len(trades_all)
wins = sum(1 for t in trades_all if t['won'])
wr = wins/n*100
wp = sum(t['pnl_pct'] for t in trades_all if t['won'])
lp = abs(sum(t['pnl_pct'] for t in trades_all if not t['won']))
pf = wp/lp if lp>0 else 999
rr = sum(t['rr'] for t in trades_all)/n
pnl = sum(t['pnl_pct'] for t in trades_all)/n
print(f"Baseline V11 (V467 engine) on 200 stocks:")
print(f"Stocks: {stocks_ok}/200 | Trades: {n} | WR: {wr:.1f}% | RR: {rr:.2f}x | PF: {pf:.0f} | P&L: {pnl:+.2f}%")
