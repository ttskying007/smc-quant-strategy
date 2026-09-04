#!/usr/bin/env python3
"""Deep dive: trace V13 OB signals through the engine's filter chain."""
import json, sys
from pathlib import Path

sys.path.insert(0, '/root/.hermes/scripts')
from v11.signals_v12 import detect_all_signals_v13_60min as v13_detect
from v11.signals_v11 import detect_all_signals_v11 as v11_detect

CACHE_DIR = Path('/root/.hermes/kline_cache_60min')

def load_ohlcv(sym):
    sf = sym.replace('.', '_') + '_60min_200.json'
    fp = CACHE_DIR / sf
    if not fp.exists():
        return None
    return json.loads(fp.read_bytes())

# Pick a stock with many trades from V474
test_stocks = ['002245.SZ', '300112.SZ', '600519.SH', '000858.SZ', '002415.SZ']

for sym in test_stocks:
    ohlcv = load_ohlcv(sym)
    if not ohlcv:
        continue
    
    sr1 = v11_detect(ohlcv, params={'fvg_min_width': None, 'sweep_lookback': 12}, tf='60min')
    sr2 = v13_detect(ohlcv, params={'fvg_min_width': None, 'sweep_lookback': 12}, tf='60min')
    
    v11_obs = [s for s in sr1.get('all', []) if 'OB' in s.get('type', '')]
    v13_obs = [s for s in sr2.get('all', []) if 'OB' in s.get('type', '')]
    
    print(f"\n{'='*80}")
    print(f"{sym}: V11 OBs={len(v11_obs)}  V13 OBs={len(v13_obs)}")
    print(f"{'='*80}")
    
    # Show detailed signal properties for first 3 V11 OBs
    print(f"\n  --- Top 3 V11 OBs ---")
    for s in v11_obs[:3]:
        meta = s.get('metadata', {}) if isinstance(s, dict) else {}
        if isinstance(s, dict):
            print(f"  idx={s.get('idx')} type={s.get('type')} "
                  f"strength={s.get('strength'):.2f} conf={s.get('confidence'):.3f} "
                  f"vol={s.get('volume_ratio'):.2f}x")
            print(f"    metadata: body={meta.get('body_pct','?')}% "
                  f"dis={meta.get('displacement_ratio','?')}x "
                  f"imp={meta.get('impulse_bars','?')} bars")
        else:
            print(f"  idx={s.idx} type={s.type} "
                  f"strength={s.strength:.2f} conf={s.confidence:.3f} "
                  f"vol={s.volume_ratio:.2f}x")
            print(f"    metadata: body={meta.get('body_pct','?')}% "
                  f"dis={meta.get('displacement_ratio','?')}x "
                  f"imp={meta.get('impulse_bars','?')} bars")
    
    # Show detailed signal properties for first 3 V13 OBs
    print(f"\n  --- Top 3 V13 OBs ---")
    for s in v13_obs[:3]:
        meta = s.get('metadata', {}) if isinstance(s, dict) else {}
        if isinstance(s, dict):
            print(f"  idx={s.get('idx')} type={s.get('type')} "
                  f"strength={s.get('strength'):.2f} conf={s.get('confidence'):.3f} "
                  f"vol={s.get('volume_ratio'):.2f}x")
            print(f"    metadata: body={meta.get('body_pct','?')}% "
                  f"dis={meta.get('displacement_ratio','?')}x "
                  f"imp={meta.get('impulse_bars','?')} bars "
                  f"method={meta.get('ob_method','?')}")
        else:
            print(f"  idx={s.idx} type={s.type} "
                  f"strength={s.strength:.2f} conf={s.confidence:.3f} "
                  f"vol={s.volume_ratio:.2f}x")
            print(f"    metadata: body={meta.get('body_pct','?')}% "
                  f"dis={meta.get('displacement_ratio','?')}x "
                  f"imp={meta.get('impulse_bars','?')} bars "
                  f"method={meta.get('ob_method','?')}")
    
    # Quality filter simulation
    print(f"\n  --- Engine filter simulation ---")
    quality_threshold = 0.50  # from v474_engine.py QUALITY_THRESHOLDS
    v11_qual = sum(1 for s in v11_obs if (s.get('confidence',0) if isinstance(s,dict) else s.confidence) >= quality_threshold)
    v13_qual = sum(1 for s in v13_obs if (s.get('confidence',0) if isinstance(s,dict) else s.confidence) >= quality_threshold)
    print(f"  After quality >= {quality_threshold}: V11={v11_qual}/{len(v11_obs)} V13={v13_qual}/{len(v13_obs)}")
    
    # Count OBs that have valid displacement info
    v11_has_meta = sum(1 for s in v11_obs if (s.get('metadata',{}) if isinstance(s,dict) else {}) != {})
    v13_has_meta = sum(1 for s in v13_obs if (s.get('metadata',{}) if isinstance(s,dict) else {}) != {})
    print(f"  Has metadata: V11={v11_has_meta}/{len(v11_obs)} V13={v13_has_meta}/{len(v13_obs)}")
    
    # Check OB method distribution for V13
    methods = {}
    for s in v13_obs:
        meta = s.get('metadata', {}) if isinstance(s, dict) else {}
        m = meta.get('ob_method', 'unknown') if isinstance(meta, dict) else 'unknown'
        methods[m] = methods.get(m, 0) + 1
    if methods:
        print(f"  V13 method distribution: {methods}")

print("\nDone.")
