#!/usr/bin/env python3
"""V469v3 200-stock test — cleaned entry + graded trailing"""
import sys, json
sys.path.insert(0, '/root/.hermes/scripts')
import v11.v469_engine as eng

symbols = sorted([f.stem.replace('_60min_200', '').replace('_', '.')
                 for f in eng.CACHE_DIR.glob('*_60min_200.json')])[:200]

eng.MIN_PROJECTED_RR = 5.0
eng.SWING_SKIP = 3
eng.POI_RETRACE_WINDOW = 50
eng.SL_MIN = 0.30
eng.TRAIL_BE = 8.0

result = eng.run_backtest(symbols, "V469v3-200")

if result and result.get('all_trades'):
    trades = result['all_trades']
    n = len(trades)
    wins = sum(1 for t in trades if t['won'])
    
    print(f"\n{'='*70}")
    print(f"V469v3 200-STOCK FINAL — MIN_PROJECTED_RR=5.0")
    print(f"{'='*70}")
    print(f"Stocks: {len(result['stock_results'])}/{len(symbols)}")
    print(f"Trades: {n} | WR: {wins/n*100:.1f}% | RR: {sum(t['rr'] for t in trades)/n:.2f}x")
    print(f"P&L: {sum(t['pnl_pct'] for t in trades)/n:+.2f}%")
    print(f"Avg hold: {sum(t['hold_bars'] for t in trades)/n:.1f}b")
    
    print(f"\nGrade breakdown:")
    for g in ['A','B','C']:
        gt = [t for t in trades if t.get('signal_grade')==g]
        if gt:
            gw = sum(1 for t in gt if t['won'])/len(gt)*100
            gr = sum(t['rr'] for t in gt)/len(gt)
            gh = sum(t['hold_bars'] for t in gt)/len(gt)
            gp = sum(t['pnl_pct'] for t in gt)/len(gt)
            print(f"  Grade {g}: n={len(gt):3d} WR={gw:.1f}% RR={gr:.2f}x P&L={gp:+.2f}% hold={gh:.1f}b")
    
    # Save for V9 comparison
    out_path = '/root/.hermes/smc_opt_v469'
    json.dump(result['stock_results'], open(f'{out_path}/v469v3_stocks.json','w'))
    json.dump(trades, open(f'{out_path}/v469v3_trades.json','w'))
    
    print(f"\n{'='*70}")
    print("COMPARISON:")
    print(f"  V468:    16st 35t WR=68.6% RR=6.77x P&L=+2.54%")
    print(f"  V469v2:  9st 20t WR=55.0% RR=4.51x P&L=+2.17%")
    print(f"  V469v3:  {len(result['stock_results'])}st {n}t WR={wins/n*100:.1f}% RR={sum(t['rr'] for t in trades)/n:.2f}x P&L={sum(t['pnl_pct'] for t in trades)/n:+.2f}%")
