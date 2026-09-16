# -*- coding: utf-8 -*-
"""r38_industry_decisive.py —— 决定性检验: 排除 2024-02 队列后聚集效应是否仍存在.

上一步(r38_industry_validate)三项排除表面全过:
  trailing 聚集仍单调 | 日内配对 +2.75pp | 10/10 行业聚集更优
**但月份集中度暴露致命问题**: 聚集交易 89.2% 落在 2024-0x(即 2024 年初),
且 2024-02 单月有 568 笔(占全年一半) —— 那是**一次市场崩盘底**。

若聚集信号其实只是"2024-02 崩盘底那一批交易"的另一种表述, 则它是**单一事件**,
与 R38 早前 C1(指数 regime 过滤) 同型 —— 事后可见但不可重复。

决定性检验(预注册):
  ① 剔除 2024-02 队列, 重做 trailing 聚集度分桶
  ② 剔除 2024 全年, 重做
  ③ 在每个非-2024-02 的年份内独立看聚集梯度
  ④ 严格配对限制在非-2024-02 日期
判据: 若剔除后聚集梯度**消失或大幅衰减** → 信号 = 单一事件, 否决。
      若梯度仍显著 → 才是可重复的行业效应。
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
    r["_ym"] = str(r["_d"])[:7] if r["_d"] else None

usable = [r for r in ev if r["_ind"] and r["_d"]]

# 月份分布(修正: 用 [:7] 得 YYYY-MM)
print("=" * 96)
print("① 聚集交易的**精确月份**分布(修正上一步 [:6] 的截断错误)")
print("=" * 96)
byind = defaultdict(list)
for r in usable:
    byind[r["_ind"]].append(r)
dayind = defaultdict(list)
for r in usable:
    dayind[(r["_d"], r["_ind"])].append(r)
for r in usable:
    r["_day_cluster"] = len(dayind[(r["_d"], r["_ind"])])

clu = [r for r in usable if r["_day_cluster"] >= 3]
cm = Counter(r["_ym"] for r in clu)
print("聚集(当日同行业>=3) n=%d | 月份数=%d" % (len(clu), len(cm)))
for k, n in cm.most_common(12):
    print("   %s  %4d (%.1f%%)" % (k, n, 100 * n / len(clu)))

# 2024-02 队列规模
feb24 = [r for r in usable if r["_ym"] == "2024-02"]
print("\n2024-02 队列: n=%d (占全体 %.1f%%)" % (len(feb24), 100 * len(feb24) / len(usable)))


def stats(rs):
    if not rs:
        return None
    p = [r["_net"] for r in rs]
    w = [x for x in p if x > 0]
    l = [x for x in p if x <= 0]
    pf = sum(w) / abs(sum(l)) if sum(l) else 99.0
    return {"n": len(p), "avg": round(sum(p) / len(p), 2),
            "wr": round(100 * len(w) / len(p), 1), "pf": round(pf, 2)}


def recompute_trailing(pool, ind_map):
    by = defaultdict(list)
    for r in pool:
        by[ind_map(r)].append(r)
    out = []
    for r in pool:
        peers = by[ind_map(r)]
        past = sum(1 for p in peers
                   if p is not r and 0 < (r["_d"] - p["_d"]).days <= 7)
        out.append((r, past))
    return out


def grad(pool, label):
    print("\n  [%s] n=%d" % (label, len(pool)))
    if len(pool) < 50:
        print("     样本不足, 跳过")
        return None
    tp = recompute_trailing(pool, lambda r: r["_ind"])
    print("     %-14s %6s %9s %7s %7s" % ("trailing", "n", "avg%", "wr", "PF"))
    res = {}
    for lo, hi in [(0, 0), (1, 1), (2, 3), (4, 999)]:
        sub = [r for r, t in tp if lo <= t <= hi]
        s = stats(sub)
        if s:
            lbl = "=0" if hi == 0 else ("=1" if lo == hi == 1 else
                  ("[2,3]" if hi == 3 else ">=4"))
            res[lbl] = s
            print("     %-14s %6d %+8.2f%% %6.1f%% %7.2f" % (lbl, s["n"], s["avg"], s["wr"], s["pf"]))
    return res


print("\n" + "=" * 96)
print("② 决定性: 剔除 2024-02 队列后, trailing 聚集梯度是否仍存在")
print("=" * 96)
full = grad(usable, "全体(含2024-02)")
no_feb = [r for r in usable if r["_ym"] != "2024-02"]
grad(no_feb, "剔除 2024-02")
no_2024 = [r for r in usable if not str(r["_ym"]).startswith("2024")]
grad(no_2024, "剔除 2024 全年")

print("\n" + "=" * 96)
print("③ 逐年独立: 聚集梯度是否在每一年内成立")
print("=" * 96)
for y in ("2023", "2024", "2025", "2026"):
    pool = [r for r in usable if str(r["_ym"]).startswith(y)]
    tp = recompute_trailing(pool, lambda r: r["_ind"])
    a = stats([r for r, t in tp if t == 0])
    b = stats([r for r, t in tp if t >= 2])
    ca = "%d %+.2f%%/%.2f" % (a["n"], a["avg"], a["pf"]) if a else "—"
    cb = "%d %+.2f%%/%.2f" % (b["n"], b["avg"], b["pf"]) if b else "—"
    print("  %s: trailing=0 %-20s | trailing>=2 %-20s" % (y, ca, cb))

print("\n  **2024 年内再分层(剔除 2024-02)**:")
p24 = [r for r in usable if str(r["_ym"]).startswith("2024") and r["_ym"] != "2024-02"]
tp = recompute_trailing(p24, lambda r: r["_ind"])
a = stats([r for r, t in tp if t == 0])
b = stats([r for r, t in tp if t >= 2])
print("     trailing=0:  %s" % ("%d %+.2f%%/%.2f" % (a["n"], a["avg"], a["pf"]) if a else "—"))
print("     trailing>=2: %s" % ("%d %+.2f%%/%.2f" % (b["n"], b["avg"], b["pf"]) if b else "—"))

print("\n" + "=" * 96)
print("④ 严格日内配对(排除 2024-02)")
print("=" * 96)
byday = defaultdict(list)
for r in no_feb:
    byday[r["_d"]].append(r)
iso_pool, clu_pool, days = [], [], 0
for d, grp in byday.items():
    iso = [r for r in grp if r["_day_cluster"] == 1]
    clu = [r for r in grp if r["_day_cluster"] >= 3]
    if iso and clu:
        days += 1
        iso_pool.extend(iso)
        clu_pool.extend(clu)
si, sc = stats(iso_pool), stats(clu_pool)
print("  可比日期数 = %d" % days)
if si and sc:
    print("    当日孤立: n=%d avg=%+.2f%% PF=%.2f" % (si["n"], si["avg"], si["pf"]))
    print("    当日聚集: n=%d avg=%+.2f%% PF=%.2f" % (sc["n"], sc["avg"], sc["pf"]))
    print("    → 配对差异 = %+.2fpp" % (sc["avg"] - si["avg"]))
else:
    print("    样本不足(无可比日期)")

print("\n" + "=" * 96)
print("裁定")
print("=" * 96)
print("  [全体]      trailing>=4 avg=%+.2f%%" % full.get(">=4", {}).get("avg", 0) if full else "n/a")