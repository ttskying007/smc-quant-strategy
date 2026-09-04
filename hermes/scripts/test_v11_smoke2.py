#!/usr/bin/env python3
"""V11 Smoke Test #2 — Use cached OHLCV data"""
import json, logging, sys
logging.basicConfig(level=logging.WARNING, format='%(levelname)s:%(name)s:%(message)s')

sys.path.insert(0, '/root/.hermes/scripts')
from v11.signals_v11 import detect_all_signals_v11
from v11.sequencer_v11 import analyze_sequence_v11, score_entry_v11
from v11.resonance_v11 import quick_analyze_v11, evaluate_full_resonance_v11
from v11.adaptive_params import calc_stock_params, detect_market_phase

# Load cached data
cache_file = '/root/.hermes/kline_cache/600519_SH_daily_300.json'
print(f"Loading: {cache_file}")
ohlcv_raw = json.loads(open(cache_file).read())
# Normalize 't' -> 'date'
for entry in ohlcv_raw:
    if 'date' not in entry and 't' in entry:
        entry['date'] = str(entry['t'])
    elif 'date' not in entry:
        entry['date'] = ''
ohlcv = ohlcv_raw
print(f"Got {len(ohlcv)} bars")
print(f"Range: {ohlcv[0].get('date','?')} to {ohlcv[-1].get('date','?')}")
print(f"Last: O={ohlcv[-1]['o']:.2f} H={ohlcv[-1]['h']:.2f} L={ohlcv[-1]['l']:.2f} C={ohlcv[-1]['c']:.2f}")

# Adaptive params
phase = detect_market_phase(ohlcv)
params = calc_stock_params(ohlcv, "600519.SH", phase=phase, tf="daily")
print(f"\nPhase: {phase}")
print(f"Params: SL={params['sl_pct']}% TP={params['tp_pct']}% score_min={params['score_min']}")
print(f"  fvg_min={params['fvg_min_width']} sweep_wick={params['sweep_wick_ratio']}")

# Signals
sig_result = detect_all_signals_v11(ohlcv, params=params, tf="daily")
st = sig_result['stats']
print(f"\nSignals: {st['total']} total ({st['bull']}bull/{st['bear']}bear)")
print(f"  FVG={st['fvg']} Sweep={st['sweep']} OB={st['ob']} CHOCH={st['choch']}")

# Show the first few and last few signals
all_sigs = sig_result['all']
if all_sigs:
    print(f"\nFirst 3 signals:")
    for s in all_sigs[:3]:
        print(f"  [{s.get('idx',0)}] {s.get('type','?'):20s} dir={s.get('direction','?'):4s} "
              f"strength={s.get('strength',0):.1f} conf={s.get('confidence',0):.2f}")
    print(f"Last 5 signals:")
    for s in all_sigs[-5:]:
        print(f"  [{s.get('idx',0)}] {s.get('type','?'):20s} dir={s.get('direction','?'):4s} "
              f"strength={s.get('strength',0):.1f} conf={s.get('confidence',0):.2f}")

# Sequence analysis
print(f"\n--- Sequence Analysis ---")
seq_result = analyze_sequence_v11(all_sigs, params=params)
best = seq_result.get('best_sequence')
if best:
    print(f"Best: {best['name']}")
    print(f"  Confidence={best['confidence']:.3f} WR={best['expected_wr']:.0%}")
    print(f"  Completeness={best['completeness']:.0%} Temporal={best['temporal_score']:.3f}")
else:
    print(f"No sequence found")
    trace = seq_result.get('sequence_trace', [])
    print(f"Trace ({len(trace)} tokens): {trace[-10:] if trace else 'empty'}")

# Entry score
entry_score = score_entry_v11(seq_result)
print(f"\nEntry Score: {entry_score['grade']} -> {entry_score['action']}")
print(f"  Score: {entry_score['final_score']:.3f} WR: {entry_score['expected_wr']:.0%}")
print(f"  {entry_score['reason']}")

# Full resonance
# Full resonance (pass tf_sequences for proper single-TF scoring)
tf_sequences = {'daily': seq_result}
resonance = evaluate_full_resonance_v11(all_signals=all_sigs, tf_sequences=tf_sequences, ohlcv=ohlcv)
rd = resonance.to_dict()
print(f"  Grade: {rd['grade']} Total: {rd['total']:.3f}")
print(f"  TF: {rd['tf_score']:.3f} Ind: {rd['indicator_score']:.3f} Swing: {rd['swing_score']:.3f} Temp: {rd['temporal_score']:.3f}")
print(f"  Layers active: {rd['layers_active']} Expected WR: {rd['expected_wr']:.0%}")

# Full decision
from v11.resonance_v11 import make_entry_decision_v11
decision = make_entry_decision_v11(resonance, seq_result, params, tf_sequences=tf_sequences)
print(f"\n--- Entry Decision ---")
print(f"  Action: {decision['action']} Grade: {decision['grade']}")
print(f"  Conf: {decision['confidence']:.3f} Reson: {decision['resonance_score']:.3f}")
print(f"  {decision['reason']}")
if decision.get('entry_price'):
    print(f"  Entry={decision['entry_price']:.2f} SL={decision['sl']:.2f} TP={decision['tp']:.2f} RR={decision['rr']}")

print("\n=== V11 PIPELINE TEST COMPLETE ===")
