# -*- coding: utf-8 -*-
"""r38_rank_oos.py —— rank 门槛的 IS/OOS 验证(新基线, 组合级).

背景: R38t 在新基线上确认 rank 门槛有效(rank>=3 PF4.04 / rank>=4 PF4.31/MDD-245),
但那是**全样本**结果。R38 的方法学纪律要求任何变体必须过 IS/OOS(R38h 教训:
技术腿 PF5.26 全样本亮眼, OOS 归零)。

本脚本对 rank 门槛做强制 IS/OOS:
  IS  = entry_date <= 20250630
  OOS = entry_date >  20250630
方案: A 等权 | C rank>=3 | D rank>=4 | E rank>=5
判据(预注册): 晋级需 OOS PF > 1.5 且 OOS/IS PF 比 > 0.5 且 OOS 不劣于等权。
同时报告各门槛在 OOS 的样本量(避免小样本误判)。
纯研究, 不修改生产。
"""
import csv, io, os, sys
from collections import defaultdict
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
HERE = r"E:\test\smc_project\research"
IS_END = "20250630"

def f(x, d=0.0):
    try: return float(x)
    except: return d

rows = list(csv.DictReader(open(os.path.join(HERE, "combo_v20f_trades.csv"), encoding="utf-8-sig")))
ev = [r for r in rows if r.get("src") == "EVENT"]
recs = []
for r in ev:
    try: rk = int(float(r.get("rank") or 0))
    except: rk = 0
    d8 = str(r.get("entry_date") or "").replace("-", "")
    recs.append({"net": f(r["net_pnl_pct"]), "rank": rk, "d": d8})

def stats(ts):
    if not ts: return None
    p = [t["net"] for t in ts]
    w = [x for x in p if x > 0]; l = [x for x in p if x <= 0]
    pf = sum(w)/abs(sum(l)) if sum(l) else 99
    eq = 0.0; peak = 0.0; mdd = 0.0
    for x in p:
        eq += x; peak = max(peak, eq); mdd = min(mdd, eq - peak)
    return {"n": len(p), "avg": round(sum(p)/len(p), 2),
            "wr": round(100*len(w)/len(p), 1), "pf": round(pf, 2),
            "mdd": round(mdd, 0), "sum": round(sum(p), 0)}

GATES = [("A 等权(现状)", 0), ("C rank>=3", 3), ("D rank>=4", 4), ("E rank>=5", 5)]

print("=" * 100)
print("rank 门槛 IS/OOS 验证 (新基线 EVENT n=%d; IS<=%s)" % (len(recs), IS_END))
print("=" * 100)
print("%-16s %6s %9s %7s %8s %9s | %6s %9s %7s %8s"
      % ("方案", "IS_n", "IS_avg%", "IS_PF", "IS_MDD", "IS_累计%", "OOS_n", "OOS_avg%", "OOS_PF", "OOS_MDD"))
res = {}
for name, g in GATES:
    isr = [t for t in recs if t["d"] <= IS_END and t["rank"] >= g]
    oosr = [t for t in recs if t["d"] > IS_END and t["rank"] >= g]
    si, so = stats(isr), stats(oosr)
    res[name] = (si, so)
    if si and so:
        print("%-16s %6d %+8.2f%% %7.2f %8.0f %+9.0f | %6d %+8.2f%% %7.2f %8.0f"
              % (name, si["n"], si["avg"], si["pf"], si["mdd"], si["sum"],
                 so["n"], so["avg"], so["pf"], so["mdd"]))

print("\n" + "=" * 100)
print("裁定 (预注册: OOS PF>1.5 且 OOS/IS 比>0.5 且 OOS PF >= 等权 OOS PF)")
print("=" * 100)
_, base_oos = res["A 等权(现状)"]
for name, g in GATES:
    if g == 0: continue
    si, so = res[name]
    if not si or not so:
        print("  %-14s 样本不足, 不可判定" % name); continue
    ratio = so["pf"] / si["pf"] if si["pf"] else 0
    ok = (so["pf"] > 1.5) and (ratio > 0.5) and (so["pf"] >= base_oos["pf"])
    print("  %-14s OOS PF=%.2f | 比=%.2f | OOS PF vs 等权 %.2f vs %.2f | %s"
          % (name, so["pf"], ratio, so["pf"], base_oos["pf"],
             "✅ 晋级" if ok else "❌ 未过线"))
    # 保留率
    tot = len(recs); keep = len([t for t in recs if t["rank"] >= g])
    print("                 保留 %d/%d (%.0f%%), OOS 保留 %d/%d"
          % (keep, tot, 100*keep/tot,
             len([t for t in recs if t["d"] > IS_END and t["rank"] >= g]),
             len([t for t in recs if t["d"] > IS_END])))

print("\n逐年 (rank>=4 vs 等权):")
for y in ("2024", "2025", "2026"):
    a = stats([t for t in recs if t["d"][:4] == y])
    d = stats([t for t in recs if t["d"][:4] == y and t["rank"] >= 4])
    if a and d:
        print("  %s: 等权 n=%3d %+.2f%%/PF%.2f | rank>=4 n=%3d %+.2f%%/PF%.2f"
              % (y, a["n"], a["avg"], a["pf"], d["n"], d["avg"], d["pf"]))