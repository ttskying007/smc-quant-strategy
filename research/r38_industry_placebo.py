# -*- coding: utf-8 -*-
"""r38_industry_placebo.py —— date-shuffle 安慰剂检验(修正 R38ao 的置换缺陷).

R38ao 的缺陷: 置换**行业标签**并未破坏**日期聚集** —— 同日交易获同一随机标签仍产生
"聚集", null 分布被高估(打乱中位 +5.36pp vs 真实 +5.92pp, 真实仅高 0.56pp)。
→ 该 p 值不可信, 结论降级为"待确认"。

本脚本用**正确的 null**: **打乱日期**(keeping industry + net + 日期多重集不变),
即在保持"全市场增持潮时间结构"的同时, 破坏"行业-日期"的真实对应。
→ 若真实 increment 显著高于该 null → 行业特异真实。

同时做:
  ② 覆盖率漂移归因(IS 命中 35% vs OOS 21%)
  ③ 2D 分层下的真实 vs null 对照(最关键: 层内增量是否真实)

判据(预注册):
  · 真实 increment > null 分布的 p95 → 行业特异成立
  · 层内(mkt 固定)增量仍显著 → 非全市场择时
纯研究, 不修改生产。
"""
import csv
import io
import json
import os
import random
import sys

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

IM = r"E:\test\smc_project\hermes\data\industry_map.json"
CSV = r"E:\test\smc_project\research\combo_v20f_trades.csv"
IS_END = "20250630"
NP = 200          # 置换次数
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


recs = []
for r in ev:
    ind = sym2ind.get(str(r["symbol"]))
    d = d2(r.get("entry_date"))
    if ind and d:
        recs.append({"ind": ind, "d": d, "ord": d.toordinal(),
                     "net": f(r["net_pnl_pct"]), "ed": str(r["entry_date"])})
N = len(recs)
print("=" * 100)
print("date-shuffle 安慰剂检验 (n=%d, %d 次置换)" % (N, NP))
print("=" * 100)

# 预计算: 行业分组索引(置换时行业不变)
inds = [r["ind"] for r in recs]
nets = [r["net"] for r in recs]
dates_pool = [r["ord"] for r in recs]


def trails(ords):
    """返回 (mkt_trail, ind_trail) 列表。O(n^2), 用 ordinal 整数比较。"""
    mkt = [0] * N
    ind = [0] * N
    for i in range(N):
        di = ords[i]
        ii = inds[i]
        m = 0
        k = 0
        for j in range(N):
            if i == j:
                continue
            dd = di - ords[j]
            if 0 < dd <= 7:
                m += 1
                if inds[j] == ii:
                    k += 1
        mkt[i] = m
        ind[i] = k
    return mkt, ind


def stats(idx_list, which_net=None):
    if not idx_list:
        return None
    p = [nets[i] for i in idx_list]
    w = [x for x in p if x > 0]
    l = [x for x in p if x <= 0]
    pf = sum(w) / abs(sum(l)) if sum(l) else 99.0
    return {"n": len(p), "avg": round(sum(p) / len(p), 2),
            "wr": round(100 * len(w) / len(p), 1), "pf": round(pf, 2)}


def increment(ind):
    """整体增量: ind>=4 与 ind==0 的 avg 差。"""
    hi = [i for i in range(N) if ind[i] >= 4]
    lo = [i for i in range(N) if ind[i] == 0]
    sh, sl = stats(hi), stats(lo)
    if sh and sl and sh["n"] >= 20 and sl["n"] >= 20:
        return sh["avg"] - sl["avg"], sh, sl
    return None, sh, sl


def layered_increment(mkt, ind):
    """层内增量: 仅用最大的两个 mkt 层, ind>=4 vs ind==0 的 avg 差(加权)。"""
    tot_w = 0.0
    acc = 0.0
    detail = []
    for mlo, mhi in [(21, 60), (151, 10 ** 9)]:
        hi = [i for i in range(N) if mlo <= mkt[i] <= mhi and ind[i] >= 4]
        lo = [i for i in range(N) if mlo <= mkt[i] <= mhi and ind[i] == 0]
        sh, sl = stats(hi), stats(lo)
        if sh and sl and sh["n"] >= 15 and sl["n"] >= 10:
            d = sh["avg"] - sl["avg"]
            w = sh["n"] + sl["n"]
            acc += d * w
            tot_w += w
            detail.append((mlo, mhi, sh["n"], sh["avg"], sl["n"], sl["avg"], round(d, 2)))
    if tot_w == 0:
        return None, detail
    return acc / tot_w, detail


# ── 真实值 ──
mkt_r, ind_r = trails(dates_pool)
inc_r, sh_r, sl_r = increment(ind_r)
lay_r, lay_detail_r = layered_increment(mkt_r, ind_r)
print("\n① 真实数据")
print("  整体: ind>=4 n=%d avg=%+.2f%% | ind=0 n=%d avg=%+.2f%% → 增量 %+.2fpp"
      % (sh_r["n"], sh_r["avg"], sl_r["n"], sl_r["avg"], inc_r))
print("  层内(mkt 固定, 加权): %s pp" % ("%+.2f" % lay_r if lay_r is not None else "n/a"))
for mlo, mhi, hn, ha, ln, la, d in lay_detail_r:
    print("     mkt[%d,%d]: ind>=4 n=%d %+.2f%% | ind=0 n=%d %+.2f%% → %+.2fpp"
          % (mlo, mhi, hn, ha, ln, la, d))

# ── 安慰剂 ──
print("\n② date-shuffle 安慰剂 (%d 次) ..." % NP)
inc_null = []
lay_null = []
for it in range(NP):
    shuffled = dates_pool[:]
    random.shuffle(shuffled)
    mk, idn = trails(shuffled)
    v, _, _ = increment(idn)
    if v is not None:
        inc_null.append(v)
    lv, _ = layered_increment(mk, idn)
    if lv is not None:
        lay_null.append(lv)
    if (it + 1) % 50 == 0:
        print("     ... %d/%d" % (it + 1, NP))


def pct(vals, v):
    if not vals:
        return None
    s = sorted(vals)
    return sum(1 for x in s if x >= v) / len(s), s[len(s) // 2], s[int(len(s) * .95)]


print("\n③ 结果对照")
for lab, real, null in (("整体增量(pp)", inc_r, inc_null),
                        ("层内增量(pp)", lay_r, lay_null)):
    if real is None or not null:
        print("  %s: 不可判定" % lab)
        continue
    p, med, p95 = pct(null, real)
    print("  %-14s 真实 %+.2f | null 中位 %+.2f p95 %+.2f | p = %.4f %s"
          % (lab, real, med, p95, p, "(显著)" if p < 0.05 else "(**不显著**)"))

# ── 覆盖率漂移 ──
print("\n④ 覆盖率漂移归因(IS 35% vs OOS 21%)")
for lab, lo, hi in (("IS", "0", IS_END), ("OOS", IS_END + "1", "99999999")):
    idx = [i for i in range(N) if lo <= recs[i]["ed"] <= hi]
    if not idx:
        continue
    hit = [i for i in idx if ind_r[i] >= 4]
    sa, sh2 = stats(idx), stats(hit)
    print("  %-4s 全体 n=%4d avg=%+.2f%% | ind>=4 n=%3d (%.0f%%) avg=%+.2f%%"
          % (lab, sa["n"], sa["avg"], sh2["n"], 100 * sh2["n"] / sa["n"], sh2["avg"]))
print("\n  逐年命中率(ind_trail>=4):")
for y in ("2023", "2024", "2025", "2026"):
    idx = [i for i in range(N) if recs[i]["ed"].startswith(y)]
    if not idx:
        continue
    hit = [i for i in idx if ind_r[i] >= 4]
    sh2 = stats(hit)
    print("    %s: %d/%d = %.0f%% %s"
          % (y, len(hit), len(idx), 100 * len(hit) / len(idx),
             ("avg=%+.2f%%" % sh2["avg"]) if sh2 else ""))

print("\n" + "=" * 100)
print("裁定")
print("=" * 100)
print("  若 层内增量 p<0.05 → 行业特异成立(可进入全链路重放)")
print("  若 p>=0.05 → 行业效应不显著, 关闭该方向")