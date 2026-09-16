# -*- coding: utf-8 -*-
"""r38_accum_sensitivity.py —— ret60 阈值的敏感性扫描 + 多重检验(判定是否过拟合).

背景(R38al): 搜索 ACCUM×2 的 regime 判别变量, 发现
  "ACCUM & ret60 <= -0.25" 可救 2024(3/3年改善)。
**但该阈值是看着 2024 子样本挑的** —— 2024 ACCUM 内 ret60<=-0.25 子集
avg+5.864%/PF5.44, 而 ret60>-0.25 子集仅 +0.879%/PF1.46。
这正是 R38ai 的陷阱形态: **事后选择阈值**。

本脚本做三件事(全部事前规定判据):
  ① 阈值敏感性: ret60 切点从 -0.15 到 -0.35 逐 0.01 扫描
     判据: 若只有一个孤立切点"有效"而邻近切点失效 → 过拟合
           若一个连续区间都有效 → 稳健
  ② IS/OOS 双段验证(该规则在 IS/OOS 都要改善)
  ③ 多重检验: 扫描 N 个切点, 期望随机命中数 = N × 单次显著性水平
  ④ 置换检验: 打乱 ret60 值, 看最佳切点的改善能否复现

先把特征缓存到 JSON(一次全市场遍历), 后续分析可廉价复用。
纯研究。
"""
import csv
import io
import json
import os
import random
import sys

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

HERE = r"E:\test\smc_project\research"
KT = r"E:\test\smc_project\hermes\kline_cache_tencent"
CACHE = os.path.join(HERE, "r38_accum_feat_cache.json")
IS_END = "20250630"
YEARS = ("2023", "2024", "2025", "2026")
random.seed(20260916)


def f(x, d=0.0):
    try:
        return float(x)
    except Exception:
        return d


# ── ① 特征缓存(一次遍历, 后续复用) ──
if os.path.exists(CACHE):
    recs = json.load(open(CACHE, encoding="utf-8"))
    print("特征缓存命中: %d 笔" % len(recs))
else:
    code2file = {fn.split("_")[0]: os.path.join(KT, fn) for fn in os.listdir(KT)
                 if fn.endswith("_daily_800.json")}
    bar_cache = {}

    def bars_of(code):
        if code not in bar_cache:
            p = code2file.get(code)
            if not p:
                bar_cache[code] = []
                return bar_cache[code]
            raw = json.load(open(p, encoding="utf-8"))
            bs = []
            for r in raw:
                t = "".join(x for x in str(r.get("t") or "") if x.isdigit())[:8]
                if t and r.get("o") and r.get("h") and r.get("l") and r.get("c") and r.get("v"):
                    bs.append({"t": t, "o": float(r["o"]), "h": float(r["h"]),
                               "l": float(r["l"]), "c": float(r["c"]), "v": float(r["v"])})
            bs.sort(key=lambda b: b["t"])
            bar_cache[code] = bs
        return bar_cache[code]

    def feats(bs, i):
        if i < 91:
            return None
        w60 = bs[i - 60:i]
        if len(w60) < 2:
            return None
        ret60 = w60[-1]["c"] / w60[0]["c"] - 1
        v20 = sum(b["v"] for b in bs[i - 20:i]) / 20
        v60 = sum(b["v"] for b in bs[i - 60:i]) / 60
        vt = v20 / v60 if v60 else 1
        if ret60 < -0.15 and vt < 0.9:
            st = "ACCUM"
        elif ret60 > 0.30 and vt > 1.3:
            st = "DISTRIB"
        elif ret60 > 0.20 and vt > 1.1:
            st = "MARKUP"
        else:
            st = "UPTREND" if ret60 > 0 else "DOWNTREND"
        if i >= 15:
            trs, pdm, ndm = [], [], []
            for k in range(i - 13, i + 1):
                up = bs[k]["h"] - bs[k - 1]["h"]
                dn = bs[k - 1]["l"] - bs[k]["l"]
                pdm.append(up if (up > dn and up > 0) else 0.0)
                ndm.append(dn if (dn > up and dn > 0) else 0.0)
                trs.append(max(bs[k]["h"] - bs[k]["l"],
                               abs(bs[k]["h"] - bs[k - 1]["c"]),
                               abs(bs[k]["l"] - bs[k - 1]["c"])))
            atr = sum(trs) / 14 if trs else 0
            pdi = 100 * (sum(pdm) / 14) / atr if atr else 0
            ndi = 100 * (sum(ndm) / 14) / atr if atr else 0
            adx = 100 * abs(pdi - ndi) / (pdi + ndi) if (pdi + ndi) else 0
        else:
            adx = 0.0
        return {"ret60": round(ret60, 6), "vt": round(vt, 4), "stage": st, "adx": round(adx, 2)}

    rows = list(csv.DictReader(open(os.path.join(HERE, "combo_v20f_trades.csv"),
                                   encoding="utf-8-sig")))
    ev = [r for r in rows if r.get("src") == "EVENT"]
    recs = []
    for r in ev:
        sym = str(r.get("symbol") or "").split(".")[0]
        d8 = str(r.get("entry_date") or "").replace("-", "")
        bs = bars_of(sym)
        if not bs:
            continue
        dates = [b["t"] for b in bs]
        if d8 not in dates:
            continue
        ei = dates.index(d8)
        if ei - 1 < 0:
            continue
        ft = feats(bs, ei - 1)
        if not ft:
            continue
        recs.append({"net": f(r["net_pnl_pct"]), "d": d8, **ft})
    json.dump(recs, open(CACHE, "w", encoding="utf-8"), ensure_ascii=False)
    print("特征已缓存: %d 笔 -> %s" % (len(recs), CACHE))


def metrics(ws):
    if not ws:
        return None
    c = [n * w for n, w in ws]
    tw = sum(w for _, w in ws)
    if tw <= 0:
        return None
    wins = [x for x in c if x > 0]
    loss = [x for x in c if x <= 0]
    pf = sum(wins) / abs(sum(loss)) if sum(loss) else 99.0
    return {"n": len(c), "exp": round(tw, 0),
            "avg_exp": round(sum(c) / tw, 3), "pf": round(pf, 2)}


def base(sub):
    return metrics([(t["net"], 1.0) for t in sub])


def cond(sub, cut):
    """ACCUM 且 ret60<=cut → ×2, 其余 ×1。"""
    return metrics([(t["net"], 2.0 if (t["stage"] == "ACCUM" and t["ret60"] <= cut) else 1.0)
                    for t in sub])


print("\n" + "=" * 100)
print("① ret60 阈值敏感性扫描 (判据: 有效切点是否构成连续区间)")
print("=" * 100)
CUTS = [round(-0.35 + 0.01 * k, 2) for k in range(21)]   # -0.35 .. -0.15
print("%-8s %6s %10s %10s %10s %10s %8s" % ("切点", "命中", "2023", "2024", "2025", "2026", "全期"))
print("%-8s %6s %10s %10s %10s %10s %8s" % ("", "", "(改善?)", "(改善?)", "(改善?)", "(改善?)", "3年+"))
good_2024 = []
good_all = []
for cut in CUTS:
    n_hit = sum(1 for t in recs if t["stage"] == "ACCUM" and t["ret60"] <= cut)
    marks = []
    yr_ok = 0
    for y in YEARS:
        rs = [t for t in recs if t["d"][:4] == y]
        if not rs:
            marks.append("-")
            continue
        a = base(rs)
        b = cond(rs, cut)
        ok = b["avg_exp"] > a["avg_exp"] and b["pf"] >= a["pf"] - 0.02
        marks.append("Y" if ok else "n")
        if ok:
            yr_ok += 1
    if marks[1] == "Y":
        good_2024.append(cut)
    if marks[1] == "Y" and marks[2] == "Y" and marks[3] == "Y":
        good_all.append(cut)
    print("%-8.2f %6d %10s %10s %10s %10s %8d"
          % (cut, n_hit, marks[0], marks[1], marks[2], marks[3], yr_ok))

print("\n  2024 改善的切点: %s" % (", ".join("%.2f" % c for c in good_2024) or "无"))
print("  2024+2025+2026 全改善的切点: %s" % (", ".join("%.2f" % c for c in good_all) or "无"))

print("\n" + "=" * 100)
print("② 连续性判定(过拟合检验)")
print("=" * 100)
if good_all:
    lo, hi = min(good_all), max(good_all)
    span = round(hi - lo, 2)
    n_good = len(good_all)
    print("  有效区间: [%.2f, %.2f]  跨度 %.2f  含 %d 个切点(共扫 %d)" % (lo, hi, span, n_good, len(CUTS)))
    print("  → %s" % ("**连续区间**(跨度>=0.05 且含>=5切点) → 稳健, 非孤立点"
                    if span >= 0.05 and n_good >= 5 else
                    "**孤立/窄区间** → 疑似过拟合(与 R38ai 同型)"))
else:
    print("  无任何切点满足 3 年全改善 → 判定**不稳健**")

print("\n" + "=" * 100)
print("③ 多重检验: 扫描 %d 个切点, 期望随机全改善个数" % len(CUTS))
print("=" * 100)
p_each = 0.5 ** 3
print("  单切点 P(3/3年改善 | 纯随机) = 0.5^3 = %.3f" % p_each)
print("  %d 个切点期望 = %.2f" % (len(CUTS), len(CUTS) * p_each))
print("  实测 3 年全改善切点数 = %d" % len(good_all))
if len(good_all) > len(CUTS) * p_each * 2:
    print("  → 实测显著高于随机期望(%.1f 倍) → 不似噪声"
          % (len(good_all) / max(0.01, len(CUTS) * p_each)))
else:
    print("  → 实测未显著超过随机期望 → 无法排除噪声")

print("\n" + "=" * 100)
print("④ 置换检验: 打乱 ret60 标签, 看能否复现'连续区间'")
print("=" * 100)
NPERM = 200
hits = 0
base_ok_all = len(good_all)
for _ in range(NPERM):
    perm = [t["ret60"] for t in recs]
    random.shuffle(perm)
    tmp = [dict(t, ret60=perm[i]) for i, t in enumerate(recs)]
    ok_cuts = []
    for cut in CUTS:
        m = []
        for y in YEARS:
            rs = [t for t in tmp if t["d"][:4] == y]
            if not rs:
                m.append("-")
                continue
            a = base(rs)
            b = metrics([(t["net"], 2.0 if (t["stage"] == "ACCUM" and t["ret60"] <= cut) else 1.0)
                         for t in rs])
            m.append("Y" if (b["avg_exp"] > a["avg_exp"] and b["pf"] >= a["pf"] - 0.02) else "n")
        if m[1] == "Y" and m[2] == "Y" and m[3] == "Y":
            ok_cuts.append(cut)
    if len(ok_cuts) >= base_ok_all:
        hits += 1
p_perm = hits / NPERM
print("  %d 次打乱中, >=%d 个切点达 3 年全改善的比例 = %.3f" % (NPERM, base_ok_all, p_perm))
print("  → 置换 p ≈ %.3f %s" % (p_perm, "(<0.05 → 显著)" if p_perm < 0.05 else "(>=0.05 → 不显著)"))

print("\n" + "=" * 100)
print("⑤ IS/OOS 双段(最终确认)")
print("=" * 100)
for cut in (good_all[:1] + good_all[-1:]) if good_all else ():
    IS = [t for t in recs if t["d"] <= IS_END]
    OOS = [t for t in recs if t["d"] > IS_END]
    ai, ao = base(IS), base(OOS)
    bi, bo = cond(IS, cut), cond(OOS, cut)
    print("  切点 %.2f:" % cut)
    print("    IS : %+.3f%%/%.2f -> %+.3f%%/%.2f" % (ai["avg_exp"], ai["pf"], bi["avg_exp"], bi["pf"]))
    print("    OOS: %+.3f%%/%.2f -> %+.3f%%/%.2f" % (ao["avg_exp"], ao["pf"], bo["avg_exp"], bo["pf"]))
    ok = bi["avg_exp"] > ai["avg_exp"] and bo["avg_exp"] > ao["avg_exp"]
    print("    → 双段改善: %s" % ("是" if ok else "**否**"))

print("\n" + "=" * 100)
print("裁定")
print("=" * 100)
if good_all and len(good_all) >= 5 and p_perm < 0.05:
    print("  ✅ 通过连续性与置换检验 → ACCUM×2(限 ret60<=区间) 可升级为**真实候选**")
    print("     但仍须做: 全链路重放(过滤次序/cap 交互) + 生产口径特征核对")
else:
    print("  ❌ 未通过稳健性检验 → 维持 R38ak 的'观察项'定性")
    print("     理由: 有效区间过窄 / 置换不显著 → 与 R38ai 事后选择同型")