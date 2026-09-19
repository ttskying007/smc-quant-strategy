# -*- coding: utf-8 -*-
"""R28: E3 按年份切分稳健性 + rank 交互 (READ-ONLY)
1) 每年: 基线 vs risk_pct>=4% 过滤后的 avg/PF/n — 检查方向逐年是否一致
2) rank 交互: 窄SL剔除集合中 rank<=3 占比 — 检验与现有 gate 的重叠度
"""
import io, sys, os, json, csv, statistics
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
from collections import defaultdict

RESEARCH = os.path.dirname(os.path.abspath(__file__))
rows = [r for r in csv.DictReader(open(os.path.join(RESEARCH, "combo_v20f_trades.csv"), encoding="utf-8"))
        if (r.get("buy_price") or "").strip()]
def f(x, d=0.0):
    try: return float(x)
    except Exception: return d

def stats(rs):
    if not rs: return None
    rets = [f(r["net_pnl_pct"]) for r in rs]
    wins = [x for x in rets if x >= 0]; losses = [x for x in rets if x < 0]
    pf = sum(wins) / abs(sum(losses)) if losses and sum(losses) else None
    return {"n": len(rs), "avg": round(statistics.mean(rets), 2),
            "wr": round(len(wins) / len(rs) * 100, 1),
            "pf": round(pf, 2) if pf else None}

years = defaultdict(list)
for r in rows:
    y = (r.get("buy_date") or "")[:4]
    years[y].append(r)

print(f"{'年份':<6}{'基线n':>6}{'avg':>8}{'PF':>7} | {'过滤n':>6}{'avg':>8}{'PF':>7} | {'Δavg':>7} {'方向'}")
out = {"by_year": [], "rank_interaction": {}}
consistent = 0; total = 0
for y in sorted(years):
    base = stats(years[y])
    filt = stats([r for r in years[y] if f(r["risk_pct"]) >= 4.0])
    if not base or not filt: continue
    d = round(filt["avg"] - base["avg"], 2)
    ok = d > 0
    consistent += ok; total += 1
    out["by_year"].append({"year": y, "base": base, "filtered": filt, "delta_avg": d, "improved": ok})
    print(f"{y:<8}{base['n']:>5}{base['avg']:>8}{str(base['pf']):>7} | {filt['n']:>5}{filt['avg']:>8}{str(filt['pf']):>7} | {d:>+6.2f} {'✓' if ok else '✗'}")

out["yearly_consistency"] = f"{consistent}/{total}"
print(f"\n逐年方向一致: {consistent}/{total}")

# rank 交互
cut = [r for r in rows if f(r["risk_pct"]) < 4.0]
le3 = sum(1 for r in cut if f(r["rank"]) <= 3)
out["rank_interaction"] = {
    "removed_n": len(cut),
    "removed_rank_le3_n": le3,
    "removed_rank_le3_share": round(le3 / len(cut) * 100, 1) if cut else None,
    "overall_rank_le3_share": round(sum(1 for r in rows if f(r["rank"]) <= 3) / len(rows) * 100, 1),
}
print(f"剔除集(n={len(cut)})中 rank<=3 占 {out['rank_interaction']['removed_rank_le3_share']}% "
      f"(全体 rank<=3 占比 {out['rank_interaction']['overall_rank_le3_share']}%)")

# 关键: 剔除后, rank>=4 子集内风险
hi = [r for r in rows if f(r["rank"]) >= 4]
hi_f = [r for r in hi if f(r["risk_pct"]) >= 4.0]
print(f"rank>=4 子集: 基线 {stats(hi)} -> 过滤后 {stats(hi_f)}")
out["rank_ge4"] = {"base": stats(hi), "filtered": stats(hi_f),
                   "delta": round(stats(hi_f)["avg"] - stats(hi)["avg"], 2)}

json.dump(out, open(os.path.join(RESEARCH, "handover", "r28_e3_yearly_rank.json"), "w", encoding="utf-8"),
          ensure_ascii=False, indent=2)
print("写出 handover/r28_e3_yearly_rank.json")
