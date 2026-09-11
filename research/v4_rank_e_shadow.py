# -*- coding: utf-8 -*-
"""v4_rank_e_shadow.py —— rank 单调性 × E 正交性(预注册 #34, 完整版)"""
import csv, json, sys, io
from collections import defaultdict
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

# SHADOW 抽样键(symbol+entry_date)
led = json.load(open(r"E:\test\smc_project\research\shadow_ledger.json", encoding="utf-8"))
shadow_keys = {(t["symbol"], str(t["entry_date"])) for t in led["trades"]}
print(f"shadow keys: {len(shadow_keys)}")

with open(r"E:\test\smc_project\research\combo_v20f_trades.csv", encoding="utf-8", errors="replace") as f:
    rows = list(csv.DictReader(f))
# 对齐(忽略 BOM 列名)
sym_key = "symbol" if "symbol" in rows[0] else "\ufeffsymbol"
matched = []
for r in rows:
    s = str(r.get(sym_key) or "")
    # csv symbol 形如 000001.SZ; shadow 同
    d8 = str(r.get("entry_date") or "")
    if (s, d8) in shadow_keys:
        try:
            rank = int(float(r.get("rank") or 0))
            pnl = float(r.get("net_pnl_pct") or 0)
        except Exception:
            continue
        matched.append((s, d8, rank, pnl))
print(f"rank 匹配: {len(matched)}/{len(shadow_keys)}")

# S1: rank 档单调性
by_rank = defaultdict(list)
for s, d8, rk, p in matched:
    by_rank[rk].append(p)
print("\nrank 档(3倍费口径的 shadow pnl):")
for rk in sorted(by_rank):
    v = by_rank[rk]
    print(f"  rank={rk}: n={len(v)} avg={round(sum(v)/len(v),2)} wr={round(len([x for x in v if x>0])/len(v)*100,1)}%")
hi = [p for _, _, rk, p in matched if rk >= 4]
lo = [p for _, _, rk, p in matched if rk < 4]
d_hi = round(sum(hi)/len(hi), 2) if hi else None
d_lo = round(sum(lo)/len(lo), 2) if lo else None
print(f"S1: rank>=4 avg={d_hi} vs <4 avg={d_lo} → 差={round(d_hi-d_lo,2) if d_hi and d_lo else None}pp")

# S3: rank 与 E 的相关性(用 E 历史)
E = {d["d8"]: d.get("e") for d in json.load(open(
    r"E:\test\smc_project\research\handover\escore_history_full.json", encoding="utf-8")
).get("days", []) if d.get("e") is not None}
pairs = [(rk, E[d8]) for s, d8, rk, p in matched if d8 in E]
if len(pairs) > 30:
    n = len(pairs)
    mx = sum(x for x, _ in pairs) / n
    my = sum(y for _, y in pairs) / n
    cov = sum((x - mx) * (y - my) for x, y in pairs) / n
    sx = (sum((x - mx) ** 2 for x, _ in pairs) / n) ** 0.5
    sy = (sum((y - my) ** 2 for _, y in pairs) / n) ** 0.5
    rho = cov / (sx * sy) if sx and sy else 0
    print(f"S3: rank×E Pearson ρ = {round(rho, 3)} (n={n})")
    verdict_S3 = abs(rho) < 0.3
else:
    print(f"S3: 样本不足(n={len(pairs)})")
    rho = None
    verdict_S3 = None
verdict = {
    "S1_rank仍携信息(高−低>2pp)": bool(d_hi is not None and d_lo is not None and d_hi - d_lo > 2.0),
    "S2_rank弱化(<2pp或反转)": bool(d_hi is not None and d_lo is not None and d_hi - d_lo < 2.0),
    "S3_rank与E正交(|ρ|<0.3)": verdict_S3,
    "rho": round(rho, 3) if rho is not None else None,
    "delta_pp": round(d_hi - d_lo, 2) if d_hi is not None and d_lo is not None else None,
}
print("\n预注册:", json.dumps(verdict, ensure_ascii=False))
json.dump({"matched": len(matched), "rank_dist": {str(k): len(v) for k, v in sorted(by_rank.items())},
           "S1_delta": verdict["delta_pp"], "S3_rho": verdict["rho"],
           "preregistered": verdict},
          open(r"E:\test\smc_project\research\handover\V4_rank单调性E正交.json", "w",
               encoding="utf-8"), ensure_ascii=False, indent=2)
print("已写 handover/V4_rank单调性E正交.json")