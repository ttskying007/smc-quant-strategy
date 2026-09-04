#!/usr/bin/env python3
"""
SMC V23 — Stock Quality Screener + Dashboard Update
====================================================
Pre-screens all 4800 stocks for swing structure quality.
Only high-swing-coverage stocks enter the live scan.

Output: quality ranking for all stocks
"""
import json, sys, time
from pathlib import Path
from collections import Counter

sys.path.insert(0, '/root/.hermes/scripts')
from v11.signals_v11 import detect_all_signals_v11
from v11.adaptive_params import calc_stock_params, detect_market_phase
from v11.weekly_trend import synthesize_weekly, weekly_trend

CACHE_DIR = Path('/root/.hermes/kline_cache')
OUTPUT_DIR = Path('/root/.hermes/smc_signals')
OUTPUT_DIR.mkdir(exist_ok=True)


def load_ohlcv(symbol):
    fname = f"{symbol.replace('.', '_')}_daily_300.json"
    fpath = CACHE_DIR / fname
    if not fpath.exists(): return None
    data = json.loads(fpath.read_text())
    if not data or len(data) < 120: return None
    for bar in data:
        if 'date' not in bar and 't' in bar: bar['date'] = str(bar['t'])
    return data


def assess_swing_quality(ohlcv, symbol):
    """
    Score a stock's swing structure quality (0-100)
    Higher = better swing structure = more reliable signals
    """
    # Detect market phase
    phase = detect_market_phase(ohlcv)
    base_params = calc_stock_params(ohlcv, symbol, phase=phase, tf='daily')
    signal_result = detect_all_signals_v11(ohlcv, params=base_params, tf='daily')
    all_signals = signal_result.get('all', [])
    
    if not all_signals or len(all_signals) < 5:
        return {'score': 0, 'reason': 'insufficient-signals'}
    
    # Check recent signals for swing structure (last 100 bars)
    n = len(ohlcv)
    recent_start = max(0, n - 100)
    recent_bars = ohlcv[recent_start:]
    recent_signals = [s for s in all_signals if s.get('idx', 0) >= recent_start]
    
    # Count swing lows in recent bars
    swing_low_count = 0
    for i in range(1, len(recent_bars) - 1):
        bar = recent_bars[i]
        if bar['l'] < recent_bars[i-1]['l'] and bar['l'] < recent_bars[i+1]['l']:
            swing_low_count += 1
    
    # Count swing highs
    swing_high_count = 0
    for i in range(1, len(recent_bars) - 1):
        bar = recent_bars[i]
        if bar['h'] > recent_bars[i-1]['h'] and bar['h'] > recent_bars[i+1]['h']:
            swing_high_count += 1
    
    # Score components
    # 1. Signal density (8-15 signals per 100 bars is ideal)
    sig_density = len(recent_signals)
    density_score = min(100, sig_density * 8)
    if sig_density > 20: density_score = max(60, 100 - (sig_density - 20) * 5)  # too many = noise
    
    # 2. Swing structure score
    swing_score = min(100, (swing_low_count + swing_high_count) * 5)
    
    # 3. FVG ratio (more FVG = better signal quality)
    fvg_count = sum(1 for s in recent_signals if 'FVG' in s.get('type', ''))
    ob_count = sum(1 for s in recent_signals if 'OB' in s.get('type', ''))
    total_qual = fvg_count + ob_count
    fvg_ratio = fvg_count / total_qual if total_qual > 0 else 0
    fvg_score = fvg_ratio * 100
    
    # 4. Weekly trend bonus
    weekly = synthesize_weekly(ohlcv)
    wt = weekly_trend(weekly, lookback=min(5, len(weekly))) if len(weekly) >= 3 else 'unknown'
    trend_bonus = 20 if wt == 'up' else (10 if wt == 'neutral' else 0)
    
    # 5. Phase bonus
    phase_bonus = {'breakout': 20, 'volatile': 15, 'ranging': 5, 'trending_up': 25, 'trending_down': 0}.get(phase, 10)
    
    # Composite score (0-100)
    final_score = density_score * 0.25 + swing_score * 0.30 + fvg_score * 0.20 + trend_bonus * 0.10 + phase_bonus * 0.15
    final_score = min(100, max(0, final_score))
    
    # Quality tier
    if final_score >= 70: tier = 'A'
    elif final_score >= 50: tier = 'B'
    elif final_score >= 30: tier = 'C'
    else: tier = 'D'
    
    return {
        'score': round(final_score, 1),
        'tier': tier,
        'swing_lows': swing_low_count,
        'swing_highs': swing_high_count,
        'signals_100': len(recent_signals),
        'fvg_ratio': round(fvg_ratio, 2),
        'phase': phase,
        'weekly_trend': wt,
        'recommend': tier in ('A', 'B'),
    }


def main():
    symbols = sorted([f.stem.replace('_daily_300', '').replace('_', '.')
                      for f in CACHE_DIR.glob('*_daily_300.json')])
    
    print(f"V23 Quality Screener — Scanning {len(symbols)} stocks...")
    print(f"{'='*60}")
    
    results = []
    t_start = time.time()
    
    for idx, sym in enumerate(symbols):
        ohlcv = load_ohlcv(sym)
        if not ohlcv: continue
        
        q = assess_swing_quality(ohlcv, sym)
        q['symbol'] = sym
        results.append(q)
        
        if (idx + 1) % 500 == 0:
            elapsed = time.time() - t_start
            print(f"  [{idx+1}/{len(symbols)}] {elapsed:.0f}s")
    
    total_time = time.time() - t_start
    
    # Stats
    tiers = Counter(r['tier'] for r in results)
    recommend = sum(1 for r in results if r.get('recommend'))
    
    print(f"\n{'='*60}")
    print(f"Quality Distribution:")
    for tier in ['A', 'B', 'C', 'D']:
        cnt = tiers.get(tier, 0)
        pct = cnt/len(results)*100
        print(f"  {tier}: {cnt:4d} stocks ({pct:.0f}%)")
    print(f"  Recommend (A+B): {recommend}/{len(results)} ({recommend/len(results)*100:.0f}%)")
    print(f"  Time: {total_time:.0f}s")
    
    # Save
    outpath = OUTPUT_DIR / 'stock_quality_ratings.json'
    json.dump({
        'timestamp': time.time(),
        'total_stocks': len(results),
        'recommended': recommend,
        'tier_distribution': dict(tiers),
        'stocks': sorted(results, key=lambda x: -x['score'])[:100],  # Top 100
    }, open(outpath, 'w'), default=str, indent=2)
    print(f"\nSaved: {outpath}")
    
    # Top A-rated stocks
    print(f"\nTop 20 A-rated Stocks:")
    a_stocks = sorted([r for r in results if r['tier'] == 'A'], key=lambda x: -x['score'])
    for r in a_stocks[:20]:
        print(f"  {r['symbol']:12s} score={r['score']:.0f} swing={r['swing_lows']}+{r['swing_highs']} "
              f"phase={r['phase']} FVG={r['fvg_ratio']:.0%}")

if __name__ == '__main__':
    main()
