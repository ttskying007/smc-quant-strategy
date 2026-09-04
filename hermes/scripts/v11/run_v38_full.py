#!/usr/bin/env python3
"""V38全量4800扫描包装器"""
import sys, json, time
from pathlib import Path
from collections import Counter

# Must set MAX_STOCKS before importing from v11
sys.path.insert(0, '/root/.hermes/scripts')
import v11.rolling_backtest_v38 as bt38

# Override
bt38.MAX_STOCKS = 4800

# Re-import common names
CACHE_DIR = bt38.CACHE_DIR
OUTPUT_DIR = bt38.OUTPUT_DIR
load_ohlcv = bt38.load_ohlcv
backtest_stock_v38 = bt38.backtest_stock_v38

def run_full():
    symbols = sorted([f.stem.replace('_daily_300', '').replace('_', '.')
                      for f in CACHE_DIR.glob('*_daily_300.json')])
    
    print("=" * 80)
    print(f"V38 — 全量4800扫描 ({len(symbols)} stocks)")
    print("=" * 80)
    
    all_trades, stock_results = [], []
    t_start = time.time()
    sl_type_stats = Counter()
    entry_type_stats = Counter()
    direction_stats = Counter()
    phase_stats = Counter()
    wr_dist = Counter()
    
    for idx, sym in enumerate(symbols):
        ohlcv = load_ohlcv(sym)
        if not ohlcv:
            continue
        
        result = backtest_stock_v38(ohlcv, sym)
        if result:
            p = result['perf']
            for k, v in p.get('sl_types', {}).items():
                sl_type_stats[k] += v
            for k, v in p.get('entry_types', {}).items():
                entry_type_stats[k] += v
            for k, v in p.get('directions', {}).items():
                direction_stats[k] += v
            phase_stats[p.get('phase', 'unknown')] += 1
            
            wr_bucket = (p['win_rate'] // 10) * 10
            wr_dist[wr_bucket] += 1
            
            all_trades.extend(result['trades'])
            stock_results.append({'symbol': sym, **p})
            
            if (idx + 1) % 500 == 0:
                elapsed = time.time() - t_start
                pct = (idx + 1) / len(symbols) * 100
                print(f"  [{idx+1}/{len(symbols)}] {pct:.0f}% | {elapsed:.0f}s | "
                      f"{len(stock_results)} tradable | {len(all_trades)} trades")
        
        if (idx + 1) % 100 == 0:
            time.sleep(0.1)
    
    total_time = time.time() - t_start
    
    if all_trades:
        n = len(all_trades)
        wins = sum(1 for t in all_trades if t['won'])
        wr = wins / n * 100
        wp = sum(t['pnl_pct'] for t in all_trades if t['won'])
        lp = abs(sum(t['pnl_pct'] for t in all_trades if not t['won']))
        pf = wp / lp if lp > 0 else 999
        rr = sum(t['rr'] for t in all_trades) / n
        pnl = sum(t['pnl_pct'] for t in all_trades) / n
        holds = [t['hold_bars'] for t in all_trades]
        
        print(f"\n{'='*80}")
        print(f"V38 FULL — {len(stock_results)}/{len(symbols)} tradable | {total_time:.0f}s")
        print(f"{'='*80}")
        print(f"  Trades: {n} | WR: {wr:.1f}% | RR: {rr:.2f}x | PF: {pf:.0f}")
        print(f"  Avg P&L: {pnl:+.2f}% | Avg hold: {sum(holds)/len(holds):.1f} bars | Max: {max(holds)}")
        print(f"  WR>=80%: {sum(1 for s in stock_results if s['win_rate']>=80)}/{len(stock_results)}")
        
        print(f"\n  Direction breakdown:")
        for d, cnt in direction_stats.most_common():
            d_trades = [t for t in all_trades if t.get('direction') == d]
            d_wr = sum(1 for t in d_trades if t['won']) / len(d_trades) * 100
            d_rr = sum(t['rr'] for t in d_trades) / len(d_trades)
            print(f"    {d:12s}: {cnt:6d} | WR={d_wr:.1f}% | avgRR={d_rr:.2f}x")
        
        print(f"\n  Entry type breakdown:")
        for et, cnt in entry_type_stats.most_common():
            et_trades = [t for t in all_trades if t.get('entry_type') == et]
            et_wr = sum(1 for t in et_trades if t['won']) / len(et_trades) * 100
            et_rr = sum(t['rr'] for t in et_trades) / len(et_trades)
            print(f"    {et:15s}: {cnt:6d} | WR={et_wr:.1f}% | avgRR={et_rr:.2f}x")
        
        print(f"\n  WR distribution:")
        for bucket in sorted(wr_dist.keys()):
            print(f"    WR {bucket:3.0f}-{bucket+9}%: {wr_dist[bucket]:4d} stocks")
        
        print(f"\n  SL Type breakdown:")
        for st, cnt in sl_type_stats.most_common():
            st_trades = [t for t in all_trades if t.get('sl_type') == st]
            st_wr = sum(1 for t in st_trades if t['won']) / len(st_trades) * 100
            st_avg = sum(t['pnl_pct'] for t in st_trades) / len(st_trades)
            print(f"    {st:20s}: {cnt:6d} ({cnt/n*100:5.1f}%) | WR={st_wr:.1f}% | avgP&L={st_avg:+.2f}%")
        
        output = {
            'config': 'V38 FULL 4800',
            'summary': {
                'n_stocks': len(stock_results),
                'n_trades': n,
                'win_rate': round(wr, 1),
                'avg_rr': round(rr, 2),
                'profit_factor': round(pf, 2),
                'avg_pnl': round(pnl, 2),
                'direction_breakdown': dict(direction_stats),
                'entry_type_breakdown': dict(entry_type_stats),
                'wr_distribution': {str(k): v for k, v in sorted(wr_dist.items())},
            },
            'stock_results': stock_results,
        }
        outpath = OUTPUT_DIR / 'backtest_v38_full.json'
        outpath.write_text(json.dumps(output, ensure_ascii=False, indent=1))
        print(f"\n  Saved: {outpath}")
    
    print()

if __name__ == '__main__':
    run_full()
