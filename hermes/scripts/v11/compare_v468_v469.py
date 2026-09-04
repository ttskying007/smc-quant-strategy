#!/usr/bin/env python3
"""Compare V468 vs V469 on top 20 OB-rich stocks"""
import sys, json
sys.path.insert(0, '/root/.hermes/scripts')
from v11.v468_engine import CACHE_DIR, load_ohlcv
from v11.signals_v11 import detect_all_signals_v11

# Get top 20 stocks by OB_Bull count
results = []
for f in list(CACHE_DIR.glob('*_60min_200.json'))[:200]:
    sym = f.stem.replace('_60min_200', '').replace('_', '.')
    ohlcv = load_ohlcv(sym)
    if not ohlcv:
        continue
    base_params = {'fvg_min_width': None, 'sweep_lookback': 12}
    sigs = detect_all_signals_v11(ohlcv, params=base_params, tf='60min')
    all_sigs = sigs.get('all', [])
    bull_ob = sum(1 for s in all_sigs if 'OB_Bull' in s.get('type','') and s.get('idx',0) >= 40)
    results.append((bull_ob, sym))
results.sort(key=lambda x: -x[0])

top20 = [r[1] for r in results[:20]]
print(f"Top 20 signal-rich stocks: {top20}")
print()

# Test V468
print("="*70)
print("V468 BASELINE")
print("="*70)
import v11.v468_engine as v468
# Temporarily set MIN_PROJECTED_RR lower for V468 to get more trades
orig_rr = v468.MIN_PROJECTED_RR
v468.MIN_PROJECTED_RR = 6.0
v468.SWING_SKIP = 3
v468.POI_RETRACE_WINDOW = 50
v468.SL_MIN = 0.30
v468.TRAIL_BE = 8.0
r1 = v468.run_backtest(top20, "V468-top20")

if r1 and r1.get('all_trades'):
    trades1 = r1['all_trades']
    n1 = len(trades1)
    w1 = sum(1 for t in trades1 if t['won'])
    print(f"\nV468 BASELINE: {n1}t, {len(r1['stock_results'])}st, WR={w1/n1*100:.1f}%, RR={sum(t['rr'] for t in trades1)/n1:.2f}x")
    
# Test V469v2
print("="*70)
print("V469v2 — MULTI-SIGNAL + GRADED TRAILING")
print("="*70)
import v11.v469_engine as v469
v469.MIN_PROJECTED_RR = 6.0
v469.SWING_SKIP = 3
v469.POI_RETRACE_WINDOW = 50
v469.SL_MIN = 0.30
v469.TRAIL_BE = 8.0
r2 = v469.run_backtest(top20, "V469-top20")

if r2 and r2.get('all_trades'):
    trades2 = r2['all_trades']
    n2 = len(trades2)
    w2 = sum(1 for t in trades2 if t['won'])
    print(f"\nV469v2 TOTAL: {n2}t, {len(r2['stock_results'])}st, WR={w2/n2*100:.1f}%, RR={sum(t['rr'] for t in trades2)/n2:.2f}x")
    
    print(f"\nGrade breakdown:")
    for g in ['A','B','C']:
        gt = [t for t in trades2 if t.get('signal_grade')==g]
        if gt:
            gw = sum(1 for t in gt if t['won'])/len(gt)*100
            gr = sum(t['rr'] for t in gt)/len(gt)
            gh = sum(t['hold_bars'] for t in gt)/len(gt)
            print(f"  {g}: n={len(gt):2d} WR={gw:.1f}% RR={gr:.2f}x hold={gh:.1f}b")

# Compare
if r1 and r2:
    print(f"\n{'='*60}")
    print(f"COMPARISON (top 20 OB-rich stocks):")
    print(f"{'='*60}")
    s1, s2 = r1['summary'], r2['summary']
    print(f"  {'Metric':20s} {'V468':>12s} {'V469v2':>12s}")
    print(f"  {'-'*44}")
    print(f"  {'Stocks':20s} {s1['n_stocks']:>12d} {s2['n_stocks']:>12d}")
    print(f"  {'Trades':20s} {s1['n_trades']:>12d} {s2['n_trades']:>12d}")
    print(f"  {'WR':20s} {s1['win_rate']:>11.1f}% {s2['win_rate']:>11.1f}%")
    print(f"  {'RR':20s} {s1['avg_rr']:>11.2f}x {s2['avg_rr']:>11.2f}x")
    print(f"  {'P&L':20s} {s1['avg_pnl']:>+11.2f}% {s2['avg_pnl']:>+11.2f}%")
    print(f"  {'PF':20s} {s1['profit_factor']:>11.0f} {s2['profit_factor']:>11.0f}")
