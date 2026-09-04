# -*- coding: utf-8 -*-
"""Rerun WDH + TP2 over Tencent full-history data (2023-04..2026-08)."""
import csv, io, json, os, sys

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
sys.path.insert(0, r"E:\test\smc_project\wdh")
sys.path.insert(0, r"E:\test\smc_project\smc_backtest_report")
import wdh_engine as we
from smc_gates import check_economic_gate

KLINE_T = r"E:\test\smc_project\hermes\kline_cache_tencent"
OUT = r"E:\test\smc_project\wdh"


def bars_for(path):
    try:
        raw = json.load(open(path, encoding="utf-8"))
    except Exception:
        return []
    out = []
    for r in raw if isinstance(raw, list) else []:
        t = str(r.get("t") or "")
        digits = "".join(c for c in t if c.isdigit())[:8]
        o, h, l, c = we.f(r.get("o")), we.f(r.get("h")), we.f(r.get("l")), we.f(r.get("c"))
        if digits and o and h and l and c:
            out.append({"t": digits, "o": o, "h": h, "l": l, "c": c})
    out.sort(key=lambda b: b["t"])
    return out


seeds_all, trades_all = [], []
n = 0
for p in sorted(os.listdir(KLINE_T)):
    if not p.endswith("_daily_800.json"):
        continue
    n += 1
    daily = bars_for(os.path.join(KLINE_T, p))
    if len(daily) < 400:
        continue
    sym = p.replace("_daily_800.json", "").replace("_", ".", 1)
    for sd in we.build_seeds(sym, daily):
        seeds_all.append(sd)
        tr = we.replay_tp2(sd, daily)
        if tr:
            trades_all.append(tr)
    if n % 1000 == 0:
        print(f"  {n} files, seeds {len(seeds_all)}, trades {len(trades_all)}", flush=True)
print(f"DONE: files={n} seeds={len(seeds_all)} trades={len(trades_all)}")

with open(os.path.join(OUT, "TP2_tencent_trades.csv"), "w", newline="", encoding="utf-8-sig") as fh:
    w = csv.DictWriter(fh, fieldnames=list(trades_all[0].keys()) if trades_all else ["symbol"])
    w.writeheader()
    for t in trades_all:
        w.writerow(t)

for t in trades_all:
    t["t1_violation"] = str(t.get("t1_violation", "")).lower() in ("true", "1", "yes")
gate = check_economic_gate(trades_all)
print("\n=== TP2 @腾讯全历史 经济门槛 ===")
for c in gate["checks"]:
    print(f"  {'PASS' if c['pass'] else 'FAIL'} {c['name']}: {c['detail']}")
print("gate_pass:", gate["gate_pass"])
for y in ("2023", "2024", "2025", "2026"):
    s = gate["yearly"][y]
    print(f"  {y}: n={s['n']} WR={s['wr']} avg={s['avg']} PF={s['pf']} payoff={s['payoff']}")
with open(os.path.join(OUT, "TP2_tencent_gate.json"), "w", encoding="utf-8") as fh:
    json.dump({"overall": gate["overall"], "yearly": gate["yearly"], "checks": gate["checks"], "gate_pass": gate["gate_pass"]}, fh, ensure_ascii=False, indent=2)
