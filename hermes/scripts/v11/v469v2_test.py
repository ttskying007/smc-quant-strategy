#!/usr/bin/env python3
"""V469v2 test — fixed sequence filter"""
import sys, json
sys.path.insert(0, '/root/.hermes/scripts')
import v11.v469_engine as eng

symbols = sorted([f.stem.replace('_60min_200', '').replace('_', '.')
                 for f in eng.CACHE_DIR.glob('*_60min_200.json')])[:20]

result = eng.run_backtest(symbols, "V469v2-20")

if result and result.get('all_trades'):
    trades = result['all_trades']
    stocks = result['stock_results']
    n = len(trades)
    wins = sum(1 for t in trades if t['won'])
    print(f"\n{'='*60}")
    print(f"V469v2 RESULTS: {n} trades, {len(stocks)} stocks")
    print(f"WR={wins/n*100:.1f}% RR={sum(t['rr'] for t in trades)/n:.2f}x")
    
    # Grade distribution
    print(f"\nGrade breakdown:")
    for g in ['A','B','C']:
        gt = [t for t in trades if t.get('signal_grade')==g]
        if gt:
            gw = sum(1 for t in gt if t['won'])/len(gt)*100
            gr = sum(t['rr'] for t in gt)/len(gt)
            print(f"  {g}: n={len(gt)} WR={gw:.1f}% RR={gr:.2f}x")
    
    # Hold distribution
    print(f"\nHold distribution:")
    for h in sorted(set(t['hold_bars'] for t in trades)):
        ht = [t for t in trades if t['hold_bars']==h]
        hw = sum(1 for t in ht if t['won'])/len(ht)*100
        hr = sum(t['rr'] for t in ht)/len(ht)
        print(f"  hold={h}b: {len(ht)} WR={hw:.1f}% RR={hr:.2f}x")
    
    # Save
    out = {'stock_results': stocks, 'all_trades': trades, 'summary': result['summary']}
    with open('/root/.hermes/smc_opt_v469/v469v2_20.json', 'w') as f:
        json.dump(out, f)
    print(f"\nSaved: /root/.hermes/smc_opt_v469/v469v2_20.json")
else:
    print("NO TRADES found")
