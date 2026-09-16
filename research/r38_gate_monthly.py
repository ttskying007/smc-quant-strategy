# -*- coding: utf-8 -*-
"""r38_gate_monthly.py —— rank 门槛是否顺带修好 4/5/6 月弱势?

背景(R38u): 4/5/6 月在新基线上恒亏, 其中 6 月样本充足(n=122)最可信; 且弱势月
rank 1-2 占比显著偏高(5月 42% vs 2月 3%)。

关键假设(本轮检验): rank>=3 门槛**恰好剔除那些低 rank 交易** → 可能已顺带修好
4/5/6 月弱势。若成立, 则**无需季节性规则**(通用规则远优于按月硬编码)。

对照:
  A 基线(无门槛) = combo_v20f_trades.csv
  B rank3 分叉    = r38_combo_rank3_trades.csv

判据: 逐月 avg/PF 对比; 重点看 4/5/6 月是否由负转正或显著改善。
另附: 门槛对各月的剔除量(解释机制)。
纯研究, 不修改生产。
"""
import csv, io, os, sys
from collections import defaultdict
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

HERE = r"E:\test\smc_project\research"
IS_END = "20250630"


def load(p):
    return list(csv.DictReader(open(p, encoding="utf-8-sig")))


def f(x, d=0.0):
    try:
        return float(x)
    except Exception:
        return d


def stats(rows):
    if not rows:
        return None
    p = [f(r["net_pnl_pct"]) for r in rows]
    w = [x for x in p if x > 0]
    l = [x for x in p if x <= 0]
    pf = sum(w) / abs(sum(l)) if sum(l) else 99.0
    return {"n": len(p), "avg": round(sum(p) / len(p), 2),
            "wr": round(100 * len(w) / len(p), 1), "pf": round(pf, 2),
            "sum": round(sum(p), 0)}


base = [r for r in load(os.path.join(HERE, "combo_v20f_trades.csv")) if r.get("src") == "EVENT"]
gate = [r for r in load(os.path.join(HERE, "r38_combo_rank3_trades.csv")) if r.get("src") == "EVENT"]

print("=" * 104)
print("rank>=3 门槛 vs 4/5/6月弱势 (EVENT 腿)")
print("=" * 104)
print("基线 EVENT n=%d | rank3 EVENT n=%d" % (len(base), len(gate)))

print("\n逐月对照 (全部 12 月):")
print("%-6s %22s %22s %10s" % ("月", "A 基线(无门槛)", "B rank3(含门槛)", "剔除量"))
neg_base = []
neg_gate = []
for mm in ("%02d" % i for i in range(1, 13)):
    a = [r for r in base if str(r.get("entry_date"))[4:6] == mm]
    b = [r for r in gate if str(r.get("entry_date"))[4:6] == mm]
    sa, sb = stats(a), stats(b)
    ca = "n=%3d %+.2f%%/PF%.2f" % (sa["n"], sa["avg"], sa["pf"]) if sa else "—"
    cb = "n=%3d %+.2f%%/PF%.2f" % (sb["n"], sb["avg"], sb["pf"]) if sb else "—"
    cut = (sa["n"] - sb["n"]) if (sa and sb) else 0
    mark = ""
    if sa and sa["avg"] < 0:
        neg_base.append(mm)
    if sb and sb["avg"] < 0:
        neg_gate.append(mm)
    if sa and sb and sa["avg"] < 0 <= sb["avg"]:
        mark = "  <== 由负转正"
    print("%-6s %22s %22s %10s%s" % (mm + "月", ca, cb, "-%d" % cut if cut else "0", mark))

print("\n" + "=" * 104)
print("焦点: 4/5/6 月")
print("=" * 104)
for mm, lab in (("04", "4月"), ("05", "5月"), ("06", "6月")):
    a = [r for r in base if str(r.get("entry_date"))[4:6] == mm]
    b = [r for r in gate if str(r.get("entry_date"))[4:6] == mm]
    sa, sb = stats(a), stats(b)
    print("\n%s:" % lab)
    if sa:
        print("  基线   n=%3d avg=%+.2f%% wr=%.1f%% PF=%.2f" % (sa["n"], sa["avg"], sa["wr"], sa["pf"]))
    if sb:
        print("  rank3  n=%3d avg=%+.2f%% wr=%.1f%% PF=%.2f" % (sb["n"], sb["avg"], sb["wr"], sb["pf"]))
    if sa and sb:
        print("  Δ      n%+d avg%+.2fpp PF%+.2f" % (sb["n"] - sa["n"], sb["avg"] - sa["avg"], sb["pf"] - sa["pf"]))
    # 基线中被门槛剔除的这批交易自身表现
    ak = {(str(r.get("symbol")), str(r.get("entry_date"))) for r in gate}
    dropped = [r for r in a if (str(r.get("symbol")), str(r.get("entry_date"))) not in ak]
    sd = stats(dropped)
    if sd:
        print("  被剔除 n=%d avg=%+.2f%% wr=%.1f%% PF=%.2f  <== 门槛剔掉的就是这些"
              % (sd["n"], sd["avg"], sd["wr"], sd["pf"]))

print("\n" + "=" * 104)
print("汇总")
print("=" * 104)
print("  基线亏损月: %s" % (", ".join(m + "月" for m in neg_base) or "无"))
print("  门槛后亏损月: %s" % (", ".join(m + "月" for m in neg_gate) or "无"))
fixed = [m for m in neg_base if m not in neg_gate]
print("  门槛修好的月: %s" % (", ".join(m + "月" for m in fixed) or "无"))
still = [m for m in neg_gate if m in neg_base]
print("  仍亏损的月: %s" % (", ".join(m + "月" for m in still) or "无"))

# FIX: 原写法 sb_all, sa_all = stats(base), stats(gate) 命名与打印顺序相反,
# 导致汇总行把 基线/rank3 的 n 与指标印反(基线印成 1402)。此处按语义命名。
sa_all, sb_all = stats(base), stats(gate)
print("\n  全样本: 基线 n=%d avg=%+.2f%% PF=%.2f | rank3 n=%d avg=%+.2f%% PF=%.2f"
      % (sa_all["n"], sa_all["avg"], sa_all["pf"], sb_all["n"], sb_all["avg"], sb_all["pf"]))

print("\n裁定:")
if fixed:
    print("  → rank>=3 门槛**顺带修好了 %s** —— 无需季节性规则(通用规则优于按月硬编码)"
          % ", ".join(m + "月" for m in fixed))
else:
    print("  → 门槛未修好任何亏损月; 4/5/6 月弱势需独立处置(季节性规则须先过 IS/OOS)")
if still:
    print("  → 仍有 %s 为负: 需进一步研究(注意 4/5 月样本小, 6 月样本足)"
          % ", ".join(m + "月" for m in still))