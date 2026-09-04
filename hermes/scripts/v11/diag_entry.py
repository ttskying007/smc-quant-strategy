#!/usr/bin/env python3
"""Diagnose: trace why evaluate_v45_entry filters out trades"""
import sys, json
sys.path.insert(0, '/root/.hermes/scripts')
from v11.v468_engine import CACHE_DIR, load_ohlcv, evaluate_v45_entry, calc_stock_params_v45
from v11.signals_v11 import detect_all_signals_v11
from v11.sequencer_v11 import analyze_sequence_v11
from v11.resonance_v11 import evaluate_full_resonance_v11, make_entry_decision_v11

sym = '000066.SZ'
# Try a stock that might have trades
ohlcv = load_ohlcv(sym)
if not ohlcv:
    print(f'{sym}: no data')
    sys.exit(1)

base_params = {'fvg_min_width': None, 'sweep_lookback': 12}
sigs = detect_all_signals_v11(ohlcv, params=base_params, tf='60min')
all_sigs = sigs.get('all', [])
n = len(ohlcv)
stock_params = calc_stock_params_v45(ohlcv, sym)

print(f'{sym}: {len(all_sigs)} signals, {n} bars\n')

# Test each OB_Bull signal for entry
for sig in all_sigs:
    sig_type = sig.get('type', '')
    if 'OB_Bull' not in sig_type:
        continue
    sig_idx = sig.get('idx', 0)
    if sig_idx < 40 or sig_idx >= n - 10:
        continue
    quality = sig.get('quality', sig.get('confidence', 0.5))
    
    print(f'--- OB_Bull@{sig_idx} q={quality:.2f} ---')
    
    sigs_up_to = [s for s in all_sigs if s.get('idx', 0) <= sig_idx]
    
    # Step 1: Check reversal
    from v11.v468_engine import is_reversal_ob
    is_rev, rev_reason = is_reversal_ob(ohlcv, sig, sigs_up_to)
    print(f'  is_reversal_ob: {is_rev} ({rev_reason})')
    if not is_rev:
        print(f'  ❌ FILTERED: reversal_ob')
        continue
    
    # Step 2: Check quality
    q_threshold = 0.50
    if quality < q_threshold:
        print(f'  ❌ FILTERED: quality {quality:.2f} < {q_threshold}')
        continue
    
    # Step 3: Check sweep_fvg
    sweep_fvg_found = False
    if sig_idx > 5:
        for ps in sigs_up_to:
            ps_type = ps.get('type', '')
            ps_idx = ps.get('idx', 0)
            if 'SweepDown' in ps_type:
                if 0 < sig_idx - ps_idx <= 5:
                    sweep_fvg_found = True
                    break
    print(f'  sweep_fvg={sweep_fvg_found}')
    
    # Step 4: Check sequence
    seq_r = analyze_sequence_v11(sigs_up_to, params=base_params)
    best_seq = seq_r.get('best_sequence')
    seq_name = best_seq.get('name', 'NONE') if best_seq else 'NONE'
    print(f'  sequence: {seq_name}')
    if not best_seq:
        print(f'  ❌ FILTERED: no sequence')
        continue
    if 'SCOUT' not in seq_name:
        print(f'  ❌ FILTERED: seq={seq_name} not SCOUT')
        continue
    
    # Step 5: Check resonance
    window = ohlcv[:sig_idx+1]
    tf_seq = {'daily': seq_r}
    res = evaluate_full_resonance_v11(all_signals=sigs_up_to, tf_sequences=tf_seq, ohlcv=window)
    print(f'  resonance: total={res.total:.3f} grade={res.grade()} active={res.layers_active}')
    
    from v11.v468_engine import RESONANCE_THRESHOLDS
    mr = RESONANCE_THRESHOLDS.get('bull', 0.50)
    if res.total < mr:
        print(f'  ❌ FILTERED: resonance {res.total:.3f} < {mr}')
        continue
    
    # Step 6: Check entry decision
    dec = make_entry_decision_v11(res, seq_r, base_params, tf_sequences=tf_seq)
    print(f'  entry_decision: {dec["action"]}')
    if dec['action'] != 'enter':
        print(f'  ❌ FILTERED: entry decision {dec["action"]}')
        continue
    
    print(f'  ✅ PASSES ALL FILTERS')
    result = evaluate_v45_entry(all_sigs, sigs_up_to, sig, ohlcv, n, 'bull', base_params, stock_params)
    if result:
        print(f'  ENTRY: idx={result["entry_idx"]} price={result["entry_price"]} sl={result["sl"]}')
        print(f'  RR={result["rr"]} P&L={result["pnl_pct"]}% hold={result["hold_bars"]}b')
