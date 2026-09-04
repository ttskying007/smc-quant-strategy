#!/usr/bin/env python3
"""
ETF & Index Scanner — V16 Strategy on ETFs + Indices
======================================================
Scan all A-share ETFs (510xxx-519xxx, 56xxxx-58xxxx, 15xxxx)
and major indices.
"""
import sys, json
sys.path.insert(0, '/root/.hermes/scripts')

from pathlib import Path
from v11.rolling_backtest_v15 import *
from collections import Counter

OUTPUT_DIR = Path('/root/.hermes/smc_opt_v16')
OUTPUT_DIR.mkdir(exist_ok=True)

# ETF patterns
ETF_PREFIXES = ['510', '511', '512', '513', '515', '516', '517', '518', '519',
                '560', '561', '562', '563', '588', '159', '520', '521', '528',
                '580', '581']

def is_etf(symbol):
    code = symbol.split('.')[0]
    for prefix in ETF_PREFIXES:
        if code.startswith(prefix):
            return True
    return False

def scan_etfs():
    symbols = sorted([f.stem.replace('_daily_300', '').replace('_', '.')
                      for f in CACHE_DIR.glob('*_daily_300.json')])
    
    etf_symbols = [s for s in symbols if is_etf(s)]
    index_symbols = [s for s in symbols if s.endswith('.SH') and s.startswith(('000', '399', '688'))][:20]
    # Actually, indices are SH000001 etc. Let me find them
    sh_index = [s for s in symbols if s.endswith('.SH') and s.startswith(('000',)) and len(s.split('.')[0]) <= 8]
    sz_index = [s for s in symbols if s.endswith('.SZ') and s.startswith(('399',))]
    all_indices = sh_index + sz_index
    
    print(f"{'='*80}")
    print(f"ETF & INDEX SCAN — V16 Strategy")
    print(f"  ETFs: {len(etf_symbols)} symbols")
    print(f"  Indices: {len(all_indices)} symbols")
    print(f"{'='*80}")
    
    results = []
    
    for sym in etf_symbols + all_indices:
        ohlcv = load_ohlcv(sym)
        if not ohlcv: continue
        result = backtest_stock(ohlcv, sym)
        trades = result.get('trades', [])
        perf = result.get('perf', {})
        
        cat = 'ETF' if is_etf(sym) else 'INDEX'
        
        if trades:
            results.append({'symbol': sym, 'category': cat, **perf,
                           'n_signals': result.get('n_signals', 0),
                           'phase': result.get('phase', '?')})
            sw_pct = perf.get('swing_sl_pct', 0)
            print(f"  {cat:5s} {sym:12s} trades={perf['n_trades']:2d} WR={perf['win_rate']:.0f}% "
                  f"RR={perf['avg_rr']:.1f}x PF={perf['profit_factor']:.1f} "
                  f"P&L={perf['avg_pnl']:+.2f}% swing={sw_pct:.0f}%")
        else:
            print(f"  {cat:5s} {sym:12s} NO-TRADE sigs={result.get('n_signals',0)} phase={result.get('phase','?')}")
    
    # Summary
    if results:
        print(f"\n{'='*80}")
        print(f"SUMMARY — {len(results)} tradable ETFs/Indices")
        print(f"{'='*80}")
        
        for cat in ['ETF', 'INDEX']:
            subset = [r for r in results if r['category'] == cat]
            if not subset: continue
            n = sum(r['n_trades'] for r in subset)
            wins = sum(r['wins'] for r in subset)
            wr = wins / n * 100 if n > 0 else 0
            avg_rr = sum(r['avg_rr'] for r in subset) / len(subset)
            print(f"  {cat}: {len(subset)} tradable, {n} trades, WR={wr:.1f}%, "
                  f"avg RR={avg_rr:.2f}x")
        
        # Save
        outpath = OUTPUT_DIR / 'v16_etf_indices.json'
        outpath.write_text(json.dumps({
            'timestamp': time.strftime('%Y-%m-%d %H:%M:%S'),
            'config': {'version': 'V16'},
            'results': results,
        }, ensure_ascii=False, indent=2, default=str))
        print(f"\n  Saved: {outpath}")

if __name__ == '__main__':
    scan_etfs()
