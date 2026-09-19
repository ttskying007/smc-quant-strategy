# -*- coding: utf-8 -*-
"""R27: E3 影子 A/B — 反事实剔除 risk_pct<阈值 的历史腿 (READ-ONLY)
不改生产。仅回答: 如果历史上我们拒绝 risk_pct<X% 的腿, 整体指标如何变化?
基线(frozen 2026-09-16): n=1527 avg=+3.77% PF=3.63
"""
import io, sys, os, json, csv, statistics
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

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
    pf = (sum(wins) / abs(sum(losses))) if losses and sum(losses) != 0 else None
    return {"n": len(rs), "avg": round(statistics.mean(rets), 2),
            "wr": round(len(wins)/len(rs)*100, 1),
            "pf": round(pf, 2) if pf else None,
            "total": round(sum(rets), 1)}

base = stats(rows)
print(f"基线 n={base['n']} avg={base['avg']}% WR={base['wr']}% PF={base['pf']} 合计={base['total']}%")

out = {"baseline": base, "scenarios": []}
for th in (2.0, 3.0, 4.0, 5.0, 6.0):
    kept = [r for r in rows if f(r["risk_pct"]) >= th]
    cut = [r for r in rows if f(r["risk_pct"]) < th]
    s_keep = stats(kept); s_cut = stats(cut)
    sc = {"min_risk_pct": th, "kept": s_keep, "removed": s_cut,
          "delta_avg_vs_base": round(s_keep["avg"] - base["avg"], 2) if s_keep else None}
    out["scenarios"].append(sc)
    print(f"门槛>={th}%: 保留 n={s_keep['n']} avg={s_keep['avg']}%({sc['delta_avg_vs_base']:+.2f}) PF={s_keep['pf']} | "
          f"剔除 n={s_cut['n']} avg={s_cut['avg']}% PF={s_cut['pf']}")

json.dump(out, open(os.path.join(RESEARCH, "handover", "r27_e3_shadow_ab.json"), "w", encoding="utf-8"),
          ensure_ascii=False, indent=2)
print("写出 handover/r27_e3_shadow_ab.json")
