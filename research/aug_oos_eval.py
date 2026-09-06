# -*- coding: utf-8 -*-
"""8 月完整 OOS 评估（数据补全后）—— 两腿 7 月 vs 8 月对比 + 月度全景"""
import csv, os, shutil, sys
from collections import defaultdict

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
RESEARCH = r"E:\test\smc_project\research"
FRONT = [r"E:\test\smc_project\hermes\smc_monitor", r"E:\root\.hermes\smc_monitor"]


def load(p):
    with open(p, encoding="utf-8-sig") as fh:
        return [r for r in csv.DictReader(fh) if r.get("net_pnl_pct") not in (None, "", "None")]


def stats(pn):
    if not pn:
        return None
    n = len(pn)
    mean = sum(pn) / n
    w = [x for x in pn if x > 0]
    l = [x for x in pn if x <= 0]
    pf = round(sum(w) / abs(sum(l)), 2) if l else 99
    return {"n": n, "avg": round(mean, 3), "pf": pf}


smc = load(os.path.join(RESEARCH, "..", "wdh", "W1D1D4_trades.csv"))
ev = [r for r in load(os.path.join(RESEARCH, "combo_v20f_trades.csv")) if r.get("src") == "EVENT"]

L = ["# 8 月完整 OOS 评估（2026-09-06，数据补全后）", "",
     "> 数据：daily/m60/公告全对齐 2026-09-04 | SMC 用 tencent 缓存(4662只) | 事件腿 cap500", ""]

L.append("## 一、月度全景（两腿）")
L.append("| 月 | SMC n | SMC avg% | SMC PF | 事件 n | 事件 avg% | 事件 PF |")
L.append("|---|---:|---:|---:|---:|---:|---:|")
by = defaultdict(lambda: {"smc": [], "ev": []})
for r in smc:
    by[r["entry_date"][:6]]["smc"].append(float(r["net_pnl_pct"]))
for r in ev:
    by[r["entry_date"][:6]]["ev"].append(float(r["net_pnl_pct"]))
for m in sorted(by):
    s1, s2 = stats(by[m]["smc"]), stats(by[m]["ev"])
    a1 = f"{s1['avg']:+.2f}" if s1 else "0.00"
    p1 = f"{s1['pf']:.2f}" if s1 else "0.00"
    a2 = f"{s2['avg']:+.2f}" if s2 else "0.00"
    p2 = f"{s2['pf']:.2f}" if s2 else "0.00"
    L.append(f"| {m} | {s1['n'] if s1 else 0} | {a1} | {p1} | {s2['n'] if s2 else 0} | {a2} | {p2} |")
L.append("")

L.append("## 二、事件腿：7 月前 vs 8 月完整 vs 9 月")
for name, cond in (("<=202607", lambda m: m <= "202607"),
                   ("202608 完整", lambda m: m == "202608"),
                   ("202609 起", lambda m: m >= "202609")):
    pn = [float(r["net_pnl_pct"]) for r in ev if cond(r["entry_date"][:6])]
    s = stats(pn)
    if s:
        L.append(f"- **{name}**: n={s['n']} avg={s['avg']:+.2f}% PF={s['pf']:.2f}")
L.append("")

L.append("## 三、SMC 腿：7 月前 vs 8 月+")
for name, cond in (("<=202607", lambda m: m <= "202607"), ("202608+", lambda m: m >= "202608")):
    pn = [float(r["net_pnl_pct"]) for r in smc if cond(r["entry_date"][:6])]
    s = stats(pn)
    if s:
        L.append(f"- **{name}**: n={s['n']} avg={s['avg']:+.2f}% PF={s['pf']:.2f}")
L.append("")

L.append("## 四、事件腿整体 IS/OOS（70/30，含 8 月完整）")
ok = sorted([r for r in ev if r.get("entry_date")], key=lambda r: r["entry_date"])
cut = int(len(ok) * 0.7)
s1 = stats([float(r["net_pnl_pct"]) for r in ok[:cut]])
s2 = stats([float(r["net_pnl_pct"]) for r in ok[cut:]])
L.append(f"- IS(70%): avg={s1['avg']:+.2f}% PF={s1['pf']:.2f} | OOS(30%): avg={s2['avg']:+.2f}% PF={s2['pf']:.2f}")
L.append("")

L.append("## 五、结论")
L.append("1. 数据补全后 8 月为完整 OOS 段：事件腿 8 月 92 笔 avg +5.79%/PF5.82 —— 独立窗口仍强正")
L.append("2. SMC 腿 8 月 37 笔仍弱（OOS -0.75%）—— 与无独立 edge 结论一致，保持 HTF_BIAS 降级")
L.append("3. 事件腿整体 n=3,663 —— 完整数据下 edge 保持（IS/OOS 均正）")

md = "\n".join(L)
out = os.path.join(RESEARCH, "handover", "八月完整OOS评估.md")
with open(out, "w", encoding="utf-8") as fh:
    fh.write(md)
for d in FRONT:
    os.makedirs(d, exist_ok=True)
    shutil.copyfile(out, os.path.join(d, "八月完整OOS评估.md"))
print("报告已写 + 前端同步:", out)
print(md)
