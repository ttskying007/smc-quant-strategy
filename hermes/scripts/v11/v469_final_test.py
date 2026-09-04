#!/usr/bin/env python3
"""V469_final 200-stock test — V468 entry + graded trailing"""
import sys, json
sys.path.insert(0, '/root/.hermes/scripts')
import v11.v469_final as eng

symbols = sorted([f.stem.replace('_60min_200', '').replace('_', '.')
                 for f in eng.CACHE_DIR.glob('*_60min_200.json')])[:200]

eng.MIN_PROJECTED_RR = 6.0
eng.SWING_SKIP = 3
eng.POI_RETRACE_WINDOW = 50
eng.SL_MIN = 0.30

result = eng.run_backtest(symbols, "V469-final-200")

if result and result.get('all_trades'):
    trades = result['all_trades']
    n = len(trades)
    wins = sum(1 for t in trades if t['won'])
    wins_all = sum(1 for t in trades if t['won'])
    rr_all = sum(t['rr'] for t in trades)/n
    pnl_all = sum(t['pnl_pct'] for t in trades)/n
    
    print(f"\n{'='*70}")
    print(f"V469 FINAL 200-STOCK")
    print(f"{'='*70}")
    print(f"Stocks: {len(result['stock_results'])}/{len(symbols)}")
    print(f"Trades: {n} | WR: {wins_all/n*100:.1f}% | RR: {rr_all:.2f}x")
    print(f"P&L: {pnl_all:+.2f}% | Hold: {sum(t['hold_bars'] for t in trades)/n:.1f}b")
    
    print(f"\nGrade breakdown:")
    for g in ['A','B','C']:
        gt = [t for t in trades if t.get('signal_grade')==g]
        if gt:
            gw = sum(1 for t in gt if t['won'])/len(gt)*100
            gr = sum(t['rr'] for t in gt)/len(gt)
            gh = sum(t['hold_bars'] for t in gt)/len(gt)
            gp = sum(t['pnl_pct'] for t in gt)/len(gt)
            print(f"  Grade {g}: n={len(gt):3d} WR={gw:.1f}% RR={gr:.2f}x P&L={gp:+.2f}% hold={gh:.1f}b")
    
    # Save
    out_path = '/root/.hermes/smc_opt_v469'
    trade_map = {}
    offset = 0
    for sr in result['stock_results']:
        trade_map[sr['symbol']] = trades[offset:offset+sr['n_trades']]
        offset += sr['n_trades']
    json.dump(trade_map, open(f'{out_path}/v469_trade_map.json','w'))
    result['stock_results'].sort(key=lambda r: -r['n_trades'])
    json.dump(result['stock_results'], open(f'{out_path}/v469_stocks.json','w'))
    json.dump(trades, open(f'{out_path}/v469_trades.json','w'))
    
    print(f"\n{'='*70}")
    print(f"VS V468 (200st, MIN_PROJECTED_RR=6.0):")
    print(f"  V468: 16st 35t WR=68.6% RR=6.77x P&L=+2.54%")
    print(f"  V469: {len(result['stock_results'])}st {n}t WR={wins_all/n*100:.1f}% RR={rr_all:.2f}x P&L={pnl_all:+.2f}%")
