# -*- coding: utf-8 -*-
"""R26 跟进: risk_pct 分布形态 + 分档胜率单调性 (READ-ONLY)
问题: H4 证伪后需确认 risk_pct≈20% 是否为 invalidation fallback,
以及 SL 距离分档与胜率/期望是否单调。
输出: research/handover/r26_riskpct_bands.json
"""
import io, sys, os, json, csv, statistics
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
from collections import Counter

RESEARCH = os.path.dirname(os.path.abspath(__file__))
CSV = os.path.join(RESEARCH, "combo_v20f_trades.csv")

def f(x, d=0.0):
    try: return float(x)
    except Exception: return d

rows = list(csv.DictReader(open(CSV, encoding="utf-8")))
n = len(rows)
rps = [f(r["risk_pct"]) for r in rows]

# 1) 直方图：找"坨点"(筛计数 > 15% 的筒)
buckets = Counter(round(v, 1) for v in rps)
top = buckets.most_common(10)
print("risk_pct 最常见取值(top10):")
for v, c in top:
    print(f"  {v:>6}% : n={c:4d} ({c/n*100:.1f}%)")

# 2) 分位数边界分档
qs = sorted(rps)
def q(p): return qs[int(p * (len(qs) - 1))]
edges = [q(0), q(0.2), q(0.4), q(0.6), q(0.8), q(1.0)]
print("\n分位边界:", [round(e, 2) for e in edges])

# 3) 五档统计
res = {"n": n, "edges": [round(e, 2) for e in edges], "bands": []}
for i in range(5):
    lo, hi = edges[i], edges[i + 1]
    sel = [r for r in rows if lo <= f(r["risk_pct"]) <= hi] if i == 4 else \
          [r for r in rows if lo <= f(r["risk_pct"]) < hi]
    if not sel: continue
    wins = [r for r in sel if f(r["net_pnl_pct"]) >= 0]
    band = {
        "band": f"{lo:.1f}-{hi:.1f}%", "n": len(sel),
        "win_rate": round(len(wins) / len(sel) * 100, 1),
        "avg_ret": round(statistics.mean(f(r["net_pnl_pct"]) for r in sel), 2),
        "avg_win": round(statistics.mean(f(r["net_pnl_pct"]) for r in wins), 2) if wins else None,
        "avg_loss": round(statistics.mean(f(r["net_pnl_pct"]) for r in sel if f(r["net_pnl_pct"]) < 0), 2) if len(sel) > len(wins) else None,
    }
    res["bands"].append(band)
    print(f"档 {band['band']:>14} n={band['n']:4d} WR={band['win_rate']:5.1f}% avg={band['avg_ret']:6.2f}% win+{band['avg_win']} loss{band['avg_loss']}")

# 4) risk_pct==20 这一坨是否是 exact 常量 (fallback 特征: 大量完全相同)
exact20 = sum(1 for v in rps if v == 20.0)
res["risk_pct_eq_20_count"] = exact20
res["risk_pct_eq_20_share"] = round(exact20 / n * 100, 1)
print(f"\nrisk_pct 精确=20.0 的数量: {exact20} ({exact20/n*100:.1f}%)")

out = os.path.join(RESEARCH, "handover", "r26_riskpct_bands.json")
json.dump(res, open(out, "w", encoding="utf-8"), ensure_ascii=False, indent=2)
print("写出:", out)
