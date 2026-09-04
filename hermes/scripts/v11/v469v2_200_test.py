#!/usr/bin/env python3
"""V469v2 200-stock test + save results for V8 frontend"""
import sys, json, time
sys.path.insert(0, '/root/.hermes/scripts')
import v11.v469_engine as eng

# Use first 200 stocks
symbols = sorted([f.stem.replace('_60min_200', '').replace('_', '.')
                 for f in eng.CACHE_DIR.glob('*_60min_200.json')])[:200]

eng.MIN_PROJECTED_RR = 6.0
eng.SWING_SKIP = 3
eng.POI_RETRACE_WINDOW = 50
eng.SL_MIN = 0.30
eng.TRAIL_BE = 8.0

result = eng.run_backtest(symbols, "V469v2-200")

if result and result.get('all_trades'):
    stocks = result['stock_results']
    trades = result['all_trades']
    n = len(trades)
    wins = sum(1 for t in trades if t['won'])
    wr = wins/n*100
    rr = sum(t['rr'] for t in trades)/n
    pnl = sum(t['pnl_pct'] for t in trades)/n
    holds = [t['hold_bars'] for t in trades]
    
    print(f"\n{'='*70}")
    print(f"V469v2 200-STOCK FINAL")
    print(f"{'='*70}")
    print(f"Stocks traded: {len(stocks)}/{len(symbols)} ({len(stocks)/len(symbols)*100:.1f}%)")
    print(f"Trades: {n}")
    print(f"WR: {wr:.1f}% | RR: {rr:.2f}x | P&L: {pnl:+.2f}%")
    print(f"Avg hold: {sum(holds)/n:.1f}b | Max hold: {max(holds)}b")
    print(f"TP hit: {sum(1 for t in trades if t.get('exit_method')=='tp_hit')}/{n}")
    
    # Grade breakdown
    print(f"\nGrade breakdown:")
    for g in ['A','B','C']:
        gt = [t for t in trades if t.get('signal_grade')==g]
        if gt:
            gw = sum(1 for t in gt if t['won'])/len(gt)*100
            gr = sum(t['rr'] for t in gt)/len(gt)
            gh = sum(t['hold_bars'] for t in gt)/len(gt)
            gp = sum(t['pnl_pct'] for t in gt)/len(gt)
            print(f"  Grade {g}: n={len(gt):3d} WR={gw:.1f}% RR={gr:.2f}x P&L={gp:+.2f}% hold={gh:.1f}b")
    
    # Hold distribution
    hold_groups = {}
    for t in trades:
        h = t['hold_bars']
        if h <= 1: grp = '1'
        elif h <= 3: grp = '2-3'
        elif h <= 6: grp = '4-6'
        elif h <= 10: grp = '7-10'
        else: grp = '11+'
        hold_groups.setdefault(grp, []).append(t)
    
    print(f"\nHold distribution:")
    for grp in ['1','2-3','4-6','7-10','11+']:
        if grp in hold_groups:
            ht = hold_groups[grp]
            hw = sum(1 for t in ht if t['won'])/len(ht)*100
            hr = sum(t['rr'] for t in ht)/len(ht)
            print(f"  hold={grp:>4s}: {len(ht):3d} WR={hw:.1f}% RR={hr:.2f}x")
    
    # W/L ratio
    wn = sum(t['pnl_pct'] for t in trades if t['won']) / wins if wins > 0 else 0
    ls = abs(sum(t['pnl_pct'] for t in trades if not t['won'])) / (n - wins) if n > wins else 0
    print(f"\nW/L ratio: avgWin={wn:.3f}% avgLoss={ls:.3f}% ratio={wn/ls:.1f}x" if ls > 0 else "")
    
    # Save for V8
    result['stock_results'].sort(key=lambda r: -r['n_trades'])
    out_data = {
        'stock_results': result['stock_results'],
        'summary': result['summary'],
        'symbols': [r['symbol'] for r in result['stock_results']],
    }
    # Save trades per symbol
    trade_map = {}
    offset = 0
    for sr in result['stock_results']:
        n_t = sr['n_trades']
        trade_map[sr['symbol']] = trades[offset:offset+n_t]
        offset += n_t
    
    out_path = '/root/.hermes/smc_opt_v469'
    json.dump(out_data, open(f'{out_path}/v469_stocks.json', 'w'))
    json.dump(trades, open(f'{out_path}/v469_trades.json', 'w'))
    json.dump(trade_map, open(f'{out_path}/v469_trade_map.json', 'w'))
    print(f"\nSaved results to {out_path}/")
    
    print(f"\n{'='*70}")
    print(f"VS V468 (200-stock historical):")
    print(f"  V468: 16st 35t WR=68.6% RR=6.77x P&L=+2.54%")
    print(f"  V469: {len(stocks)}st {n}t WR={wr:.1f}% RR={rr:.2f}x P&L={pnl:+.2f}%")
