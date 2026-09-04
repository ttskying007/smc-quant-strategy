# -*- coding: utf-8 -*-
"""SMC 腿恢复：检查 wdh trades + 月度互补验证 + 整合进 v20f"""
import csv, io, json, os, sys
from collections import defaultdict
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

p = r"E:\test\smc_project\wdh\W1D1D4_trades.csv"
rows = []
with open(p, encoding="utf-8-sig") as fh:
    reader = csv.DictReader(fh)
    fields = reader.fieldnames
    for r in reader:
        rows.append(r)
print(f"SMC 交易: {len(rows)} 笔")
print(f"字段: {fields[:12]}")

# performance
key = "net_pnl_pct" if "net_pnl_pct" in fields else ("pnl_pct" if "pnl_pct" in fields else None)
if key:
    pnls = []
    dates = []
    for r in rows:
        try:
            pnls.append(float(r.get(key, 0)))
            dates.append(str(r.get("entry_date", r.get("entry_idx", "")))[:10])
        except Exception:
            pass
    if pnls:
        wins = [x for x in pnls if x > 0]
        pf = sum(wins) / abs(sum(x for x in pnls if x <= 0)) if any(x <= 0 for x in pnls) else 99
        print(f"\navg {sum(pnls)/len(pnls):+.2f}% | 胜率 {100*len(wins)/len(pnls):.0f}% | PF {pf:.2f}")
        # by year
        for y in ("2024", "2025", "2026"):
            ys = [pnls[i] for i in range(len(pnls)) if dates[i][:4] == y]
            if ys:
                print(f"  {y}: n={len(ys)} avg={sum(ys)/len(ys):+.2f}%")
        # monthly complement vs event
        ev = []
        with open(r"E:\test\smc_project\research\combo_v20f_trades.csv", encoding="utf-8-sig") as fh2:
            for r2 in csv.DictReader(fh2):
                if r2.get("src") == "EVENT":
                    ev.append((str(r2["entry_date"])[:6], float(r2["net_pnl_pct"])))
        smc_m = defaultdict(list)
        ev_m = defaultdict(list)
        for i, d in enumerate(dates):
            if d[:6] >= "202309":
                smc_m[d[:6]].append(pnls[i])
        for m, pnl in ev:
            if m >= "202309":
                ev_m[m].append(pnl)
        print("\n=== SMC vs 事件 月度互补（2026）===")
        for m in sorted(set(list(smc_m.keys()) + list(ev_m.keys()))):
            if not m.startswith("2026"):
                continue
            s_avg = sum(smc_m[m]) / len(smc_m[m]) if smc_m[m] else 0
            e_avg = sum(ev_m[m]) / len(ev_m[m]) if ev_m[m] else 0
            if smc_m[m] and ev_m[m]:
                tag = "互补✓" if (s_avg > 0 and e_avg < 0) or (s_avg < 0 and e_avg > 0) else ""
                print(f"  {m}: SMC {s_avg:+.2f}% vs 事件 {e_avg:+.2f}% {tag}")
