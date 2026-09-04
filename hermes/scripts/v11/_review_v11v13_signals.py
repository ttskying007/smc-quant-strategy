#!/usr/bin/env python3
"""Compare V11 vs V13 OB signal quality at signal level (before engine filtering)."""
import json, sys, statistics
from pathlib import Path

sys.path.insert(0, '/root/.hermes/scripts')
from v11.signals_v11 import detect_all_signals_v11 as v11_detect
from v11.signals_v12 import detect_all_signals_v13_60min as v13_detect

CACHE_DIR = Path('/root/.hermes/kline_cache_60min')

# Use symbol list from V474 full scan
with open('/root/.hermes/smc_opt_v474/v45_full.json') as f:
    all_trades = json.load(f)

# Get the top 10 stocks by trade count from V474
from collections import Counter
sym_counter = Counter()
for t in all_trades:
    pass  # no symbol in flat trades

# Instead, use known symbols from cache
symbols = sorted([f.stem.replace('_60min_200', '').replace('_', '.')
                  for f in CACHE_DIR.glob('*_60min_200.json')])

def load_ohlcv(sym):
    sf = sym.replace('.', '_') + '_60min_200.json'
    fp = CACHE_DIR / sf
    if not fp.exists():
        return None
    return json.loads(fp.read_bytes())

print("=" * 100)
print("V11 vs V13 OB SIGNAL QUALITY COMPARISON (30 stocks)")
print("=" * 100)

# Sample 30 stocks across market caps
test_symbols = [s for s in symbols if '688' not in s][:30]

all_v11_obs = []
all_v13_obs = []

for sym in test_symbols:
    ohlcv = load_ohlcv(sym)
    if not ohlcv or len(ohlcv) < 60:
        continue
    
    # V11 signals
    sr1 = v11_detect(ohlcv, params={'fvg_min_width': None, 'sweep_lookback': 12}, tf='60min')
    v11_obs = [s for s in sr1.get('all', []) if 'OB' in s.get('type', '')]
    all_v11_obs.extend(v11_obs)
    
    # V13 signals
    sr2 = v13_detect(ohlcv, params={'fvg_min_width': None, 'sweep_lookback': 12}, tf='60min')
    v13_obs = [s for s in sr2.get('all', []) if 'OB' in s.get('type', '')]
    all_v13_obs.extend(v13_obs)

print(f"\nV11: {len(all_v11_obs)} OB signals across {len(test_symbols)} stocks")
print(f"V13: {len(all_v13_obs)} OB signals across {len(test_symbols)} stocks")
print(f"Ratio: {len(all_v13_obs)/max(len(all_v11_obs),1):.2f}x")

# Strength comparison
def get_attr(sigs, attr, default=0):
    vals = []
    for s in sigs:
        if isinstance(s, dict):
            v = s.get(attr, s.get(attr.replace('strength','strength'), default))
        else:
            v = getattr(s, attr, default)
        if v is not None:
            vals.append(float(v))
    return vals

v11_strength = get_attr(all_v11_obs, 'strength')
v13_strength = get_attr(all_v13_obs, 'strength')
v11_confidence = get_attr(all_v11_obs, 'confidence')
v13_confidence = get_attr(all_v13_obs, 'confidence')

print(f"\nSTRENGTH:  V11 mean={statistics.mean(v11_strength):.2f} median={statistics.median(v11_strength):.2f}")
print(f"           V13 mean={statistics.mean(v13_strength):.2f} median={statistics.median(v13_strength):.2f}")
print(f"CONFIDENCE: V11 mean={statistics.mean(v11_confidence):.3f} median={statistics.median(v11_confidence):.3f}")
print(f"           V13 mean={statistics.mean(v13_confidence):.3f} median={statistics.median(v13_confidence):.3f}")

# Check metadata
print(f"\n--- V13 fallback ratio ---")
fb_count = 0
for s in all_v13_obs:
    meta = s.get('metadata', {}) if isinstance(s, dict) else getattr(s, 'metadata', {})
    if meta.get('ob_method', '').startswith('v13_fallback'):
        fb_count += 1
print(f"  Forward-fallback OBs: {fb_count}/{len(all_v13_obs)} ({fb_count/max(len(all_v13_obs),1)*100:.0f}%)")

# Displacement ratio comparison
print(f"\n--- DISPLACEMENT RATIO ---")
v11_disps = []
for s in all_v11_obs:
    meta = s.get('metadata', {}) if isinstance(s, dict) else getattr(s, 'metadata', {})
    if isinstance(meta, dict):
        v11_disps.append(meta.get('displacement_ratio', 0))
v13_disps = []
for s in all_v13_obs:
    meta = s.get('metadata', {}) if isinstance(s, dict) else getattr(s, 'metadata', {})
    if isinstance(meta, dict):
        v13_disps.append(meta.get('displacement_ratio', 0))

if v11_disps:
    print(f"  V11: mean={statistics.mean(v11_disps):.2f}x median={statistics.median(v11_disps):.2f}x range={min(v11_disps):.2f}-{max(v11_disps):.2f}x")
if v13_disps:
    print(f"  V13: mean={statistics.mean(v13_disps):.2f}x median={statistics.median(v13_disps):.2f}x range={min(v13_disps):.2f}-{max(v13_disps):.2f}x")

# Body pct comparison
print(f"\n--- BODY PCT ---")
v11_bodies = []
for s in all_v11_obs:
    meta = s.get('metadata', {}) if isinstance(s, dict) else getattr(s, 'metadata', {})
    if isinstance(meta, dict):
        v11_bodies.append(meta.get('body_pct', 0))
v13_bodies = []
for s in all_v13_obs:
    meta = s.get('metadata', {}) if isinstance(s, dict) else getattr(s, 'metadata', {})
    if isinstance(meta, dict):
        v13_bodies.append(meta.get('body_pct', 0))

if v11_bodies:
    print(f"  V11: mean={statistics.mean(v11_bodies):.3f}% median={statistics.median(v11_bodies):.3f}% range={min(v11_bodies):.3f}-{max(v11_bodies):.3f}%")
if v13_bodies:
    print(f"  V13: mean={statistics.mean(v13_bodies):.3f}% median={statistics.median(v13_bodies):.3f}% range={min(v13_bodies):.3f}-{max(v13_bodies):.3f}%")

# Impulse bars comparison
print(f"\n--- IMPULSE BARS ---")
v11_imp = []
for s in all_v11_obs:
    meta = s.get('metadata', {}) if isinstance(s, dict) else getattr(s, 'metadata', {})
    if isinstance(meta, dict):
        v11_imp.append(meta.get('impulse_bars', 0))
v13_imp = []
for s in all_v13_obs:
    meta = s.get('metadata', {}) if isinstance(s, dict) else getattr(s, 'metadata', {})
    if isinstance(meta, dict):
        v13_imp.append(meta.get('impulse_bars', 0))

if v11_imp:
    print(f"  V11: mean={statistics.mean(v11_imp):.1f} median={statistics.median(v11_imp):.0f}")
if v13_imp:
    print(f"  V13: mean={statistics.mean(v13_imp):.1f} median={statistics.median(v13_imp):.0f}")

# Volume ratio comparison
print(f"\n--- VOLUME RATIO ---")
v11_vol = get_attr(all_v11_obs, 'volume_ratio')
v13_vol = get_attr(all_v13_obs, 'volume_ratio')
if v11_vol: print(f"  V11: mean={statistics.mean(v11_vol):.2f}x median={statistics.median(v11_vol):.2f}x")
if v13_vol: print(f"  V13: mean={statistics.mean(v13_vol):.2f}x median={statistics.median(v13_vol):.2f}x")

print("\nDone.")
