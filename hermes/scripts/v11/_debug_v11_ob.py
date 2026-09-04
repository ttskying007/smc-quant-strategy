#!/usr/bin/env python3
"""Debug why V11 returns 0 OB on these stocks."""
import json, sys
from pathlib import Path
sys.path.insert(0, '/root/.hermes/scripts')
from v11.signals_v11 import detect_all_signals_v11

CACHE = Path('/root/.hermes/kline_cache_60min')
cf = CACHE / "688800_SH_60min_200.json"
with open(cf) as f:
    ohlcv = json.load(f)

print(f"OHLCV type: {type(ohlcv).__name__}, len={len(ohlcv)}")
print(f"First bar type: {type(ohlcv[0]).__name__}, keys={list(ohlcv[0].keys())[:6]}")
print(f"First bar sample: {ohlcv[0]}")

# Call V11 and catch any errors
try:
    r = detect_all_signals_v11(ohlcv)
    print(f"\nV11 result keys: {list(r.keys())[:10]}")
    print(f"OB_Bull: {len(r.get('OB_Bull', []))}")
    print(f"OB_Bear: {len(r.get('OB_Bear', []))}")
    print(f"FVG_Bull: {len(r.get('FVG_Bull', []))}")
    print(f"all signals: {len(r.get('all', []))}")
except Exception as e:
    print(f"V11 error: {type(e).__name__}: {e}")
    import traceback
    traceback.print_exc()
