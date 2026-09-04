#!/usr/bin/env python3
# SMC V10 — End-to-End Verification
"""Run V10 full pipeline on 40 stocks and compare with V9."""

import sys, json, time, logging
from pathlib import Path
from collections import defaultdict

sys.path.insert(0, str(Path(__file__).parent.parent))

logging.basicConfig(level=logging.WARNING, format='%(message)s')
log = logging.getLogger('v10_verify')

from v9.smc_hubble import fetch_kline, kline_to_ohlcv, calc_atr_pct
from v9.smc_signals import detect_all_signals, score_signal
from v9.smc_backtest import evaluate_trades as eval_v9, compute_score as score_v9

from v10 import swing_points, signal_sequencer, resonance_engine
from v10.smc_backtest_v10 import evaluate_trades_v10, compute_score_v10

# ─── Parameters: V10-friendly (moderate strictness) ───
V10_PARAMS = {
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
    '300274.SZ', '002352.SZ', '601899.SH', '300498.SZ',
    '000002.SZ', '688111.SH', '600900.SH', '600941.SH',
    '002475.SZ', '000725.SZ',
]

RESONANCE_THRESHOLD = 0.30


def verify_one(symbol, params):
    """Run V10 full analysis on one stock."""
    try:
        kline = fetch_kline(symbol, 'daily', 120)
        if not kline or len(kline) < 30:
            return None
        
        ohlcv = kline_to_ohlcv(kline)
        atr_pct = calc_atr_pct(ohlcv)
        
        # V9 baseline
        v9_result = eval_v9(ohlcv, params)
        v9_n = v9_result.get('n_trades', 0)
        v9_wr = v9_result.get('wins', 0) / max(1, v9_n) * 100
        
        # V10: swing
        swing_data = swing_points.find_swing_points(ohlcv)
        phase = swing_data.get('current_phase', 'ranging')
        
        # V10: sequence
        raw_signals = detect_all_signals(ohlcv, params)
        seq_result = signal_sequencer.analyze_signal_sequence(raw_signals)
        
        # V10: resonance
        res_score = resonance_engine.evaluate_full_resonance(
            tf_directions={'daily': swing_data['tree'].get('direction', 'bull')},
            signals=raw_signals,
            swing_tree=swing_data['tree'],
            seq_result=seq_result,
            symbol=symbol,
        )
        
        # V10: backtest
        v10_result = evaluate_trades_v10(
            ohlcv, params, phase=phase,
            swing_data=swing_data,
            resonance_threshold=RESONANCE_THRESHOLD,
        )
        v10_n = v10_result.get('n_trades', 0)
        v10_wr = v10_result.get('wins', 0) / max(1, v10_n) * 100
        
        return {
            'symbol': symbol,
            'phase': phase,
            'atr_pct': round(atr_pct, 2),
            'swing': {'macro': len(swing_data.get('macro', [])),
                      'meso': len(swing_data.get('meso', []))},
            'resonance_total': round(res_score.total, 3),
            'resonance_layers': res_score.layers,
            'sequence': seq_result.get('best_sequence', {}).get('name', 'None'),
            'sequence_dir': seq_result.get('direction'),
            'v9': {'n': v9_n, 'wr': round(v9_wr, 1)},
            'v10': {'n': v10_n, 'wr': round(v10_wr, 1)},
            'v10_trades': v10_result.get('trades', []),
            'v10_rejected': len(v10_result.get('rejected_signals', [])),
        }
    except Exception as e:
        return {'symbol': symbol, 'error': str(e)}


def main():
    print(f"\n{'='*70}")
    print(f"  SMC V10 — End-to-End Verification ({len(STOCKS)} stocks)")
    print(f"  Resonance threshold: {RESONANCE_THRESHOLD}")
    print(f"{'='*70}\n")
    
    results = []
    phases = defaultdict(int)
    total_v9_trades = 0
    total_v10_trades = 0
    total_v9_wins = 0
    total_v10_wins = 0
    
    for i, symbol in enumerate(STOCKS):
        sys.stdout.write(f"\r  [{i+1:2d}/{len(STOCKS)}] {symbol:12s}...")
        sys.stdout.flush()
        
        r = verify_one(symbol, V10_PARAMS)
        if r is None or 'error' in r:
            continue
        
        results.append(r)
        phases[r.get('phase', 'unknown')] += 1
        
        total_v9_trades += r['v9']['n']
        total_v10_trades += r['v10']['n']
        total_v9_wins += int(r['v9']['wr'] / 100 * r['v9']['n'])
        total_v10_wins += int(r['v10']['wr'] / 100 * r['v10']['n'])
    
    print(f"\n\n{'='*70}")
    print(f"  RESULTS SUMMARY")
    print(f"{'='*70}\n")
    
    # Per-phase stats
    print(f"  Market Phases:")
    for phase, count in sorted(phases.items(), key=lambda x: -x[1]):
        phase_results = [r for r in results if r.get('phase') == phase]
        if phase_results:
            avg_wr = sum(r['v10']['wr'] for r in phase_results if r['v10']['n'] > 0) / max(1, sum(1 for r in phase_results if r['v10']['n'] > 0))
            avg_res = sum(r['resonance_total'] for r in phase_results) / len(phase_results)
            print(f"    {phase:20s}: {count:2d} stocks, avg WR={avg_wr:.1f}%, avg Resonance={avg_res:.3f}")
    
    # V9 vs V10 comparison
    v9_wr = total_v9_wins / max(1, total_v9_trades) * 100
    v10_wr = total_v10_wins / max(1, total_v10_trades) * 100
    
    print(f"\n  V9  vs  V10:")
    print(f"    {'':15s} {'Trades':>8s} {'Wins':>6s} {'WR':>8s}")
    print(f"    {'V9 (baseline)':15s} {total_v9_trades:>8d} {total_v9_wins:>6d} {v9_wr:>7.1f}%")
    print(f"    {'V10 (resonance)':15s} {total_v10_trades:>8d} {total_v10_wins:>6d} {v10_wr:>7.1f}%")
    
    # By resonance layers
    print(f"\n  By Resonance Layers:")
    for layers in [0, 1, 2, 3, 4]:
        layer_results = [r for r in results if r.get('resonance_layers') == layers]
        if layer_results:
            layer_wr = sum(r['v10']['wr'] for r in layer_results if r['v10']['n'] > 0) / max(1, sum(1 for r in layer_results if r['v10']['n'] > 0))
            print(f"    L{layers} ({len(layer_results):2d} stocks): avg WR={layer_wr:.1f}%")
    
    # By sequence tier
    print(f"\n  By Sequence Tier:")
    for tier_name in ['LONG_GOLD', 'SHORT_GOLD', 'LONG_SILVER', 'SHORT_SILVER', 'LONG_BRONZE', 'SHORT_BRONZE']:
        tier_results = [r for r in results if tier_name in r.get('sequence', '')]
        if tier_results:
            tier_wr = sum(r['v10']['wr'] for r in tier_results if r['v10']['n'] > 0) / max(1, sum(1 for r in tier_results if r['v10']['n'] > 0))
            print(f"    {tier_name:16s} ({len(tier_results):2d} stocks): avg WR={tier_wr:.1f}%")
    
    # Top signals
    print(f"\n  Top V10 Signals (by resonance):")
    sorted_results = sorted(results, key=lambda r: r['resonance_total'], reverse=True)[:10]
    for r in sorted_results:
        ticker = r['symbol'].replace('.SH','').replace('.SZ','')
        print(f"    {r['symbol']:12s} {ticker:6s} "
              f"Res={r['resonance_total']:.3f} "
              f"L={r['resonance_layers']} "
              f"Phase={r.get('phase','?'):12s} "
              f"Seq={r.get('sequence','?'):16s} "
              f"V9={r['v9']['wr']:.0f}%/{r['v9']['n']}t "
              f"V10={r['v10']['wr']:.0f}%/{r['v10']['n']}t "
              f"Rej={r['v10_rejected']}")
    
    # Save results
    out_path = Path.home() / '.hermes' / 'smc_opt_v10' / 'verify_results.json'
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with open(out_path, 'w') as f:
        json.dump({
            'params': V10_PARAMS,
            'resonance_threshold': RESONANCE_THRESHOLD,
            'summary': {
                'v9_wr': round(v9_wr, 1),
                'v10_wr': round(v10_wr, 1),
                'v9_trades': total_v9_trades,
                'v10_trades': total_v10_trades,
                'v9_wins': total_v9_wins,
                'v10_wins': total_v10_wins,
                'improvement': round(v10_wr - v9_wr, 1),
            },
            'results': results,
        }, f, indent=2, ensure_ascii=False)
    
    print(f"\n  Results saved to: {out_path}")
    print(f"\n{'='*70}\n")


if __name__ == '__main__':
    main()
