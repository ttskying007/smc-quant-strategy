#!/usr/bin/env python3
"""
V13 parameter tuning tool.
Patches detect_ob_v13_60min in signals_v12.py, runs 200-stock test, collects results.
Usage: python3 _v13_tune.py
Modify COMBOS list to test different parameter sets.
"""
import subprocess, json, shutil, re, time
from pathlib import Path

SIGNALS = '/root/.hermes/scripts/v11/signals_v12.py'
BACKUP = SIGNALS + '.bak'
CACHE = Path('/root/.hermes/kline_cache_60min')

COMBOS = [
    ('A_current',  0.10, 0.7, 5, 0.3),
    ('B_medium',   0.12, 0.8, 4, 0.4),
    ('C_tighter',  0.15, 0.8, 4, 0.5),
    ('D_strict',   0.15, 1.0, 3, 0.5),
    ('E_light',    0.10, 0.8, 5, 0.3),
    ('F_balanced', 0.12, 0.7, 4, 0.5),
]

files = sorted(CACHE.glob('*_60min_200.json'))[:200]
SYMBOLS = [f.stem.replace('_60min_200','').replace('_','.') for f in files]

def patch(body, dis, near_w, vol):
    with open(SIGNALS) as f: src = f.read()
    src = re.sub(r'(if body_pct < )[\d.]+(:.*# )[\d.]+% minimum body',
                 lambda m: f'if body_pct < {body}{m.group(2)}{body}% minimum body', src)
    src = re.sub(r'(if dis_ratio >= )[\d.]+(:.*# relaxed:)',
                 lambda m: f'if dis_ratio >= {dis}{m.group(2)}', src)
    src = re.sub(r'(near_sw = any\(abs\(i - si\) <= )[\d]+( for si in swing_near_idxs\))',
                 lambda m: f'near_sw = any(abs(i - si) <= {near_w}{m.group(2)}', src)
    src = re.sub(r"(vol_ok = bar\['v'\] > adaptive\['vol_median'\] \* )[\d.]+",
                 lambda m: f"vol_ok = bar['v'] > adaptive['vol_median'] * {vol}", src)
    with open(SIGNALS, 'w') as f: f.write(src)

if __name__ == '__main__':
    shutil.copy2(SIGNALS, BACKUP)
    results = {}
    for cname, body, dis, near_w, vol in COMBOS:
        patch(body, dis, near_w, vol)
        # ... (test code - see actual _v13_tune.py)
    shutil.copy2(BACKUP, SIGNALS)
    Path(BACKUP).unlink()
