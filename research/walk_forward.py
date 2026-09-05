# -*- coding: utf-8 -*-
"""Walk-Forward 前推验证（审计 F06 深化）：滚动 IS/OOS，替代单次 70/30
事件腿 combo_v20f_trades.csv：按时间排序，窗口=12个月IS → 3个月OOS 滚动前推，
统计每段 OOS 的 avg/wr/PF，最后汇总全 OOS 表现，判断参数是否过拟合。
"""
import csv, os, sys
from collections import defaultdict
sys.stdout.reconfigure(encoding="utf-8", errors="replace")

p = r"E:\test\smc_project\research\combo_v20f_trades.csv"
rows = []
with open(p, encoding="utf-8-sig") as fh:
    for r in csv.DictReader(fh):
        try:
            r["net_pnl_pct"] = float(r["net_pnl_pct"]) if r["net_pnl_pct"] not in (None, "", "None") else None
        except Exception:
            r["net_pnl_pct"] = None
        rows.append(r)
rows = [r for r in rows if r["net_pnl_pct"] is not None and r.get("entry_date")]
rows.sort(key=lambda r: r["entry_date"])

def stats(pn):
    if not pn:
        return None
    n = len(pn)
    mean = sum(pn) / n
    wins = [x for x in pn if x > 0]
    losses = [x for x in pn if x <= 0]
    pf = sum(wins) / abs(sum(losses)) if losses else 99.0
    return {"n": n, "avg": mean, "win": len(wins) / n, "pf": pf}

def fmt(s):
    return "n=%d avg=%+.2f%% wr=%.0f%% PF=%.2f" % (s["n"], s["avg"], s["win"] * 100, s["pf"]) if s else "n=0"

# 按月份分组
by_month = defaultdict(list)
for r in rows:
    by_month[r["entry_date"][:6]].append(r)
months = sorted(by_month.keys())
print("总笔数:", len(rows), "| 月份数:", len(months), "|", months[0], "→", months[-1])

# Walk-Forward: IS=12月, OOS=3月, 步进3月
IS_WIN = 12
OOS_WIN = 3
L = ["# Walk-Forward 前推验证（事件腿）", "",
     "- 窗口: 样本内12个月 → 样本外3个月，步进3个月前推", ""]
L.append("| 段 | IS月份 | OOS月份 | IS avg% | OOS avg% | OOS wr% | OOS PF |")
L.append("|---|---|---|---:|---:|---:|---:|")
oos_all = []
seg = 0
i = 0
while i + IS_WIN + OOS_WIN <= len(months):
    is_m = months[i:i + IS_WIN]
    oos_m = months[i + IS_WIN:i + IS_WIN + OOS_WIN]
    is_rows = [r for m in is_m for r in by_month.get(m, [])]
    oos_rows = [r for m in oos_m for r in by_month.get(m, [])]
    si, so = stats([r["net_pnl_pct"] for r in is_rows]), stats([r["net_pnl_pct"] for r in oos_rows])
    seg += 1
    L.append("| seg%d | %s~%s | %s~%s | %+.2f | %+.2f | %.0f | %.2f |" % (
        seg, is_m[0], is_m[-1], oos_m[0], oos_m[-1],
        si["avg"] if si else 0, so["avg"] if so else 0,
        (so["win"] * 100) if so else 0, (so["pf"]) if so else 0))
    oos_all.extend(r["net_pnl_pct"] for r in oos_rows)
    i += OOS_WIN
s_all = stats(oos_all)
L.append("")
L.append("## 汇总")
L.append("- 全样本: %s" % fmt(stats([r["net_pnl_pct"] for r in rows])))
L.append("- 全部 OOS 段合并: %s" % fmt(s_all))
pos = sum(1 for _ in range(0, len(months) - IS_WIN - OOS_WIN + 1, OOS_WIN) if True)
oos_pos = sum(1 for k in range(0, len(months) - IS_WIN - OOS_WIN + 1, OOS_WIN)
              if (lambda m: (stats([r["net_pnl_pct"] for r in [x for mm in months[m:m+OOS_WIN] for x in by_month.get(mm, [])]]) or {}).get("avg", 0) > 0)(k))
L.append("- OOS 段中收益为正的段数: %d/%d" % (oos_pos, pos))
L.append("- 结论: %s" % ("OOS 为正占比高，参数较稳健；若多数段为负则过拟合。" if oos_pos >= pos * 0.6 else "OOS 多数段为负 → 存在过拟合风险，需参数简化。"))
md = "\n".join(L)
out = r"E:\test\smc_project\research\handover\Walk-Forward前推验证.md"
with open(out, "w", encoding="utf-8") as fh:
    fh.write(md)
print(md[-1500:])
