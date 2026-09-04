#!/usr/bin/env python3
"""V469 20-stock grid search + results analysis"""
import sys, json
sys.path.insert(0, '/root/.hermes/scripts')
from v11.v469_engine import run_grid_search, CACHE_DIR

symbols = sorted([f.stem.replace('_60min_200', '').replace('_', '.')
                 for f in CACHE_DIR.glob('*_60min_200.json')])[:20]

param_grid = [
    {'swing_skip': 3, 'poi_window': 50, 'sl_min': 0.30, 'trail_be': 8.0, 'min_rr': 8.0},
    {'swing_skip': 2, 'poi_window': 50, 'sl_min': 0.30, 'trail_be': 8.0, 'min_rr': 8.0},
    {'swing_skip': 4, 'poi_window': 50, 'sl_min': 0.30, 'trail_be': 8.0, 'min_rr': 8.0},
    {'swing_skip': 3, 'poi_window': 80, 'sl_min': 0.30, 'trail_be': 8.0, 'min_rr': 8.0},
    {'swing_skip': 3, 'poi_window': 30, 'sl_min': 0.30, 'trail_be': 8.0, 'min_rr': 8.0},
    {'swing_skip': 3, 'poi_window': 50, 'sl_min': 0.50, 'trail_be': 8.0, 'min_rr': 8.0},
    {'swing_skip': 3, 'poi_window': 50, 'sl_min': 0.30, 'trail_be': 8.0, 'min_rr': 6.0},
    {'swing_skip': 3, 'poi_window': 50, 'sl_min': 0.30, 'trail_be': 10.0, 'min_rr': 8.0},
    {'swing_skip': 2, 'poi_window': 80, 'sl_min': 0.50, 'trail_be': 10.0, 'min_rr': 6.0},
    {'swing_skip': 4, 'poi_window': 30, 'sl_min': 0.30, 'trail_be': 6.0, 'min_rr': 10.0},
]

# Run low-RRmin combos first as they'll find more trades
result = run_grid_search(symbols, param_grid)

# Save
import json
with open('/root/.hermes/smc_opt_v469/grid_search_results.json', 'w') as f:
    json.dump(result, f)

print(f"\n{'='*80}")
print(f"GRID SEARCH COMPLETE — {len(result)} combinations on 20 stocks")
print(f"{'='*80}")

# Best by combined WR*RR
scored = []
for i, r in enumerate(result):
    s = r['summary']
    p = r['params']
    if s['n_trades'] >= 5:
        score = s['win_rate'] * s['avg_rr'] / 100  # WR% * RR / 100
        scored.append({'idx': i, 'score': score, **p, **s})

scored.sort(key=lambda x: -x['score'])

print(f"\nTop 5 by WR*RR combined score:")
for i, r in enumerate(scored[:5]):
    print(f"  {i+1}. SS={r['swing_skip']} POI={r['poi_window']} SL={r['sl_min']} "
          f"BE={r['trail_be']} RRmin={r['min_rr']}  "
          f"→ n={r['n_trades']} WR={r['win_rate']:.1f}% RR={r['avg_rr']:.2f}x "
          f"P&L={r['avg_pnl']:+.2f}% score={r['score']:.1f}")
