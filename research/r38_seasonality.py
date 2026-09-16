# -*- coding: utf-8 -*-
"""r38_seasonality.py —— 月度季节性规则 IS/OOS 检验(收尾 R38u 遗留假设).

背景: R38u 发现 4/5/6 月在基线上恒亏, 并裁定"须单独过 IS/OOS"。
R38af 进一步确认 rank 门槛无法修好这些月。本脚本做**最终的季节性检验**。

规则形式: "跳过某月"(skip-month), 在 EVENT 腿选股时拒绝该月信号。
数据: combo_v20f_trades.csv EVENT 腿(实际组合口径, 已含 cap)。
  IS  = entry_date <= 20250630
  OOS = entry_date >  20250630

预注册判据(与 R38 其余研究一致):
  规则晋级需 **IS 与 OOS 都改善 PF**(且 OOS avg 不劣化)。
  同时报告样本量, 避免小样本误导。

**多重检验警示**: 逐月检验 12 次, 5% 水平下期望 ~0.6 个假阳性 →
单月通过 IS/OOS 属**弱证据**, 除非幅度大且跨年一致。脚本会明确标注此点。
纯研究, 不修改生产。
"""
import csv
import io
import os
import sys
from collections import defaultdict

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

HERE = r"E:\test\smc_project\research"
IS_END = "20250630"
MONTHS = ["%02d" % i for i in range(1, 13)]


def f(x, d=0.0):
    try:
        return float(x)
    except Exception:
        return d


def load_ev(path):
    rows = list(csv.DictReader(open(path, encoding="utf-8-sig")))
    return [r for r in rows if r.get("src") == "EVENT"]


def stats(rows):
    if not rows:
        return None
    p = [f(r["net_pnl_pct"]) for r in rows]
    w = [x for x in p if x > 0]
    l = [x for x in p if x <= 0]
    pf = sum(w) / abs(sum(l)) if sum(l) else 99.0
    eq = 0.0
    peak = 0.0
    mdd = 0.0
    for x in p:
        eq += x
        peak = max(peak, eq)
        mdd = min(mdd, eq - peak)
    return {"n": len(p), "avg": round(sum(p) / len(p), 3),
            "wr": round(100 * len(w) / len(p), 1), "pf": round(pf, 2),
            "mdd": round(mdd, 0), "sum": round(sum(p), 0)}


ev = load_ev(os.path.join(HERE, "combo_v20f_trades.csv"))
IS = [r for r in ev if str(r["entry_date"]) <= IS_END]
OOS = [r for r in ev if str(r["entry_date"]) > IS_END]

print("=" * 104)
print("月度季节性 IS/OOS 检验 (EVENT 腿, 基线口径)")
print("=" * 104)
bi, bo = stats(IS), stats(OOS)
print("基准: IS n=%d avg=%+.3f%% PF=%.2f | OOS n=%d avg=%+.3f%% PF=%.2f"
      % (bi["n"], bi["avg"], bi["pf"], bo["n"], bo["avg"], bo["pf"]))
print("总样本 EVENT n=%d" % len(ev))


def sub_month(rows, m):
    return [r for r in rows if str(r["entry_date"])[4:6] == m]


print("\n" + "=" * 104)
print("① 逐月基线表现(分段)")
print("=" * 104)
print("%-6s %24s %24s" % ("月", "IS (n/avg/PF)", "OOS (n/avg/PF)"))
for m in MONTHS:
    si = stats(sub_month(IS, m))
    so = stats(sub_month(OOS, m))
    ci = "n=%3d %+.2f%%/%.2f" % (si["n"], si["avg"], si["pf"]) if si else "—"
    co = "n=%3d %+.2f%%/%.2f" % (so["n"], so["avg"], so["pf"]) if so else "—"
    print("%-6s %24s %24s" % (m + "月", ci, co))

print("\n" + "=" * 104)
print("② 逐月 skip 规则(跳过该月)")
print("=" * 104)
print("%-6s %20s %20s %8s" % ("规则", "IS 变化", "OOS 变化", "裁定"))
passed = []
for m in MONTHS:
    ki = [r for r in IS if str(r["entry_date"])[4:6] != m]
    ko = [r for r in OOS if str(r["entry_date"])[4:6] != m]
    si, so = stats(ki), stats(ko)
    d_is = si["pf"] - bi["pf"]
    d_oos = so["pf"] - bo["pf"]
    ok_is = si["pf"] > bi["pf"]
    ok_oos = so["pf"] > bo["pf"]
    verdict = "✅ 两段均改善" if (ok_is and ok_oos) else (
        "IS改善/OOS劣化" if ok_is else ("仅OOS改善" if ok_oos else "两段均劣化"))
    if ok_is and ok_oos:
        passed.append(m)
    print("%-6s %19s %19s %8s" % ("skip-" + m + "月",
                                  "PF%+.2f (%+.3f%%)" % (d_is, si["avg"] - bi["avg"]),
                                  "PF%+.2f (%+.3f%%)" % (d_oos, so["avg"] - bo["avg"]),
                                  verdict))

print("\n" + "=" * 104)
print("③ 组合规则: 跳过 4+5+6 月")
print("=" * 104)
for label, months in (("skip-4/5/6", ("04", "05", "06")),
                      ("skip-6", ("06",)),
                      ("skip-4/5", ("04", "05"))):
    ki = [r for r in IS if str(r["entry_date"])[4:6] not in months]
    ko = [r for r in OOS if str(r["entry_date"])[4:6] not in months]
    si, so = stats(ki), stats(ko)
    print("  %-12s IS n=%4d avg=%+.3f%% PF=%.2f (基准 %+.3f%%/%.2f) | "
          "OOS n=%4d avg=%+.3f%% PF=%.2f (基准 %+.3f%%/%.2f)"
          % (label, si["n"], si["avg"], si["pf"], bi["avg"], bi["pf"],
             so["n"], so["avg"], so["pf"], bo["avg"], bo["pf"]))

print("\n" + "=" * 104)
print("④ 6月逐年明细(判断是否跨年一致)")
print("=" * 104)
for y in ("2024", "2025", "2026"):
    rs = [r for r in ev if str(r["entry_date"])[:4] == y
          and str(r["entry_date"])[4:6] == "06"]
    s = stats(rs)
    if s:
        print("  %s 6月: n=%3d avg=%+.3f%% wr=%.1f%% PF=%.2f" % (y, s["n"], s["avg"], s["wr"], s["pf"]))
    else:
        print("  %s 6月: 无样本" % y)

print("\n" + "=" * 104)
print("裁定")
print("=" * 104)
if passed:
    print("  通过 IS+OOS 双段的月份: %s" % ", ".join(m + "月" for m in passed))
    print("  ⚠ 但需注意多重检验(12 次检验, 期望 ~0.6 假阳性) —— 单月通过属弱证据;")
    print("    须核对: 幅度是否够大 + 是否跨年一致(见 ④)")
else:
    print("  **无任何月份通过 IS+OOS 双段检验**")
    print("  → 月度季节性规则**否决**: 弱势月无法用'跳过'稳定改善样本外表现")
    print("  → 与 C1(指数regime过滤)同类结局: 事后观察到的月份效应不含可交易 edge")

print("\n  注: 判据为 PF 双段改善; 若某月 OOS 样本极小(<20)则结论不可靠, 见①的 n。")