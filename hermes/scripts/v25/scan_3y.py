#!/usr/bin/env python3
"""
V26 3-year full scan — generate picks from 750-bar kline data
Scans ALL stocks with 750-bar kline cache, detects SMC signals,
finds quality entries across the full 3-year span.
"""
import json, sys
from pathlib import Path
from collections import Counter, defaultdict

sys.path.insert(0, '/root/.hermes/scripts')
from v11.signals_v22 import detect_all_signals_v22 as detect_sigs

KLINE_DIR = Path('/root/.hermes/kline_cache')
OUT_DIR = Path('/root/.hermes/smc_opt_v25')

# Quality filters (same as V26 engine)
ALLOWED_ZONES = {'OB_Bull', 'FVG_Bull', 'BPR'}
ALLOWED_CONFS = {'PINBAR_ENTRY', 'CHOCH_ENTRY', 'BOS_ENTRY', 'SWEEP_ENTRY'}


def scan_stock(kfile):
    """Scan one stock for all entry opportunities across 3 years"""
    try:
        klines = json.loads(kfile.read_text())
    except:
        return []
    
    # Parse data
    for b in klines:
        for k in ('o', 'h', 'l', 'c', 'v'):
            if k in b:
                b[k] = float(b[k])
    
    if len(klines) < 100:
        return []
    
    # Get symbol
    sym = kfile.stem.replace('_daily_750', '').replace('_daily_300', '')
    symbol = sym.replace('_SH', '.SH').replace('_SZ', '.SZ').replace('_BJ', '.BJ')
    
    # Detect all SMC signals
    try:
        sigs, summary, swings, sig_dict = detect_sigs(klines)
    except:
        return []
    
    if not sigs:
        return []
    
    # Find bull zones (demand zones)
    bull_signals = [s for s in sigs if hasattr(s, 'type') and 'Bull' in str(s.type)]
    
    picks = []
    n = len(klines)
    
    for sig in bull_signals:
        sig_type = str(sig.type) if hasattr(sig, 'type') else ''
        if sig_type not in ALLOWED_ZONES:
            continue
        
        zone_bar = sig.bar if hasattr(sig, 'bar') else sig.idx
        if zone_bar < 20 or zone_bar >= n - 20:
            continue
        
        # Get zone boundaries
        # Get zone boundaries from meta or kline data
        if hasattr(sig, 'meta') and sig.meta:
            dz_low = sig.meta.get('ob_low', float(klines[zone_bar].get('l', 0)))
            dz_high = sig.meta.get('ob_high', float(klines[zone_bar].get('h', 0)))
        else:
            dz_low = float(klines[zone_bar].get('l', 0))
            dz_high = float(klines[zone_bar].get('h', 0))
        
        if dz_low <= 0:
            continue
        
        # Scan forward for retrace entries
        for entry_bar in range(zone_bar + 2, min(zone_bar + 120, n - 5)):
            lo = float(klines[entry_bar].get('l', 0))
            cl = float(klines[entry_bar].get('c', 0))
            op = float(klines[entry_bar].get('o', 0))
            hi = float(klines[entry_bar].get('h', 0))
            
            # Filter: price must actually enter zone (retrace)
            if lo > dz_low:
                continue
            
            # Filter: zone must not be too deeply penetrated
            if lo < dz_low * 0.95:
                break  # Zone likely broken
            
            # Check for bounce confirmation
            # Pinbar: long lower wick, close near high
            body = abs(cl - op)
            lower_wick = min(op, cl) - lo
            is_pinbar = lower_wick > body * 2 and cl > (hi + lo) / 2
            
            # BOS: price breaks above recent swing high
            recent_high = max(float(klines[j].get('h', 0)) for j in range(max(0, zone_bar), entry_bar + 1))
            is_bos = hi > recent_high * 1.005
            
            # Filter: FVG zones need stronger confirmation
            if sig_type == 'FVG_Bull' and not (is_pinbar or is_bos):
                continue  # FVG needs PINBAR or BOS
            
            # CHOCH: structure shift
            is_choch = False
            if entry_bar > zone_bar + 5:
                prev_lows = [float(klines[j].get('l', 0)) for j in range(zone_bar, entry_bar)]
                if prev_lows:
                    min_prev = min(prev_lows)
                    is_choch = lo > min_prev and cl > (hi + lo) / 2
            
            # Sweep entry: liquidity sweep then recovery
            is_sweep = False
            if entry_bar > zone_bar + 3:
                sweep_low = min(float(klines[j].get('l', 0)) for j in range(max(0, entry_bar - 5), entry_bar))
                is_sweep = sweep_low < dz_low * 0.98 and lo > dz_low and cl > dz_low
            
            # Determine entry confirmation
            conf_type = None
            if is_pinbar:
                conf_type = 'PINBAR_ENTRY'
            elif is_bos:
                conf_type = 'BOS_ENTRY'
            elif is_choch:
                conf_type = 'CHOCH_ENTRY'
            elif is_sweep:
                conf_type = 'SWEEP_ENTRY'
            
            if conf_type not in ALLOWED_CONFS:
                continue
            
            # Entry at next bar open (T+1)
            if entry_bar + 1 >= n:
                continue
            entry_price = float(klines[entry_bar + 1].get('o', 0))
            if entry_price <= 0:
                continue
            
            # Build pick
            entry_date = str(klines[entry_bar + 1].get('t', klines[entry_bar + 1].get('date', '')))
            
            # Context sequence (simplified)
            ctx_parts = [sig_type.replace('_Bull', '')]
            if is_pinbar: ctx_parts.append('PINBAR')
            elif is_bos: ctx_parts.append('BOS')
            elif is_choch: ctx_parts.append('CHOCH')
            elif is_sweep: ctx_parts.append('SWEEP')
            ctx_parts.append(conf_type.replace('_ENTRY', ''))
            
            pick = {
                'symbol': symbol,
                'engine': 'V26-3Y',
                'entry_date': entry_date,
                'entry_idx': entry_bar + 1,
                'price': round(entry_price, 2),
                'entry_price': round(entry_price, 2),
                'zone_type': sig_type,
                'zone_bar': zone_bar,
                'zone_age': entry_bar - zone_bar,
                'conf_type': conf_type,
                'ctx_seq': ' → '.join(ctx_parts),
                'detail': ' → '.join(ctx_parts),
                'regime': '',
                'dz_low': round(dz_low, 2),
                'dz_high': round(dz_high, 2),
                'score': 5,
                'retrace_pct': round((dz_low - lo) / dz_low * 100, 1) if dz_low > 0 else 0,
                'entry_quality': 'zone内' if lo <= dz_low else 'zone附近',
                # V25 fields
                'v25_sl_price': 0,
                'v25_sl_pct': 0,
                'v25_tp_tiers': [],
                'v25_cost_line': round(dz_low, 2),
                'v25_zone_bottom': round(dz_low, 2),
                'v25_zone_top': round(dz_high, 2),
                'v25_atr': 0,
                'v25_atr_pct': 0,
                'v25_vol_class': '',
                'v253_quality': 12,
                'v253_tier': 'STANDARD',
            }
            picks.append(pick)
            
            # Only take 1 entry per zone
            break
    
    return picks


def main():
    # Find all available kline files (prefer 750, fallback 300)
    files_750 = list(KLINE_DIR.glob('*_daily_750.json'))
    files_300 = list(KLINE_DIR.glob('*_daily_300.json'))
    
    # Use 750 files primarily
    files = files_750 if len(files_750) > 100 else files_300
    print(f"Scanning {len(files)} stocks with {files[0].stem.split('_')[-1]} bars...")
    
    all_picks = []
    stats = Counter()
    
    for i, f in enumerate(files):
        picks = scan_stock(f)
        if picks:
            all_picks.extend(picks)
            for p in picks:
                stats[f"{p['zone_type']}+{p['conf_type']}"] += 1
        
        if (i + 1) % 500 == 0:
            print(f"  {i+1}/{len(files)}: {len(all_picks)} picks so far...")
    
    print(f"\nTotal: {len(all_picks)} picks from {len(files)} stocks")
    print(f"Combo distribution: {dict(stats.most_common(10))}")
    
    # Deduplicate by symbol+date
    seen = set()
    unique = []
    for p in all_picks:
        key = f"{p['symbol']}_{p['entry_date']}"
        if key not in seen:
            seen.add(key)
            unique.append(p)
    
    print(f"After dedup: {len(unique)} unique picks")
    
    # Sort by date
    unique.sort(key=lambda x: x['entry_date'])
    
    # Save
    out = OUT_DIR / 'v26_picks_3y.json'
    out.write_text(json.dumps(unique, ensure_ascii=False, indent=2))
    print(f"Saved: {out} ({len(unique)} picks)")
    
    # Date range
    dates = [p['entry_date'] for p in unique if p['entry_date']]
    if dates:
        print(f"Date range: {min(dates)} → {max(dates)}")


if __name__ == '__main__':
    main()
