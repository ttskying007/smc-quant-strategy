#!/usr/bin/env python3
"""V11 Multi-Stock Backtest — using cached daily data"""
import json, logging, sys, time
from pathlib import Path

logging.basicConfig(level=logging.WARNING, format='%(levelname)s:%(name)s:%(message)s')
sys.path.insert(0, '/root/.hermes/scripts')

from v11.data_loader import load_cached_ohlcv
from v11.signals_v11 import detect_all_signals_v11
from v11.sequencer_v11 import analyze_sequence_v11
from v11.resonance_v11 import evaluate_full_resonance_v11, make_entry_decision_v11
from v11.adaptive_params import calc_stock_params, detect_market_phase

CACHE_DIR = Path('/root/.hermes/kline_cache')

# Get first 15 cached stocks
symbols = sorted([
    f.stem.replace('_daily_300', '').replace('_', '.')
    for f in CACHE_DIR.glob('*_daily_300.json')
])[:20]

print("=" * 70)
print("V11 BACKTEST — BASELINE (20 stocks, daily, cached data)")
print("=" * 70)

results = {}
total_trades = 0
total_wins = 0

for idx, sym in enumerate(symbols):
    t0 = time.time()
    ohlcv = load_cached_ohlcv(sym, 'daily', 300)
    if not ohlcv or len(ohlcv) < 60:
        print(f"  [{idx+1}/{len(symbols)}] {sym}: SKIP (no data)")
        continue
    
    # Adaptive params
    phase = detect_market_phase(ohlcv)
    params = calc_stock_params(ohlcv, sym, phase=phase, tf="daily")
    
    # Full signal detection on entire dataset
    sig_result = detect_all_signals_v11(ohlcv, params=params, tf="daily")
    all_signals = sig_result['all']
    
    # Sequence analysis
    seq_result = analyze_sequence_v11(all_signals, params=params)
    best = seq_result.get('best_sequence')
    
    # Resonance (pass tf_sequences for proper single-TF scoring)
    tf_sequences = {'daily': seq_result}
    resonance = evaluate_full_resonance_v11(all_signals=all_signals, tf_sequences=tf_sequences, ohlcv=ohlcv)
    
    # Entry decision
    decision = make_entry_decision_v11(resonance, seq_result, params, tf_sequences=tf_sequences)
    
    elapsed = time.time() - t0
    
    results[sym] = {
        'params': {k: params[k] for k in ['sl_pct','tp_pct','score_min','fvg_min_width','sweep_wick_ratio']},
        'signals': sig_result['stats'],
        'sequence': {
            'name': best['name'] if best else None,
            'confidence': best['confidence'] if best else 0,
            'wr': best['expected_wr'] if best else 0,
            'description': best['description'] if best else 'none',
        },
        'resonance': resonance.to_dict(),
        'decision': decision,
        'phase': phase,
    }
    
    # Summary line
    seq_name = (best['name'] if best else 'NONE').ljust(14)
    dec_action = decision['action'].upper().ljust(6)
    dec_grade = decision['grade']
    st = sig_result['stats']
    rd = resonance.to_dict()
    print(f"  [{idx+1:2d}/{len(symbols)}] {sym:12s} | "
          f"Seq={seq_name} WR={best['expected_wr']:.0%}" if best else f"Seq={'NONE':14s} WR={0:.0%}" + " | "
          f"Res={rd['grade']}({rd['total']:.2f}) | "
          f"Dec={dec_grade}({dec_action}) | "
          f"Sigs={st['total']:3d} | "
          f"{elapsed:.1f}s")

# Summary
print(f"\n{'='*70}")
print(f"SUMMARY — {len(results)} stocks analyzed")
print(f"{'='*70}")

# Count grades
from collections import Counter
seq_counts = Counter()
dec_counts = Counter()
for r in results.values():
    sn = r['sequence']['name']
    seq_counts[sn.split('_')[0] if sn else 'NONE'] += 1
    dec_counts[r['decision']['action']] += 1

print(f"\nSequence distribution:")
for k, v in seq_counts.most_common():
    print(f"  {k:15s}: {v}")

print(f"\nDecision distribution:")
for k, v in dec_counts.most_common():
    print(f"  {k:10s}: {v}")

print(f"\nDetailed results saved to /root/.hermes/smc_opt_v11/baseline_results.json")
Path('/root/.hermes/smc_opt_v11').mkdir(parents=True, exist_ok=True)
Path('/root/.hermes/smc_opt_v11/baseline_results.json').write_text(
    json.dumps(results, ensure_ascii=False, indent=2, default=str)
)
