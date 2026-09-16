# -*- coding: utf-8 -*-
"""r38_gate_monthly_clean.py —— 用 cap 前全集重做门槛×月度分析(修正方法论).

问题(上一版 r38_gate_monthly.py 的缺陷):
  它用 combo_v20f_trades.csv 与 r38_combo_rank3_trades.csv(两者都已过月度 cap=500)
  做集合差来求"被门槛剔除"的交易 —— 但两份 CSV 的 cap 排序结果不同, 差值里
  **混合了"门槛剔除"与"cap 挤出"两种效应**, 不能归因于门槛。

正确做法:
  用 r38_rank_chain_cands.json(cap **前**的全部事件腿候选, 1547 笔, 每笔带真实 rank)
  直接按 rank>=3 切分。这样"被剔除"= 纯粹的 rank<3, 与 cap 无关。

同时给出两种口径的对照, 便于识别 cap 干扰的幅度。
纯研究, 不修改生产。
"""
import csv, io, json, os, sys
from collections import defaultdict
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

HERE = r"E:\test\smc_project\research"


def f(x, d=0.0):
    try:
        return float(x)
    except Exception:
        return d


def stats(rows):
    if not rows:
        return None
    p = [f(r["net"]) if "net" in r else f(r["net_pnl_pct"]) for r in rows]
    w = [x for x in p if x > 0]
    l = [x for x in p if x <= 0]
    pf = sum(w) / abs(sum(l)) if sum(l) else 99.0
    return {"n": len(p), "avg": round(sum(p) / len(p), 2),
            "wr": round(100 * len(w) / len(p), 1), "pf": round(pf, 2)}


cands = json.load(open(os.path.join(HERE, "r38_rank_chain_cands.json"), encoding="utf-8"))
print("=" * 100)
print("门槛 × 月度分析(修正版: 用 cap 前全集, 纯 rank 切分)")
print("=" * 100)
print("候选全集(cap 前): %d 笔" % len(cands))
rk = defaultdict(int)
for c in cands:
    rk[int(c["rank"])] += 1
print("rank 分布: %s" % dict(sorted(rk.items())))
keep = [c for c in cands if c["rank"] >= 3]
drop = [c for c in cands if c["rank"] < 3]
print("门槛通过: %d | 被门槛剔除: %d" % (len(keep), len(drop)))

print("\n" + "=" * 100)
print("① 被门槛剔除的交易(纯 rank<3) —— 逐月看它们的真实质量")
print("=" * 100)
bym_drop = defaultdict(list)
bym_all = defaultdict(list)
for c in cands:
    bym_all[str(c["d"])[4:6]].append(c)
for c in drop:
    bym_drop[str(c["d"])[4:6]].append(c)

print("%-6s %8s %20s %20s" % ("月", "剔除量", "被剔除者质量", "全集质量"))
for mm in ("%02d" % i for i in range(1, 13)):
    sa = stats(bym_all.get(mm, []))
    sd = stats(bym_drop.get(mm, []))
    c1 = "n=%d %+.2f%%/PF%.2f" % (sd["n"], sd["avg"], sd["pf"]) if sd else "—"
    c2 = "n=%d %+.2f%%/PF%.2f" % (sa["n"], sa["avg"], sa["pf"]) if sa else "—"
    flag = ""
    if sd:
        if sd["avg"] < 0:
            flag = "  剔除=正确(差票)"
        else:
            flag = "  ⚠ 剔除=错误(好票被砍)"
    print("%-6s %8d %20s %20s%s" % (mm + "月", len(bym_drop.get(mm, [])), c1, c2, flag))

print("\n" + "=" * 100)
print("② 焦点: 4/5/6 月 —— 门槛是否修好")
print("=" * 100)
for mm, lab in (("04", "4月"), ("05", "5月"), ("06", "6月")):
    a = stats(bym_all.get(mm, []))
    b = stats([c for c in bym_all.get(mm, []) if c["rank"] >= 3])
    d = stats(bym_drop.get(mm, []))
    print("\n%s (cap 前口径):" % lab)
    if a:
        print("  全集      n=%3d avg=%+.2f%% wr=%.1f%% PF=%.2f" % (a["n"], a["avg"], a["wr"], a["pf"]))
    if b:
        print("  rank>=3   n=%3d avg=%+.2f%% wr=%.1f%% PF=%.2f" % (b["n"], b["avg"], b["wr"], b["pf"]))
    if d:
        print("  被剔除    n=%3d avg=%+.2f%% wr=%.1f%% PF=%.2f" % (d["n"], d["avg"], d["wr"], d["pf"]))
    if a and b:
        print("  Δ         n%+d avg%+.2fpp PF%+.2f" % (b["n"] - a["n"], b["avg"] - a["avg"], b["pf"] - a["pf"]))
        if a["avg"] < 0 <= b["avg"]:
            print("  → ✅ 由负转正")
        elif a["avg"] < 0 and b["avg"] < 0:
            print("  → ❌ 仍为负(未修好)")

print("\n" + "=" * 100)
print("③ 汇总裁定")
print("=" * 100)
neg_all, neg_keep = [], []
for mm in ("%02d" % i for i in range(1, 13)):
    a = stats(bym_all.get(mm, []))
    b = stats([c for c in bym_all.get(mm, []) if c["rank"] >= 3])
    if a and a["avg"] < 0:
        neg_all.append(mm)
    if b and b["avg"] < 0:
        neg_keep.append(mm)
print("  全集亏损月:   %s" % (", ".join(m + "月" for m in neg_all) or "无"))
print("  门槛后亏损月: %s" % (", ".join(m + "月" for m in neg_keep) or "无"))
fixed = [m for m in neg_all if m not in neg_keep]
broke = [m for m in neg_keep if m not in neg_all]
print("  门槛修好:     %s" % (", ".join(m + "月" for m in fixed) or "无"))
print("  门槛弄坏:     %s" % (", ".join(m + "月" for m in broke) or "无"))

sa, sb = stats(cands), stats(keep)
print("\n  全集:   n=%d avg=%+.2f%% PF=%.2f" % (sa["n"], sa["avg"], sa["pf"]))
print("  门槛后: n=%d avg=%+.2f%% PF=%.2f" % (sb["n"], sb["avg"], sb["pf"]))

print("\n裁定:")
if fixed:
    print("  → 门槛顺带修好了 %s —— 无需季节性规则" % ", ".join(m + "月" for m in fixed))
else:
    print("  → 门槛**未修好任何亏损月** → 4/5/6 月弱势是独立的季节性问题,")
    print("     rank 门槛(通用质量闸)无法解决; 若要做季节性规避, 须单独过 IS/OOS")
# 被剔除者的整体质量(判断门槛是否在弱势月"帮倒忙")
sd_all = stats(drop)
print("  被剔除整体: n=%d avg=%+.2f%% PF=%.2f (正=门槛砍掉了赚钱的票)"
      % (sd_all["n"], sd_all["avg"], sd_all["pf"]))