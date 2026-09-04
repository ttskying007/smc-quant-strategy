# -*- coding: utf-8 -*-
"""Upgrade production v13 -> v16b: SMC leg = R20+stage+FVG (199, 3.8%) + v13 events.
Balanced: more SMC supply than v13 (31->199), keeps FVG quality, 2025 best (+2.42%)."""
import json, io, sys
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

# v16b = v15 result (same config); use v15 trades? v16b wasn't saved. Rebuild from v15-run combo
# v15 (combo_v15_run) had same SMC (199) + v13 events = identical to v16b. Save it.
import csv
from collections import defaultdict

# run combo_v15 to save trades (v16b config)
import subprocess
PY = r"C:\Users\Administrator\AppData\Roaming\uv\python\cpython-3.12.13-windows-x86_64-none\python.exe"
r = subprocess.run([PY, r"E:\test\smc_project\research\combo_v15_run.py"], capture_output=True, text=True, timeout=1800, cwd=r"E:\test\smc_project\research", encoding="utf-8", errors="replace")
print("v15 run exit:", r.returncode)

trades = []
with open(r"E:\test\smc_project\research\combo_v15_trades.csv", encoding="utf-8-sig") as fh:
    for rr in csv.DictReader(fh):
        rr["net_pnl_pct"] = float(rr["net_pnl_pct"])
        trades.append(rr)


def stats(rs):
    n = len(rs)
    if not n:
        return None
    w = sum(1 for t in rs if t["net_pnl_pct"] > 0)
    gp = sum(max(t["net_pnl_pct"], 0) for t in rs)
    gl = abs(sum(min(t["net_pnl_pct"], 0) for t in rs))
    return {"n": n, "wr": round(100 * w / n, 1), "avg": round(sum(t["net_pnl_pct"] for t in rs) / n, 3),
            "cum": round(sum(t["net_pnl_pct"] for t in rs), 1), "pf": round(gp / gl, 2) if gl else 0}


by_m = defaultdict(list)
for t in trades:
    by_m[str(t["entry_date"])[:6]].append(t)
monthly = [{"month": m, **stats(by_m[m])} for m in sorted(by_m) if stats(by_m[m]) and m >= "202309"]
by_y = defaultdict(list)
for t in trades:
    by_y[str(t["entry_date"])[:4]].append(t)
yearly = [{"year": y, **stats(by_y[y])} for y in sorted(by_y) if stats(by_y[y])]

dash = {
    "updated": "2026-08-18",
    "version": "COMBO_V16B_BEHAVIOR_DNA_FVG",
    "total_trades": len(trades),
    "yearly": yearly,
    "monthly": monthly,
    "note": "组合v16b = SMC(R20+拉升+熊市FVG, 199笔/3.8%) + 事件(逆势+趋势+深度持有, 5067笔) — SMC腿供应恢复",
}
old = {}
try:
    old = json.load(open(r"E:\test\smc_project\research\combo_dashboard.json", encoding="utf-8"))
except Exception:
    pass
if old.get("paper_production"):
    dash["paper_production"] = old["paper_production"]
if old.get("current_scanner"):
    dash["current_scanner"] = old["current_scanner"]
with open(r"E:\test\smc_project\research\combo_dashboard.json", "w", encoding="utf-8") as fh:
    json.dump(dash, fh, ensure_ascii=False, indent=2)
print("dashboard v16b saved")

reg_p = r"E:\test\smc_project\hermes\smc_monitor\production_registry.json"
reg = json.load(open(reg_p, encoding="utf-8"))
reg["research_candidates"]["COMBO_SMC_EVENT"].update({
    "version": "COMBO_V16B_BEHAVIOR_DNA_FVG",
    "yearly_avg": {y["year"]: y["avg"] for y in yearly if y["year"] in ("2024", "2025", "2026")},
    "yearly_pf": {y["year"]: y["pf"] for y in yearly if y["year"] in ("2024", "2025", "2026")},
    "upgrade_note": "v16b SMC腿供应恢复（31→199笔/3.8%）：总体 +5.38%/PF 3.14，2025 +2.42% 最优，结构更均衡",
})
with open(reg_p, "w", encoding="utf-8") as fh:
    json.dump(reg, fh, ensure_ascii=False, indent=2)
print("registry v16b recorded")
for y in yearly:
    print(f"  {y['year']}: n={y['n']} avg={y['avg']:+.2f}% PF={y['pf']}")
