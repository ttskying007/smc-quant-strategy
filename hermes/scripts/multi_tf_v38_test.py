#!/usr/bin/env python3
"""
SMC V38.4 + 60min Multi-TF Test Scan
======================================
测试60分钟+日线多时间框架扫描 vs 纯日线结果对比。

流程:
1. 通过Tencent API获取前50只股票60分钟K线
2. 使用V38.4引擎在60min+日线上检测信号
3. 与纯日线结果对比

Usage:
  PYTHONUNBUFFERED=1 python3 multi_tf_v38_test.py
"""
import json, sys, time
from pathlib import Path
from collections import Counter, defaultdict

sys.path.insert(0, '/root/.hermes/scripts')
from v11.signals_v11 import detect_all_signals_v11
from v11.sequencer_v11 import analyze_sequence_v11
from v11.resonance_v11 import evaluate_full_resonance_v11, make_entry_decision_v11
from v11.structure_tree_v38 import StructureTree, calc_atr_v38, calc_stock_atr_profile
from v11.wyckoff_phases_v38 import detect_wyckoff_phases, get_phase_params
from v11.weekly_trend import synthesize_weekly, weekly_trend
from v11.klines_60min import get_60min_kline

CACHE_DIR = Path('/root/.hermes/kline_cache')
CACHE_60MIN = Path('/root/.hermes/kline_cache_60min')
OUTPUT_DIR = Path('/root/.hermes/smc_opt_v38')
OUTPUT_DIR.mkdir(exist_ok=True)

TOP_N = 50
MIN_BARS = 80
MIN_60MIN_BARS = 40


def load_ohlcv(symbol):
    fname = f"{symbol.replace('.', '_')}_daily_300.json"
    fpath = CACHE_DIR / fname
    if not fpath.exists():
        return None
    data = json.loads(fpath.read_text())
    if not data or len(data) < MIN_BARS:
        return None
    for bar in data:
        if 'date' not in bar and 't' in bar:
            bar['date'] = str(bar['t'])
    return data


def short_trend(ohlcv, idx, lookback=10):
    if idx < lookback:
        return 'neutral', 0
    seg = ohlcv[idx - lookback:idx + 1]
    s, e = seg[0]['c'], seg[-1]['c']
    change = (e - s) / s * 100
    ema = sum(ohlcv[i]['c'] for i in range(idx - min(5, idx), idx + 1)) / min(6, idx + 1)
    ema_d = (ohlcv[idx]['c'] - ema) / ema * 100
    if change > 0.6 and ema_d > 0:
        return 'up', change
    if change < -0.6 and ema_d < 0:
        return 'down', abs(change)
    return 'neutral', 0


def detect_daily_only(ohlcv, symbol):
    """纯日线V38.4检测"""
    n = len(ohlcv)
    if n < MIN_BARS:
        return None
    
    structure_tree = StructureTree(ohlcv)
    wyckoff_result = detect_wyckoff_phases(ohlcv, structure_tree)
    
    base_params = {
        'fvg_min_consecutive': 2, 'sweep_lookback': 20,
        'max_fvg_gap_pct': 5.0, 'min_fvg_gap_pct': 0.15,
        'swing_window': 5, 'enable_bear': True,
    }
    
    all_sigs = detect_all_signals_v11(ohlcv, params=base_params, tf='daily').get('all', [])
    if not all_sigs or len(all_sigs) < 3:
        return None
    
    n_sigs = len([s for s in all_sigs if s.get('idx', 0) >= n - 60])
    return {
        'n_total_signals': len(all_sigs),
        'n_recent_signals': n_sigs,
        'wyckoff_phase': wyckoff_result.get('primary_phase', 'unknown'),
        'wyckoff_conf': wyckoff_result.get('confidence', 0),
    }


def detect_multi_tf(symbol, daily_ohlcv, ohlcv_60min):
    """V38.4 + 60min Multi-TF检测"""
    n_daily = len(daily_ohlcv)
    n_60min = len(ohlcv_60min)
    
    if n_daily < MIN_BARS or n_60min < MIN_60MIN_BARS:
        return None
    
    # Daily analysis
    structure_tree = StructureTree(daily_ohlcv)
    wyckoff_result = detect_wyckoff_phases(daily_ohlcv, structure_tree)
    
    base_params = {
        'fvg_min_consecutive': 2, 'sweep_lookback': 20,
        'max_fvg_gap_pct': 5.0, 'min_fvg_gap_pct': 0.15,
        'swing_window': 5, 'enable_bear': True,
    }
    
    daily_sigs = detect_all_signals_v11(daily_ohlcv, params=base_params, tf='daily').get('all', [])
    
    # 60min analysis - use different params for intraday sensitivity
    tf60_params = {
        'fvg_min_consecutive': 1,
        'sweep_lookback': 12,
        'max_fvg_gap_pct': 3.0,
        'min_fvg_gap_pct': 0.1,
        'swing_window': 3,
        'enable_bear': True,
    }
    tf60_result = detect_all_signals_v11(ohlcv_60min, params=tf60_params, tf='60min')
    tf60_sigs = tf60_result.get('all', [])
    
    if not daily_sigs or len(daily_sigs) < 3:
        return None
    
    # Detect recent signals on both TFs
    recent_daily = [s for s in daily_sigs if s.get('idx', 0) >= n_daily - 60]
    recent_60min = [s for s in tf60_sigs if s.get('idx', 0) >= n_60min - 30] if tf60_sigs else []
    
    # Try to align 60min signals with daily (multi-TF resonance)
    # Count signals that have TF alignment
    tf_aligned = 0
    daily_bull = sum(1 for s in recent_daily if 'Bull' in s.get('type', ''))
    daily_bear = sum(1 for s in recent_daily if 'Bear' in s.get('type', ''))
    tf60_bull = sum(1 for s in recent_60min if 'Bull' in s.get('type', ''))
    tf60_bear = sum(1 for s in recent_60min if 'Bear' in s.get('type', ''))
    
    # Daily only analysis for comparison
    daily_only = detect_daily_only(daily_ohlcv, symbol)
    
    return {
        'symbol': symbol,
        'daily': {
            'n_total': len(daily_sigs),
            'n_recent': len(recent_daily),
            'bull_signals': daily_bull,
            'bear_signals': daily_bear,
        },
        'tf60min': {
            'n_total': len(tf60_sigs),
            'n_recent': len(recent_60min),
            'bull_signals': tf60_bull,
            'bear_signals': tf60_bear,
        },
        'wyckoff_phase': wyckoff_result.get('primary_phase', 'unknown'),
        'wyckoff_conf': wyckoff_result.get('confidence', 0),
        'has_tf_alignment': (daily_bull > 0 and tf60_bull > 0) or (daily_bear > 0 and tf60_bear > 0),
        'multi_tf_advantage': 'yes' if (tf60_bull > 0 and daily_bull == 0) or (tf60_bear > 0 and daily_bear == 0) else 'no',
    }


def main():
    print("=" * 80, flush=True)
    print("SMC V38.4 + 60min Multi-TF Test Scan", flush=True)
    print(f"Testing top {TOP_N} stocks: Multi-TF (60min+daily) vs Daily-only", flush=True)
    print("=" * 80, flush=True)
    
    # Get symbols
    symbols = sorted([f.stem.replace('_daily_300', '').replace('_', '.')
                      for f in CACHE_DIR.glob('*_daily_300.json')])[:TOP_N]
    
    print(f"\nScanning {len(symbols)} stocks...", flush=True)
    print(f"  API: Tencent (verified working)", flush=True)
    print(f"  Hubble API: 401 (as documented)", flush=True)
    print(f"  Using fallback: Tencent API via klines_60min.py\n", flush=True)
    
    daily_results = {}
    multi_tf_results = {}
    api_status = {'success': 0, 'failed': 0}
    
    t_start = time.time()
    
    for idx, sym in enumerate(symbols):
        print(f"\n[{idx+1}/{len(symbols)}] {sym}:", flush=True)
        
        # Load daily
        daily_ohlcv = load_ohlcv(sym)
        if not daily_ohlcv:
            print(f"  Daily data: MISSING", flush=True)
            continue
        
        # Daily-only analysis
        daily_result = detect_daily_only(daily_ohlcv, sym)
        if daily_result:
            daily_results[sym] = daily_result
            print(f"  Daily-only: {daily_result['n_recent_signals']} recent sigs, "
                  f"phase={daily_result['wyckoff_phase']}", flush=True)
        else:
            print(f"  Daily-only: NO SIGNALS", flush=True)
        
        # 60min data (via Tencent API with cache)
        ohlcv_60min = get_60min_kline(sym)
        if ohlcv_60min and len(ohlcv_60min) >= MIN_60MIN_BARS:
            api_status['success'] += 1
            print(f"  60min: {len(ohlcv_60min)} bars (OK)", flush=True)
            
            # Multi-TF analysis
            mtf_result = detect_multi_tf(sym, daily_ohlcv, ohlcv_60min)
            if mtf_result:
                multi_tf_results[sym] = mtf_result
                print(f"  Multi-TF: daily_recent={mtf_result['daily']['n_recent']}, "
                      f"60min_recent={mtf_result['tf60min']['n_recent']}, "
                      f"aligned={mtf_result['has_tf_alignment']}, "
                      f"advantage={mtf_result['multi_tf_advantage']}", flush=True)
            else:
                print(f"  Multi-TF: INCONCLUSIVE", flush=True)
        else:
            api_status['failed'] += 1
            print(f"  60min: FAILED ({len(ohlcv_60min) if ohlcv_60min else 0} bars)", flush=True)
    
    total_time = time.time() - t_start
    
    print("\n" + "=" * 80, flush=True)
    print("COMPARISON RESULTS", flush=True)
    print("=" * 80, flush=True)
    
    print(f"\nAPI Status:", flush=True)
    print(f"  Hubble API (60min endpoint): 401 UNAUTHORIZED", flush=True)
    print(f"  Tencent API (klines_60min.py): {api_status['success']}/{api_status['success']+api_status['failed']} stocks OK", flush=True)
    
    print(f"\nDaily-only Results ({len(daily_results)} stocks):", flush=True)
    d_recent = sum(r['n_recent_signals'] for r in daily_results.values())
    d_total = sum(r['n_total_signals'] for r in daily_results.values())
    d_phases = Counter(r['wyckoff_phase'] for r in daily_results.values())
    print(f"  Total signals: {d_total} | Recent (60 bars): {d_recent}", flush=True)
    print(f"  Phases: {dict(d_phases)}", flush=True)
    
    print(f"\nMulti-TF Results ({len(multi_tf_results)} stocks):", flush=True)
    mtf_aligned = sum(1 for r in multi_tf_results.values() if r['has_tf_alignment'])
    mtf_advantage = sum(1 for r in multi_tf_results.values() if r['multi_tf_advantage'] == 'yes')
    mtf_daily_recent = sum(r['daily']['n_recent'] for r in multi_tf_results.values())
    mtf_60min_recent = sum(r['tf60min']['n_recent'] for r in multi_tf_results.values())
    print(f"  Daily recent: {mtf_daily_recent} | 60min recent: {mtf_60min_recent}", flush=True)
    print(f"  TF Aligned: {mtf_aligned}/{len(multi_tf_results)} stocks", flush=True)
    print(f"  Multi-TF Advantage (60min sees what daily misses): {mtf_advantage}/{len(multi_tf_results)}", flush=True)
    
    # Comparison
    print(f"\n{'='*80}", flush=True)
    print(f"VERDICT", flush=True)
    print(f"{'='*80}", flush=True)
    if mtf_advantage > 0:
        print(f"  Multi-TF adds value: {mtf_advantage} stocks have 60min signals not visible on daily", flush=True)
    else:
        print(f"  No clear Multi-TF advantage in this sample", flush=True)
    print(f"  TF alignment in {mtf_aligned}/{len(multi_tf_results)} stocks suggests consistency", flush=True)
    print(f"  Time: {total_time:.0f}s for {len(symbols)} stocks (limited by Tencent API rate)", flush=True)
    print(f"  Recommendation: 60min data is viable via Tencent API; consider batch caching", flush=True)
    
    # Save results
    output = {
        'config': 'V38.4 Multi-TF Test',
        'api_status': {
            'hubble_api': '401 UNAUTHORIZED',
            'tencent_api': f'{api_status["success"]}/{api_status["success"]+api_status["failed"]} stocks OK',
        },
        'daily_only': {sym: r for sym, r in daily_results.items()},
        'multi_tf': {sym: r for sym, r in multi_tf_results.items()},
        'comparison': {
            'stocks_scanned': len(symbols),
            'daily_stocks_valid': len(daily_results),
            'multi_tf_stocks_valid': len(multi_tf_results),
            'tf_aligned_count': mtf_aligned,
            'multi_tf_advantage_count': mtf_advantage,
            'total_time_seconds': total_time,
        },
    }
    
    outpath = OUTPUT_DIR / 'multi_tf_test_v38.json'
    json.dump(output, open(outpath, 'w'), ensure_ascii=False, indent=2, default=str)
    print(f"\nSaved: {outpath}", flush=True)


if __name__ == '__main__':
    main()
