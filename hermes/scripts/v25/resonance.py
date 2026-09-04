#!/usr/bin/env python3
"""
Multi-Timeframe Resonance Detector for V25.5
Checks daily-level signals against 60min-level confirmation.

Resonance types:
  STRONG:  日线信号 + 60min同向信号 + 60min结构确认
  WEAK:    日线信号 only (no 60min confirmation)  
  CONFLICT: 日线bull信号 + 60min bear结构
"""
import json, sys, os, time, urllib.request
from pathlib import Path
from collections import defaultdict
from datetime import datetime

sys.path.insert(0, '/root/.hermes/scripts')
sys.path.insert(0, '/root/.hermes/scripts/v11')

KLINE_DIR = Path('/root/.hermes/kline_cache')
PICKS_PATH = Path('/root/.hermes/smc_opt_v25/v25_picks.json')

# Tencent 60min kline endpoint
K60_URL = "http://ifzq.gtimg.cn/appstock/app/kline/mkline?param={code},m60,,200"

def download_60min(code):
    """Download 60min klines for one stock from Tencent."""
    try:
        r = urllib.request.urlopen(K60_URL.format(code=code), timeout=15)
        data = json.loads(r.read())
        stock_key = list(data.get('data', {}).keys())[0]
        raw = data['data'][stock_key].get('m60', [])
        klines = []
        for item in raw:
            klines.append({
                't': item[0],
                'o': float(item[1]),
                'c': float(item[2]),
                'h': float(item[3]),
                'l': float(item[4]),
                'v': float(item[5]),
            })
        return klines
    except Exception as e:
        return None

def detect_60min_swings(klines):
    """Detect swing highs/lows on 60min."""
    swings = {'highs': [], 'lows': []}
    for i in range(5, len(klines) - 5):
        h = klines[i]['h']
        l = klines[i]['l']
        # Swing high
        is_high = all(h >= klines[j]['h'] for j in range(i-3, i+4) if j != i)
        if is_high:
            swings['highs'].append({'idx': i, 'price': h, 'date': klines[i]['t']})
        # Swing low
        is_low = all(l <= klines[j]['l'] for j in range(i-3, i+4) if j != i)
        if is_low:
            swings['lows'].append({'idx': i, 'price': l, 'date': klines[i]['t']})
    return swings

def detect_60min_structure(klines):
    """Detect market structure (bullish/bearish) on 60min."""
    swings = detect_60min_swings(klines)
    highs = swings['highs']
    lows = swings['lows']
    
    if len(highs) < 2 or len(lows) < 2:
        return 'NEUTRAL'
    
    # Check last 2 swing highs: higher highs = bullish
    recent_highs = sorted(highs, key=lambda x: x['idx'])[-3:]
    recent_lows = sorted(lows, key=lambda x: x['idx'])[-3:]
    
    hh = all(recent_highs[i]['price'] > recent_highs[i-1]['price'] 
             for i in range(1, len(recent_highs)))
    hl = all(recent_lows[i]['price'] > recent_lows[i-1]['price'] 
             for i in range(1, len(recent_lows)))
    
    if hh and hl:
        return 'BULLISH'
    
    lh = all(recent_highs[i]['price'] < recent_highs[i-1]['price'] 
             for i in range(1, len(recent_highs)))
    ll = all(recent_lows[i]['price'] < recent_lows[i-1]['price'] 
             for i in range(1, len(recent_lows)))
    
    if lh and ll:
        return 'BEARISH'
    
    return 'NEUTRAL'

def detect_60min_fvg(klines):
    """Detect FVG on 60min near current price."""
    fvgs = []
    for i in range(1, len(klines) - 1):
        b0, b1, b2 = klines[i], klines[i-1], klines[i-2]
        # Bullish FVG: gap up between b2 high and b0 low
        if b0['l'] > b2['h']:
            fvgs.append({'type': 'BULL', 'top': b0['l'], 'bottom': b2['h'], 'idx': i, 'date': b0['t']})
        # Bearish FVG: gap down between b2 low and b0 high
        if b0['h'] < b2['l']:
            fvgs.append({'type': 'BEAR', 'top': b2['l'], 'bottom': b0['h'], 'idx': i, 'date': b0['t']})
    return fvgs

def assess_resonance(daily_pick, k60):
    """
    Check if daily signal has 60min confirmation.
    Returns resonance score 0-10.
    """
    score = 0
    details = []
    
    if not k60 or len(k60) < 50:
        return 0, ['NO_60MIN_DATA']
    
    entry_price = daily_pick.get('price', daily_pick.get('entry_price', 0))
    structure = detect_60min_structure(k60)
    fvgs = detect_60min_fvg(k60)
    
    # 1. Structure alignment (+3)
    if structure == 'BULLISH':
        score += 3
        details.append('60M_BULL_STRUCT')
    elif structure == 'BULLISH':
        score += 3
        details.append('60M_BULL_STRUCT')
    
    # 2. Recent FVG near entry (+2)
    if k60:
        last_price = k60[-1]['c']
        for f in fvgs[-5:]:
            if f['type'] == 'BULL' and f['bottom'] <= entry_price <= f['top']:
                score += 2
                details.append('60M_FVG_AT_ENTRY')
                break
    
    # 3. Sweep on 60min (+2)
    swings = detect_60min_swings(k60)
    recent_low = min(s['price'] for s in swings['lows'][-3:]) if swings['lows'] else 0
    if recent_low and k60:
        # Check if recent price swept a prior low
        prior_lows = [s['price'] for s in swings['lows'][:-3]] if len(swings['lows']) > 3 else []
        if prior_lows and recent_low < min(prior_lows):
            score += 2
            details.append('60M_SWEEP')
    
    # 4. Price above 60min MA20 (+1)
    if len(k60) >= 20:
        ma20 = sum(b['c'] for b in k60[-20:]) / 20
        if k60[-1]['c'] > ma20:
            score += 1
            details.append('60M_ABOVE_MA20')
    
    # 5. BOS/CHOCH on 60min in last 10 bars (+2)
    if len(swings['highs']) >= 2 and len(swings['lows']) >= 2:
        recent_h = swings['highs'][-1]['price']
        prev_h = swings['highs'][-2]['price']
        recent_l = swings['lows'][-1]['price']
        prev_l = swings['lows'][-2]['price']
        if recent_h > prev_h or recent_l < prev_l:
            score += 2
            details.append('60M_BOS_CHOCH')
    
    return score, details

def main(limit=50):
    """Download 60min data for top picks and compute resonance."""
    picks = json.loads(PICKS_PATH.read_text())
    
    # Top picks by quality
    picks.sort(key=lambda x: -(x.get('v253_quality', 0)))
    picks = picks[:limit]
    
    print(f"Multi-TF resonance scan: {len(picks)} picks")
    
    results = []
    resonance_dist = defaultdict(int)
    
    for i, p in enumerate(picks):
        sym = p['symbol']
        code = sym.replace('.SH', 'sh').replace('.SZ', 'sz').replace('.BJ', 'bj')
        code_tencent = code  # Already correct format: sh600519, sz000001
        
        # Try cached first
        parts = sym.replace('.SH', '_SH').replace('.SZ', '_SZ').replace('.BJ', '_BJ')
        cache_path = KLINE_DIR / f'{parts}_60min_200.json'
        
        k60 = None
        if cache_path.exists():
            k60 = json.loads(cache_path.read_text())
        else:
            k60 = download_60min(code_tencent)
            if k60:
                cache_path.write_text(json.dumps(k60, ensure_ascii=False))
                time.sleep(0.1)  # Rate limit
        
        if not k60:
            continue
        
        score, details = assess_resonance(p, k60)
        resonance_dist[score] += 1
        
        resonance_label = 'STRONG' if score >= 6 else 'WEAK' if score >= 3 else 'NONE'
        
        results.append({
            'symbol': sym,
            'quality': p.get('v253_quality', 0),
            'zone_type': p.get('zone_type', ''),
            'conf_type': p.get('conf_type', ''),
            'resonance_score': score,
            'resonance_label': resonance_label,
            'details': details,
            'entry_price': p.get('price', 0),
        })
        
        if (i+1) % 20 == 0:
            print(f"  {i+1}/{len(picks)}...")
    
    # Sort by resonance
    results.sort(key=lambda x: -(x['resonance_score'] + x['quality'] * 0.01))
    
    print(f"\n═══ Multi-TF Resonance Results ═══")
    print(f"  Scanned: {len(results)} picks with 60min data")
    print(f"\n  Resonance distribution:")
    for score in sorted(resonance_dist, reverse=True):
        label = 'STRONG' if score >= 6 else 'WEAK' if score >= 3 else 'NONE'
        bar = '█' * resonance_dist[score]
        print(f"    {label:7s} (≥{score}): {resonance_dist[score]:3d} {bar}")
    
    # Top STRONG picks
    strong = [r for r in results if r['resonance_label'] == 'STRONG']
    print(f"\n  Top STRONG resonance ({len(strong)}):")
    for r in strong[:10]:
        print(f"    {r['symbol']} score={r['resonance_score']} {r['zone_type']}/{r['conf_type']} -> {', '.join(r['details'])}")
    
    # Save
    out_path = Path('/root/.hermes/smc_opt_v25/v25_resonance.json')
    out_path.write_text(json.dumps(results, ensure_ascii=False, indent=2))
    print(f"\nSaved: {out_path}")
    
    return results

if __name__ == '__main__':
    main()
