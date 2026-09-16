# -*- coding: utf-8 -*-
"""r38_industry_vs_market.py —— 最终判定: 行业特异 vs 全市场增持潮.

前一步结论: 行业聚集效应剔除 2024-02 后仍成立(trailing>=4: +7.97%/PF9.58),
剔除 2024 全年也成立(+9.22%/PF10.24)。**比预期强**。

但剩最后一个致命混淆: 聚集可能只是**全市场增持潮**的代理
(2024-02 崩盘底全市场都在增持)。若如此, 它与已被否决的 C1(指数 regime) 同型 ——
事后可见但不可重复。

本脚本做 2D 分层判定:
  对每笔交易计算:
    mkt_trail = 全市场**所有行业**过去 7 日的增持笔数(不含当日)
    ind_trail = **同行业**过去 7 日的增持笔数
  ① 先看 mkt_trail 本身的梯度(是否全市场计数就够)
  ② 在 **mkt_trail 固定** 的层内, 看 ind_trail 是否仍有增量
  ③ IS/OOS 双段对最终候选定义
  ④ 置换检验(打乱行业标签)确认行业维度不是噪声

判据(预注册):
  · 若 ind_trail 在 mkt_trail 层内仍有显著增量 → **行业特异, 候选成立**
  · 若 ind_trail 增量消失 → 只是全市场择时, 与 C1 同型, 否决
  · 置换: 打乱行业标签后增量消失 → 行业维度真实
纯研究, 不修改生产。
"""
import csv
import io
import json
import os
import random
import sys
from collections import defaultdict

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

IM = r"E:\test\smc_project\hermes\data\industry_map.json"
CSV = r"E:\test\smc_project\research\combo_v20f_trades.csv"
IS_END = "20250630"
random.seed(20260916)


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
usable.sort(key=lambda r: r["_d"])
print("=" * 100)
print("最终判定: 行业特异 vs 全市场增持潮 (n=%d)" % len(usable))
print("=" * 100)


def compute_trails(pool, ind_key=lambda r: r["_ind"]):
    """O(n^2) 但 n~1500 可接受。返回 (mkt_trail, ind_trail)。"""
    out = {}
    for r in pool:
        mkt = 0
        ind = 0
        for p in pool:
            if p is r:
                continue
            dd = (r["_d"] - p["_d"]).days
            if 0 < dd <= 7:
                mkt += 1
                if ind_key(p) == ind_key(r):
                    ind += 1
        out[id(r)] = (mkt, ind)
    return out


trails = compute_trails(usable)
for r in usable:
    r["_mkt"], r["_ind_t"] = trails[id(r)]


def stats(rs):
    if not rs:
        return None
    p = [r["_net"] for r in rs]
    w = [x for x in p if x > 0]
    l = [x for x in p if x <= 0]
    pf = sum(w) / abs(sum(l)) if sum(l) else 99.0
    return {"n": len(p), "avg": round(sum(p) / len(p), 2),
            "wr": round(100 * len(w) / len(p), 1), "pf": round(pf, 2)}


# ══ ① 全市场计数梯度 ══
print("\n" + "=" * 100)
print("① 全市场增持计数(mkt_trail, 过去7日所有行业) 单独看")
print("=" * 100)
print("%-16s %6s %9s %7s %7s" % ("mkt_trail", "n", "avg%", "wr", "PF"))
for lo, hi in [(0, 5), (6, 20), (21, 50), (51, 100), (101, 9999)]:
    sub = [r for r in usable if lo <= r["_mkt"] <= hi]
    s = stats(sub)
    if s:
        print("%-16s %6d %+8.2f%% %6.1f%% %7.2f"
              % ("[%d,%d]" % (lo, hi) if hi < 9999 else ">=%d" % lo,
                 s["n"], s["avg"], s["wr"], s["pf"]))

# ══ ② 2D 分层: mkt_trail 固定后看 ind_trail ══
print("\n" + "=" * 100)
print("② **2D 分层**: 在 mkt_trail 固定的层内, ind_trail 是否仍有增量")
print("=" * 100)
MKT_BUCKETS = [(0, 20), (21, 60), (61, 150), (151, 9999)]
IND_BUCKETS = [(0, 0), (1, 3), (4, 999)]
print("%-14s %-12s %6s %9s %7s %7s" % ("mkt_trail", "ind_trail", "n", "avg%", "wr", "PF"))
for mlo, mhi in MKT_BUCKETS:
    for ilo, ihi in IND_BUCKETS:
        sub = [r for r in usable
               if mlo <= r["_mkt"] <= mhi and ilo <= r["_ind_t"] <= ihi]
        s = stats(sub)
        if s and s["n"] >= 15:
            print("%-14s %-12s %6d %+8.2f%% %6.1f%% %7.2f"
                  % ("[%d,%d]" % (mlo, mhi) if mhi < 9999 else ">=%d" % mlo,
                     "=0" if ihi == 0 else ("[1,3]" if ihi == 3 else ">=4"),
                     s["n"], s["avg"], s["wr"], s["pf"]))
    print("  " + "-" * 60)

# ══ ③ 置换检验: 打乱行业标签 ══
print("\n" + "=" * 100)
print("③ 置换检验: 打乱行业标签, 看 ind_trail 增量能否复现")
print("=" * 100)


def ind_increment(pool, ind_key):
    t = compute_trails(pool, ind_key)
    hi = [r for r in pool if t[id(r)][1] >= 4]
    lo = [r for r in pool if t[id(r)][1] == 0]
    sh, sl = stats(hi), stats(lo)
    if sh and sl and sh["n"] >= 20 and sl["n"] >= 20:
        return sh["avg"] - sl["avg"]
    return None


real_inc = ind_increment(usable, lambda r: r["_ind"])
print("  真实行业标签: >=4 与 =0 的 avg 差 = %s" % (
    "%+.2fpp" % real_inc if real_inc is not None else "n/a"))

NPERM = 30
hits = 0
vals = []
for _ in range(NPERM):
    labs = {}
    for r in usable:
        labs[id(r)] = random.randint(0, 40)
    v = ind_increment(usable, lambda r: labs.get(id(r), 0))
    if v is not None:
        vals.append(v)
        if v >= real_inc:
            hits += 1
if vals:
    vals.sort()
    print("  %d 次打乱: 中位 %+.2fpp | p90 %+.2fpp | >=真实值比例 %.2f"
          % (NPERM, vals[len(vals) // 2], vals[int(len(vals) * .9)], hits / len(vals)))
    print("  → 置换 p ≈ %.3f %s" % (hits / len(vals),
          "(<0.05 → 行业维度真实)" if hits / len(vals) < 0.05 else "(>=0.05 → 不显著)"))

# ══ ④ 候选定义 IS/OOS ══
print("\n" + "=" * 100)
print("④ 候选定义 IS/OOS: ind_trail >= 4 (行业过去7日增持>=4笔)")
print("=" * 100)
for lab, lo, hi in (("IS", "0", IS_END), ("OOS", IS_END + "1", "99999999")):
    pool = [r for r in usable if lo <= str(r["entry_date"]) <= hi]
    t = compute_trails(usable, lambda r: r["_ind"])
    for r in pool:
        r["_ind_t2"] = t[id(r)][1]
    hi_g = [r for r in pool if r["_ind_t2"] >= 4]
    all_g = pool
    sh, sa = stats(hi_g), stats(all_g)
    if sh and sa:
        print("  %-4s 全体 n=%4d avg=%+.2f%% PF=%.2f | ind>=4 n=%3d (%.0f%%) avg=%+.2f%% PF=%.2f"
              % (lab, sa["n"], sa["avg"], sa["pf"], sh["n"], 100 * sh["n"] / sa["n"],
                 sh["avg"], sh["pf"]))

print("\n" + "=" * 100)
print("裁定")
print("=" * 100)
print("  判据: ind_trail 在 mkt_trail 层内仍有增量 + 置换显著 => 行业特异候选成立")