import json
from collections import Counter

with open('/root/.hermes/smc_opt_v25/v25_picks.json') as f:
    picks = json.load(f)

total = len(picks)
print(f"=== SMC V25 Pick Quality Analysis ===\n")
print(f"Total picks: {total}")

# Compute RR from v25 fields: TP1 / SL
low_rr = []
rr_values = []
for p in picks:
    sl = p.get('v25_sl_pct', 0)
    tp_tiers = p.get('v25_tp_tiers', [])
    tp1 = tp_tiers[0].get('pct', 0) if tp_tiers else 0
    rr = round(tp1 / sl, 2) if sl > 0 and tp1 > 0 else 0.0
    rr_values.append(rr)
    if rr < 1.5:
        low_rr.append((p['symbol'], rr, sl, tp1, p.get('v25_vol_class','?')))

# RR distribution
rr_values.sort()
print(f"\n--- Risk/Reward (TP1/SL) ---")
print(f"RR < 1.0: {sum(1 for r in rr_values if r < 1.0)}")
print(f"RR < 1.5: {len(low_rr)}")
print(f"RR range: {rr_values[0]:.2f} - {rr_values[-1]:.2f}")
print(f"RR median: {rr_values[len(rr_values)//2]:.2f}")
p90_idx = int(len(rr_values) * 0.9)
print(f"RR p90: {rr_values[min(p90_idx, len(rr_values)-1)]:.2f}")

if low_rr:
    print(f"\nLow RR picks (<1.5) — top 15:")
    low_rr.sort(key=lambda x: x[1])
    for sym, rr, sl, tp1, vol in low_rr[:15]:
        print(f"  {sym:12s} RR={rr:.2f}  SL={sl:.1f}%  TP1={tp1:.1f}%  vol={vol}")

# Vol class breakdown
vols = Counter(p.get('v25_vol_class', '?') for p in picks)
print(f"\n--- Vol Classes ---")
for v, c in vols.most_common():
    print(f"  {v}: {c}")

# Win/loss
won = sum(1 for p in picks if p.get('won'))
lost = total - won
print(f"\n--- Backtest Outcomes ---")
print(f"  Won: {won} ({won/total*100:.1f}%)")
print(f"  Lost: {lost} ({lost/total*100:.1f}%)")

# PnL stats
pnls = [p.get('pnl_pct', 0) for p in picks]
avg_pnl = sum(pnls) / len(pnls) if pnls else 0
print(f"  Avg PnL: {avg_pnl:+.2f}%")

# SL outliers (very wide stops)
wide_sl = [(p['symbol'], p.get('v25_sl_pct', 0)) for p in picks if p.get('v25_sl_pct', 0) > 15]
if wide_sl:
    print(f"\n--- Wide SL (>15%) — {len(wide_sl)} picks ---")
    for sym, sl in sorted(wide_sl, key=lambda x: -x[1])[:10]:
        print(f"  {sym:12s} SL={sl:.1f}%")

# Regime breakdown
regimes = Counter(p.get('regime', '?') for p in picks)
print(f"\n--- Regimes ---")
for r, c in regimes.most_common():
    print(f"  {r}: {c}")

# Engines
engines = Counter(p.get('engine', '?') for p in picks)
print(f"\n--- Engines ---")
for e, c in engines.most_common():
    print(f"  {e}: {c}")

print(f"\n=== Summary: {'HEALTHY' if len(low_rr) < total*0.3 else 'ATTENTION NEEDED'} ===")
