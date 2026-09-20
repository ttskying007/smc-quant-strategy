# -*- coding: utf-8 -*-
"""R55: SL 结构语义一致性审计 — 环节5闭环 (R53 病例审计的最后一环)
问题: 生产 SL(swing低−0.5ATR) 是否落在"最近被跌破的结构位"(最后BOS↓/CHoCH↓的摆动低)下方?
  - sl1 < broken_low → SL 在结构无效位之下 ✓ (语义: 跌破该位才承认反转失败)
  - sl1 >= broken_low → SL 停在已破位区间内 = 结构暴露(止损放在"无人区")
只做一致性测量, 不做 edge 声明。
"""
import csv, os, sys, io, json
sys.path.insert(0, r"E:\test\smc_project\research")
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")
import paper_sim as ps

HERE = r"E:\test\smc_project\research"
PIVOT = 3

def last_broken_low(bs, sig_i):
    """信号日时点: 最近一次收盘跌破摆动低的事件位 (BOS↓/CHoCH↓/INIT↓), 返回 (level, gap_days) or None"""
    N = len(bs)
    piv_l = {}
    for j in range(PIVOT, N - PIVOT):
        ci = j + PIVOT
        if ps.is_swing_low(bs, j): piv_l.setdefault(ci, bs[j]["l"])
    last_l = None
    broken = None  # (level, k)
    for k in range(PIVOT, min(sig_i, N - 1) + 1):
        c = bs[k]["c"]
        if k in piv_l and (last_l is None or piv_l[k] != last_l):
            last_l = piv_l[k]
        if last_l and c < last_l:
            broken = (last_l, k)  # 记录最近一次破位
            last_l = None
    return broken

rows = []
for r in csv.DictReader(open(os.path.join(HERE, "combo_v20f_trades.csv"), encoding="utf-8-sig")):
    if not (r.get("buy_price") or "").strip(): continue
    rows.append(r)

ok_below = []; exposed = []; no_break = []; miss = 0
for r in rows:
    sym = (r.get("\ufeffsymbol") or r.get("symbol") or "")[:6]
    ed = r.get("entry_date", "")
    try:
        bp = float(r["buy_price"]); sl = float(r["sl"]); pnl = float(r["net_pnl_pct"])
    except Exception:
        miss += 1; continue
    bs = ps.bars_of(sym)
    if not bs: miss += 1; continue
    dates = [b["t"] for b in bs]
    if ed not in dates: miss += 1; continue
    sig_i = dates.index(ed) - 1
    if sig_i < 30: miss += 1; continue
    br = last_broken_low(bs, sig_i)
    if br is None:
        no_break.append({"pnl": pnl, "sl_dist": (bp - sl) / bp * 100})
        continue
    level, k = br
    rec = {"pnl": pnl, "broken_level": level, "broken_gap": sig_i - k,
           "sl_dist": (bp - sl) / bp * 100}
    if sl < level:
        ok_below.append(rec)
    else:
        exposed.append(rec)

def st(rs):
    if not rs: return {"n": 0}
    pn = [x["pnl"] for x in rs]
    w = [x for x in pn if x > 0]; l = [x for x in pn if x <= 0]
    return {"n": len(rs), "avg": round(sum(pn)/len(pn), 2),
            "wr": round(len(w)/len(rs)*100, 1),
            "pf": round(sum(w)/abs(sum(l)), 2) if l and sum(l) else 99.0,
            "avg_sl_dist": round(sum(x["sl_dist"] for x in rs)/len(rs), 1)}

out = {"n_checked": len(rows) - miss, "no_broken_low": st(no_break),
       "sl_below_structure": st(ok_below), "sl_exposed_in_broken_zone": st(exposed)}
print(f"检查 {len(rows)-miss} 腿 (跳过 {miss})")
for k in ("sl_below_structure", "sl_exposed_in_broken_zone", "no_broken_low"):
    print(f"  {k}: {out[k]}")
if ok_below and exposed:
    print(f"\n暴露占比: {len(exposed)/(len(ok_below)+len(exposed))*100:.1f}% (有破位历史的腿中)")

json.dump(out, open(os.path.join(HERE, "handover", "r55_sl_semantics_audit.json"), "w", encoding="utf-8"),
          ensure_ascii=False, indent=2)
print("写出 handover/r55_sl_semantics_audit.json")
