#!/usr/bin/env python3
"""V11 Smoke Test: full pipeline end-to-end"""
import json, logging, sys
logging.basicConfig(level=logging.WARNING, format='%(levelname)s:%(name)s:%(message)s')

from v11.rate_limiter import get_limiter
from v11.tf_data import fetch_single_tf
from v11.signals_v11 import detect_all_signals_v11
from v11.sequencer_v11 import analyze_sequence_v11
from v11.resonance_v11 import quick_analyze_v11
from v11.adaptive_params import calc_stock_params, detect_market_phase
from v11.backtest_v11 import backtest_single_stock_v11

limiter = get_limiter(max_rps=2, max_concurrent=2)

# Test stocks
test_symbols = ['600519.SH', '000001.SZ', '300750.SZ', '510050.SH', '399001.SZ']

print("=" * 70)
print("V11 SMOKE TEST — Full Pipeline")
print("=" * 70)

for sym in test_symbols:
    print(f"\n{'='*60}")
    print(f"  {sym}")
    print(f"{'='*60}")
    
    ohlcv = fetch_single_tf(sym, "daily", 300, limiter=limiter)
    if not ohlcv or len(ohlcv) < 50:
        print(f"  SKIP: insufficient data ({len(ohlcv) if ohlcv else 0})")
        continue
    
    print(f"  Bars: {len(ohlcv)}  Last: {ohlcv[-1].get('date','')} C={ohlcv[-1]['c']:.2f}")
    
    # Adaptive params
    phase = detect_market_phase(ohlcv)
    params = calc_stock_params(ohlcv, sym, phase=phase, tf="daily")
    print(f"  Phase: {phase}")
    print(f"  Params: SL={params['sl_pct']}% TP={params['tp_pct']}% score_min={params['score_min']}")
    
    # Signals
    sig_result = detect_all_signals_v11(ohlcv, params=params, tf="daily")
    st = sig_result['stats']
    print(f"  Signals: {st['total']} total ({st['bull']} bull/{st['bear']} bear)")
    print(f"    FVG={st['fvg']} Sweep={st['sweep']} OB={st['ob']} CHOCH={st['choch']}")
    
    # Sequence analysis
    seq_result = analyze_sequence_v11(sig_result['all'], params=params)
    best = seq_result.get('best_sequence')
    if best:
        print(f"  Sequence: {best['name']} ({best['description']})")
        print(f"    Confidence={best['confidence']:.3f} WR={best['expected_wr']:.0%}")
        print(f"    Completeness={best['completeness']:.0%} Temporal={best['temporal_score']:.3f}")
    else:
        trace = seq_result.get('sequence_trace', [])
        print(f"  No sequence. Trace({len(trace)}): {trace[-5:] if trace else 'empty'}")
    
    # Resonance + Entry
    analysis = quick_analyze_v11(ohlcv, params=params, tf="daily")
    dec = analysis['decision']
    print(f"  Decision: {dec['action'].upper()} | Grade={dec['grade']} | Conf={dec['confidence']:.3f}")
    print(f"    {dec['reason']}")
    if dec.get('entry_price'):
        print(f"    Entry={dec['entry_price']:.2f} SL={dec['sl']:.2f} TP={dec['tp']:.2f} RR={dec['rr']}")
    
    # Quick backtest
    bt = backtest_single_stock_v11(ohlcv, symbol=sym, params=params, tf="daily")
    bts = bt.get('stats', {})
    print(f"  Backtest: WR={bts.get('win_rate','?')}% RR={bts.get('avg_rr','?')}x")
    print(f"    Trades={bts.get('n_trades','?')} W={bts.get('n_wins','?')} L={bts.get('n_losses','?')}")
    print(f"    PF={bts.get('profit_factor','?')} MaxDrawdown={bts.get('max_drawdown','?')}%")

print("\n" + "=" * 70)
print("SMOKE TEST COMPLETE")
print("=" * 70)
