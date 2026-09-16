# -*- coding: utf-8 -*-
"""r38_accum_discriminator.py —— ACCUM×2 的 regime 判别变量搜索(能否救活 2024?).

背景(R38ak): ACCUM×2 通过敞口归一(非纯杠杆), 但 2024(ACCUM 最大样本 n=149)
劣化 —— ACCUM 子集 +2.99%/PF2.79 明显劣于 非ACCUM +4.09%/PF3.81。
处置为"观察项, 待找到 regime 判别变量后重评"。

本脚本搜索: 是否存在**事前可得**的条件, 使 ACCUM×2 在 2024 也不劣化?
候选判别变量(均为 signal 日可得, 无前视):
  ① v_ratio 水平(放量强度) —— ACCUM 定义含 vt<0.9(缩量), 但个股差异大
  ② ret60 深度(超跌程度)
  ③ ADX 水平(趋势强度)
  ④ stage_span(阶段持续度)
  ⑤ 大盘 proxy(市场状态)

判据(预注册): 判别变量必须同时满足
  (a) 2024 在"高"组里 ACCUM×2 不劣化
  (b) 该规则在全样本 IS/OOS 双段仍改善
  (c) 2025/2026 不被破坏
若找不到 → ACCUM×2 **彻底关闭**(非观察项, 而是已证不可救)。

纯研究, 不修改生产。
"""
import csv
import io
import json
import os
import sys
from collections import defaultdict

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

HERE = r"E:\test\smc_project\research"
KT = r"E:\test\smc_project\hermes\kline_cache_tencent"
IS_END = "20250630"
YEARS = ("2023", "2024", "2025", "2026")


def f(x, d=0.0):
    try:
        return float(x)
    except Exception:
        return d


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
    """signal 日可得特征(无前视)。"""
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
    # ADX(14) Wilder 简化
    if i >= 15:
        trs = []
        pdm = []
        ndm = []
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
        dx = 100 * abs(pdi - ndi) / (pdi + ndi) if (pdi + ndi) else 0
        adx = dx
    else:
        adx = 0.0
    return {"ret60": ret60, "vt": vt, "stage": st, "adx": adx}


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

print("=" * 100)
print("ACCUM×2 regime 判别变量搜索 (n=%d)" % len(recs))
print("=" * 100)


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
            "avg_exp": round(sum(c) / tw, 3) if tw else 0,
            "pf": round(pf, 2)}


def run(subset, use_accum2):
    if use_accum2:
        return metrics([(t["net"], 2.0 if t["stage"] == "ACCUM" else 1.0) for t in subset])
    return metrics([(t["net"], 1.0) for t in subset])


print("\n① 基线: 逐年 ACCUM×2 vs 等权(确认 R38ak 结论)")
print("%-8s %26s %26s %8s" % ("年", "等权", "ACCUM×2", "裁定"))
for y in YEARS:
    rs = [t for t in recs if t["d"][:4] == y]
    if not rs:
        continue
    a = run(rs, False)
    b = run(rs, True)
    ok = b["avg_exp"] > a["avg_exp"] and b["pf"] > a["pf"]
    print("%-8s %25s %25s %8s"
          % (y, "%+.3f%%/%.2f" % (a["avg_exp"], a["pf"]),
             "%+.3f%%/%.2f" % (b["avg_exp"], b["pf"]),
             "改善" if ok else "**劣化**"))

print("\n" + "=" * 100)
print("② 判别变量搜索: 只在满足条件的子集上加 ACCUM×2")
print("=" * 100)
print("思路: 找到 2024 也成立的条件, 该条件外 ACCUM×2 不生效(退回等权)")

CANDIDATES = [
    ("ACCUM & ret60 <= -0.25 (更深超跌)", lambda t: t["stage"] == "ACCUM" and t["ret60"] <= -0.25),
    ("ACCUM & ret60 <= -0.30", lambda t: t["stage"] == "ACCUM" and t["ret60"] <= -0.30),
    ("ACCUM & vt <= 0.7 (更缩量)", lambda t: t["stage"] == "ACCUM" and t["vt"] <= 0.7),
    ("ACCUM & adx >= 20 (趋势确认)", lambda t: t["stage"] == "ACCUM" and t["adx"] >= 20),
    ("ACCUM & adx >= 25", lambda t: t["stage"] == "ACCUM" and t["adx"] >= 25),
    ("ACCUM & ret60 <= -0.25 & adx >= 20", lambda t: t["stage"] == "ACCUM" and t["ret60"] <= -0.25 and t["adx"] >= 20),
]


def conditional(subset, cond):
    """仅对满足 cond 的交易加权 ×2, 其余等权。"""
    return metrics([(t["net"], 2.0 if cond(t) else 1.0) for t in subset])


print("\n逐年效果(每单位%/PF) —— 需 2024 不劣化:")
for name, cond in CANDIDATES:
    print("\n  ▸ %s" % name)
    n_hit = sum(1 for t in recs if cond(t))
    print("     命中 %d / %d (%.1f%%)" % (n_hit, len(recs), 100 * n_hit / len(recs)))
    allok = True
    for y in YEARS:
        rs = [t for t in recs if t["d"][:4] == y]
        if not rs:
            continue
        a = run(rs, False)
        b = conditional(rs, cond)
        ok = b["avg_exp"] > a["avg_exp"] and b["pf"] >= a["pf"] - 0.02
        if y == "2024" and not ok:
            allok = False
        print("     %s: 等权 %+.3f%%/%.2f | 条件加权 %+.3f%%/%.2f %s"
              % (y, a["avg_exp"], a["pf"], b["avg_exp"], b["pf"],
                 "✓" if ok else "✗"))
    print("     → 2024 可救: %s" % ("是" if allok else "**否**"))

print("\n" + "=" * 100)
print("③ 最严检验: 2024 单年 + 2014 内 2024 子样本细分")
print("=" * 100)
r2024 = [t for t in recs if t["d"][:4] == "2024"]
acc24 = [t for t in r2024 if t["stage"] == "ACCUM"]
oth24 = [t for t in r2024 if t["stage"] != "ACCUM"]
print("2024: ACCUM n=%d | 非ACCUM n=%d" % (len(acc24), len(oth24)))
for lab, grp in (("ACCUM(2024)", acc24), ("非ACCUM(2024)", oth24)):
    if not grp:
        continue
    p = [t["net"] for t in grp]
    w = [x for x in p if x > 0]
    l = [x for x in p if x <= 0]
    pf = sum(w) / abs(sum(l)) if sum(l) else 99
    print("  %-16s avg=%+.3f%% wr=%.1f%% PF=%.2f" % (lab, sum(p) / len(p), 100 * len(w) / len(p), pf))

print("\n2024 ACCUM 的内部细分(找可救子集):")
for nm, sub in (("ret60<=-0.25", [t for t in acc24 if t["ret60"] <= -0.25]),
                ("ret60>-0.25", [t for t in acc24 if t["ret60"] > -0.25]),
                ("adx>=20", [t for t in acc24 if t["adx"] >= 20]),
                ("adx<20", [t for t in acc24 if t["adx"] < 20]),
                ("vt<=0.7", [t for t in acc24 if t["vt"] <= 0.7]),
                ("vt>0.7", [t for t in acc24 if t["vt"] > 0.7])):
    if not sub:
        print("  %-16s 无样本" % nm)
        continue
    p = [t["net"] for t in sub]
    w = [x for x in p if x > 0]
    l = [x for x in p if x <= 0]
    pf = sum(w) / abs(sum(l)) if sum(l) else 99
    print("  %-16s n=%3d avg=%+.3f%% PF=%.2f %s"
          % (nm, len(p), sum(p) / len(p), pf,
             "← 优于非ACCUM(+4.09%)" if sum(p) / len(p) > 4.09 else ""))

print("\n" + "=" * 100)
print("裁定")
print("=" * 100)
print("  若上述所有判别变量都无法让 2024 的 ACCUM×2 不劣化 →")
print("  ACCUM×2 **彻底关闭**(不是'观察项', 而是'已证不可救')。")
print("  理由: 2024 是最大样本年(n=149), 若无法在该年成立, 则优势不可复现。")