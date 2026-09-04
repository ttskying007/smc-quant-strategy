#!/usr/bin/env python3
# SMC V10 — Per-Stock Optimization Runner
"""Run per-stock optimization and save results."""

import sys, json, time, logging
from pathlib import Path
from collections import defaultdict

sys.path.insert(0, str(Path(__file__).parent.parent))

logging.basicConfig(level=logging.INFO, format='%(asctime)s [%(levelname)s] %(message)s')
log = logging.getLogger('v10_opt_runner')

from v9.smc_hubble import fetch_kline, kline_to_ohlcv, calc_atr_pct
from v9.smc_signals import detect_all_signals
from v10 import swing_points, signal_sequencer, resonance_engine
from v10.smc_backtest_v10 import evaluate_trades_v10
from v10.per_stock_opt import (
    optimize_per_stock, batch_optimize, save_per_stock_params,
    compute_per_stock_stats, GLOBAL_BEST,
)

# Tuned V10-friendly global params (based on verify results)
V10_GLOBAL = {
    'fvg_min_width': 0.10, 'fvg_merge_dist': 3,
    'sweep_lookback': 12, 'sweep_wick_ratio': 2.5,
    'ob_strength_min': 1.0, 'confirm_range': 3,
    'min_sources': 2, 'score_min': 1.5, 'max_trades': 5,
    'atr_min_pct': 0.5, 'atr_max_pct': 12.0,
    'sl_pct': 2.0, 'tp_pct': 6.0, 'vol_adapt_sl': 0.6,
}

STOCKS = [
    '600519.SH', '000858.SZ', '300750.SZ', '601318.SH',
    '002415.SZ', '002594.SZ', '600036.SH', '688981.SH',
    '300059.SZ', '600030.SH', '000001.SZ', '300124.SZ',
    '600276.SH', '600887.SH', '002304.SZ', '600809.SH',
    '000333.SZ', '002230.SZ', '600585.SH', '601012.SH',
    '688111.SH', '600900.SH', '600941.SH',
    '002475.SZ', '000725.SZ', '300498.SZ',
]


def v10_backtest_fn(symbol, params):
    """Backtest function for per-stock optimizer."""
    kline = fetch_kline(symbol, 'daily', 120)
    if not kline or len(kline) < 30:
        return {'wr': 0, 'n': 0, 'pf': 0, 'rr_avg': 0}
    
    ohlcv = kline_to_ohlcv(kline)
    
    # Compute swing once
    swing_data = swing_points.find_swing_points(ohlcv)
    phase = swing_data.get('current_phase', 'ranging')
    
    # Run V10 evaluation
    result = evaluate_trades_v10(
        ohlcv, params, phase=phase,
        swing_data=swing_data,
        resonance_threshold=0.30,
    )
    
    n = result.get('n_trades', 0)
    wins = result.get('wins', 0)
    returns = result.get('returns', [])
    rr_list = result.get('rr_list', [])
    
    wr = wins / n * 100 if n > 0 else 0
    rr_avg = sum(rr_list) / len(rr_list) if rr_list else 0
    
    # Profit factor
    gross_win = sum(r for r in returns if r > 0)
    gross_loss = abs(sum(r for r in returns if r <= 0))
    pf = gross_win / gross_loss if gross_loss > 0 else 99
    
    return {
        'wr': round(wr, 1),
        'n': n,
        'pf': round(pf, 2),
        'rr_avg': round(rr_avg, 2),
    }


def main():
    log.info(f"Starting per-stock optimization for {len(STOCKS)} stocks...")
    log.info(f"Using V10 global params as seed")
    
    results = batch_optimize(
        STOCKS,
        v10_backtest_fn,
        global_best=V10_GLOBAL,
        iterations_per_stock=100,
        verbose=True,
    )
    
    # Save
    out_path = save_per_stock_params(results, V10_GLOBAL)
    
    # Stats
    stats = compute_per_stock_stats(results)
    log.info(f"\n{'='*60}")
    log.info(f"  Per-Stock Optimization Results")
    log.info(f"{'='*60}")
    log.info(f"  Stocks: {stats['total_stocks']} | With trades: {stats['stocks_with_trades']}")
    log.info(f"  Total trades: {stats['total_trades']}")
    log.info(f"  Avg WR: {stats['avg_wr']}% | Avg RR: {stats['avg_rr']}")
    log.info(f"  WR range: {stats['wr_min']}% - {stats['wr_max']}% (median {stats['wr_median']}%)")
    log.info(f"  Improved: {stats['improved_count']} | Unchanged: {stats['unchanged_count']}")
    log.info(f"  Avg improvement: {stats['avg_improvement']}")
    log.info(f"  Saved to: {out_path}")
    
    # Print top/bottom
    sorted_results = sorted(
        [(s, r) for s, r in results.items() if r.get('n', 0) > 0],
        key=lambda x: x[1].get('wr', 0), reverse=True
    )
    
    log.info(f"\n  Top 5:")
    for s, r in sorted_results[:5]:
        log.info(f"    {s}: WR={r['wr']}% RR={r['rr_avg']} N={r['n']} PF={r['pf']} "
                 f"(+{r['improvement']})")
    
    log.info(f"\n  Bottom 5:")
    for s, r in sorted_results[-5:]:
        log.info(f"    {s}: WR={r['wr']}% RR={r['rr_avg']} N={r['n']} PF={r['pf']}")


if __name__ == '__main__':
    main()
