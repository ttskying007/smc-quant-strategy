# -*- coding: utf-8 -*-
"""R31: rank 语义在 canonical v20f 基线上的复核 (READ-ONLY)
问题: "rank≥4 更好" 是否为历史口径残留? 分年份 × rank 档 看 avg/PF/WR 单调性。
若不再单调 -> gate 语义需重审 (不动生产, 只出证据)。
"""
import csv, os, sys, json, statistics
sys.stdout.reconfigure(encoding="utf-8", errors="replace")
from collections import defaultdict

HERE = os.path.dirname(os.path.abspath(__file__))
rows = []
for r in csv.DictReader(open(os.path.join(HERE, "combo_v20f_trades.csv"), encoding="utf-8-sig")):
    if not (r.get("buy_price") or "").strip():
        continue
    try:
        r["_pnl"] = float(r["net_pnl_pct"]); r["_rank"] = float(r["rank"]); r["_y"] = (r.get("buy_date") or "")[:4]
    except Exception:
        continue
    rows.append(r)

def stats(rs):
    if len(rs) < 5: return None
    pn = [r["_pnl"] for r in rs]
    w = [x for x in pn if x > 0]; l = [x for x in pn if x <= 0]
    pf = sum(w)/abs(sum(l)) if l and sum(l) else 99.0
    return {"n": len(rs), "avg": round(sum(pn)/len(pn), 2),
            "wr": round(len(w)/len(rs)*100, 1), "pf": round(pf, 2)}

out = {"n_total": len(rows), "by_rank": {}, "rank_by_year": {}}

print("== 全体 rank 档 ==")
for k in sorted(set(r["_rank"] for r in rows)):
    sel = [r for r in rows if r["_rank"] == k]
    s = stats(sel)
    if s:
        out["by_rank"][str(int(k))] = s
        print(f"  rank={int(k)}: n={s['n']:4d} avg={s['avg']:+.2f}% WR={s['wr']:.1f}% PF={s['pf']:.2f}")

print("\n== rank 档 × 年份 (avg% | PF) ==")
years = sorted(set(r["_y"] for r in rows))
header = "rank | " + " | ".join(years)
print(header)
mono_violations = 0
for k in sorted(set(r["_rank"] for r in rows)):
    cells = []
    for y in years:
        s = stats([r for r in rows if r["_rank"] == k and r["_y"] == y])
        cells.append(f"{s['avg']:+.2f}/{s['pf']:.2f}" if s else "  -  ")
        out["rank_by_year"].setdefault(str(int(k)), {})[y] = s
    print(f"  {int(k)}  | " + " | ".join(cells))

# 关键判定: 每年 rank>=4 是否优于 rank<4
print("\n== 年度判定: rank>=4 vs rank<4 ==")
verdicts = {}
for y in years:
    hi = stats([r for r in rows if r["_rank"] >= 4 and r["_y"] == y])
    lo = stats([r for r in rows if r["_rank"] < 4 and r["_y"] == y])
    if hi and lo:
        d = round(hi["avg"] - lo["avg"], 2)
        verdicts[y] = {"hi_avg": hi["avg"], "lo_avg": lo["avg"], "delta": d,
                       "hi_pf": hi["pf"], "lo_pf": lo["pf"], "hi_better": d > 0}
        print(f"  {y}: rank>=4 avg={hi['avg']:+.2f} PF={hi['pf']:.2f}  vs rank<4 avg={lo['avg']:+.2f} PF={lo['pf']:.2f}  Δ={d:+.2f} {'✓' if d>0 else '✗'}")
out["yearly_rank_premium"] = verdicts
pos = sum(1 for v in verdicts.values() if v["hi_better"])
out["rank_premium_consistency"] = f"{pos}/{len(verdicts)}"
print(f"\nrank溢价逐年一致: {pos}/{len(verdicts)}")

json.dump(out, open(os.path.join(HERE, "handover", "r31_rank_semantics_recheck.json"), "w", encoding="utf-8"),
          ensure_ascii=False, indent=2)
print("写出 handover/r31_rank_semantics_recheck.json")
