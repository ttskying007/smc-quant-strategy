# -*- coding: utf-8 -*-
"""R65 治疗性仿真 — 冻结基线上的"如果 Jev 影子变成 gate/rank 分量"对照"""
import json, collections

recs = [json.loads(l) for l in open(r"E:\test\smc_project\research\jev_audit_cache_v2.jsonl", encoding="utf-8")]


def pf(rows):
    pos = sum(r["net_pnl_pct"] for r in rows if r["net_pnl_pct"] > 0)
    neg = -sum(r["net_pnl_pct"] for r in rows if r["net_pnl_pct"] < 0)
    return pos / neg if neg else float("inf")


def st(rows):
    n = len(rows)
    if not n:
        return 0, 0, 0, 0
    avg = sum(r["net_pnl_pct"] for r in rows) / n
    wr = sum(1 for r in rows if r["net_pnl_pct"] > 0) / n * 100
    return n, round(avg, 2), round(wr, 1), round(pf(rows), 2)


print("=== 全基线 1858 ==="); print(" ", st(recs))
print("\n=== 手术A: 过滤 p_valid<0.2 (Jev严重怀疑区) ===")
sub = [r for r in recs if (r.get("p_valid") or 0) >= 0.2]
print("  all: ", st(recs)); print("  left:", st(sub))
by_year = collections.defaultdict(list)
for r in sub:
    by_year[r["entry_date"][:4]].append(r)
for y in sorted(by_year):
    print(f"  {y}:", st(by_year[y]))

print("\n=== 手术B: 过滤 p_valid<0.2 且 timing<2 ===")
sub2 = [r for r in recs if (r.get("p_valid") or 0) >= 0.2 and (r.get("timing") or 0) >= 2]
print("  left:", st(sub2))

print("\n=== 手术C: rank 软降权 — p_valid<0.2 权重0.3 ===")
sub3 = []
for r in recs:
    w = 1.0 if (r.get("p_valid") or 0) >= 0.2 else 0.3
    sub3.append((r, w))
nw = sum(w for _, w in sub3)
av3 = sum(r["net_pnl_pct"] * w for r, w in sub3) / nw
print(f"  n_w={nw:.0f} avg={av3:.2f}  (基线 avg 4.07)")

print("\n=== 手术D: 若 SL 放宽一档能否救 sl_too_tight?(估算)")
tight = [r for r in recs if r.get("tpsl") == "sl_too_tight"]
print(f"  sl_too_tight 桶 n={len(tight)} avg={sum(r['net_pnl_pct'] for r in tight)/len(tight):.2f}")
# 他们 MFE ≥某阈值的比例 = 涨过又被SL打掉
recoverable = [r for r in tight if r["net_pnl_pct"] < 0]
print(f"  其中亏损腿 n={len(recoverable)} — 若 SL×0.96 放宽可能挽回部分(需回测验证)")
