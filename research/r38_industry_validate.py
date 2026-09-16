# -*- coding: utf-8 -*-
"""r38_industry_validate.py —— 行业聚集效应的严格验证(排除三大混淆).

上一步发现(初测):
  孤立(=1)  n=349 avg=+0.89%  PF=1.44
  聚集(>=10) n=517 avg=+7.65% PF=13.40
  IS/OOS 双段、逐年均改善 -> 表面是重大发现
**但初测有致命缺陷**: 聚集度用 ±7 日(含未来) 计算 = **前视偏差**。

本脚本做三项严格排除:
  ① **前视**: 改用 **trailing window**(仅过去 N 日, 不含当日及未来)重算聚集度
  ② **时间混淆**: 聚集期可能恰是市场底部(如 2024-02 有 568 笔)。
     用**日内配对**检验 —— 同一天内比较"该行业有聚集"vs"该行业孤立"的交易,
     日期固定后, 时间效应被完全消除。
  ③ **行业×时间共线**: 检查聚集度高的交易是否集中在少数行业/少数月份。

判据(预注册, 严格):
  · trailing 聚集度仍单调 → 非前视
  · **日内配对**: 同日配对差异仍显著 → 非时间混淆
  · 跨行业稳健 → 非单一行业驱动
  三者全过才算候选; 任一不过则否决。
纯研究, 不修改生产。
"""
import csv
import io
import json
import os
import sys
from collections import Counter, defaultdict

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

IM = r"E:\test\smc_project\hermes\data\industry_map.json"
CSV = r"E:\test\smc_project\research\combo_v20f_trades.csv"
IS_END = "20250630"
YEARS = ("2023", "2024", "2025", "2026")


def f(x, d=0.0):
    try:
        return float(x)
    except Exception:
        return d


raw = json.load(open(IM, encoding="utf-8"))
sym2ind = {}
for x in raw:
    if isinstance(x, dict):
        s = str(x.get("symbol") or "").strip()
        i = str(x.get("industry") or "").strip()
        if s and i:
            sym2ind[s] = i

ev = [r for r in csv.DictReader(open(CSV, encoding="utf-8-sig")) if r.get("src") == "EVENT"]

import datetime as dt


def d2(s):
    s = str(s).replace("-", "")[:8]
    try:
        return dt.date(int(s[:4]), int(s[4:6]), int(s[6:8]))
    except Exception:
        return None


for r in ev:
    r["_ind"] = sym2ind.get(str(r["symbol"]))
    r["_d"] = d2(r.get("entry_date"))
    r["_net"] = f(r["net_pnl_pct"])

usable = [r for r in ev if r["_ind"] and r["_d"]]
print("=" * 96)
print("行业聚集效应严格验证 (可算 %d / %d)" % (len(usable), len(ev)))
print("=" * 96)


def stats(rs):
    if not rs:
        return None
    p = [r["_net"] for r in rs]
    w = [x for x in p if x > 0]
    l = [x for x in p if x <= 0]
    pf = sum(w) / abs(sum(l)) if sum(l) else 99.0
    return {"n": len(p), "avg": round(sum(p) / len(p), 2),
            "wr": round(100 * len(w) / len(p), 1), "pf": round(pf, 2)}


# ══ ① 前视修正: trailing window(仅过去 N 日, 不含当日) ══
print("\n" + "=" * 96)
print("① 前视修正: trailing 聚集度(仅过去 N 日, 不含当日及未来)")
print("=" * 96)

byind = defaultdict(list)
for r in usable:
    byind[r["_ind"]].append(r)

for r in usable:
    peers = byind[r["_ind"]]
    # 仅统计 **过去 1..7 日** 内同行业的其他增持(signal 日之前, 不含当日)
    past = sum(1 for p in peers
               if p is not r and p["_d"] and 0 < (r["_d"] - p["_d"]).days <= 7)
    r["_trail"] = past

print("%-16s %6s %9s %7s %7s" % ("trailing 笔数", "n", "avg%", "wr", "PF"))
for lo, hi in [(0, 0), (1, 1), (2, 3), (4, 7), (8, 999)]:
    sub = [r for r in usable if lo <= r["_trail"] <= hi]
    s = stats(sub)
    if s:
        lbl = "=0(完全孤立)" if hi == 0 else ("=1" if lo == hi == 1 else
              ("[%d,%d]" % (lo, hi) if hi < 999 else ">=%d" % lo))
        print("%-16s %6d %+8.2f%% %6.1f%% %7.2f" % (lbl, s["n"], s["avg"], s["wr"], s["pf"]))

# ══ ② 日内配对(消除时间效应) ══
print("\n" + "=" * 96)
print("② 日内配对: 同一天内 '该行业有聚集' vs '孤立'(时间效应被完全消除)")
print("=" * 96)

# 定义: 对每笔交易, 看 **当天**(同一 entry_date) 该行业是否有 >=2 笔增持
dayind = defaultdict(list)
for r in usable:
    dayind[(r["_d"], r["_ind"])].append(r)

for r in usable:
    r["_day_cluster"] = len(dayind[(r["_d"], r["_ind"])])   # 含自身

print("%-18s %6s %9s %7s %7s" % ("当日同行业笔数", "n", "avg%", "wr", "PF"))
for lo, hi in [(1, 1), (2, 2), (3, 4), (5, 999)]:
    sub = [r for r in usable if lo <= r["_day_cluster"] <= hi]
    s = stats(sub)
    if s:
        lbl = "=1(当日孤立)" if lo == hi == 1 else ("=2" if lo == hi == 2 else
              ("[%d,%d]" % (lo, hi) if hi < 999 else ">=%d" % lo))
        print("%-18s %6d %+8.2f%% %6.1f%% %7.2f" % (lbl, s["n"], s["avg"], s["wr"], s["pf"]))

# 严格日内配对: 仅用"同一天既有孤立又有聚集"的日期
print("\n  **严格配对**(仅计入同日同时存在孤立与聚集的日期):")
pair_days = 0
iso_pool, clu_pool = [], []
for d, grp in defaultdict(list, {}).items():
    pass
byday = defaultdict(list)
for r in usable:
    byday[r["_d"]].append(r)
for d, grp in byday.items():
    iso = [r for r in grp if r["_day_cluster"] == 1]
    clu = [r for r in grp if r["_day_cluster"] >= 3]
    if iso and clu:
        pair_days += 1
        iso_pool.extend(iso)
        clu_pool.extend(clu)
si, sc = stats(iso_pool), stats(clu_pool)
print("    可比日期数 = %d" % pair_days)
if si and sc:
    print("    当日孤立: n=%d avg=%+.2f%% PF=%.2f" % (si["n"], si["avg"], si["pf"]))
    print("    当日聚集: n=%d avg=%+.2f%% PF=%.2f" % (sc["n"], sc["avg"], sc["pf"]))
    print("    → 配对差异 = %+.2fpp (PF %+.2f)" % (sc["avg"] - si["avg"], sc["pf"] - si["pf"]))

# ══ ③ 行业×时间共线检查 ══
print("\n" + "=" * 96)
print("③ 聚集交易的行业/时间集中度(共线检查)")
print("=" * 96)
clu = [r for r in usable if r["_day_cluster"] >= 3]
print("聚集(当日同行业>=3) n=%d" % len(clu))
ci = Counter(r["_ind"] for r in clu)
print("  行业集中度: 前5占 %.1f%%" % (100 * sum(n for _, n in ci.most_common(5)) / len(clu)))
for k, n in ci.most_common(5):
    print("    %-32s %4d (%.1f%%)" % (k[:30], n, 100 * n / len(clu)))
cm = Counter(str(r["_d"])[:6] for r in clu)
print("  月份集中度: 前5占 %.1f%%" % (100 * sum(n for _, n in cm.most_common(5)) / len(clu)))
for k, n in cm.most_common(5):
    print("    %s %4d (%.1f%%)" % (k, n, 100 * n / len(clu)))

# ══ ④ 逐行业稳健性(排除单行业驱动) ══
print("\n" + "=" * 96)
print("④ 逐行业稳健性(聚集 vs 孤立, 仅列样本足够的行业)")
print("=" * 96)
print("%-30s %20s %20s" % ("行业", "孤立(=1)", "聚集(>=3)"))
robust = 0
checked = 0
for ind, grp in sorted(byind.items(), key=lambda kv: -len(kv[1])):
    iso = [r for r in grp if r["_day_cluster"] == 1]
    c3 = [r for r in grp if r["_day_cluster"] >= 3]
    if len(iso) >= 8 and len(c3) >= 8:
        checked += 1
        si, sc = stats(iso), stats(c3)
        better = sc["avg"] > si["avg"]
        if better:
            robust += 1
        print("%-30s %20s %20s %s" % (ind[:28],
              "%d %+.1f%%" % (si["n"], si["avg"]),
              "%d %+.1f%%" % (sc["n"], sc["avg"]),
              "✓" if better else "✗"))
print("  → 可检验行业 %d, 其中聚集更优 %d (%.0f%%)"
      % (checked, robust, 100 * robust / checked if checked else 0))

# ══ 裁定 ══
print("\n" + "=" * 96)
print("裁定")
print("=" * 96)
t0 = stats([r for r in usable if r["_trail"] == 0])
t8 = stats([r for r in usable if r["_trail"] >= 8])
print("  [前视修正] trailing=0: n=%d avg=%+.2f%% PF=%.2f | trailing>=8: n=%d avg=%+.2f%% PF=%.2f"
      % (t0["n"], t0["avg"], t0["pf"], t8["n"], t8["avg"], t8["pf"]))
print("  [日内配对] 差异 %s" % ("%+.2fpp" % (sc["avg"] - si["avg"]) if (si and sc) else "n/a"))
print("  [逐行业]   %d/%d 行业聚集更优" % (robust, checked))
print("\n  三项排除全过 => 候选; 任一不过 => 否决。")
print("  注: 若日内配对差异大幅缩小/消失 => 原发现主要是**时间效应**(市场底部)而非行业效应。")