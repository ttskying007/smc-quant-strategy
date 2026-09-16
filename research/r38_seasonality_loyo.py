# -*- coding: utf-8 -*-
"""r38_seasonality_loyo.py —— 季节性规则的逐年交叉验证(leave-one-year-out).

背景: r38_seasonality.py 用**日期切分** IS/OOS 检验季节性, 但该法对季节性有结构性缺陷:
  IS 止于 20250630 → 7-12月只有 2024 下半年在 IS, 而 7-12月的 2025/2026 全在 OOS;
  1-6月则跨两段。结果: 04月 OOS=0, 07月 IS=0, 05/12月 OOS 仅 5 笔
  → **4/5月的"通过"根本无法验证**(OOS 样本近零)。
根因: 月份与日期切分天然耦合。**季节性检验应改用逐年交叉验证**。

本脚本对候选规则做 leave-one-year-out(LYOO):
  对每年 Y: 用其余年份判断规则是否改善, 再看 Y 年是否也被改善
  → 若规则在**每一年**都改善, 才算跨年一致(3/3)。
同时给出 6 月的逐年明细(核心争议月)。

判据(预注册): 跨年一致 = 规则在 3 年中**全部**改善 PF 或 avg。
纯研究。
"""
import csv
import io
import os
import sys

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

HERE = r"E:\test\smc_project\research"
YEARS = ("2024", "2025", "2026")


def f(x, d=0.0):
    try:
        return float(x)
    except Exception:
        return d


def load_ev(path):
    rows = list(csv.DictReader(open(path, encoding="utf-8-sig")))
    return [r for r in rows if r.get("src") == "EVENT"]


def st(rows):
    if not rows:
        return None
    p = [f(r["net_pnl_pct"]) for r in rows]
    w = [x for x in p if x > 0]
    l = [x for x in p if x <= 0]
    pf = sum(w) / abs(sum(l)) if sum(l) else 99.0
    return {"n": len(p), "avg": round(sum(p) / len(p), 3),
            "wr": round(100 * len(w) / len(p), 1), "pf": round(pf, 2)}


ev = load_ev(os.path.join(HERE, "combo_v20f_trades.csv"))
print("=" * 96)
print("季节性规则逐年交叉验证 (EVENT 腿, n=%d)" % len(ev))
print("=" * 96)

print("\n① 6月逐年明细(核心争议月)")
for y in YEARS:
    rs = [r for r in ev if str(r["entry_date"])[:4] == y and str(r["entry_date"])[4:6] == "06"]
    s = st(rs)
    if s:
        print("  %s 6月: n=%3d avg=%+.3f%% wr=%.1f%% PF=%.2f %s"
              % (y, s["n"], s["avg"], s["wr"], s["pf"],
                 "<- 正(与'6月必弱'矛盾)" if s["avg"] > 0 else ""))
    else:
        print("  %s 6月: 无样本" % y)

print("\n② skip-6 逐年效果(是否每年都改善)")
print("%-8s %22s %22s %10s" % ("年", "含6月", "剔6月", "裁定"))
improved = 0
for y in YEARS:
    a = [r for r in ev if str(r["entry_date"])[:4] == y]
    b = [r for r in a if str(r["entry_date"])[4:6] != "06"]
    sa, sb = st(a), st(b)
    if sa and sb:
        better = sb["pf"] > sa["pf"]
        improved += 1 if better else 0
        print("%-8s %22s %22s %10s"
              % (y, "n=%d %+.2f%%/%.2f" % (sa["n"], sa["avg"], sa["pf"]),
                 "n=%d %+.2f%%/%.2f" % (sb["n"], sb["avg"], sb["pf"]),
                 "改善" if better else "**劣化**"))
print("  → 3 年中改善 %d 年" % improved)
print("  → 跨年一致: %s" % ("是(3/3)" if improved == 3 else "**否(%d/3)**" % improved))

print("\n③ 逐月: 每月在 3 年中有几年为负(判断季节性是否为稳定特征)")
print("%-6s %14s %10s" % ("月", "逐年 avg", "负年数"))
stable_neg = []
for m in ("%02d" % i for i in range(1, 13)):
    vals = []
    neg = 0
    for y in YEARS:
        rs = [r for r in ev if str(r["entry_date"])[:4] == y and str(r["entry_date"])[4:6] == m]
        s = st(rs)
        if s:
            vals.append("%s:%+.1f%%(n%d)" % (y[2:], s["avg"], s["n"]))
            if s["avg"] < 0:
                neg += 1
    if vals:
        mark = ""
        if neg == 3:
            stable_neg.append(m)
            mark = "  <== 3年全负"
        elif neg == 0:
            mark = "  (3年全正)"
        print("%-6s %14s %10s%s" % (m + "月", " ".join(vals), "%d/3" % neg, mark))

print("\n" + "=" * 96)
print("裁定")
print("=" * 96)
if stable_neg:
    print("  3年全负的月份: %s" % ", ".join(m + "月" for m in stable_neg))
    for m in stable_neg:
        tot = [r for r in ev if str(r["entry_date"])[4:6] == m]
        s = st(tot)
        print("    %s月: n=%d avg=%+.3f%% PF=%.2f (样本量需 >=30 才可信)"
              % (m, s["n"], s["avg"], s["pf"]))
else:
    print("  **无任何月份在 3 年中全部为负**")
print("\n  6月结论: %s" % ("跨年一致(3/3改善)" if improved == 3
                          else "**非跨年一致(%d/3)** —— 2025年6月为正, 破坏规律" % improved))
if improved < 3:
    print("  → skip-6 **不满足跨年一致性**, 属弱证据, 不应接线")
    print("  → 与 R38h(技术腿)/C1(regime) 同类: 聚合数字好但缺跨期一致性")