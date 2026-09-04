#!/usr/bin/env python3
"""
V25 Unified Pipeline — Full Market Scan with Quality + MTF Resonance
1. Scan ALL stocks for signals (using signals_v22)
2. Score each by zone quality, signal sequence, confirmation (V25.3)
3. Check MTF resonance (V25.4)
4. Apply dynamic SL/TP (V25.1)
5. Output quality-ranked picks

This replaces the old V24 scan with the full V25 quality pipeline.
"""
import json, sys, os, time
from pathlib import Path
from collections import defaultdict, Counter
from typing import List, Dict, Tuple

sys.path.insert(0, '/root/.hermes/scripts')
sys.path.insert(0, '/root/.hermes/scripts/v11')
sys.path.insert(0, '/root/.hermes/scripts/v25')

from signal_quality import (
    score_all_picks, score_zone_quality, score_signal_sequence,
    score_entry_confirmation, score_mtf_resonance, compute_combined_quality,
    parse_signal_sequence
)
from mtf_resonance import compute_mtf_resonance
from engine_v25 import (
    compute_dynamic_sltp, find_smart_money_cost, 
    compute_atr, load_kline_cache, V25Config
)

KLINE_DIR = Path('/root/.hermes/kline_cache')
OUT_DIR = Path('/root/.hermes/smc_opt_v25')


def load_daily_kline(symbol: str) -> List[Dict]:
    """Load daily kline for a symbol."""
    parts = symbol.replace('.SH', '_SH').replace('.SZ', '_SZ').replace('.BJ', '_BJ')
    path = KLINE_DIR / f'{parts}_daily_300.json'
    if path.exists():
        try:
            data = json.loads(path.read_text())
            for b in data:
                for k in ('o', 'h', 'l', 'c'):
                    if k in b:
                        b[k] = float(b[k])
            return data
        except:
            pass
    return []


def detect_zone_and_entry(signals: List, klines: List[Dict], entry_idx: int) -> Dict:
    """
    Detect the active zone and entry confirmation at entry_idx.
    Scans backward from entry to find the nearest demand zone.
    """
    from signals_v22 import Signal
    
    # Get signals up to entry_idx
    sigs_before = [s for s in signals if s.idx <= entry_idx]
    
    if not sigs_before:
        return None
    
    # Find nearest bull zone (FVG, OB, Breaker, IFVG) before entry
    bull_zones = [s for s in sigs_before if 'Bull' in getattr(s, 'type', '')
                  and any(t in getattr(s, 'type', '') for t in ('FVG', 'OB', 'Breaker', 'IFVG', 'BPR'))]
    
    if not bull_zones:
        return None
    
    # Closest zone to entry
    zone = max(bull_zones, key=lambda s: s.idx)
    
    # Entry confirmation: IDM/PB bounce near zone
    conf = None
    for s in sigs_before[::-1]:
        if s.idx >= zone.idx and getattr(s, 'type', '') in ('IDM_BOUNCE', 'PB_BOUNCE', 'REV_BOUNCE'):
            conf = s
            break
    
    # Build signal sequence string (signals between zone and entry)
    zone_sigs = [s for s in sigs_before if s.idx >= zone.idx]
    zone_sigs.sort(key=lambda s: s.idx)
    seq_parts = []
    for s in zone_sigs[-8:]:  # Last 8 signals only
        seq_parts.append(getattr(s, 'type', '?'))
    ctx_seq = '→'.join(seq_parts)
    
    # Zone prices
    bar = klines[zone.idx] if zone.idx < len(klines) else None
    close = float(bar.get('c', 0)) if bar else 0
    
    return {
        'zone_type': getattr(zone, 'type', ''),
        'zone_bar': zone.idx,
        'zone_age': entry_idx - zone.idx,
        'entry_idx': entry_idx,
        'entry_price': float(klines[entry_idx].get('c', 0)),
        'conf_type': getattr(conf, 'type', '') if conf else 'IDM_BOUNCE',
        'ctx_seq': ctx_seq,
        'detail': ctx_seq,
        # Zone bounds from kline
        'dz_low': float(getattr(zone, 'lower', close * 0.98)),
        'dz_high': float(getattr(zone, 'upper', close * 1.02)),
        'score': getattr(zone, 'strength', 5),
    }


def scan_single_stock(symbol: str, klines: List[Dict], params: Dict = None) -> List[Dict]:
    """Scan a single stock for V25 quality setups."""
    if len(klines) < 60:
        return []
    
    from signals_v22 import detect_all_signals_v22
    
    try:
        signals, stats, swings, swings_dict = detect_all_signals_v22(klines, params)
    except Exception:
        return []
    
    if not signals:
        return []
    
    recent_start = max(0, len(klines) - 30)
    picks = []
    
    bull_zone_types = {'FVG_Bull', 'OB_Bull', 'BreakerBlock_Bull', 'IFVG_Bull', 'BPR'}
    zones = [s for s in signals if s.type in bull_zone_types and s.idx >= recent_start - 20]
    
    for zone in zones:
        zone_idx = zone.idx
        zone_lo = zone.lower
        zone_hi = zone.upper
        
        for i in range(zone_idx + 1, min(zone_idx + 10, len(klines))):
            bar = klines[i]
            lo = float(bar.get('l', 0))
            hi = float(bar.get('h', 0))
            cl = float(bar.get('c', 0))
            
            if not (lo <= zone_hi and hi >= zone_lo):
                continue
            
            entry_price = cl
            if entry_price <= 0:
                continue
            
            # Phase 0 Fix: Reject entry above zone (max 0.8% tolerance)
            entry_above_zone_pct = (entry_price / zone_hi - 1) * 100 if zone_hi > 0 else 0
            if entry_above_zone_pct > 0.8:
                continue  # Price already broke through zone, no retrace happened
            
            # Phase 0 Fix: Entry position validation
            # Entry should be at or below zone high, ideally in lower 50% of zone
            if entry_price < zone_lo * 0.97:
                continue  # Entry too far below zone (zone invalidated)
            
            # Entry confirmation type (check signals at entry bar)
            sigs_at_entry = [s for s in signals if i-1 <= s.idx <= i+1]
            entry_types = [s.type for s in sigs_at_entry]
            if any('Sweep' in t for t in entry_types):
                conf_type = 'SWEEP_ENTRY'
            elif any('Pinbar' in t for t in entry_types):
                conf_type = 'PINBAR_ENTRY'
            elif any('OTE' in t for t in entry_types):
                conf_type = 'OTE_ENTRY'
            elif any('CHOCH' in t for t in entry_types):
                conf_type = 'CHOCH_ENTRY'
            elif any('BOS' in t for t in entry_types):
                conf_type = 'BOS_ENTRY'
            elif any('Breaker' in t for t in entry_types):
                conf_type = 'BREAKER_ENTRY'
            else:
                conf_type = 'ZONE_RETRACE'
            
            # Build compact SMC story: Zone → [key intermediate] → Entry
            essential_intermediate = {'Sweep_BSL','Sweep_SSL','CHOCH_Bull','CHOCH_Bear',
                        'BOS_Bull','BOS_Bear','MSS_Bull','MSS_Bear','LiquidityVoid'}
            zone_sigs = [s for s in signals if zone_idx < s.idx < i and s.type in essential_intermediate]
            zone_sigs.sort(key=lambda s: s.idx)
            
            # Human-readable zone name
            zone_name = zone.type.replace('_Bull','').replace('_Bear','')
            if zone_name == 'BPR':
                zone_name = 'Range'
            
            # Build clean story: [Sweep]→[CHOCH/BOS]→[Zone]→[Entry]
            story_parts = []
            seen = set()
            for s in zone_sigs[-4:]:  # Last 4 signals only
                t = s.type
                clean = t.replace('_Bull','').replace('_Bear','')
                if clean in ('Sweep_BSL','Sweep_SSL'):
                    clean = 'Sweep'
                if clean in ('CHOCH','BOS','MSS'):
                    clean = clean  # Keep as-is
                if clean == 'LiquidityVoid':
                    clean = 'LV'
                if clean not in seen:
                    story_parts.append(clean)
                    seen.add(clean)
                    if len(story_parts) >= 2:
                        break
            
            story_parts.append(zone_name)
            
            # Clean entry label
            el = conf_type.replace('_ENTRY','')
            if el == 'ZONE_RETRACE': el = 'Retrace'
            story_parts.append(el)
            
            ctx_seq = ' → '.join(story_parts)
            
            atr, atr_pct = compute_atr(klines, 14, i)
            if atr == 0:
                continue
            
            # V25.5: Market state detection — skip RANGE
            from v25.state_backtest import detect_market_state
            mkt_state = detect_market_state(klines, i)
            if mkt_state['state'] == 'RANGE':
                continue  # RANGE stocks have 44% WR, skip entirely
            
            closes = [float(klines[j].get('c', 0)) for j in range(max(0, i-60), i+1)]
            ma20 = sum(closes[-20:]) / min(20, len(closes))
            pct_from_ma = (entry_price - ma20) / ma20 * 100
            if pct_from_ma > 2:
                regime = 'TREND_UP'
            elif pct_from_ma > 0:
                regime = 'WEAK_UP'
            elif pct_from_ma < -2:
                regime = 'TREND_DOWN'
            else:
                regime = 'WEAK_DOWN' if pct_from_ma < 0 else 'RANGE'
            
            z_score, _ = score_zone_quality(zone.type, i - zone_idx, ctx_seq, conf_type)
            s_score, _ = score_signal_sequence(ctx_seq)
            c_score, _ = score_entry_confirmation(conf_type, ctx_seq)
            m_score, _ = score_mtf_resonance(str(klines[i].get('t', '')), regime)
            
            quality = compute_combined_quality(z_score, s_score, c_score, m_score)
            if quality['tier'] == 'REJECT':
                continue
            
            # V25.5: State-adaptive SL (from detected market state)
            state_params = mkt_state['params']
            sl_price = zone_lo - atr * state_params['sl_atr_mult']
            
            # Phase 0 Fix: Hard floor SL must be below zone_low by at least 0.5%
            hard_floor_sl = zone_lo * 0.995
            sl_price = max(sl_price, hard_floor_sl)
            
            # Final check: ensure SL is below zone_low
            if sl_price >= zone_lo:
                sl_price = zone_lo * 0.995
            
            sl_pct = abs(entry_price - sl_price) / entry_price * 100
            
            # V25.1: Structural TP from swing highs (skip nearest, use 2nd+)
            highs = sorted(set(round(float(klines[j].get('h', 0)), 2) 
                          for j in range(max(0, i-60), min(i+5, len(klines)))
                          if float(klines[j].get('h', 0)) > entry_price * 1.03))
            if len(highs) >= 2:
                tp1 = highs[1]  # 2nd nearest high
            elif len(highs) == 1:
                tp1 = highs[0]
            else:
                tp1 = entry_price * (1 + atr_pct * 1.5 / 100)
            tp1_pct = (tp1 - entry_price) / entry_price * 100
            
            rr = tp1_pct / sl_pct if sl_pct > 0 else 0
            if rr < 0.6:
                continue
            
            # ── V25.1: Require Sweep/CHOCH/BOS in signal chain ──
            has_structure = any(s in ctx_seq for s in ('Sweep','CHOCH','BOS'))
            if not has_structure:
                continue
            
            pick = {
                'symbol': symbol, 'engine': 'V25',
                'entry_date': str(klines[i].get('t', klines[i].get('date', ''))),
                'entry_idx': i, 'price': round(entry_price, 2),
                'entry_price': round(entry_price, 2),
                'zone_type': zone.type, 'zone_bar': zone_idx,
                'zone_age': i - zone_idx, 'conf_type': conf_type,
                'ctx_seq': ctx_seq, 'detail': ctx_seq, 'regime': regime,
                'dz_low': round(zone_lo, 2), 'dz_high': round(zone_hi, 2),
                'score': round(quality['total'], 0),
                'v253_quality': quality['total'], 'v253_tier': quality['tier'],
                'v253_breakdown': quality['breakdown'],
                'v25_sl_price': round(sl_price, 2),
                'v25_sl_pct': round(sl_pct, 2),
                'v25_tp_tiers': [
                    {'price': round(tp1, 2), 'pct': round(tp1_pct, 1),
                     'type': 'TP1 ATR', 'alloc': 0.5},
                    {'price': 0, 'pct': 0, 'type': 'TP2 Runner', 'alloc': 0.5},
                ],
                'v25_cost_line': round(zone_lo + (zone_hi - zone_lo) * 0.7, 2),
                'v25_zone_bottom': round(zone_lo, 2),
                'v25_zone_top': round(zone_hi, 2),
                'v25_atr': round(atr, 2), 'v25_atr_pct': round(atr_pct, 2),
            }
            picks.append(pick)
            break
    
    return picks


def run_full_scan(limit: int = None, min_quality: str = 'SPECULATIVE'):
    """
    Run full V25 scan on all stocks.
    limit: max stocks to scan (None = all)
    min_quality: minimum tier to include
    """
    # Get all kline symbols
    kline_files = sorted(KLINE_DIR.glob('*_daily_300.json'))
    symbols = []
    for f in kline_files:
        name = f.stem.replace('_daily_300', '')
        if '_SH' in name:
            sym = name.replace('_SH', '.SH')
        elif '_SZ' in name:
            sym = name.replace('_SZ', '.SZ')
        elif '_BJ' in name:
            sym = name.replace('_BJ', '.BJ')
        else:
            continue
        symbols.append(sym)
    
    if limit:
        symbols = symbols[:limit]
    
    print(f"V25 Full Scan: {len(symbols)} stocks, min quality: {min_quality}")
    t0 = time.time()
    
    tier_order = {'ELITE': 0, 'STANDARD': 1, 'SPECULATIVE': 2}
    min_tier_val = tier_order.get(min_quality, 2)
    
    all_picks = []
    stocks_with_picks = 0
    
    for i, sym in enumerate(symbols):
        klines = load_daily_kline(sym)
        if not klines:
            continue
        
        picks = scan_single_stock(sym, klines)
        if picks:
            stocks_with_picks += 1
            all_picks.extend(picks)
        
        if (i + 1) % 500 == 0:
            elapsed = time.time() - t0
            print(f"  {i+1}/{len(symbols)} stocks ({elapsed:.0f}s), "
                  f"{stocks_with_picks} with picks, {len(all_picks)} total")
    
    elapsed = time.time() - t0
    
    # Filter by quality
    filtered = [p for p in all_picks if tier_order.get(p['v253_tier'], 9) <= min_tier_val]
    
    # Sort by quality score
    filtered.sort(key=lambda p: (-p['v253_quality'], -p.get('v25_atr_pct', 0)))
    
    print(f"\nScan complete: {elapsed:.0f}s, {stocks_with_picks}/{len(symbols)} stocks with picks")
    print(f"Total picks: {len(all_picks)}, after filter: {len(filtered)}")
    
    # Tier distribution
    tiers = Counter(p['v253_tier'] for p in filtered)
    for tier in ['ELITE', 'STANDARD', 'SPECULATIVE']:
        n = tiers.get(tier, 0)
        print(f"  {tier}: {n} ({n/len(filtered)*100:.0f}%)" if filtered else f"  {tier}: 0")
    
    # Save
    out_path = OUT_DIR / 'v25_full_scan.json'
    out_path.write_text(json.dumps(filtered, ensure_ascii=False, indent=2))
    print(f"\nSaved {len(filtered)} picks to {out_path}")
    
    # Top picks
    if filtered:
        print(f"\nTop 10 picks:")
        for p in filtered[:10]:
            tp = p['v25_tp_tiers'][0]
            rr = tp['pct'] / p['v25_sl_pct'] if p['v25_sl_pct'] > 0 else 0
            print(f"  {p['symbol']}: Q={p['v253_quality']} {p['v253_tier']} "
                  f"SL={p['v25_sl_pct']:.1f}% TP={tp['pct']:.1f}% RR={rr:.2f} "
                  f"zone={p['zone_type']} conf={p['conf_type']} regime={p.get('regime','?')}")
    
    return filtered


if __name__ == '__main__':
    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument('--limit', type=int, default=None, help='Max stocks to scan')
    ap.add_argument('--quality', type=str, default='SPECULATIVE', 
                    choices=['ELITE', 'STANDARD', 'SPECULATIVE'],
                    help='Minimum quality tier')
    args = ap.parse_args()
    
    run_full_scan(limit=args.limit, min_quality=args.quality)
