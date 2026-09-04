# -*- coding: utf-8 -*-
"""Run M0-TP2 tiered-exit replay over W1D1D4 seeds."""
import csv, io, json, os, sys

sys.path.insert(0, r"E:\test\smc_project\wdh")
sys.path.insert(0, r"E:\test\smc_project\smc_backtest_report")
import wdh_engine as we
from smc_gates import check_economic_gate

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

KLINE = r"E:\test\smc_project\hermes\kline_cache"
OUT = r"E:\test\smc_project\wdh"

seeds = []
with open(os.path.join(OUT, "W1D1D4_seeds.csv"), encoding="utf-8-sig") as fh:
    for r in csv.DictReader(fh):
        seeds.append({k.lstrip("\ufeff"): v for k, v in r.items()})
print("seeds:", len(seeds))

cache = {}
trades = []
for sd in seeds:
    sym = sd["symbol"]
    ks = cache.get(sym)
    if ks is None:
        p = os.path.join(KLINE, sym.replace(".", "_") + "_daily_750.json")
        if not os.path.exists(p):
            continue
        ks = we.bars_for(p)
        cache[sym] = ks
    tr = we.replay_tp2(sd, ks)
    if tr:
        trades.append(tr)

print("trades:", len(trades))
with open(os.path.join(OUT, "TP2_trades.csv"), "w", newline="", encoding="utf-8-sig") as fh:
    w = csv.DictWriter(fh, fieldnames=list(trades[0].keys()) if trades else ["symbol"])
    w.writeheader()
    for t in trades:
        w.writerow(t)

# eval with proper t1 parse
for t in trades:
    t["t1_violation"] = str(t.get("t1_violation", "")).lower() in ("true", "1", "yes")
gate = check_economic_gate(trades)
print("\n=== M0-TP2 经济门槛 ===")
for c in gate["checks"]:
    print(f"  {'PASS' if c['pass'] else 'FAIL'} {c['name']}: {c['detail']}")
print("gate_pass:", gate["gate_pass"])
print("yearly:")
for y in ("2023", "2024", "2025", "2026"):
    s = gate["yearly"][y]
    print(f"  {y}: n={s['n']} WR={s['wr']} avg={s['avg']} PF={s['pf']} payoff={s['payoff']}")
from collections import Counter
print("exit reasons:", dict(Counter(t.get("reason") for t in trades)))
with open(os.path.join(OUT, "TP2_gate_result.json"), "w", encoding="utf-8") as fh:
    json.dump({"overall": gate["overall"], "yearly": gate["yearly"], "checks": gate["checks"],
               "gate_pass": gate["gate_pass"]}, fh, ensure_ascii=False, indent=2)
