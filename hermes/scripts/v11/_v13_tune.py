#!/usr/bin/env python3
"""V13 param tune: 6 combos, file patching, 200 stock test."""
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

# Precision regex to only touch V13 fallback, not V12
def patch(body, dis, near_w, vol):
    with open(SIGNALS) as f: src = f.read()
    # body_pct - only V13 line (has comment with %)
    src = re.sub(r'(if body_pct < )[\d.]+(:.*# )[\d.]+% minimum body',
                 lambda m: f'if body_pct < {body}{m.group(2)}{body}% minimum body', src)
    # dis_ratio - V13 only (relaxed comment)
    src = re.sub(r'(if dis_ratio >= )[\d.]+(:.*# relaxed:)',
                 lambda m: f'if dis_ratio >= {dis}{m.group(2)}', src)
    # near_sw - V13 only (uses near_sw = any( pattern, not near_str)
    src = re.sub(r'(near_sw = any\(abs\(i - si\) <= )[\d]+( for si in swing_near_idxs\))',
                 lambda m: f'near_sw = any(abs(i - si) <= {near_w}{m.group(2)}', src)
    # vol_median - only V13 fallback (vol_ok = bar['v'] > adaptive['vol_median'] * ...)
    src = re.sub(r"(vol_ok = bar\['v'\] > adaptive\['vol_median'\] \* )[\d.]+",
                 lambda m: f"vol_ok = bar['v'] > adaptive['vol_median'] * {vol}", src)
    with open(SIGNALS, 'w') as f: f.write(src)

# Verify
src = open(SIGNALS).read()
print("Verify single-match per pattern:")
for label, pat in [
    ("body_pct V13", r"if body_pct < [\d.]+:.*# [\d.]+% minimum body"),
    ("dis_ratio V13", r"if dis_ratio >= [\d.]+:.*# relaxed:"),
    ("near_sw V13", r"near_sw = any\(abs\(i - si\) <= [\d]+ for si in swing_near_idxs\)"),
    ("vol_median V13", r"vol_ok = bar\['v'\] > adaptive\['vol_median'\] \* [\d.]+"),
]:
    ms = re.findall(pat, src)
    print(f"  {label}: {len(ms)} match(es)" + (" OK" if len(ms) in [1,2] else " PROBLEM!"))

shutil.copy2(SIGNALS, BACKUP)
results = {}
t_start = time.time()

for cname, body, dis, near_w, vol in COMBOS:
    print(f"\n--- {cname}: body={body} dis={dis} near={near_w} vol={vol} ---")
    patch(body, dis, near_w, vol)

    test_code = f'''
import sys, json
sys.path.insert(0, '/root/.hermes/scripts')
from v11.v474_engine import load_ohlcv, calc_stock_params_v45, evaluate_v45_entry, TRADE_SIGNAL_TYPES
from v11.signals_v12 import detect_all_signals_v13_60min
symbols = {json.dumps(SYMBOLS)}
trades_all, stocks_ok = [], 0
for sym in symbols:
    ohlcv = load_ohlcv(sym)
    if not ohlcv or len(ohlcv) < 60: continue
    n = len(ohlcv)
    stock_params = calc_stock_params_v45(ohlcv, sym)
    base_params = {{'fvg_min_width': None, 'sweep_lookback': 12}}
    sr = detect_all_signals_v13_60min(ohlcv, params=base_params, tf='60min')
    all_sigs = sr.get('all', [])
    if not all_sigs or len(all_sigs) < 3: continue
    trades, used = [], set()
    for sig in all_sigs:
        si = sig.get('idx', 0) if isinstance(sig, dict) else getattr(sig, 'idx', 0)
        st = sig.get('type', '') if isinstance(sig, dict) else getattr(sig, 'type', '')
        if st not in TRADE_SIGNAL_TYPES: continue
        if 'OB' not in st: continue
        if si < 40 or si >= n - 10: continue
        su = [s for s in all_sigs if (s.get('idx',0) if isinstance(s,dict) else s.idx) <= si]
        r = evaluate_v45_entry(all_sigs, su, sig, ohlcv, n, 'bull', base_params, stock_params)
        if r:
            if r['entry_idx'] in used: continue
            used.add(r['entry_idx'])
            trades.append(r)
    if len(trades) >= 2:
        stocks_ok += 1
        trades_all.extend(trades)
n = len(trades_all)
if n:
    wins = sum(1 for t in trades_all if t['won'])
    wr = wins/n*100
    wp = sum(t['pnl_pct'] for t in trades_all if t['won'])
    lp = abs(sum(t['pnl_pct'] for t in trades_all if not t['won']))
    pf = wp/lp if lp>0 else 999
    rr = sum(t['rr'] for t in trades_all)/n
    pnl = sum(t['pnl_pct'] for t in trades_all)/n
    print(f"Stocks: {{stocks_ok}}/200 | Trades: {{n}} | WR: {{wr:.1f}}% | RR: {{rr:.2f}}x | PF: {{pf:.0f}} | P&L: {{pnl:+.2f}}%")
else:
    print("Stocks: 0/200 | Trades: 0 | WR: 0.0% | RR: 0.00x | PF: 0 | P&L: +0.00%")
'''
    proc = subprocess.run(['python3', '-c', test_code],
                          capture_output=True, text=True, timeout=180,
                          cwd='/root/.hermes/scripts/v11')
    output = (proc.stdout + proc.stderr).strip()
    # Parse
    stocks, trades, wr, rr, pf, pnl = 0, 0, 0.0, 0.0, 0, 0.0
    for line in output.split('\n'):
        if 'Stocks:' in line:
            parts = line.split('|')
            for p in parts:
                p = p.strip()
                if p.startswith('Stocks:'): stocks = int(p.split('/')[0].split(':')[1].strip())
                elif p.startswith('Trades:'): trades = int(p.split(':')[1].strip())
                elif p.startswith('WR:'): wr = float(p.split('%')[0].split(':')[1].strip())
                elif p.startswith('RR:'): rr = float(p.split('x')[0].split(':')[1].strip())
                elif p.startswith('PF:'): pf = float(p.split(':')[1].strip())
                elif p.startswith('P&L:'): pnl = float(p.split('%')[0].split(':')[1].strip())
            break
    results[cname] = {'stocks': stocks, 'trades': trades, 'WR': wr, 'RR': rr, 'PF': pf, 'P&L': pnl,
                      'params': {'body':body,'dis':dis,'near_w':near_w,'vol':vol}}
    print(f"  => {results[cname]}")

# Restore
shutil.copy2(BACKUP, SIGNALS)
Path(BACKUP).unlink()

print(f"\n\n{'='*70}")
print(f"  V13 PARAM TUNE — {len(SYMBOLS)} stocks, {time.time()-t_start:.0f}s")
print(f"{'='*70}")
print(f"  {'Combo':12s} {'body':>5s} {'dis':>4s} {'near':>4s} {'vol':>4s} {'Stocks':>6s} {'Trades':>6s} {'WR%':>6s} {'RR':>6s} {'PF':>6s}")
print(f"  {'-'*70}")
for cname, r in sorted(results.items(), key=lambda x: -x[1].get('WR', 0)):
    p = r['params']
    print(f"  {cname:12s} {p['body']:5.2f} {p['dis']:4.1f} {p['near_w']:4d} {p['vol']:4.1f} {r['stocks']:6d} {r['trades']:6d} {r['WR']:6.1f} {r['RR']:6.2f} {r['PF']:>6.0f}")
print(f"{'='*70}")

out = Path('/root/.hermes/smc_opt_v474/v13_param_tune.json')
out.write_text(json.dumps(results, indent=2))
print(f"\nSaved to {out}")
