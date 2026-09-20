# -*- coding: utf-8 -*-
"""R53: 688326.SH SMC 推理链逐环追踪 — 生产代码实际执行 vs SMC 标准序列
用户序列: 趋势判定(延续/回调/反转) → BOS/CHoCH → POI(OB/FVG)位置/时间/范围 → 距离 → SL/TP
"""
import sys, os, io, sqlite3, json
sys.path.insert(0, r"E:\test\smc_project\research")
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")
import paper_sim as ps

CODE = "688326.SH"
code6 = "688326"
bs = ps.bars_of(code6)
print(f"bars: {len(bs)}  range {bs[0]['t']} → {bs[-1]['t']}")
i_last = len(bs) - 1

# ---- 环节1: 趋势/阶段判定 (生产实际) ----
st, deep = ps.stage_and_deep(bs, i_last)
adx = ps.adx14_of(bs, i_last)
w60 = bs[i_last-60:i_last]; w90 = bs[i_last-90:i_last]
ret60 = w60[-1]["c"]/w60[0]["c"]-1; ret90 = w90[-1]["c"]/w90[0]["c"]-1
v20 = sum(b["v"] for b in bs[i_last-20:i_last])/20
v60 = sum(b["v"] for b in w60)/60
print(f"\n[环节1 趋势判定] stage_and_deep → {st} deep={deep}  ADX={adx:.1f}  ret60={ret60*100:.1f}% ret90={ret90*100:.1f}% v20/v60={v20/v60:.2f}")
print("  ⚠ 生产用的判据是 60日收益率+量比分档 — 无任何 BOS/CHoCH/摆动结构输入")

# ---- 环节2: BOS/CHoCH (生产: 不存在; 此处现场计算 canonical 版本) ----
PIVOT = 3
def swings(bs, lo, hi):
    highs, lows = [], []
    for j in range(lo, hi):
        if j < PIVOT or j + PIVOT >= len(bs): continue
        if ps.is_swing_high(bs, j): highs.append((bs[j]["t"], bs[j]["h"]))
        if ps.is_swing_low(bs, j): lows.append((bs[j]["t"], bs[j]["l"]))
    return highs, lows

lo = max(90, i_last - 120)
highs, lows = swings(bs, lo, i_last)
# 用最近摆动点做简单结构事件检测
events = []
last_high = None; last_low = None; trend = None
hi_q = list(highs); lo_q = list(lows)
all_piv = sorted([(t, h, "H") for t, h in highs] + [(t, l, "L") for t, l in lows])
cur_trend = None
choch = None
for k in range(len(all_piv)):
    t, px, kind = all_piv[k]
    # 确认时间 = pivot 后 PIVOT 根
    ci = [b["t"] for b in bs].index(t) + PIVOT
    if ci >= len(bs): continue
    c = bs[ci]["c"]
    if kind == "H":
        if cur_trend == "up" and c > px:
            events.append((bs[ci]["t"], "BOS↑", f"破前高 {px}"))
        elif cur_trend == "down" and c > px and choch != bs[ci]["t"]:
            events.append((bs[ci]["t"], "CHoCH↑", f"下升趋势中破摆动高 {px}"))
            choch = bs[ci]["t"]
        if cur_trend is None: cur_trend = "up"
    else:
        if cur_trend == "down" and c < px:
            events.append((bs[ci]["t"], "BOS↓", f"破前低 {px}"))
        elif cur_trend == "up" and c < px and choch != bs[ci]["t"]:
            events.append((bs[ci]["t"], "CHoCH↓", f"上升趋势中破摆动低 {px}"))
            choch = bs[ci]["t"]
        if cur_trend is None: cur_trend = "down"
    # 更新趋势
    recent = [e for e in events if e[0] == bs[ci]["t"]]
    if recent:
        k2 = recent[-1][1]
        if "↑" in k2: cur_trend = "up"
        else: cur_trend = "down"
print(f"\n[环节2 BOS/CHoCH] 生产链: 完全不存在此环节 (stage 用 ret/vol)")
print(f"  现场按 canonical 规则算出最近 5 个结构事件:")
for e in events[-5:]:
    print(f"   {e[0]}  {e[1]:<7} {e[2]}")

# ---- 环节3: POI (生产: swing+FVG 简化版) ----
d_last = bs[i_last]["t"]
tp1, tp2, tp3, tp4, sl1, sl2, note = ps.structural_sltp(code6, d_last, src='EVENT', stage=st, adx=adx or 0)
c_last = bs[i_last]["c"]
print(f"\n[环节3 POI] structural_sltp 锚点 (现价 {c_last}):")
print(f"  highs(>现价的前高): {[round(h,2) for _, h in highs][-6:]}")
print(f"  lows(最近摆动低):   {[round(l,2) for _, l in lows][-4:]}")
print(f"  tp1={tp1} tp2={tp2} tp3={tp3} tp4={tp4}")
print(f"  sl1={sl1} sl2={sl2}")
print(f"  note: {note}")
# FVG 现场统计 (20bar 内)
fvg_up = [(bs[k-2]["t"], round(bs[k-2]["h"],2), round(bs[k]["l"],2)) for k in range(max(2,i_last-20), i_last+1) if bs[k]["l"] > bs[k-2]["h"]]
fvg_dn = [(bs[k-2]["t"], round(bs[k]["h"],2), round(bs[k-2]["l"],2)) for k in range(max(2,i_last-20), i_last+1) if bs[k]["h"] < bs[k-2]["l"]]
print(f"  20bar内 bullish FVG: {fvg_up[-3:]}")
print(f"  20bar内 bearish FVG: {fvg_dn[-3:]}")
print("  ⚠ 无 Order Block 检测 / 无 IFVG / 无 premium-discount 分区 / 无 equal-highs 流动性")

# ---- 环节4: 距离/位置 ----
if tp1: print(f"\n[环节4 距离] 现价→tp1 {abs(c_last/tp1-1)*100:.1f}%  现价→sl1 {abs(sl1/c_last-1)*100:.1f}%  R:R≈{(tp1/c_last-1)/(1-sl1/c_last):.2f}" if sl1<c_last else "")
print(f"  入场方式: 0.99×signal收盘 限价回踩 or T+1开盘 — 与 POI 位置无关(固定1%折扣, 非结构位)")

# ---- 环节5: 事件腿存在性 ----
conn = sqlite3.connect(r"E:\test\smc_project\announce\smc_announce.db")
rows = conn.execute("SELECT date, title FROM announce WHERE stock_code LIKE ? ORDER BY date DESC LIMIT 5", (code6+"%",)).fetchall()
conn.close()
print(f"\n[环节5 事件源] {code6} 最近公告:")
for d, ti in rows: print(f"   {d} {ti[:50]}")
