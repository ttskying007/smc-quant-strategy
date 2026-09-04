#!/usr/bin/env python3
"""V470 funnel diagnostic — show signal counts at each filter stage"""
import sys, json
from pathlib import Path
sys.path.insert(0, '/root/.hermes/scripts')
sys.path.insert(0, '/root/.hermes/scripts/v11')

from v470_engine import (load_ohlcv, calc_stock_params_v45,
    evaluate_v45_entry, TRADE_SIGNAL_TYPES, ENTRY_SIGNAL_TYPES,
    RESONANCE_THRESHOLDS, QUALITY_THRESHOLDS, ENABLE_BEAR, MIN_PROJECTED_RR)
from v11.signals_vPine import detect_all_signals_vPine as detect_all_signals_v11

def diagnose_stock(symbol, ohlcv):
    n = len(ohlcv)
    if n < 60:
        return None

    stock_params = calc_stock_params_v45(ohlcv, symbol)
    base_params = {'fvg_min_width': None, 'sweep_lookback': 12}

    signals_result = detect_all_signals_v11(ohlcv, params=base_params, tf='60min')
    all_signals = signals_result.get('all', [])

    stats = {
        'total_signals': len(all_signals),
        'type_counts': {},
        'dir_counts': {},
        'filter_stage': {
            'wrong_type': 0,
            'not_ob': 0,
            'no_quality': 0,
            'bad_displacement': 0,
            'bad_bear': 0,
            'bad_sequence': 0,
            'bad_resonance': 0,
            'no_tp': 0,
            'low_rr': 0,
        }
    }

    for sig in all_signals:
        st = sig.get('type', '')
        d = sig.get('direction', '')
        stats['type_counts'][st] = stats['type_counts'].get(st, 0) + 1
        stats['dir_counts'][d] = stats['dir_counts'].get(d, 0) + 1

    ob_signals = [s for s in all_signals if 'OB' in s.get('type', '') and 'BreakerBlock' not in s.get('type', '')]
    stats['ob_candidates'] = len(ob_signals)

    for sig in ob_signals:
        sig_idx = sig.get('idx', 0)
        direction = sig.get('direction', '')
        if sig_idx < 40 or sig_idx >= n - 10:
            stats['filter_stage']['wrong_type'] += 1  # boundary
            continue
        if direction == 'bear' and not ENABLE_BEAR:
            stats['filter_stage']['bad_bear'] += 1
            continue
        if direction == 'bear' and 'OB' not in sig.get('type', ''):
            stats['filter_stage']['bad_bear'] += 1
            continue

        quality = sig.get('confidence', sig.get('quality', 0.5))
        q_threshold = QUALITY_THRESHOLDS.get(sig.get('type', ''), 0.50)
        if quality < q_threshold:
            stats['filter_stage']['no_quality'] += 1
            continue

        displacement = sig.get('displacement_ratio', 0)
        if displacement < 0.7:
            stats['filter_stage']['bad_displacement'] += 1
            continue

        sigs_up_to = [s for s in all_signals if s.get('idx', 0) <= sig_idx]

        # Quick sequence check
        from v11.sequencer_v11 import analyze_sequence_v11
        seq_r = analyze_sequence_v11(sigs_up_to, params=base_params)
        best_seq = seq_r.get('best_sequence')
        if not best_seq or 'SCOUT' not in best_seq.get('name', ''):
            stats['filter_stage']['bad_sequence'] += 1
            continue

        # Quick resonance check
        from v11.resonance_v11 import evaluate_full_resonance_v11
        window = ohlcv[:sig_idx+1]
        tf_seq = {'daily': seq_r}
        res = evaluate_full_resonance_v11(
            all_signals=sigs_up_to,
            tf_sequences=tf_seq, ohlcv=window)
        mr = RESONANCE_THRESHOLDS.get(direction, 0.50)
        if res.total < mr:
            stats['filter_stage']['bad_resonance'] += 1
            continue

        # If we got here, it would make a trade
        stats['pass_all'] = stats.get('pass_all', 0) + 1
        stats[f'pass_{direction}'] = stats.get(f'pass_{direction}', 0) + 1

    return stats


CACHE_DIR = Path('/root/.hermes/kline_cache_60min')
all_symbols = sorted([f.stem.replace('_60min_200', '').replace('_', '.')
                     for f in CACHE_DIR.glob('*_60min_200.json')])
test_syms = all_symbols[:200]

total_stats = {
    'total_signals': 0, 'ob_candidates': 0, 'pass_all': 0,
    'type_counts': {}, 'filter_stage': {}}

for idx, sym in enumerate(test_syms):
    ohlcv = load_ohlcv(sym)
    if not ohlcv:
        continue
    st = diagnose_stock(sym, ohlcv)
    if st:
        total_stats['total_signals'] += st['total_signals']
        total_stats['ob_candidates'] += st.get('ob_candidates', 0)
        total_stats['pass_all'] = total_stats.get('pass_all', 0) + st.get('pass_all', 0)
        for k in st.get('filter_stage', {}):
            total_stats['filter_stage'][k] = total_stats['filter_stage'].get(k, 0) + st['filter_stage'][k]
        for t, c in st.get('type_counts', {}).items():
            total_stats['type_counts'][t] = total_stats['type_counts'].get(t, 0) + c

        if st.get('pass_all', 0) > 0 or st.get('ob_candidates', 0) > 5:
            print(f"{sym:12s}: signals={st['total_signals']:3d} OBs={st.get('ob_candidates',0):3d} "
                  f"pass={st.get('pass_all',0):2d} filtered={dict(st['filter_stage'])}")

print(f"\n{'='*80}")
print(f"TOTAL: signals={total_stats['total_signals']} OBs={total_stats['ob_candidates']} "
      f"pass_all={total_stats.get('pass_all',0)}")
print(f"Filter breakdown: {dict(total_stats['filter_stage'])}")
print(f"Signal types: {dict(total_stats['type_counts'])}")