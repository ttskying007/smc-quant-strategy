#!/usr/bin/env python3
"""Signal timing and sequence analysis for SMC V11.3"""
import json
from collections import defaultdict, Counter

def analyze():
    # Load v3 data (multi-seq backtest)
    data = json.load(open('/root/.hermes/smc_opt_v11/backtest_v11_v3.json'))
    trades = data['all_trades']
    stocks = data['stocks']
    
    seq_trades = defaultdict(list)
    for t in trades:
        seq = t.get('seq_name', '?')
        seq_trades[seq].append(t)
    
    print("=" * 65)
    print("SMC V11 Signal Timing Analysis — v3 baseline (1113 trades)")
    print("=" * 65)
    print()
    
    print("=== Sequence Type WR Breakdown ===")
    for seq, ts in sorted(seq_trades.items(), key=lambda x: -len(x[1])):
        wins = sum(1 for t in ts if t['won'])
        wr = wins/len(ts)*100
        hold = sum(t['hold_bars'] for t in ts)/len(ts)
        avg_pnl = sum(t['pnl_pct'] for t in ts)/len(ts)
        avg_rr = sum(t['rr'] for t in ts)/len(ts)
        print(f"  {seq:20s}: n={len(ts):4d} WR={wr:5.1f}% RR={avg_rr:5.2f}x PL={avg_pnl:+.2f}% hold={hold:.1f}b")
    
    print()
    print("=== Silver WR by Stock Phase ===")
    silver_trades = seq_trades.get('LONG_SILVER_A', [])
    if silver_trades:
        # Map trades to stock phase
        # v3 all_trades indexed by stock order
        offset = 0
        for s in stocks:
            n = s['n_trades']
            stock_trades = trades[offset:offset+n]
            offset += n
            silver_in_stock = [t for t in stock_trades if t.get('seq_name') == 'LONG_SILVER_A']
            if silver_in_stock:
                wins = sum(1 for t in silver_in_stock if t['won'])
                wr = wins/len(silver_in_stock)*100
                print(f"  {s['symbol']:10s}: {len(silver_in_stock):3d} trades WR={wr:5.1f}% phase={s.get('phase','?')}")
    
    print()
    print("=== Scout FVG WR by Stock Phase ===")
    offset = 0
    for s in stocks:
        n = s['n_trades']
        stock_trades = trades[offset:offset+n]
        offset += n
        scout_in_stock = [t for t in stock_trades if t.get('seq_name') == 'LONG_SCOUT_FVG']
        if scout_in_stock:
            wins = sum(1 for t in scout_in_stock if t['won'])
            wr = wins/len(scout_in_stock)*100
            print(f"  {s['symbol']:10s}: {len(scout_in_stock):3d} trades WR={wr:5.1f}% phase={s.get('phase','?')}")
    
    print()
    print("=" * 65)
    print("SMC V11.3 Final Result Analysis — 470 trades, WR=73.0%")
    print("=" * 65)
    
    v7 = json.load(open('/root/.hermes/smc_opt_v11/backtest_v11_v7.json'))
    trades7 = v7['all_trades']
    stocks7 = v7['stocks']
    
    print(f"\nTotal: {len(trades7)} trades, {len(stocks7)} tradable stocks")
    
    # Winners vs Losers detail
    wins7 = [t for t in trades7 if t['won']]
    losses7 = [t for t in trades7 if not t['won']]
    
    print(f"\n=== Winners (n={len(wins7)}) ===")
    hold_w = Counter(t['hold_bars'] for t in wins7)
    print(f"  Hold bars: {dict(sorted(hold_w.most_common(5)))}")
    conf_w = Counter(t.get('confidence', 0) for t in wins7)
    print(f"  Confidence: {dict(sorted(conf_w.most_common(5)))}")
    
    print(f"\n=== Losers (n={len(losses7)}) ===")
    hold_l = Counter(t['hold_bars'] for t in losses7)
    print(f"  Hold bars: {dict(sorted(hold_l.most_common(5)))}")
    conf_l = Counter(t.get('confidence', 0) for t in losses7)
    print(f"  Confidence: {dict(sorted(conf_l.most_common(5)))}")
    
    print(f"\n=== Signal Type Distribution ===")
    sig_dist = Counter(t.get('seq_name', '?') for t in trades7)
    for sig, cnt in sig_dist.most_common():
        wins = sum(1 for t in trades7 if t.get('seq_name') == sig and t['won'])
        print(f"  {sig:20s}: n={cnt:4d} WR={wins/cnt*100:.1f}%")
    
    print(f"\n=== Resonance Grade (v7) ===")
    grade_dist = Counter(t.get('resonance_grade', '?') for t in trades7)
    for g, cnt in grade_dist.most_common():
        wins = sum(1 for t in trades7 if t.get('resonance_grade') == g and t['won'])
        print(f"  Grade {g:5s}: n={cnt:4d} WR={wins/cnt*100:.1f}%")
    
    print(f"\n=== Per-Stock Summary ===")
    high_wr80 = [s for s in stocks7 if s['win_rate'] >= 80]
    med_wr = [s for s in stocks7 if 60 <= s['win_rate'] < 80]
    low_wr = [s for s in stocks7 if s['win_rate'] < 60]
    
    print(f"  WR>=80%: {len(high_wr80)} stocks")
    print(f"  WR 60-80%: {len(med_wr)} stocks")
    print(f"  WR <60%: {len(low_wr)} stocks")
    
    print(f"\n  Top 10 high-WR:")
    for s in sorted(stocks7, key=lambda x: -x['win_rate'])[:10]:
        print(f"    {s['symbol']:10s} WR={s['win_rate']:5.1f}% n={s['n_trades']:3d} RR={s['avg_rr']:.2f}x phase={s.get('phase','?'):15s}")
    
    print(f"\n  Bottom 10 low-WR:")
    for s in sorted(stocks7, key=lambda x: x['win_rate'])[:10]:
        print(f"    {s['symbol']:10s} WR={s['win_rate']:5.1f}% n={s['n_trades']:3d} RR={s['avg_rr']:.2f}x phase={s.get('phase','?'):15s}")
    
    print(f"\n=== Phase Distribution (V11.3) ===")
    phase_dist = Counter(s.get('phase', '?') for s in stocks7)
    for p, cnt in phase_dist.most_common():
        wr_list = [s['win_rate'] for s in stocks7 if s.get('phase') == p]
        print(f"  {p:15s}: {cnt:3d} stocks avg_WR={sum(wr_list)/len(wr_list):.1f}%")
    
    print(f"\n=== Signal Density vs WR (V11.3) ===")
    density_buckets = [(0,50), (50,80), (80,110), (110,150), (150,999)]
    for lo, hi in density_buckets:
        subset = [s for s in stocks7 if lo <= s.get('n_signals', 0) < hi]
        if subset:
            avg_wr = sum(s['win_rate'] for s in subset) / len(subset)
            avg_n = sum(s['n_trades'] for s in subset) / len(subset)
            print(f"  signals [{lo:3d}-{hi:3d}): {len(subset):3d} stocks avg_WR={avg_wr:.1f}% avg_trades={avg_n:.1f}")

if __name__ == '__main__':
    analyze()
