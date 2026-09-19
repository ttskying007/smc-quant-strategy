# -*- coding: utf-8 -*-
"""R38(本轮): 分板块绩效拆解 (READ-ONLY)
沪主板60xxxx/深主板00xxxx=10%涨跌幅; 创业板30xxxx/科创板68xxxx=20%; 北交所8/4=30%。
SL/TP 的 ATR 语义在不同涨跌停制度下可能不等效 — 检查是否某板块系统性拖累。
"""
import csv, os, sys, json, statistics
sys.stdout.reconfigure(encoding="utf-8", errors="replace")
from collections import defaultdict

HERE = os.path.dirname(os.path.abspath(__file__))
rows = []
for r in csv.DictReader(open(os.path.join(HERE, "combo_v20f_trades.csv"), encoding="utf-8-sig")):
    if not (r.get("buy_price") or "").strip(): continue
    try:
        r["_pnl"] = float(r["net_pnl_pct"]); r["_rp"] = float(r["risk_pct"]); r["_rank"] = float(r["rank"])
    except Exception: continue
    sym = (r.get("\ufeffsymbol") or r.get("symbol") or "").strip()
    pre = sym[:2]
    r["_board"] = ("沪市主板" if sym.startswith("60") else
                  "深市主板" if sym.startswith(("000", "001", "002", "003")) else
                  "创业板" if sym.startswith("30") else
                  "科创板" if sym.startswith("68") else
                  "北交所" if sym[:1] in "48" else "其他")
    rows.append(r)

def stats(rs):
    if len(rs) < 5: return None
    pn = [r["_pnl"] for r in rs]
    w = [x for x in pn if x > 0]; l = [x for x in pn if x <= 0]
    pf = sum(w)/abs(sum(l)) if l and sum(l) else 99.0
    return {"n": len(rs), "avg": round(sum(pn)/len(rs), 2), "wr": round(len(w)/len(rs)*100, 1),
            "pf": round(pf, 2),
            "avg_risk": round(statistics.mean(r["_rp"] for r in rs), 1),
            "avg_rank": round(statistics.mean(r["_rank"] for r in rs), 2)}

by = defaultdict(list)
for r in rows: by[r["_board"]].append(r)

out = {"n": len(rows), "boards": {}}
print(f"{'板块':<10}{'n':>6}{'avg':>8}{'WR':>7}{'PF':>6}{'avgRisk':>9}{'avgRank':>9}")
for b, rs in sorted(by.items(), key=lambda kv: -len(kv[1])):
    s = stats(rs)
    out["boards"][b] = s
    if s:
        print(f"{b:<10}{s['n']:>6}{s['avg']:>+7.2f}{s['wr']:>6.1f}{s['pf']:>6.2f}{s['avg_risk']:>8.1f}%{s['avg_rank']:>8.2f}")

# 年份×板块 最简判定: 20%板(创业+科创)是否逐年弱于10%板
hivol = ["创业板", "科创板"]
yr_out = {}
for y in ("2024", "2025", "2026"):
    a = [r for r in rows if r["_board"] in hivol and (r.get("buy_date") or "")[:4] == y]
    b2 = [r for r in rows if r["_board"] not in hivol and r["_board"] != "其他" and (r.get("buy_date") or "")[:4] == y]
    sa, sb = stats(a), stats(b2)
    yr_out[y] = {"hivol(20%)": sa, "main(10%)": sb,
                 "delta": round(sa["avg"] - sb["avg"], 2) if sa and sb else None}
    print(f"{y}: 20%板 {sa['avg'] if sa else '-'} vs 10%板 {sb['avg'] if sb else '-'}  Δ={yr_out[y]['delta']}")
out["yearly_20vs10"] = yr_out

json.dump(out, open(os.path.join(HERE, "handover", "r38_board_decomp.json"), "w", encoding="utf-8"),
          ensure_ascii=False, indent=2)
print("写出 handover/r38_board_decomp.json")
