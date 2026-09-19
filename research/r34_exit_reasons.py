# -*- coding: utf-8 -*-
"""R34: 退出原因分解 — 交易质量差的出口侧证据 (READ-ONLY)
问题: reason(SL_HIT/SL_GAP/BE/TP1/TP2_RUNNER/TIME_STOP/...) 分布×贡献度×年份漂移
回答: 亏损主要来自哪个退出通道? 该通道是否随年份稳定?
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
        r["_pnl"] = float(r["net_pnl_pct"]); r["_y"] = (r.get("buy_date") or "")[:4]
        r["_hold"] = float(r["hold_bars"]) if r.get("hold_bars") else None
    except Exception:
        continue
    rows.append(r)

def agg(rs):
    if not rs: return None
    pn = [r["_pnl"] for r in rs]
    w = [x for x in pn if x > 0]; l = [x for x in pn if x <= 0]
    return {"n": len(rs), "sum_pnl": round(sum(pn), 1),
            "avg": round(sum(pn)/len(pn), 2),
            "wr": round(len(w)/len(rs)*100, 1),
            "avg_hold": round(statistics.mean(r["_hold"] for r in rs if r["_hold"]) ,1) if any(r["_hold"] for r in rs) else None}

by_reason = defaultdict(list)
for r in rows:
    by_reason[r.get("reason") or "UNK"].append(r)

total_pnl = sum(r["_pnl"] for r in rows)
print(f"n={len(rows)} 总pnl={total_pnl:.1f}%")
print(f"{'reason':<18}{'n':>5}{'占比':>7}{'sum_pnl':>9}{'贡献%':>8}{'avg':>8}{'WR':>6}{'hold':>6}")
table = []
for reason, rs in sorted(by_reason.items(), key=lambda kv: -abs(sum(x['_pnl'] for x in kv[1]))):
    s = agg(rs)
    sp = sum(x["_pnl"] for x in rs)
    contrib = sp / total_pnl * 100
    table.append({"reason": reason, **s, "pnl_contrib_pct": round(contrib, 1)})
    print(f"{reason:<18}{s['n']:>5}{s['n']/len(rows)*100:>6.1f}%{sp:>+9.1f}{contrib:>+7.1f}%{s['avg']:>+7.2f}{s['wr']:>5.1f}{str(s['avg_hold']):>6}")

# 年份漂移: 每个退出原因在 2024→2026 的 sum_pnl 贡献
print("\n== 退出原因 × 年份 (sum_pnl) ==")
drift = {}
for reason, rs in by_reason.items():
    per_y = {}
    for y in ("2023", "2024", "2025", "2026"):
        ys = [r for r in rs if r["_y"] == y]
        if ys: per_y[y] = round(sum(r["_pnl"] for r in ys), 1)
    drift[reason] = per_y
    print(f"  {reason:<16} {per_y}")

out = {"n": len(rows), "total_pnl": round(total_pnl, 1), "by_reason": table, "reason_yearly_drift": drift}
json.dump(out, open(os.path.join(HERE, "handover", "r34_exit_reason_decomp.json"), "w", encoding="utf-8"),
          ensure_ascii=False, indent=2)
print("\n写出 handover/r34_exit_reason_decomp.json")
