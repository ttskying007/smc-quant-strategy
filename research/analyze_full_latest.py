# -*- coding: utf-8 -*-
"""全面回测分析器（2026-09-06 最终）—— 逐年/逐月/分板块/分reason/IS-OOS + 前端同步
输入：SMC腿 W1D1D4_trades.csv + 事件腿 combo_v20f_trades.csv
输出：handover/最新全量回测分析.md + .json + 前端双目录同步
"""
import csv, json, os, sys, shutil
from collections import defaultdict
sys.stdout.reconfigure(encoding="utf-8", errors="replace")

RESEARCH = r"E:\test\smc_project\research"
HERMES_MON = r"E:\test\smc_project\hermes\smc_monitor"
MIRROR2 = r"E:\root\.hermes\smc_monitor"

def load(p):
    with open(p, encoding="utf-8-sig") as fh:
        return [r for r in csv.DictReader(fh) if r.get("net_pnl_pct") not in (None, "", "None")]

def stats(pn):
    if not pn:
        return None
    n = len(pn); mean = sum(pn) / n
    wins = [x for x in pn if x > 0]; losses = [x for x in pn if x <= 0]
    return {"n": n, "avg": round(mean, 3), "wr": round(len(wins)/n, 3),
            "pf": round(sum(wins)/abs(sum(losses)), 2) if losses else 99}

smc = load(os.path.join(RESEARCH, "..", "wdh", "W1D1D4_trades.csv"))
ev = load(os.path.join(RESEARCH, "combo_v20f_trades.csv"))
ev_event = [r for r in ev if r.get("src") == "EVENT"]
print(f"SMC: {len(smc)} | 事件: {len(ev_event)}")

L = ["# 最新全量回测分析（2026-09-06）", "",
     "> 引擎：P1-1 唯一执行内核 | SMC 全市场 4905 只 + 事件腿 cap500", ""]

def board(r):
    c = str(r["symbol"]).split(".")[0]
    if c.startswith(("300", "301")): return "创业板"
    if c.startswith("688"): return "科创板"
    if c.startswith(("4", "8", "9")): return "北交所"
    return "主板"

# 一、总体
L.append("## 一、总体")
for name, rows in (("SMC腿", smc), ("事件腿", ev_event)):
    s = stats([float(r["net_pnl_pct"]) for r in rows])
    if s:
        L.append(f"- **{name}**: n={s['n']:,} avg={s['avg']:+.2f}% wr={s['wr']*100:.0f}% PF={s['pf']:.2f}")
L.append("")

# 二、逐年
L.append("## 二、逐年")
L.append("| 年 | SMC n | SMC avg% | SMC PF | 事件 n | 事件 avg% | 事件 PF |")
L.append("|---|---:|---:|---:|---:|---:|---:|")
by = defaultdict(lambda: {"smc": [], "ev": []})
for r in smc:
    by[r["entry_date"][:4]]["smc"].append(float(r["net_pnl_pct"]))
for r in ev_event:
    by[r["entry_date"][:4]]["ev"].append(float(r["net_pnl_pct"]))
for y in sorted(by):
    s1, s2 = stats(by[y]["smc"]), stats(by[y]["ev"])
    L.append(f"| {y} | {s1['n'] if s1 else 0} | {s1['avg'] if s1 else 0:+.2f} | {s1['pf'] if s1 else 0:.2f} | "
             f"{s2['n'] if s2 else 0} | {s2['avg'] if s2 else 0:+.2f} | {s2['pf'] if s2 else 0:.2f} |")
L.append("")

# 三、逐月（事件腿）
L.append("## 三、逐月（事件腿）")
by_m = defaultdict(list)
for r in ev_event:
    by_m[r["entry_date"][:6]].append(float(r["net_pnl_pct"]))
L.append("| 月 | n | avg% | PF |")
L.append("|---|---:|---:|---:|")
for m in sorted(by_m):
    s = stats(by_m[m])
    if s:
        L.append(f"| {m} | {s['n']} | {s['avg']:+.2f} | {s['pf']:.2f} |")
L.append("")

# 四、分板块
L.append("## 四、分板块（两腿）")
L.append("| 板块 | SMC n | SMC avg% | SMC PF | 事件 n | 事件 avg% | 事件 PF |")
L.append("|---|---:|---:|---:|---:|---:|---:|")
bd = defaultdict(lambda: {"smc": [], "ev": []})
for r in smc:
    bd[board(r)]["smc"].append(float(r["net_pnl_pct"]))
for r in ev_event:
    bd[board(r)]["ev"].append(float(r["net_pnl_pct"]))
for b in ("主板", "创业板", "科创板", "北交所"):
    s1, s2 = stats(bd[b]["smc"]), stats(bd[b]["ev"])
    L.append(f"| {b} | {s1['n'] if s1 else 0} | {s1['avg'] if s1 else 0:+.2f} | {s1['pf'] if s1 else 0:.2f} | "
             f"{s2['n'] if s2 else 0} | {s2['avg'] if s2 else 0:+.2f} | {s2['pf'] if s2 else 0:.2f} |")
L.append("")

# 五、SMC reason 分布
L.append("## 五、SMC 出场 reason 分布")
rc = defaultdict(list)
for r in smc:
    rc[r["reason"]].append(float(r["net_pnl_pct"]))
for k, v in sorted(rc.items(), key=lambda x: -len(x[1])):
    s = stats(v)
    L.append(f"- **{k}**: {s['n']}笔 ({s['n']/len(smc)*100:.0f}%) avg={s['avg']:+.2f}% PF={s['pf']:.2f}")
L.append("")

# 六、IS/OOS
L.append("## 六、IS/OOS（70/30）")
for name, rows in (("SMC腿", smc), ("事件腿", ev_event)):
    ok = sorted([r for r in rows if r.get("entry_date")], key=lambda r: r["entry_date"])
    cut = int(len(ok) * 0.7)
    s1, s2 = stats([float(r["net_pnl_pct"]) for r in ok[:cut]]), stats([float(r["net_pnl_pct"]) for r in ok[cut:]])
    L.append(f"- **{name}**: IS {s1['avg']:+.2f}%/PF{s1['pf']} → OOS {s2['avg']:+.2f}%/PF{s2['pf']}")
L.append("")

md = "\n".join(L)
out_md = os.path.join(RESEARCH, "handover", "最新全量回测分析.md")
with open(out_md, "w", encoding="utf-8") as fh:
    fh.write(md)
# JSON
data = {"smc_total": len(smc), "event_total": len(ev_event)}
for name, rows in (("SMC", smc), ("EVENT", ev_event)):
    data[name] = stats([float(r["net_pnl_pct"]) for r in rows])
out_json = os.path.join(RESEARCH, "handover", "最新全量回测分析.json")
with open(out_json, "w", encoding="utf-8") as fh:
    json.dump(data, fh, ensure_ascii=False, indent=1)
print("报告已写:", out_md)

# 前端同步（回测分析 → 双目录）
for d in (HERMES_MON, MIRROR2):
    os.makedirs(d, exist_ok=True)
    shutil.copyfile(out_md, os.path.join(d, "最新全量回测分析.md"))
    shutil.copyfile(out_json, os.path.join(d, "最新全量回测分析.json"))
print("回测分析已同步前端双目录")
print(md[:2000])
