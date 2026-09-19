# -*- coding: utf-8 -*-
"""E3 frozen OOS 判定脚本 (v_minrisk_ab.py)
预注册: research/handover/preregister_E3_min_riskpct.md (2026-09-20)
判定标准(冻结): OOS 段合并 avg 提升 >= +0.4pp, PF 不下降, 翻转段占比 < 40%
方法: 沿用 walk_forward.py 的 12月IS→3月OOS 滚动; 每个 OOS 段对比
      base (全部腿) vs gated (risk_pct>=4.0%) 的 avg/PF。
只读 CSV。风险字段 risk_pct 为入场时已知量, 无前视。
"""
import csv, os, sys, json
from collections import defaultdict
sys.stdout.reconfigure(encoding="utf-8", errors="replace")

HERE = os.path.dirname(os.path.abspath(__file__))
CSV = os.path.join(HERE, "combo_v20f_trades.csv")
GATE = 4.0  # 预注册首选门槛, 冻结

def f(x):
    try: return float(x)
    except Exception: return None

rows = []
with open(CSV, encoding="utf-8-sig") as fh:
    for r in csv.DictReader(fh):
        pnl = f(r.get("net_pnl_pct"))
        rp = f(r.get("risk_pct"))
        if pnl is None or not r.get("entry_date"):
            continue
        if not (r.get("buy_price") or "").strip():  # 剔除 CONT 占位
            continue
        rows.append({"pnl": pnl, "rp": rp, "ym": r["entry_date"][:6]})
rows.sort(key=lambda r: r["ym"])
by_month = defaultdict(list)
for r in rows:
    by_month[r["ym"]].append(r)
months = sorted(by_month)

def stats(rs):
    if not rs: return None
    pn = [r["pnl"] for r in rs]
    w = [x for x in pn if x > 0]; l = [x for x in pn if x <= 0]
    pf = sum(w) / abs(sum(l)) if l and sum(l) else 99.0
    return {"n": len(pn), "avg": sum(pn) / len(pn), "pf": pf,
            "wr": len(w) / len(pn)}

IS, OOS, STEP = 12, 3, 3
segs = []
i = 0
while i + IS + OOS <= len(months):
    om = months[i + IS: i + IS + OOS]
    oos_rows = [r for m in om for r in by_month[m]]
    b = stats(oos_rows)
    g = stats([r for r in oos_rows if r["rp"] is not None and r["rp"] >= GATE])
    segs.append({"oos": f"{om[0]}~{om[-1]}", "base": b, "gated": g})
    i += STEP

print(f"窗口 {IS}m IS/{OOS}m OOS, OOS 段数={len(segs)}, gate=risk_pct>={GATE}%")
print(f"{'OOS段':<16}{'base n':>7}{'avg':>8}{'PF':>7} | {'gate n':>7}{'avg':>8}{'PF':>7} | {'Δavg':>7}")
flips = 0
for s in segs:
    b, g = s["base"], s["gated"]
    if not b or not g:
        print(f"{s['oos']:<16} (数据不足)"); continue
    d = g["avg"] - b["avg"]
    if d < 0: flips += 1
    print(f"{s['oos']:<16}{b['n']:>6}{b['avg']:>+8.2f}{b['pf']:>7.2f} | {g['n']:>6}{g['avg']:>+8.2f}{g['pf']:>7.2f} | {d:>+6.2f} {'✗翻转' if d < 0 else '✓'}")

# 全 OOS 合并
all_oos = [r for m_i in range(0, len(months) - IS - OOS + 1, STEP)
           for m in months[m_i + IS: m_i + IS + OOS] for r in by_month[m]]
b_all = stats(all_oos)
g_all = stats([r for r in all_oos if r["rp"] is not None and r["rp"] >= GATE])
d_avg = g_all["avg"] - b_all["avg"]
flip_ratio = flips / len([s for s in segs if s["base"] and s["gated"]]) if segs else 1

verdict = {
    "pass": bool(d_avg >= 0.4 and g_all["pf"] >= b_all["pf"] and flip_ratio < 0.40),
    "oos_base": b_all, "oos_gated": g_all, "delta_avg": round(d_avg, 3),
    "delta_pf": round(g_all["pf"] - b_all["pf"], 3),
    "flip_ratio": round(flip_ratio, 3),
    "criteria": {"delta_avg>=+0.4": d_avg >= 0.4,
                 "pf_not_worse": g_all["pf"] >= b_all["pf"],
                 "flip_ratio<0.40": flip_ratio < 0.40},
}
print("\n=== 冻结判定 ===")
print(f"全OOS: base n={b_all['n']} avg={b_all['avg']:+.2f}% PF={b_all['pf']:.2f}")
print(f"       gate n={g_all['n']} avg={g_all['avg']:+.2f}% PF={g_all['pf']:.2f}")
print(f"Δavg={d_avg:+.3f}pp (需>=+0.4)  ΔPF={verdict['delta_pf']:+.3f} 翻转段={flips}/{len(segs)} (需<40%)")
print(f"判定: {'✅ PASS — 可进入下一步(仍需生产A/B验证)' if verdict['pass'] else '❌ FAIL — 按预注册弃用'}")

json.dump({"segments": segs, "verdict": verdict},
          open(os.path.join(HERE, "handover", "e3_frozen_oos_result.json"), "w", encoding="utf-8"),
          ensure_ascii=False, indent=2)
print("写出 handover/e3_frozen_oos_result.json")
