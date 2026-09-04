#!/usr/bin/env python3
"""Deep diagnostic: why POI activation rate is so low?"""
import sys, json
from pathlib import Path
sys.path.insert(0, '/root/.hermes/scripts')
sys.path.insert(0, '/root/.hermes/scripts/v11')

from v470_engine import (load_ohlcv, calc_stock_params_v45,
    evaluate_v45_entry, TRADE_SIGNAL_TYPES, RESONANCE_THRESHOLDS,
    QUALITY_THRESHOLDS, ENABLE_BEAR, MIN_PROJECTED_RR, POI_RETRACE_WINDOW)
from v11.signals_vPine import detect_all_signals_vPine as detect_all_signals_v11
from v11.sequencer_v11 import analyze_sequence_v11
from v11.resonance_v11 import evaluate_full_resonance_v11

def deep_diagnose(symbol, ohlcv):
    n = len(ohlcv)
    if n < 60:
        return
    stock_params = calc_stock_params_v45(ohlcv, symbol)
    base_params = {'fvg_min_width': None, 'sweep_lookback': 12}
    signals_result = detect_all_signals_v11(ohlcv, params=base_params, tf='60min')
    all_signals = signals_result.get('all', [])

    ob_signals = [s for s in all_signals if 'OB' in s.get('type','') and 'BreakerBlock' not in s.get('type','')]

    for sig in ob_signals[:5]:  # first 5 OBs
        sig_idx = sig.get('idx', 0)
        direction = sig.get('direction', '')
        if direction == 'bear':
            continue
        if sig_idx < 40 or sig_idx >= n - 10:
            continue

        quality = sig.get('confidence', sig.get('quality', 0.5))
        q_threshold = QUALITY_THRESHOLDS.get(sig.get('type',''), 0.50)
        displacement = sig.get('displacement_ratio', 0)

        lower = sig.get('lower', 0)
        upper = sig.get('upper', 0)
        zone_width_pct = (upper - lower) / max(lower, 0.01) * 100 if lower > 0 else 0

        print(f"\n{symbol} OB at bar {sig_idx}: type={sig.get('type')} dir={direction}")
        print(f"  price range={lower:.2f}-{upper:.2f} (zone width={zone_width_pct:.3f}%)")
        print(f"  quality={quality:.3f} (threshold={q_threshold}) disp={displacement:.2f}")
        print(f"  metadata: {sig.get('metadata', {})}")

        # Check sequence + resonance quickly
        sigs_up_to = [s for s in all_signals if s.get('idx',0) <= sig_idx]
        seq_r = analyze_sequence_v11(sigs_up_to, params=base_params)
        best_seq = seq_r.get('best_sequence')
        has_scout = best_seq and 'SCOUT' in best_seq.get('name','')

        window = ohlcv[:sig_idx+1]
        tf_seq = {'daily': seq_r}
        res = evaluate_full_resonance_v11(all_signals=sigs_up_to, tf_sequences=tf_seq, ohlcv=window)
        mr = RESONANCE_THRESHOLDS.get(direction, 0.50)

        print(f"  sequence: {best_seq.get('name','NONE') if best_seq else 'NONE'}, scout={has_scout}")
        print(f"  resonance_total={res.total:.3f} (threshold={mr})")

        if quality >= q_threshold and displacement >= 0.7 and has_scout and res.total >= mr:
            entry_bar = max(sig_idx, sig.get('confirmed_at', sig_idx))
            # Now check POI scan
            poi_found = False
            scan_range_end = min(entry_bar + POI_RETRACE_WINDOW, n - 2)
            print(f"  WOULD ENTER: entry_bar={entry_bar}, scanning to bar {scan_range_end}")

            # Check bars BEFORE entry_bar for POI (price may already have passed through)
            for j in range(entry_bar - 5, entry_bar + 1):
                if j < 0: continue
                b = ohlcv[j]
                if b['l'] <= upper and b['h'] >= lower:
                    print(f"  ALREADY AT POI: bar {j} low={b['l']:.2f} high={b['h']:.2f} touches zone")
                    break

            # Check forward scan
            for candidate in range(entry_bar + 1, scan_range_end):
                bar = ohlcv[candidate]
                if bar['l'] <= upper and bar['h'] >= lower:
                    poi_found = True
                    print(f"  POI HIT at bar {candidate}: low={bar['l']:.2f} high={bar['h']:.2f}")
                    break

            if not poi_found:
                # Show price range during scan window
                min_low = min(ohlcv[c]['l'] for c in range(entry_bar+1, scan_range_end)) if entry_bar+1 < scan_range_end else 0
                max_high = max(ohlcv[c]['h'] for c in range(entry_bar+1, scan_range_end)) if entry_bar+1 < scan_range_end else 0
                print(f"  POI MISS: price range in window low={min_low:.2f} high={max_high:.2f}, zone={lower:.2f}-{upper:.2f}")
                print(f"  zone_width={zone_width_pct:.3f}%, gap_to_low={abs(min_low-upper):.2f}, gap_to_high={abs(max_high-lower):.2f}")

CACHE_DIR = Path('/root/.hermes/kline_cache_60min')
all_symbols = sorted([f.stem.replace('_60min_200','').replace('_','.') for f in CACHE_DIR.glob('*_60min_200.json')])

for sym in all_symbols[:20]:
    ohlcv = load_ohlcv(sym)
    if ohlcv:
        deep_diagnose(sym, ohlcv)