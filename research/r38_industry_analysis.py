# -*- coding: utf-8 -*-
"""r38_industry_analysis.py —— 行业维度假设检验(唯一未接入的新信息源).

industry_map.json 结构(已探明):
  元素 = {updateDate, code('sh.600000'), code_name, industry('J66货币金融服务'),
          industryClassification('证监会行业分类'), symbol('600000.SH')}
  **匹配键必须是 symbol**(上一版误用 code 得 0% 覆盖)
  行业数 84, 其中 industry 为空者 323 项

行业维度假设(H1): 内部人增持在行业内**聚集**(同期同行业多股增持)是否预测更优结果?
  SMC/Order Flow 视角: 行业内同步增持 = 聪明钱在板块层面的共识, 应强于孤立事件。
  缠论/Wyckoff 视角: 板块级 accumulation 确认个股 stage。

检验设计(全部用 signal 日可得信息, 无前视):
  ① 覆盖率核对(symbol 键)
  ② 行业 × 结果(是否存在行业效应)
  ③ **行业聚集度**: 同一行业在 ±N 日窗口内的增持笔数 → 分桶看结果
  ④ IS/OOS 双段

判据(预注册): 聚集度高的桶需 IS/OOS 双段 avg 与 PF 均优于低聚集桶, 且样本 >= 30。
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


# ── 行业映射(symbol -> industry) ──
raw = json.load(open(IM, encoding="utf-8"))
sym2ind = {}
for x in raw:
    if not isinstance(x, dict):
        continue
    s = str(x.get("symbol") or "").strip()
    ind = str(x.get("industry") or "").strip()
    if s and ind:
        sym2ind[s] = ind
print("=" * 96)
print("① 覆盖率核对(symbol 键)")
print("=" * 96)
print("industry_map 有效条数(有 industry) = %d / %d" % (len(sym2ind), len(raw)))

ev = [r for r in csv.DictReader(open(CSV, encoding="utf-8-sig")) if r.get("src") == "EVENT"]
n_hit = sum(1 for r in ev if str(r["symbol"]) in sym2ind)
print("EVENT 覆盖: %d / %d (%.1f%%)" % (n_hit, len(ev), 100 * n_hit / len(ev)))
if n_hit == 0:
    print("\n⚠ 覆盖率 0 —— 放弃本方向(无可用行业标签)")
    sys.exit(0)


def stats(rs):
    if not rs:
        return None
    p = [f(r["net_pnl_pct"]) for r in rs]
    w = [x for x in p if x > 0]
    l = [x for x in p if x <= 0]
    pf = sum(w) / abs(sum(l)) if sum(l) else 99.0
    return {"n": len(p), "avg": round(sum(p) / len(p), 2),
            "wr": round(100 * len(w) / len(p), 1), "pf": round(pf, 2)}


# ── ② 行业 × 结果 ──
print("\n" + "=" * 96)
print("② 行业 × 结果(样本>=30 的行业)")
print("=" * 96)
byind = defaultdict(list)
for r in ev:
    ind = sym2ind.get(str(r["symbol"]))
    if ind:
        byind[ind].append(r)
rows = []
for ind, rs in byind.items():
    s = stats(rs)
    if s["n"] >= 30:
        rows.append((ind, s))
rows.sort(key=lambda x: -x[1]["avg"])
print("%-34s %5s %9s %7s %7s" % ("行业", "n", "avg%", "wr", "PF"))
print("  --- 最优 8 ---")
for ind, s in rows[:8]:
    print("%-34s %5d %+8.2f%% %6.1f%% %7.2f" % (ind[:32], s["n"], s["avg"], s["wr"], s["pf"]))
print("  --- 最差 8 ---")
for ind, s in rows[-8:]:
    print("%-34s %5d %+8.2f%% %6.1f%% %7.2f" % (ind[:32], s["n"], s["avg"], s["wr"], s["pf"]))
print("  行业数(n>=30) = %d | 全体 avg=%+.2f%%" % (len(rows), stats(ev)["avg"]))

# ── ③ 行业聚集度(signal 日 ±5 日内同行业增持笔数) ──
print("\n" + "=" * 96)
print("③ 行业聚集度(同一行业 signal 日 ±5 交易日窗口内的增持笔数)")
print("=" * 96)
# 用 calendar-day ±7 近似(数据仅到日, 无交易日历于此; 保守用 ±7 日)
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

byind2 = defaultdict(list)
for r in ev:
    if r["_ind"] and r["_d"]:
        byind2[r["_ind"]].append(r)

for r in ev:
    if not (r["_ind"] and r["_d"]):
        r["_crowd"] = None
        continue
    peers = byind2[r["_ind"]]
    cnt = sum(1 for p in peers if p["_d"] and abs((p["_d"] - r["_d"]).days) <= 7)
    r["_crowd"] = cnt   # 含自身

crowded = [r for r in ev if r["_crowd"] is not None]
print("可算聚集度: %d / %d" % (len(crowded), len(ev)))
print("\n%-14s %6s %9s %7s %7s" % ("聚集度(笔)", "n", "avg%", "wr", "PF"))
BINS = [(1, 1), (2, 2), (3, 4), (5, 9), (10, 999)]
for lo, hi in BINS:
    sub = [r for r in crowded if lo <= r["_crowd"] <= hi]
    s = stats(sub)
    if s:
        lbl = "=1(孤立)" if lo == hi == 1 else ("[%d,%d]" % (lo, hi) if hi < 999 else ">=%d" % lo)
        print("%-14s %6d %+8.2f%% %6.1f%% %7.2f" % (lbl, s["n"], s["avg"], s["wr"], s["pf"]))

# ── ④ IS/OOS ──
print("\n" + "=" * 96)
print("④ IS/OOS 双段(孤立 vs 聚集)")
print("=" * 96)
print("%-10s %22s %22s" % ("分组", "IS (n/avg/PF)", "OOS (n/avg/PF)"))
for lbl, cond in (("孤立 =1", lambda c: c == 1),
                  ("聚集 >=2", lambda c: c >= 2),
                  ("聚集 >=3", lambda c: c >= 3),
                  ("强聚集 >=5", lambda c: c >= 5)):
    isr = [r for r in crowded if cond(r["_crowd"]) and str(r["entry_date"]) <= IS_END]
    oosr = [r for r in crowded if cond(r["_crowd"]) and str(r["entry_date"]) > IS_END]
    si, so = stats(isr), stats(oosr)
    ci = "%d %+.2f%%/%.2f" % (si["n"], si["avg"], si["pf"]) if si else "—"
    co = "%d %+.2f%%/%.2f" % (so["n"], so["avg"], so["pf"]) if so else "—"
    print("%-10s %22s %22s" % (lbl, ci, co))

print("\n" + "=" * 96)
print("⑤ 逐年(孤立 vs 聚集>=3)")
print("=" * 96)
for y in YEARS:
    a = stats([r for r in crowded if r["_crowd"] == 1 and str(r["entry_date"])[:4] == y])
    b = stats([r for r in crowded if r["_crowd"] >= 3 and str(r["entry_date"])[:4] == y])
    ca = "%d %+.2f%%/%.2f" % (a["n"], a["avg"], a["pf"]) if a else "—"
    cb = "%d %+.2f%%/%.2f" % (b["n"], b["avg"], b["pf"]) if b else "—"
    print("  %s: 孤立 %-20s | 聚集>=3 %-20s" % (y, ca, cb))

print("\n" + "=" * 96)
print("裁定")
print("=" * 96)
iso = stats([r for r in crowded if r["_crowd"] == 1])
c3 = stats([r for r in crowded if r["_crowd"] >= 3])
if iso and c3:
    print("  孤立(=1): n=%d avg=%+.2f%% PF=%.2f" % (iso["n"], iso["avg"], iso["pf"]))
    print("  聚集(>=3): n=%d avg=%+.2f%% PF=%.2f" % (c3["n"], c3["avg"], c3["pf"]))
    better = c3["avg"] > iso["avg"] and c3["pf"] > iso["pf"]
    print("  → 聚集更优: %s" % ("是(需过 IS/OOS 复核)" if better else "**否**"))
else:
    print("  样本不足")