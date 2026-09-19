# -*- coding: utf-8 -*-
"""R39: 板块内 stratify risk_pct — 验证'宽SL优势'是否纯属板块构成效应
若同板块内 SL 宽度不再单调 -> R26 现象确认为 Simpson's paradox (构成效应)。
"""
import csv, os, sys, json, statistics
sys.stdout.reconfigure(encoding="utf-8", errors="replace")
from collections import defaultdict

HERE = os.path.dirname(os.path.abspath(__file__))
rows = []
for r in csv.DictReader(open(os.path.join(HERE, "combo_v20f_trades.csv"), encoding="utf-8-sig")):
    if not (r.get("buy_price") or "").strip(): continue
    try:
        r["_pnl"] = float(r["net_pnl_pct"]); r["_rp"] = float(r["risk_pct"])
    except Exception: continue
    sym = (r.get("\ufeffsymbol") or r.get("symbol") or "")
    r["_board"] = ("CY" if sym.startswith("30") else "KC" if sym.startswith("68")
                   else "SZ" if sym.startswith(("000","001","002","003")) else
                   "SH" if sym.startswith("60") else "OT")
    rows.append(r)

def st(rs):
    if len(rs) < 8: return None
    pn = [r["_pnl"] for r in rs]
    w = sum(1 for x in pn if x > 0)
    return {"n": len(rs), "avg": round(sum(pn)/len(pn), 2), "wr": round(w/len(rs)*100, 1)}

BANDS = [(0, 5), (5, 10), (10, 16), (16, 24), (24, 100)]
out = {}
print(f"{'board':<5}" + "".join(f"{f'{a}-{b}%':>14}" for a, b in BANDS))
simpson_evidence = {}
for bd in ("CY", "KC", "SZ", "SH"):
    sel = [r for r in rows if r["_board"] == bd]
    cells = []
    per_band = {}
    for a, b in BANDS:
        s = st([r for r in sel if a <= r["_rp"] < b])
        per_band[f"{a}-{b}"] = s
        cells.append(f"{s['avg']:>+6.2f}/{s['wr']:>4.0f}/{s['n']:>3d}" if s else "      -      ")
    out[bd] = per_band
    print(f"{bd:<5}" + "".join(f"{c:>14}" for c in cells))
    # 板块内单调性粗判
    avgs = [per_band[f"{a}-{b}"]["avg"] for a, b in BANDS if per_band[f"{a}-{b}"]]
    if len(avgs) >= 3:
        simpson_evidence[bd] = {"avgs_by_band": avgs,
                                "monotone_up": all(avgs[i] <= avgs[i+1] for i in range(len(avgs)-1))}

out["interpretation"] = simpson_evidence
print("\n板块内沿 SL 宽度的 avg 序列:")
for bd, ev in simpson_evidence.items():
    print(f"  {bd}: {ev['avgs_by_band']} 单调升={ev['monotone_up']}")

json.dump(out, open(os.path.join(HERE, "handover", "r39_board_stratified_sl.json"), "w", encoding="utf-8"),
          ensure_ascii=False, indent=2)
print("写出 handover/r39_board_stratified_sl.json")
