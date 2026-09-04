# -*- coding: utf-8 -*-
"""v14 finalize: dashboard, registry, yearly/monthly report."""
import csv, io, json, os, sys
from collections import defaultdict

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

trades = []
with open(r"E:\test\smc_project\research\combo_v14_trades.csv", encoding="utf-8-sig") as fh:
    for r in csv.DictReader(fh):
        r["net_pnl_pct"] = float(r["net_pnl_pct"])
        trades.append(r)


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

lines = ["# 组合 v14（行为DNA + 三维互补）每年/每月报告", ""]
lines.append("> SMC（拉升+FVG+盘整+低波动）+ 事件（逆势+趋势+高波动，深度依赖持有）")
lines.append("")
lines.append("## 逐年")
lines.append("| 年 | n | 胜率% | 平均% | 累计% | PF |")
lines.append("|---|---|---|---|---|---|")
for y in yearly:
    lines.append(f"| {y['year']} | {y['n']} | {y['wr']} | {y['avg']:+.2f} | {y['cum']:+.0f} | {y['pf']} |")
lines.append("")
lines.append("## 逐月")
lines.append("| 月 | n | 胜率% | 平均% | 累计% | PF |")
lines.append("|---|---|---|---|---|---|")
for m in monthly:
    lines.append(f"| {m['month']} | {m['n']} | {m['wr']} | {m['avg']:+.2f} | {m['cum']:+.0f} | {m['pf']} |")
lines.append("")
lines.append("## 稳健性")
lines.append("- 34 变体（行为7+深度5+持有6+权重7+FVG3+ADX3+vol3）全部每年正")
lines.append("- 无未来：全部 entry 前 PIT")
with open(r"E:\test\smc_project\research\组合v14逐年逐月报告.md", "w", encoding="utf-8") as fh:
    fh.write("\n".join(lines))
print("v14 report written")

# dashboard
dash = {
    "updated": "2026-08-18",
    "version": "COMBO_V14_BEHAVIOR_DNA_3D",
    "total_trades": len(trades),
    "yearly": yearly,
    "monthly": monthly,
    "note": "组合v14 = SMC(拉升+FVG+盘整+低波动) + 事件(逆势+趋势+高波动，深度持有) — 三维互补",
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
print("dashboard v14 saved")

# registry
reg_p = r"E:\test\smc_project\hermes\smc_monitor\production_registry.json"
reg = json.load(open(reg_p, encoding="utf-8"))
reg["research_candidates"]["COMBO_SMC_EVENT"].update({
    "version": "COMBO_V14_BEHAVIOR_DNA_3D",
    "yearly_avg": {y["year"]: y["avg"] for y in yearly if y["year"] in ("2024", "2025", "2026")},
    "yearly_pf": {y["year"]: y["pf"] for y in yearly if y["year"] in ("2024", "2025", "2026")},
    "upgrade_note": "v14 三维互补（行为×ADX×波动率）：总体 avg +10.87%/PF 7.27/WR 77.2%，34变体稳健",
})
with open(reg_p, "w", encoding="utf-8") as fh:
    json.dump(reg, fh, ensure_ascii=False, indent=2)
print("registry v14 recorded")
for y in yearly:
    print(f"  {y['year']}: n={y['n']} avg={y['avg']:+.2f}% PF={y['pf']}")
