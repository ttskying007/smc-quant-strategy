#!/usr/bin/env python3
"""Run GA search on V6.1"""
import sys, os
sys.path.insert(0, os.path.expanduser('~/.hermes/scripts'))
from smc_engine_v61 import genetic_search, get_klines, load_cached_bars

# Use medium test set (50 stocks)
test_stocks = ['600519.SH','000001.SZ','000858.SZ','600036.SH',
               '002594.SZ','300750.SZ','601318.SH','600887.SH',
               '000002.SZ','600585.SH','688981.SH','002415.SZ',
               '603259.SH','000333.SZ','002475.SZ','300124.SZ',
               '002230.SZ','600690.SH','000651.SZ','002304.SZ',
               '600036.SH','600030.SH','600104.SH','601088.SH',
               '601166.SH','601288.SH','601328.SH','601398.SH',
               '601628.SH','601857.SH','600900.SH','600276.SH',
               '600309.SH','603288.SH','002714.SZ','300760.SZ',
               '000568.SZ','000725.SZ','002142.SZ','002236.SZ',
               '002352.SZ','300059.SZ','300015.SZ','300274.SZ',
               '300413.SZ','300498.SZ','600809.SH','601012.SH',
               '601899.SH','603986.SH']

base_params = {
    'fvg_th': 0.25, 'score_th': 2.5, 'sl_mult': 2.0, 'tp_mult': 2.5,
    'min_sigs': 2, 'wick_min': 2.0, 'sl_strict': 1.5, 'tp_strict': 3.0,
    'score_gold': 4.0, 'min_sigs_strict': 3
}

print("="*70)
print("  V6.1 Genetic Algorithm Search - Phase 1")
print("="*70)

result = genetic_search(test_stocks, base_params, generations=15, pop_size=12, mutation_rate=0.3)

if result:
    print(f"\n{'='*70}")
    print(f"  GA Search Complete!")
    print(f"{'='*70}")
    import json
    print(json.dumps(result, indent=2))