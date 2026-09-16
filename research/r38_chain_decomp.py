# -*- coding: utf-8 -*-
"""r38_chain_decomp.py —— 全链路审计的效应分解(解释 R38x 与全链路的巨大差异).

R38x(CSV 离线): rank_prod>=3 → OOS PF 4.52
全链路重放:     rank_prod>=3 → OOS PF 3.67 (差 0.85!)
且 >=4 全链路 IS/OOS 4.26/4.32 看似最优, 但那是因为 CONT 整腿被剔除。

本脚本用缓存候选(r38_rank_chain_cands.json, 免重跑)做干净分解:
  ① CONT 腿自身的 IS/OOS 质量(是否拖累)
  ② EVENT 腿(不含 CONT) 在 gate 0/2/3/4 下的 IS/OOS
  ③ "剔除 CONT" 效应 vs "EVENT 加门槛" 效应 的分离
纯研究。
"""
import csv, io, json, os, sys
from collections import defaultdict
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
HERE = r"E:\test\smc_project\research"
IS_END = "20250630"

cands = json.load(open(os.path.join(HERE, "r38_rank_chain_cands.json"), encoding="utf-8"))
cont = []
with open(os.path.join(HERE, "cont_v20f_new.csv"), encoding="utf-8-sig") as fh:
    for row in csv.DictReader(fh):
        cont.append({"s": row.get("symbol"), "d": str(row.get("entry_date")),
                     "net": float(row["net_pnl_pct"]), "rank": 3, "stage": "CONT"})

def st(ts):
    if not ts: return None
    p = [t["net"] for t in ts]
    w = [x for x in p if x > 0]; l = [x for x in p if x <= 0]
    pf = sum(w)/abs(sum(l)) if sum(l) else 99
    return dict(n=len(p), avg=round(sum(p)/len(p), 2),
                wr=round(100*len(w)/len(p), 1), pf=round(pf, 2))

def seg(ts, lo_hi):
    lo, hi = lo_hi
    return [t for t in ts if lo <= str(t["d"]) <= hi]

IS = ("00000000", IS_END); OOS = (IS_END + "1", "99999999")

print("=" * 96)
print("① CONT 腿自身质量(全链路基线里最可疑的拖累源)")
print("=" * 96)
for lab, w in (("全样本", ("00000000", "99999999")), ("IS", IS), ("OOS", OOS)):
    s = st(seg(cont, w))
    if s: print("  CONT %-6s n=%3d avg=%+.2f%% wr=%.1f%% PF=%.2f" % (lab, s["n"], s["avg"], s["wr"], s["pf"]))

print("\n" + "=" * 96)
print("② EVENT 腿(不含 CONT, 不含月度cap) 在 gate 0/2/3/4 下")
print("=" * 96)
print("%-16s %6s %9s %7s | %6s %9s %7s" % ("EVENT-only", "IS_n", "IS_avg%", "IS_PF", "OOS_n", "OOS_avg%", "OOS_PF"))
for g in (0, 2, 3, 4):
    ev = [t for t in cands if t["rank"] >= g]
    si, so = st(seg(ev, IS)), st(seg(ev, OOS))
    if si and so:
        print("%-16s %6d %+8.2f%% %7.2f | %6d %+8.2f%% %7.2f"
              % ("gate>=%d" % g, si["n"], si["avg"], si["pf"], so["n"], so["avg"], so["pf"]))

print("\n" + "=" * 96)
print("③ 效应分离: 基线(CONT+EVENT, 已cap) 的三种改法")
print("=" * 96)
def build(gate, gate_cont=True):
    pool = [t for t in cands if t["rank"] >= gate]
    pool += [t for t in cont if (t["rank"] >= gate if gate_cont else True)]
    seen = set(); dedup = []
    for t in pool:
        k = (str(t["s"]), str(t["d"]))
        if k in seen: continue
        seen.add(k); dedup.append(t)
    bym = defaultdict(list)
    for t in dedup: bym[str(t["d"])[:6]].append(t)
    out = []
    for m, v in sorted(bym.items()):
        out.extend(sorted(v, key=lambda t: -t["rank"])[:500])
    return out

cases = [
    ("A 基线 (gate0, 含CONT)", lambda: build(0, True)),
    ("B 只剔 CONT (gate0)", lambda: build(0, False)),
    ("C EVENT>=3 (含CONT)", lambda: build(3, True)),
    ("D EVENT>=3 (剔CONT)", lambda: build(3, False)),
    ("E EVENT>=4 (含CONT)", lambda: build(4, True)),
    ("F EVENT>=4 (剔CONT)", lambda: build(4, False)),
]
print("%-24s %6s %9s %7s | %6s %9s %7s %8s" % ("方案", "IS_n", "IS_avg%", "IS_PF", "OOS_n", "OOS_avg%", "OOS_PF", "全n"))
for name, fn in cases:
    tr = fn()
    si, so = st(seg(tr, IS)), st(seg(tr, OOS))
    if si and so:
        print("%-24s %6d %+8.2f%% %7.2f | %6d %+8.2f%% %7.2f %8d"
              % (name, si["n"], si["avg"], si["pf"], so["n"], so["avg"], so["pf"], len(tr)))

print("\n" + "=" * 96)
print("裁定")
print("=" * 96)
def oos_pf(g, gc):
    si, so = st(seg(build(g, gc), OOS)), None
    return so
def pfs(fn):
    tr = fn(); so = st(seg(tr, OOS)); return so["pf"] if so else 0
a, b = pfs(cases[0][1]), pfs(cases[1][1])
c, d = pfs(cases[2][1]), pfs(cases[3][1])
e, f = pfs(cases[4][1]), pfs(cases[5][1])
print("  A 基线 OOS PF      = %.2f" % a)
print("  B 只剔 CONT        = %.2f  (Δ %+.2f — 剔除CONT的效应)" % (b, b - a))
print("  C EVENT>=3 含CONT  = %.2f  (Δ %+.2f — 门槛总效应)" % (c, c - a))
print("  D EVENT>=3 剔CONT  = %.2f" % d)
print("  E EVENT>=4 含CONT  = %.2f  (Δ %+.2f)" % (e, e - a))
print("  F EVENT>=4 剔CONT  = %.2f  (Δ %+.2f)" % (f, f - a))
print("\n  → 若 B(只剔CONT) 的增益 >= C(门槛) 的增益, 说明'>=4 看似最优'主要来自")
print("    剔除 CONT 腿, 而非 rank 门槛本身; 则应先讨论 CONT 腿去留, 而非加门槛。")