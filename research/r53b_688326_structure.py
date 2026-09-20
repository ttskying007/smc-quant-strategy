# -*- coding: utf-8 -*-
"""R53b: 688326.SH canonical BOS/CHoCH 重算 (标准算法: 跟踪最近确认摆动高/低, 收盘穿越判定)
规则出处: KB internal_and_external_bos_and_choch —
  External BOS: 破趋势方向摆动点=延续; External CHoCH: 破逆趋势摆动点=反转预警
"""
import sys, os, io, json
sys.path.insert(0, r"E:\test\smc_project\research")
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")
import paper_sim as ps

CODE = "688326"
bs = ps.bars_of(CODE)
PIVOT = 3
N = len(bs)

# 1) 收集全部已确认摆动点 (j+PIVOT<=确认bar)
piv_h = {}  # confirm_idx -> (pivot_idx, price)
piv_l = {}
for j in range(PIVOT, N - PIVOT):
    ci = j + PIVOT
    if ps.is_swing_high(bs, j): piv_h[ci] = (j, bs[j]["h"])
    if ps.is_swing_low(bs, j):  piv_l[ci] = (j, bs[j]["l"])

# 2) 逐bar扫描: 收盘穿越"最近确认的摆动高/低"
events = []
trend = None
last_h = None  # (price, pivot_t)
last_l = None
for k in range(PIVOT, N):
    c = bs[k]["c"]; t = bs[k]["t"]
    if k in piv_h: last_h = (piv_h[k][1], bs[piv_h[k][0]]["t"])
    if k in piv_l: last_l = (piv_l[k][1], bs[piv_l[k][0]]["t"])
    if last_h and c > last_h[0]:
        kind = "BOS↑" if trend == "up" else ("CHoCH↑" if trend == "down" else "INIT↑")
        events.append((t, kind, f"收{c:.2f} 破摆动高 {last_h[0]:.2f}({last_h[1]})"))
        trend = "up"; last_h = None
    elif last_l and c < last_l[0]:
        kind = "BOS↓" if trend == "down" else ("CHoCH↓" if trend == "up" else "INIT↓")
        events.append((t, kind, f"收{c:.2f} 破摆动低 {last_l[0]:.2f}({last_l[1]})"))
        trend = "down"; last_l = None

print(f"{CODE} 结构事件总数: {len(events)}  当前趋势: {trend}")
print("\n2026 年以来的结构事件:")
for t, k, d in events:
    if t >= "20260101":
        print(f"  {t}  {k:<7} {d}")

# 3) 当前位置 vs 最近结构: 价格在哪个 POI 区?
i = N - 1
c = bs[i]["c"]
# premium/discount: 用最近一段摆动区间 (近90日)
w = bs[i-90:i]
rng_hi = max(b["h"] for b in w); rng_lo = min(b["l"] for b in w)
eq = (rng_hi + rng_lo) / 2
zone = "premium(高价区)" if c > eq * 1.02 else ("discount(低价区)" if c < eq * 0.98 else "equilibrium(均衡)")
print(f"\n90日区间 {rng_lo:.2f}-{rng_hi:.2f}  EQ={eq:.2f}  现价 {c} → {zone}")
# 最近的有效 FVG
fvg_up = [(bs[k-2]["t"], round(bs[k-2]["h"],2), round(bs[k]["l"],2)) for k in range(max(2,i-60), i+1) if bs[k]["l"] > bs[k-2]["h"]]
fvg_dn = [(bs[k-2]["t"], round(bs[k]["h"],2), round(bs[k-2]["l"],2)) for k in range(max(2,i-60), i+1) if bs[k]["h"] < bs[k-2]["l"]]
print(f"60日内 bullish FVG: {fvg_up[-4:]}")
print(f"60日内 bearish FVG: {fvg_dn[-4:]}")
out = {"code": CODE, "n_events": len(events), "trend_now": trend,
       "events_2026": [e for e in events if e[0] >= "20260101"],
       "range90": [rng_lo, rng_hi], "eq": eq, "close": c, "zone": zone}
json.dump(out, open(r"E:\test\smc_project\research\handover\r53_688326_structure.json", "w", encoding="utf-8"), ensure_ascii=False, indent=2)
print("\n写出 handover/r53_688326_structure.json")
