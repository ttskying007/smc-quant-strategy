#!/usr/bin/env python3
"""Test: Does Signal object support .get()?"""
import sys
sys.path.insert(0, '/root/.hermes/scripts')
from v11.signals_v12 import Signal, detect_all_signals_v13_60min
import json

# Test basic Signal.get()
s = Signal(type='OB_Bull', idx=10, direction='bull', price=100.0, strength=5.0, confidence=0.5, lower=99.0, upper=101.0)
print(f"Signal type: {type(s).__name__}")
try:
    val = s.get('type')
    print(f"s.get('type') = {val}")
except AttributeError as e:
    print(f"s.get('type') FAILS: {e}")
    print(f"  getattr(s, 'type') = {getattr(s, 'type', '?')}")
    print(f"  s.type = {s.type}")

# Test real signals from V13 detection
cache_dir = '/root/.hermes/kline_cache_60min'
for sym in ['002245.SZ', '600519.SH']:
    fp = f'{cache_dir}/{sym.replace(".","_")}_60min_200.json'
    ohlcv = json.loads(open(fp).read())
    sr = detect_all_signals_v13_60min(ohlcv, tf='60min')
    all_s = sr.get('all', [])
    print(f"\n{sym}: {len(all_s)} total signals")
    for i, sig in enumerate(all_s[:3]):
        actual_type = type(sig).__name__
        try:
            t = sig.get('type', '?')
            print(f"  [{i}] {actual_type}: .get('type')={t}")
        except AttributeError:
            # Try with getattr
            try:
                t = getattr(sig, 'type', '?')
                print(f"  [{i}] {actual_type}: getattr FAILS, fallback={t}")
            except:
                print(f"  [{i}] {actual_type}: COMPLETELY BROKEN")
        except Exception as e:
            print(f"  [{i}] {actual_type}: ERROR={e}")
    
    # Check what types we have
    type_counts = {}
    for sig in all_s:
        tn = type(sig).__name__
        type_counts[tn] = type_counts.get(tn, 0) + 1
    print(f"  Type distribution: {type_counts}")
    
    # Specifically check OB signals
    obs = [s for s in all_s if hasattr(s, 'type') and s.type.startswith('OB')]
    print(f"  OB count: {len(obs)}")
    if obs:
        print(f"  First OB type: {type(obs[0]).__name__}")
        if hasattr(obs[0], 'metadata'):
            print(f"  Metadata: {obs[0].metadata}")
        elif isinstance(obs[0], dict):
            print(f"  Dict keys: {list(obs[0].keys())[:10]}")

print("\nDone.")
