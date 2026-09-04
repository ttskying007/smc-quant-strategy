# -*- coding: utf-8 -*-
import csv, io, json, os, sys

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
sys.path.insert(0, r"E:\test\smc_project\smc_backtest_report")
from smc_gates import check_economic_gate

trades = []
with open(r"E:\test\smc_project\wdh\W1D1D4_trades.csv", encoding="utf-8-sig") as fh:
    for r in csv.DictReader(fh):
        r["t1_violation"] = str(r.get("t1_violation", "")).lower() in ("true", "1", "yes")
        trades.append(r)

print("trades:", len(trades))
gate = check_economic_gate(trades)
for c in gate["checks"]:
    print(f"  {'PASS' if c['pass'] else 'FAIL'} {c['name']}: {c['detail']}")
print("gate_pass:", gate["gate_pass"])
print("yearly:")
for y in ("2023", "2024", "2025", "2026"):
    s = gate["yearly"][y]
    print(f"  {y}: n={s['n']} WR={s['wr']} avg={s['avg']} PF={s['pf']}")
# exit reasons
from collections import Counter
print("exit reasons:", dict(Counter(t.get("reason") for t in trades)))
with open(r"E:\test\smc_project\wdh\wdh_gate_result.json", "w", encoding="utf-8") as fh:
    json.dump({"n": gate["overall"], "yearly": gate["yearly"], "checks": gate["checks"], "gate_pass": gate["gate_pass"]},
              fh, ensure_ascii=False, indent=2)
