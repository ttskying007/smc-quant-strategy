# -*- coding: utf-8 -*-
"""R30: E3 翻转段解剖 — 窄SL腿在 202502-04 / 202603-06 发生了什么?
若窄SL弱势是特定市况(regime)驱动, 则"自适应gate"比固定gate更优。
READ-ONLY。输出 research/handover/r30_e3_flip_segments.json
"""
import csv, os, sys, json, statistics
sys.stdout.reconfigure(encoding="utf-8", errors="replace")
from collections import Counter, defaultdict

HERE = os.path.dirname(os.path.abspath(__file__))
rows = []
for r in csv.DictReader(open(os.path.join(HERE, "combo_v20f_trades.csv"), encoding="utf-8-sig")):
    if not (r.get("buy_price") or "").strip():
        continue
    try:
        r["_pnl"] = float(r["net_pnl_pct"]); r["_rp"] = float(r["risk_pct"]); r["_rank"] = float(r["rank"])
    except Exception:
        continue
    r["_ym"] = (r.get("entry_date") or "")[:6]
    rows.append(r)

def stats(rs):
    if not rs: return None
    pn = [r["_pnl"] for r in rs]
    w = [x for x in pn if x > 0]
    l = [x for x in pn if x <= 0]
    pf = sum(w) / abs(sum(l)) if l and sum(l) else 99.0
    return {"n": len(pn), "avg": round(sum(pn)/len(pn), 2), "wr": round(len(w)/len(pn)*100, 1), "pf": round(pf, 2)}

FLIPS = ["202502", "202503", "202504", "202603", "202604", "202605", "202606"]
# OOS windows were 202502~202504 and 202603~202605(3mo) — use exact oos months
W1 = ["202502", "202503", "202504"]
W2 = ["202603", "202604", "202605"]

def seg(months):
    sel = [r for r in rows if r["_ym"] in months]
    narrow = [r for r in sel if r["_rp"] < 4.0]
    wide = [r for r in sel if r["_rp"] >= 4.0]
    return sel, narrow, wide

out = {}
for name, months in (("flip_202502_04", W1), ("flip_202603_05", W2)):
    sel, nar, wid = seg(months)
    rec = {"all": stats(sel), "narrow_lt4": stats(nar), "wide_ge4": stats(wid),
           "narrow_rank_dist": {str(k): v for k, v in sorted(Counter(int(r['_rank']) for r in nar).items())},
           "narrow_reason_dist": dict(Counter(r.get("reason", "?") for r in nar))}
    out[name] = rec
    print(f"== {name} ==")
    print(f"  全段: {rec['all']}")
    print(f"  窄SL(<4%): {rec['narrow_lt4']}  rank分布 {rec['narrow_rank_dist']}")
    print(f"  宽SL(>=4%): {rec['wide_ge4']}")
    print(f"  窄腿退出原因: {dict(list(rec['narrow_reason_dist'].items())[:6])}")

# 对照: 其余月份窄SL表现 (非翻转段)
other_narrow = [r for r in rows if r["_rp"] < 4.0 and r["_ym"] not in W1 + W2]
print(f"\n其余月份窄SL(<4%): {stats(other_narrow)}")
out["narrow_other_months"] = stats(other_narrow)

# 窄腿 hold_bars 特征(是否快速被扫)
h = [float(r["hold_bars"]) for r in rows if r["_rp"] < 4.0 and r["_ym"] in W1 + W2 and (r.get("hold_bars") or "").strip()]
if h:
    h.sort()
    out["flip_narrow_holdbars"] = {"n": len(h), "median": h[len(h)//2], "mean": round(sum(h)/len(h), 1)}
    print(f"翻转段窄腿 hold_bars: n={len(h)} median={h[len(h)//2]} mean={sum(h)/len(h):.1f}")

json.dump(out, open(os.path.join(HERE, "handover", "r30_e3_flip_segments.json"), "w", encoding="utf-8"),
          ensure_ascii=False, indent=2)
print("\n写出 handover/r30_e3_flip_segments.json")
