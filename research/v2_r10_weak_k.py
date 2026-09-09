# -*- coding: utf-8 -*-
"""R10 弱市加权k生产决策: 纯净口径CSV(1640)重跑WF k稳定性
V1迭代4结论(混合口径): k滚动不稳健(6/8窗选k=1) → 降级研究保留。
但生产CFG仍启用k=2(b4d8e35基于A/B双段单调证据, 早于WF证据)。
决策规则(预注册):
  纯净口径WF若 k=1 在>=5/7窗被选 → k=2 无滚动稳健性 → 生产禁用(CFG.WEAK_MARKET_WEIGHT=False)
  若 k>=1.5 稳定被选 → 维持生产
方法: 与 event_walkforward.py 同机制(12m train→3m test→roll 3m), k选择=train风险调整和最大。
"""
import csv, io, json, random, sys
from collections import defaultdict
sys.path.insert(0, r"E:\test\smc_project\research")
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

OOS = "20250701"
CSV = r"E:\test\smc_project\research\combo_v20f_trades.csv"
KT = r"E:\test\smc_project\hermes\kline_cache_tencent"

rows = [r for r in csv.DictReader(open(CSV, encoding="utf-8-sig"))
        if r.get("src") == "EVENT" and r.get("net_pnl_pct") not in (None, "", "None")]
for r in rows:
    r["net"] = float(r["net_pnl_pct"])
    r["risk_pct"] = float(r.get("risk_pct") or 0)

# 市场代理(决策时点可得, ≤d8 数据)
snap = json.load(open(KT + r"\.mkt_sample.json", encoding="utf-8"))
code2bars = {}
for f in snap:
    try:
        raw = json.load(open(KT + os.sep if False else KT + "\\" + f, encoding="utf-8"))
        b2 = sorted((("".join(c for c in str(x.get("t") or "") if c.isdigit())[:8], float(x["c"]))
                     for x in raw if x.get("c") and x.get("o")), key=lambda x: x[0])
        if len(b2) >= 25:
            code2bars[f] = b2
    except Exception:
        continue

import os  # noqa (前置使用)

def proxy_on(d8):
    rets = []
    for f, b2 in code2bars.items():
        ds = [x[0] for x in b2]
        i = None
        for k in range(len(ds) - 1, -1, -1):
            if ds[k] <= d8:
                i = k; break
        if i is None or i < 20:
            continue
        rets.append(b2[i][1] / b2[i - 20][1] - 1)
    return sum(rets) / len(rets) if rets else None

for t in rows:
    t["proxy"] = proxy_on(t["entry_date"])

def shift_ym(m, n):
    y, mm = int(m[:4]), int(m[4:6])
    t_ = y * 12 + mm - 1 + n
    return f"{t_//12:04d}{t_%12+1:02d}"

by_month = defaultdict(list)
for t in rows:
    by_month[t["entry_date"][:6]].append(t)
months = sorted(by_month)
KS = [1.0, 1.5, 2.0, 2.5, 3.0]

def riskadj(trs, k):
    return sum(max(0.3, min(2.0, 1 - k * t["proxy"])) * t["net"] * (1.0 / t["risk_pct"] / 100)
               for t in trs if t["proxy"] is not None and t["risk_pct"] > 0)

windows = []
cur_m = months[0]
while True:
    tr_end = shift_ym(cur_m, 12)
    te_start, te_end = tr_end, shift_ym(tr_end, 3)
    if te_start > months[-1]:
        break
    tr_tr = [t for m in months if cur_m <= m < tr_end for t in by_month[m]]
    te_tr = [t for m in months if te_start <= m < te_end for t in by_month[m]]
    if len(tr_tr) >= 25 and len(te_tr) >= 4:
        best_k, best_v = None, -1e18
        for k in KS:
            v = riskadj(tr_tr, k)
            if v > best_v:
                best_k, best_v = k, v
        # 测试期: 用选定k vs 固定k=1 的净值对比
        def eq(trs, k):
            e = 1.0
            for t in sorted(trs, key=lambda x: x["entry_date"]):
                if t["proxy"] is None or t["risk_pct"] <= 0:
                    continue
                w = max(0.3, min(2.0, 1 - k * t["proxy"]))
                pos = min(1.0 / t["risk_pct"] / 100, 0.25)
                e *= (1 + w * pos * t["net"] / 100)
            return e
        windows.append({"test": f"{te_start}~{te_end}", "n": len(te_tr), "k_sel": best_k,
                        "eq_sel": round(eq(te_tr, best_k), 4), "eq_k1": round(eq(te_tr, 1.0), 4)})
    cur_m = shift_ym(cur_m, 3)

prod_sel = 1.0; prod_k1 = 1.0
k_hist = defaultdict(int)
for w in windows:
    prod_sel *= w["eq_sel"]; prod_k1 *= w["eq_k1"]
    k_hist[w["k_sel"]] += 1
    print(f"  {w['test']}: n={w['n']:3d} k_sel={w['k_sel']} eq_sel={w['eq_sel']:.4f} vs eq_k1={w['eq_k1']:.4f}")

k1_count = k_hist.get(1.0, 0)
verdict = {
    "windows": len(windows), "k_histogram": dict(k_hist),
    "k1_selected_windows": k1_count,
    "prod_eq_selected": round(prod_sel, 4), "prod_eq_fixed_k1": round(prod_k1, 4),
    "selected_beats_fixed_k1": prod_sel > prod_k1,
}
verdict["disable_k2_in_production"] = (k1_count >= len(windows) - 2) or (not verdict["selected_beats_fixed_k1"])
print(f"\n== R10 纯净口径 WF k 稳定性 ==")
print(f"  k直方图: {dict(k_hist)}")
print(f"  累计净值: 选择k={prod_sel:.4f} vs 固定k=1 {prod_k1:.4f}")
print(f"  → 决策: {'禁用生产k=2 (CFG.WEAK_MARKET_WEIGHT=False)' if verdict['disable_k2_in_production'] else '维持生产k=2'}")

json.dump({"verdict": verdict, "windows": windows},
          open(r"E:\test\smc_project\research\handover\R10弱市权重纯净WF决策.json", "w", encoding="utf-8"),
          ensure_ascii=False, indent=2, default=str)
print("已写 handover/R10弱市权重纯净WF决策.json")