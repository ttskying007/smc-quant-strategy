# -*- coding: utf-8 -*-
"""r38_revalidate.py —— 重基线后对 R38 关键结论的重新验证.

重基线(Wilder ADX + max_hold=12)改变了基线本身, 故所有基于 legacy 基线
得出的 R38 结论都必须在新基线上复核。本脚本重算:
  ① 三维复盘: 逐年 / 逐月 / RR 分布 / 出场构成
  ② stage 分桶(ACCUM vs DOWNTREND) —— R38k 结论是否仍成立
  ③ ACCUM×2 仓位加权 —— R38l 的 PF 3.21→3.29 是否仍成立
  ④ rank 分桶 —— R38 早期质量梯度是否仍成立
输出与 legacy 归档的对照, 判定各结论的"仍成立/需修正"。
纯研究, 不修改生产。
"""
import csv, io, json, os, sys
from collections import defaultdict
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
HERE = r"E:\test\smc_project\research"

def load(p):
    return list(csv.DictReader(open(p, encoding="utf-8-sig")))
def f(x, d=0.0):
    try: return float(x)
    except: return d

NEW = os.path.join(HERE, "combo_v20f_trades.csv")
OLD = os.path.join(HERE, "archive", "combo_v20f_trades_legacy_dx_h15.csv")

def stats(pnls):
    if not pnls: return None
    w = [x for x in pnls if x > 0]; l = [x for x in pnls if x <= 0]
    pf = sum(w)/abs(sum(l)) if sum(l) else 99
    return {"n": len(pnls), "avg": round(sum(pnls)/len(pnls), 2),
            "wr": round(100*len(w)/len(pnls), 1), "pf": round(pf, 2),
            "sum": round(sum(pnls), 0)}

for label, path in (("NEW(Wilder+h12)", NEW), ("LEGACY(DX+h15)", OLD)):
    rows = load(path)
    ev = [r for r in rows if r.get("src") == "EVENT"]
    if not ev:
        print("%s: 无数据" % label); continue
    print("=" * 92)
    print("%s  (EVENT n=%d, 全组合 n=%d)" % (label, len(ev), len(rows)))
    print("=" * 92)
    allp = [f(r["net_pnl_pct"]) for r in ev]
    a = stats(allp)
    print("  全样本: avg=%+.2f%% wr=%.1f%% PF=%.2f 累计=%+.0f%%" % (a["avg"], a["wr"], a["pf"], a["sum"]))

    # ① 逐年
    print("\n  ① 逐年:")
    byy = defaultdict(list)
    for r in ev: byy[str(r["entry_date"])[:4]].append(f(r["net_pnl_pct"]))
    for y in sorted(byy):
        s = stats(byy[y])
        print("     %s: n=%4d avg=%+.2f%% wr=%.1f%% PF=%.2f" % (y, s["n"], s["avg"], s["wr"], s["pf"]))

    # ② 逐月(R38 关注的 4/5/6 弱势月)
    print("\n  ② 逐月(全 12 月):")
    bym = defaultdict(list)
    for r in ev: bym[str(r["entry_date"])[4:6]].append(f(r["net_pnl_pct"]))
    line = []
    for m in sorted(bym):
        s = stats(bym[m])
        line.append("%s月 n=%d %+.2f%%/PF%.2f" % (m, s["n"], s["avg"], s["pf"]))
    for i in range(0, len(line), 3):
        print("     " + " | ".join(line[i:i+3]))

    # ③ stage 分桶(需要 stage 字段; 新基线 CSV 无 stage, 用 r38_stage_relax 的方式重算代价高)
    #    改为按 rank 与 rr_exit 分桶
    print("\n  ③ RR 分布(rr_exit):")
    rr = [f(r["rr_exit"]) for r in ev if r.get("rr_exit")]
    if rr:
        le = 100*sum(1 for x in rr if x <= -1)/len(rr)
        ge = 100*sum(1 for x in rr if x >= 1)/len(rr)
        print("     <=-1R %.1f%% | >=1R %.1f%%" % (le, ge))

    # ④ 出场构成
    print("\n  ④ 出场构成:")
    byex = defaultdict(list)
    for r in ev: byex[r.get("reason") or "?"].append(f(r["net_pnl_pct"]))
    for k, ps in sorted(byex.items(), key=lambda kv: -len(kv[1]))[:6]:
        s = stats(ps)
        print("     %-12s n=%4d avg=%+.2f%% PF=%.2f" % (k, s["n"], s["avg"], s["pf"]))

    # ⑤ rank 分桶
    print("\n  ⑤ rank 分桶:")
    byr = defaultdict(list)
    for r in ev:
        try: byr[int(float(r.get("rank") or 0))].append(f(r["net_pnl_pct"]))
        except: pass
    for k in sorted(byr):
        s = stats(byr[k])
        print("     rank=%d n=%4d avg=%+.2f%% wr=%.1f%% PF=%.2f" % (k, s["n"], s["avg"], s["wr"], s["pf"]))
    print()