#!/usr/bin/env python3
"""Debug V12 OB backward scan - why producing zero results."""
import json, sys, os
sys.path.insert(0, '/root/.hermes/scripts')
os.chdir('/root/.hermes/scripts/v11')

from signals_v12 import detect_swings_v12, calc_adaptive_thresholds

with open('/root/.hermes/kline_cache_60min/600997_SH_60min_200.json') as f:
    ohlcv = json.load(f)
if not isinstance(ohlcv, list):
    ohlcv = ohlcv.get('data', ohlcv.get('klines', ohlcv))

adaptive = calc_adaptive_thresholds(ohlcv)
vol_median = adaptive['vol_median']
print(f"vol_median = {vol_median}")

swing_highs, swing_lows = detect_swings_v12(ohlcv)
print(f"Swing highs: {len(swing_highs)}, Swing lows: {len(swing_lows)}")

n = len(ohlcv)
displacement_mult = 1.0
require_volume = True
processed = set()

# Manually run the V12 backward scan for each swing high
for sh_idx, sh_price in swing_highs:
    if sh_idx < 5:
        continue
    phase = 'skip'
    impulse_len = 0
    ob_idx = None

    for bi in range(sh_idx - 1, max(sh_idx - 25, 4), -1):
        bar = ohlcv[bi]
        is_bear = bar['c'] < bar['o']
        is_bull = bar['c'] > bar['o']

        if phase == 'skip':
            if is_bear:
                continue
            elif is_bull:
                phase = 'impulse'
                impulse_len = 1
            else:
                continue
        elif phase == 'impulse':
            if is_bull:
                impulse_len += 1
                continue
            elif is_bear:
                ob_idx = bi
                break
            else:
                ob_idx = bi
                break

    if ob_idx is None or impulse_len < 2:
        print(f"  SH[{sh_idx:3d}] price={sh_price:.3f}: SKIP (ob_idx={ob_idx}, impulse_len={impulse_len})")
        continue

    ob_bar = ohlcv[ob_idx]
    body_pct = abs(ob_bar['c'] - ob_bar['o']) / max(ob_bar['o'], 0.01) * 100
    if body_pct < 0.15:
        print(f"  SH[{sh_idx:3d}] price={sh_price:.3f}: SKIP body too small ({body_pct:.2f}%)")
        continue

    bar_range = ob_bar['h'] - ob_bar['l']
    if bar_range <= 0:
        continue

    displacement = sh_price - ob_bar['l']
    dis_ratio = displacement / bar_range

    if dis_ratio < displacement_mult:
        print(f"  SH[{sh_idx:3d}] price={sh_price:.3f}: SKIP dis_ratio={dis_ratio:.2f} < {displacement_mult}")
        continue

    # Volume check
    impulse_end = ob_idx + impulse_len + 1
    impulse_vols = [ohlcv[j]['v'] for j in range(ob_idx + 1, min(impulse_end + 1, n))]
    avg_imp_v = sum(impulse_vols) / max(len(impulse_vols), 1)
    vol_ok = avg_imp_v > vol_median * 1.2 or ob_bar['v'] > vol_median * 1.2

    print(f"  SH[{sh_idx:3d}] price={sh_price:.3f}: OB at [{ob_idx:3d}] "
          f"body={body_pct:.2f}% dis_ratio={dis_ratio:.2f} impulse={impulse_len} "
          f"vol_ok={vol_ok} avg_imp_v={avg_imp_v:.0f} ob_v={ob_bar['v']:.0f} vol_med={vol_median:.0f}")
    
    if not vol_ok and require_volume:
        print(f"    -> VOLUME FAIL: avg_imp_v={avg_imp_v:.0f} < {vol_median*1.2:.0f}")

print("\n=== Now testing with require_volume=False ===")
processed_2 = set()
count = 0
for sh_idx, sh_price in swing_highs:
    if sh_idx < 5: continue
    phase = 'skip'
    impulse_len = 0
    ob_idx = None
    for bi in range(sh_idx - 1, max(sh_idx - 25, 4), -1):
        bar = ohlcv[bi]
        is_bear = bar['c'] < bar['o']
        is_bull = bar['c'] > bar['o']
        if phase == 'skip':
            if is_bear: continue
            elif is_bull: phase = 'impulse'; impulse_len = 1
            else: continue
        elif phase == 'impulse':
            if is_bull: impulse_len += 1; continue
            elif is_bear: ob_idx = bi; break
            else: ob_idx = bi; break
    if ob_idx is None or impulse_len < 2: continue
    count += 1

print(f"Total OBs from swing scan (volume-agnostic): {count}")
