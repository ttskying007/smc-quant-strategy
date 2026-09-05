# -*- coding: utf-8 -*-
"""修复前后回测对比：旧版(MAX_HOLD5/固定阈值/无防未来) vs 修复后(ISO周/OB/量能/BOS12/涨停/滑点)"""
import csv, os, sys
from collections import defaultdict
sys.stdout.reconfigure(encoding="utf-8", errors="replace")

WDH = r"E:\test\smc_project\wdh"
def load(p):
    rows = []
    with open(os.path.join(WDH, p), encoding="utf-8-sig") as fh:
        for r in csv.DictReader(fh):
            try:
                r["net_pnl_pct"] = float(r["net_pnl_pct"]) if r["net_pnl_pct"] not in (None, "", "None") else None
            except Exception:
                r["net_pnl_pct"] = None
            rows.append(r)
    return rows

def stats(pnls):
    if not pnls:
        return None
    n = len(pnls)
    mean = sum(pnls) / n
    wins = [x for x in pnls if x > 0]
    losses = [x for x in pnls if x <= 0]
    pf = sum(wins) / abs(sum(losses)) if losses else 99.0
    return {"n": n, "avg": mean, "win": len(wins) / n, "pf": pf}

pre = load("W1D1D4_trades.csv")      # 旧版（刚跑）
fix = load("W1D1D4_trades_fixed.csv")  # 修复后（备份）

L = ["# 修复前后回测对比（SMC腿 W1D1D4）", ""]
L.append("| 指标 | 修复前(旧版) | 修复后 | 变化 |")
L.append("|---|---:|---:|---:|")
for name, key in (("交易数", "n"), ("均值%", "avg"), ("胜率%", "win"), ("PF", "pf")):
    s0, s1 = stats([r["net_pnl_pct"] for r in pre if r["net_pnl_pct"] is not None]), stats([r["net_pnl_pct"] for r in fix if r["net_pnl_pct"] is not None])
    if name == "交易数":
        v0, v1 = len([r for r in pre if r["net_pnl_pct"] is not None]), len([r for r in fix if r["net_pnl_pct"] is not None])
        L.append(f"| {name} | {v0:,} | {v1:,} | {v1-v0:+,} (×{v1/max(v0,1):.1f}) |")
    else:
        a, b = s0[key], s1[key]
        delta = (b - a) if name in ("均值%", "胜率%") else (b - a)
        L.append(f"| {name} | {a*100 if name=='胜率%' else a:+.2f} | {b*100 if name=='胜率%' else b:+.2f} | {delta*100 if name=='胜率%' else delta:+.2f} |")
L.append("")

# 逐年对比
L.append("## 逐年对比")
by = {}
for tag, rows in (("修复前", pre), ("修复后", fix)):
    d = defaultdict(list)
    for r in rows:
        if r["net_pnl_pct"] is None:
            continue
        d[str(r["entry_date"])[:4]].append(r["net_pnl_pct"])
    by[tag] = d
all_y = sorted(set(by["修复前"]) | set(by["修复后"]))
L.append("| 年份 | 修复前 n | 修复前均值% | 修复后 n | 修复后均值% |")
L.append("|---|---:|---:|---:|---:|")
for y in all_y:
    s0 = stats(by["修复前"].get(y, []))
    s1 = stats(by["修复后"].get(y, []))
    L.append(f"| {y} | {s0['n'] if s0 else 0} | {s0['avg'] if s0 else 0:+.2f} | {s1['n'] if s1 else 0} | {s1['avg'] if s1 else 0:+.2f} |")
L.append("")

# 卖点分布对比
L.append("## 卖点分布对比")
for tag, rows in (("修复前", pre), ("修复后", fix)):
    rc = defaultdict(int)
    for r in rows:
        rc[r.get("reason", "?")] += 1
    tot = len(rows) or 1
    L.append(f"- **{tag}**: " + ", ".join(f"{k}={v}({v/tot*100:.0f}%)" for k, v in sorted(rc.items(), key=lambda kv: -kv[1])))
L.append("")

md = "\n".join(L)
out = r"E:\test\smc_project\research\handover\修复前后回测对比.md"
with open(out, "w", encoding="utf-8") as fh:
    fh.write(md)
print(md)
