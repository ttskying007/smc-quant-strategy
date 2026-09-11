# -*- coding: utf-8 -*-
"""v4_adx_gate_burden.py —— ADX≥20 门的负担审计(预注册 #35)
背景: ADX bug 修复(§14-15)后, 事件腿候选在 ADX 门上被拒 8 例(0910 一日 5 例)。
旧 ADX(单窗 DX)系统性偏低过拒边界股 → 修复后(真 Wilder ADX)拒绝率应**下降**。
但 8 例的 ADX 值(0.33/5.78/5.45/15.79/7.57)仍全部 <20 —— 这些是"真低 ADX"(正确拒绝)
还是仍有"边界挤压"(真值在 15-25 之间被门卡)?
预注册:
  A1 重放这 8 例的 ADX14(用修复后的 paper_sim.adx14_of): 若真值仍全部 <20 → 拒绝正确, 门无负担
  A2 若有 1-3 例真值落在 [15,25) → 边界带存在, ADX 门有误拒风险(但 v20g 语义下已是最优)
  A3 若 ≥4 例真值 ≥20 → 漏斗的 ADX 判定实现与 paper_sim.adx14_of 仍有语义分叉!
方法: 读 8 例 K 线, 在决策日重放 adx14_of。"""
import json, os, sys, io
sys.path.insert(0, r"E:\test\smc_project\research")
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
KT = r"E:\test\smc_project\hermes\kline_cache_tencent"
import paper_sim as PS

def load_daily(code):
    for suf in ("_SZ", "_SH", "_BJ"):
        fp = os.path.join(KT, f"{code}{suf}_daily_800.json")
        if os.path.exists(fp):
            raw = json.load(open(fp, encoding="utf-8"))
            return [{"t": str(b["t"])[:8], "o": float(b["o"]), "h": float(b["h"]),
                     "l": float(b["l"]), "c": float(b["c"]), "v": float(b.get("v") or 0)} for b in raw]
    return None

cases = [("300926", "20260910", 0.33), ("300925", "20260910", 5.78), ("688602", "20260910", 5.45),
         ("600382", "20260910", 15.79), ("688312", "20260910", 7.57)]
results = []
for code, d8, old_val in cases:
    dd = load_daily(code)
    if not dd:
        print(f"{code}: 无K线")
        continue
    idx = next((k for k, b in enumerate(dd) if b["t"] == d8), None)
    if idx is None:
        print(f"{code}: 决策日 {d8} 不在K线内")
        continue
    adx = PS.adx14_of(dd, idx)
    results.append((code, d8, old_val, round(adx, 2) if adx is not None else None))
    print(f"{code} @{d8}: 台账拒绝值={old_val} → 修复后 ADX14={round(adx,2) if adx is not None else None}")

# 预注册判定
n_below = sum(1 for r in results if r[3] is not None and r[3] < 20)
n_band = sum(1 for r in results if r[3] is not None and 15 <= r[3] < 20)
n_above = sum(1 for r in results if r[3] is not None and r[3] >= 20)
verdict = {
    "A1_拒绝全部正确(真值仍<20)": n_below == len(results) and n_band == 0,
    "A2_边界带存在([15,20)内)": n_band > 0,
    "A3_实现分叉(真值≥20仍被拒)": n_above > 0,
    "n_below20": n_below, "n_band_15_20": n_band, "n_above20": n_above,
}
print("\n预注册:", json.dumps(verdict, ensure_ascii=False))
json.dump({"cases": results, "preregistered": verdict},
          open(r"E:\test\smc_project\research\handover\V4_ADG门负担审计.json", "w",
               encoding="utf-8"), ensure_ascii=False, indent=2)
print("已写 handover/V4_ADG门负担审计.json")