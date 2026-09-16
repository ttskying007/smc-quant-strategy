# -*- coding: utf-8 -*-
"""r38_rank_sizing.py —— 由上轮发现引出的假设: rank 作仓位权重 vs 硬门槛.

背景(R38af 发现): rank>=3 硬门槛剔掉的 142 笔整体**是赚钱的**(avg+2.17%/PF2.32),
门槛提升的是"每单位资金效率"而非"剔除垃圾"。→ 那么**硬性剔除可能是次优的**:
更优做法是保留全部交易、按 rank 加权仓位, 既保留正期望又捕获质量梯度。

检验方案(用 cap 前全集 1547 笔, 含真实 rank 与 net):
  A 等权(全集基准)           w=1
  B 硬门槛 rank>=3           rank<3 剔除
  C 线性加权                 w = rank/4
  D 温和加权                 w = 1.0 if rank<4 else 1.5
  E 阶梯加权                 w = 1.0/1.5/2.0 for rank 1-3/4-6/7+
  F 下限保护线性             w = max(0.5, rank/4)

判据: 每单位收益 / PF / MDD / 累计。核心问题: 是否存在某个加权方案
**同时**优于 A(等权) 与 B(硬门槛)?
纯研究, 不修改生产。
"""
import io
import json
import os
import sys

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

HERE = r"E:\test\smc_project\research"
IS_END = "20250630"

cands = json.load(open(os.path.join(HERE, "r38_rank_chain_cands.json"), encoding="utf-8"))
print("=" * 100)
print("rank 作仓位权重 vs 硬门槛 (cap 前全集 n=%d)" % len(cands))
print("=" * 100)


def weighted(trades, wf):
    """按权重计算组合指标。wf(t)->w。"""
    ws = [(t["net"], wf(t)) for t in trades]
    c = [n * w for n, w in ws]
    tw = sum(w for _, w in ws)
    wins = [x for x in c if x > 0]
    loss = [x for x in c if x <= 0]
    pf = sum(wins) / abs(sum(loss)) if sum(loss) else 99.0
    eq = 0.0
    peak = 0.0
    mdd = 0.0
    for x in c:
        eq += x
        peak = max(peak, eq)
        mdd = min(mdd, eq - peak)
    return {"n": len(c), "exp": round(tw, 0),
            "avg_exp": round(sum(c) / tw, 3) if tw else 0,
            "pf": round(pf, 2), "mdd": round(mdd, 0), "sum": round(sum(c), 0)}


SCHEMES = [
    ("A 等权(全集)", lambda t: 1.0),
    ("B 硬门槛 rank>=3", None),          # 特殊: 剔除
    ("C 线性 w=rank/4", lambda t: t["rank"] / 4.0),
    ("D 温和 w=1/1.5", lambda t: 1.5 if t["rank"] >= 4 else 1.0),
    ("E 阶梯 1/1.5/2", lambda t: 2.0 if t["rank"] >= 7 else (1.5 if t["rank"] >= 4 else 1.0)),
    ("F 下限线性 max(.5,r/4)", lambda t: max(0.5, t["rank"] / 4.0)),
]

print("%-26s %7s %10s %8s %8s %10s" % ("方案", "敞口", "每单位%", "PF", "MDD%", "累计%"))
res = {}
for name, wf in SCHEMES:
    if wf is None:
        sub = [t for t in cands if t["rank"] >= 3]
        s = weighted(sub, lambda t: 1.0)
    else:
        s = weighted(cands, wf)
    res[name] = s
    print("%-26s %7.0f %+9.3f%% %8.2f %8.0f %+10.0f"
          % (name, s["exp"], s["avg_exp"], s["pf"], s["mdd"], s["sum"]))

print("\n" + "=" * 100)
print("IS/OOS 稳健性(关键: 加权是否跨段有效)")
print("=" * 100)
print("%-26s %22s %22s" % ("方案", "IS (每单位%/PF)", "OOS (每单位%/PF)"))
for name, wf in SCHEMES:
    if wf is None:
        isr = [t for t in cands if t["rank"] >= 3 and str(t["d"]) <= IS_END]
        oosr = [t for t in cands if t["rank"] >= 3 and str(t["d"]) > IS_END]
        si = weighted(isr, lambda t: 1.0)
        so = weighted(oosr, lambda t: 1.0)
    else:
        isr = [t for t in cands if str(t["d"]) <= IS_END]
        oosr = [t for t in cands if str(t["d"]) > IS_END]
        si = weighted(isr, wf)
        so = weighted(oosr, wf)
    print("%-26s %21s %21s"
          % (name, "%+.3f%%/%.2f" % (si["avg_exp"], si["pf"]),
             "%+.3f%%/%.2f" % (so["avg_exp"], so["pf"])))

print("\n" + "=" * 100)
print("裁定: 是否存在同时优于 A(等权) 与 B(硬门槛) 的方案?")
print("=" * 100)
a, b = res["A 等权(全集)"], res["B 硬门槛 rank>=3"]
print("  A 等权   : 每单位 %+.3f%% PF %.2f MDD %.0f 累计 %+.0f"
      % (a["avg_exp"], a["pf"], a["mdd"], a["sum"]))
print("  B 硬门槛 : 每单位 %+.3f%% PF %.2f MDD %.0f 累计 %+.0f"
      % (b["avg_exp"], b["pf"], b["mdd"], b["sum"]))
better = []
for name, wf in SCHEMES:
    if wf is None:
        continue
    s = res[name]
    if (s["avg_exp"] > a["avg_exp"] and s["pf"] >= a["pf"]
            and s["avg_exp"] >= b["avg_exp"] and s["pf"] >= b["pf"] - 0.02):
        better.append(name)
if better:
    print("\n  → 候选(同时不劣于两者): %s" % ", ".join(better))
    for nm in better:
        s = res[nm]
        print("     %-24s 每单位%+.3f%% PF%.2f MDD%.0f 累计%+.0f"
              % (nm, s["avg_exp"], s["pf"], s["mdd"], s["sum"]))
else:
    print("\n  → 无方案同时优于两者: 加权与硬门槛各有所长")
    print("     (硬门槛 PF 最高但放弃正期望; 加权保留全量但 PF 提升有限)")