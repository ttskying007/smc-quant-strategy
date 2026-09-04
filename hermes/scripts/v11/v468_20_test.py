#!/usr/bin/env python3
"""V468 20-stock comprehensive test — verify A+D+C fixes"""
import sys, json
sys.path.insert(0, '/root/.hermes/scripts')
from v11.v468_engine import run_backtest, CACHE_DIR

symbols = sorted([f.stem.replace('_60min_200', '').replace('_', '.')
                 for f in CACHE_DIR.glob('*_60min_200.json')])[:20]

result = run_backtest(symbols, "V468-60min")

if not result or not result.get('all_trades'):
    print("NO TRADES FOUND")
    sys.exit(1)

trades = result['all_trades']
stocks = result['stock_results']
summary = result['summary']
n = len(trades)
wins = sum(1 for t in trades if t['won'])
wr = wins/n*100
rr = sum(t['rr'] for t in trades)/n
pnl = sum(t['pnl_pct'] for t in trades)/n

print(f"\n{'='*80}")
print(f"V468 RESULTS: {n} trades, {len(stocks)} stocks")
print(f"WR={wr:.1f}% RR={rr:.2f}x P&L={pnl:+.2f}%")
print(f"{'='*80}\n")

# FIX A: Check TP reachability
tp_reached = sum(1 for t in trades if t.get('exit_method') == 'tp_hit')
print(f"FIX A — Swing skip 8→3:")
print(f"  TP hit: {tp_reached}/{n} ({tp_reached/n*100:.1f}%)")
tp_types = {}
for t in trades:
    tt = t.get('tp_type', 'none')
    tp_types[tt] = tp_types.get(tt, 0) + 1
for tt, cnt in sorted(tp_types.items(), key=lambda x:-x[1]):
    print(f"  TP type {tt}: {cnt}")

# FIX D: Check entry pricing
print(f"\nFIX D — ENTRY_AT_ZONE (no 0.995 discount):")
fake_discounts = 0
honest_zone_entries = 0
close_entries = 0
for t in trades[:20]:
    entry = t['entry_price']
    sl = t['sl']
    sl_pct = t['sl_pct']
    entry_type = t['entry_type']
    # Check if entry matches OB lower approximately
    ratio = None
    print(f"  {t.get('entry_type','?'):12s} entry={entry:.2f} sl={sl:.2f} sl%={sl_pct:.2f}% hold={t['hold_bars']}b rr={t['rr']:.1f}x")

# FIX C: Check POI retrace
print(f"\nFIX C — POI retrace entry:")
poi_count = sum(1 for t in trades if t.get('poi_activated', False))
retrace_avg = sum(t.get('poiretrace_bars', 0) for t in trades) / n if n > 0 else 0
retrace_max = max(t.get('poiretrace_bars', 0) for t in trades)
print(f"  POI activated: {poi_count}/{n} ({poi_count/n*100:.1f}%)")
print(f"  Avg retrace wait: {retrace_avg:.1f} bars")
print(f"  Max retrace wait: {retrace_max} bars")
retrace_dist = {}
for t in trades:
    r = t.get('poiretrace_bars', 0)
    retrace_dist[r] = retrace_dist.get(r, 0) + 1
for r in sorted(retrace_dist.keys()):
    print(f"  wait={r}b: {retrace_dist[r]} trades")

# Hold bars distribution
print(f"\nHold bars distribution:")
holds = {}
for t in trades:
    h = t['hold_bars']
    holds[h] = holds.get(h, 0) + 1
for h in sorted(holds.keys()):
    sub = [t for t in trades if t['hold_bars'] == h]
    w = sum(1 for t in sub if t['won'])/len(sub)*100
    r = sum(t['rr'] for t in sub)/len(sub)
    p = sum(t['pnl_pct'] for t in sub)/len(sub)
    print(f"  hold={h:2d}b: {holds[h]:3d} trades WR={w:.1f}% RR={r:.2f}x P&L={p:+.2f}%")
