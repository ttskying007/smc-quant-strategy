#!/usr/bin/env python3
"""
V25.4 Multi-Timeframe Resonance Engine
Checks real weekly and 60min kline alignment for each pick.

Resonance scoring:
  W - Weekly trend (MA20 direction, structure position) 0-3
  D - Daily zone quality (signal quality on daily) 0-3  
  H - 60min alignment (entry timing, micro-structure) 0-4
  Combined: 0-10
"""
import json, sys, os
from pathlib import Path
from collections import defaultdict
from typing import List, Dict, Tuple, Optional

# ── Weekly Trend Analysis ──

WEEKLY_CACHE = Path('/root/.hermes/kline_cache_weekly')
CACHE_60 = Path('/root/.hermes/kline_cache_60min')
DAILY_CACHE = Path('/root/.hermes/kline_cache')

def load_kline(symbol: str, cache_dir: Path, suffix: str) -> List[Dict]:
    """Load kline from cache. symbol: '000001.SZ'"""
    parts = symbol.replace('.SH', '_SH').replace('.SZ', '_SZ').replace('.BJ', '_BJ')
    path = cache_dir / f'{parts}_{suffix}.json'
    if path.exists():
        try:
            return json.loads(path.read_text())
        except:
            pass
    return []


def weekly_trend_score(symbol: str) -> Tuple[int, Dict]:
    """
    Analyze weekly trend for MTF resonance.
    Returns (score 0-3, details)
    """
    klines = load_kline(symbol, WEEKLY_CACHE, 'weekly_300')
    if not klines:
        # Fallback: derive from daily
        daily = load_kline(symbol, DAILY_CACHE, 'daily_300')
        if not daily:
            return 0, {'error': 'No kline data'}
        
        # Approximate weekly from daily (every 5th bar)
        weekly = []
        for i in range(0, len(daily), 5):
            if i + 4 < len(daily):
                chunk = daily[i:i+5]
                o = float(chunk[0].get('o', 0))
                c = float(chunk[-1].get('c', 0))
                h = max(float(b.get('h', 0)) for b in chunk)
                l = min(float(b.get('l', 0)) for b in chunk)
                weekly.append({'o': o, 'c': c, 'h': h, 'l': l})
        klines = weekly
    
    if len(klines) < 20:
        return 2, {'note': 'Short history, default neutral', 'bars': len(klines)}
    
    # MA20 trend
    closes = [float(b.get('c', 0)) for b in klines[-20:]]
    ma20 = sum(closes) / len(closes)
    current = closes[-1]
    prev = closes[-2] if len(closes) >= 2 else current
    
    # Trend direction
    ma_slope = (closes[-1] - closes[-5]) / max(abs(closes[-5]), 0.01) * 100 if len(closes) >= 5 else 0
    
    details = {
        'current': round(current, 2),
        'ma20': round(ma20, 2),
        'pct_from_ma': round((current - ma20) / ma20 * 100, 1),
        'ma_slope': round(ma_slope, 1),
        'bars': len(klines),
    }
    
    if current > ma20 and ma_slope > 2:
        return 3, {**details, 'trend': 'STRONG_UP'}
    elif current > ma20:
        return 2, {**details, 'trend': 'WEAK_UP'}
    elif current < ma20 and ma_slope < -2:
        return 1, {**details, 'trend': 'STRONG_DOWN'}
    elif current < ma20:
        return 1, {**details, 'trend': 'WEAK_DOWN'}
    else:
        return 2, {**details, 'trend': 'FLAT'}


def hourly_alignment_score(symbol: str, entry_date: str = '') -> Tuple[int, Dict]:
    """
    Analyze 60min structure for entry timing alignment.
    Returns (score 0-4, details)
    """
    klines = load_kline(symbol, CACHE_60, '60min_300')
    if not klines:
        return 2, {'note': 'No 60min data, default neutral', 'bars': 0}
    
    if len(klines) < 20:
        return 2, {'note': f'Short history ({len(klines)} bars)', 'bars': len(klines)}
    
    # Find approximate entry point
    entry_idx = None
    if entry_date:
        for i, b in enumerate(klines):
            if str(b.get('t', b.get('date', ''))) == entry_date:
                entry_idx = i
                break
    
    if entry_idx is None:
        entry_idx = len(klines) - 1  # Use latest
    
    # Check micro-structure at entry
    recent = klines[max(0, entry_idx - 20): entry_idx + 1]
    if not recent:
        return 2, {'note': 'No recent bars', 'bars': len(klines)}
    
    closes = [float(b.get('c', 0)) for b in recent]
    highs = [float(b.get('h', 0)) for b in recent]
    lows = [float(b.get('l', 0)) for b in recent]
    
    current = closes[-1] if closes else 0
    avg_high = sum(highs) / len(highs) if highs else 0
    
    # Score components
    score = 2  # Base
    
    # 1. Price relative to recent range
    if current > 0 and avg_high > 0:
        range_pct = (current - min(lows)) / (max(highs) - min(lows)) * 100 if max(highs) > min(lows) else 50
        if 20 <= range_pct <= 40:
            score += 1  # Near support = good entry zone
        elif 60 <= range_pct <= 80:
            score -= 1  # Near resistance = poor entry
    
    # 2. Recent momentum (last 5 bars)
    if len(closes) >= 5:
        last5 = closes[-5:]
        if all(last5[i] <= last5[i+1] for i in range(len(last5)-1)):
            pass  # Uptrend - neutral for buy entries
        elif all(last5[i] >= last5[i+1] for i in range(len(last5)-1)):
            score += 1  # Pullback completed - good entry
    
    # 3. Volume check (higher vol at zone = stronger)
    # (skipped - no volume data reliably available)
    
    return min(4, max(0, score)), {
        'entry_idx': entry_idx,
        'total_bars': len(klines),
        'recent_bars': len(recent),
        'range_position': round(range_pct if 'range_pct' in dir() else 50, 0),
        'score': score,
    }


def daily_structure_score(symbol: str, pick: Dict) -> Tuple[int, Dict]:
    """
    Analyze daily chart structure quality.
    Returns (score 0-3, details)
    """
    klines = load_kline(symbol, DAILY_CACHE, 'daily_300')
    if not klines or len(klines) < 50:
        return 1, {'note': 'Insufficient daily data', 'bars': len(klines) if klines else 0}
    
    closes = [float(b.get('c', 0)) for b in klines]
    highs = [float(b.get('h', 0)) for b in klines]
    lows = [float(b.get('l', 0)) for b in klines]
    
    current = closes[-1] if closes else 0
    if current <= 0:
        return 1, {'note': 'Invalid price data'}
    
    # MA20 trend
    ma20 = sum(closes[-20:]) / 20
    pct_from_ma = (current - ma20) / ma20 * 100
    
    # 60-day high proximity
    h60 = max(highs[-60:]) if len(highs) >= 60 else max(highs)
    pct_from_high = (current - h60) / h60 * 100
    
    # 20-day low/high range
    l20 = min(lows[-20:]) if len(lows) >= 20 else min(lows)
    h20 = max(highs[-20:]) if len(highs) >= 20 else max(highs)
    range_20 = (current - l20) / max(h20 - l20, 0.01) * 100
    
    score = 2  # Base
    
    # Above MA20 = bullish structure
    if pct_from_ma > 2:
        score += 1
    elif pct_from_ma < -2:
        score -= 1
    
    # Not too close to 60-day high (room to run)
    if -30 < pct_from_high < -2:
        score += 1  # Pulled back from high = good setup
    elif pct_from_high > -1:
        score -= 1  # At all-time high = risky
    
    return min(3, max(0, score)), {
        'ma20_pct': round(pct_from_ma, 1),
        'high60_pct': round(pct_from_high, 1),
        'range20_pct': round(range_20, 1),
        'bars': len(klines),
    }


def compute_mtf_resonance(symbol: str, pick: Dict) -> Dict:
    """Compute complete MTF resonance score 0-10."""
    
    # W: Weekly trend (0-3)
    w_score, w_details = weekly_trend_score(symbol)
    
    # D: Daily structure (0-3)
    d_score, d_details = daily_structure_score(symbol, pick)
    
    # H: Hourly alignment (0-4)
    entry_date = str(pick.get('entry_date', ''))
    h_score, h_details = hourly_alignment_score(symbol, entry_date)
    
    total = w_score + d_score + h_score
    
    # Tier
    if total >= 8:
        tier = 'STRONG'
        bonus_mult = 1.3
    elif total >= 5:
        tier = 'ALIGNED'
        bonus_mult = 1.0
    elif total >= 3:
        tier = 'WEAK'
        bonus_mult = 0.7
    else:
        tier = 'MISALIGNED'
        bonus_mult = 0.0
    
    return {
        'mtf_total': total,
        'mtf_tier': tier,
        'mtf_bonus_mult': bonus_mult,
        'mtf_weekly': w_score,
        'mtf_daily': d_score,
        'mtf_hourly': h_score,
        'mtf_weekly_detail': w_details,
        'mtf_daily_detail': d_details,
        'mtf_hourly_detail': h_details,
    }


# ── Batch Processor ──

def run_mtf_analysis(picks: List[Dict]) -> List[Dict]:
    """Run MTF resonance analysis on all picks."""
    results = []
    
    for i, p in enumerate(picks):
        sym = p['symbol']
        
        try:
            mtf = compute_mtf_resonance(sym, p)
        except Exception as e:
            mtf = {
                'mtf_total': 0,
                'mtf_tier': 'ERROR',
                'mtf_bonus_mult': 0,
                'error': str(e),
            }
        
        enhanced = dict(p)
        enhanced.update(mtf)
        results.append(enhanced)
        
        if (i + 1) % 50 == 0:
            print(f"  {i+1}/{len(picks)}...")
    
    return results


if __name__ == '__main__':
    picks_path = '/root/.hermes/smc_opt_v25/v253_scored_picks.json'
    
    if not Path(picks_path).exists():
        picks_path = '/root/.hermes/smc_opt_v25/v25_picks.json'
    
    picks = json.loads(Path(picks_path).read_text())
    print(f"Running MTF resonance on {len(picks)} picks...")
    
    results = run_mtf_analysis(picks)
    
    # Stats
    from collections import Counter
    tiers = Counter(p['mtf_tier'] for p in results)
    scores = [p['mtf_total'] for p in results if p['mtf_total'] > 0]
    
    print(f"\nMTF Resonance distribution:")
    for tier in ['STRONG', 'ALIGNED', 'WEAK', 'MISALIGNED', 'ERROR']:
        n = tiers.get(tier, 0)
        print(f"  {tier:12s}: {n:4d} ({n/len(results)*100:5.1f}%)")
    
    if scores:
        print(f"\nMTF Score: {min(scores)}-{max(scores)}, avg={sum(scores)/len(scores):.1f}")
    
    # Show some examples
    by_mtf = sorted(results, key=lambda p: -p['mtf_total'])
    print(f"\nTop 5 MTF picks:")
    for p in by_mtf[:5]:
        w = p.get('mtf_weekly_detail', {})
        d = p.get('mtf_daily_detail', {})
        print(f"  {p['symbol']}: MTF={p['mtf_total']} (W={p['mtf_weekly']} D={p['mtf_daily']} H={p['mtf_hourly']}) "
              f"trend={w.get('trend','?')} ma20%={d.get('ma20_pct','?')}%")
    
    # Save
    out_path = Path('/root/.hermes/smc_opt_v25/v254_mtf_scored.json')
    out_path.write_text(json.dumps(results, ensure_ascii=False, indent=2))
    print(f"\nSaved to {out_path}")
