# -*- coding: utf-8 -*-
"""R54: E4 影子A/B 第1步 — 结构趋势过滤器在 1527 腿上的因果回放
口径:
  - 每腿 signal_i = entry_date 前一交易日 (gen_v20f: entry_idx=i+1)
  - 趋势状态 = r53b 检测器在 signal_i 收盘时的状态 (只用 <=signal_i 的已确认事件, 无前视)
  - 分组: trend=up / CHoCH↑窗口(5/10bar) / down
  - READ-ONLY: 不改基线, 只统计 — E4 采纳仍需 frozen OOS (预注册纪律)
"""
import csv, os, sys, io, json, datetime
sys.path.insert(0, r"E:\test\smc_project\research")
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")
import paper_sim as ps

HERE = r"E:\test\smc_project\research"
PIVOT = 3
_bars_cache = {}
_piv_cache = {}

def get_bars(sym6):
    if sym6 not in _bars_cache:
        _bars_cache[sym6] = ps.bars_of(sym6)
    return _bars_cache[sym6]

def trend_state_at(bs, sig_i):
    """因果趋势状态: 扫描至 sig_i, 返回 (trend, last_choch_up_gap, last_event_kind)"""
    N = len(bs)
    piv_h = {}; piv_l = {}
    for j in range(PIVOT, N - PIVOT):
        ci = j + PIVOT
        if ps.is_swing_high(bs, j): piv_h.setdefault(ci, []).append((j, bs[j]["h"]))
        if ps.is_swing_low(bs, j):  piv_l.setdefault(ci, []).append((j, bs[j]["l"]))
    trend = None; last_choch_up = None; last_kind = None
    last_h = None; last_l = None
    for k in range(PIVOT, min(sig_i, N - 1) + 1):
        c = bs[k]["c"]
        if k in piv_h:
            if last_h is None or piv_h[k][-1][1] != last_h[0]: last_h = (piv_h[k][-1][1], bs[piv_h[k][-1][0]]["t"])
        if k in piv_l:
            if last_l is None or piv_l[k][-1][1] != last_l[0]: last_l = (piv_l[k][-1][1], bs[piv_l[k][-1][0]]["t"])
        if last_h and c > last_h[0]:
            if trend == "down":
                last_choch_up = k; last_kind = "CHoCH↑"
            else:
                last_kind = "BOS↑"
            trend = "up"; last_h = None
        elif last_l and c < last_l[0]:
            last_kind = "BOS↓" if trend == "down" else "CHoCH↓"
            trend = "down"; last_l = None
    return trend, last_choch_up, last_kind

rows = []
for r in csv.DictReader(open(os.path.join(HERE, "combo_v20f_trades.csv"), encoding="utf-8-sig")):
    if not (r.get("buy_price") or "").strip(): continue
    rows.append(r)
print(f"canonical legs: {len(rows)}")

res = []
miss = 0
for r in rows:
    sym = (r.get("\ufeffsymbol") or r.get("symbol") or "")
    sym6 = sym[:6]
    ed = r.get("entry_date", "")
    pnl = float(r["net_pnl_pct"])
    bs = get_bars(sym6)
    if not bs: miss += 1; continue
    dates = [b["t"] for b in bs]
    if ed not in dates: miss += 1; continue
    idx = dates.index(ed)
    sig_i = idx - 1
    if sig_i < 95: miss += 1; continue
    trend, choch_up_k, last_kind = trend_state_at(bs, sig_i)
    res.append({"sym": sym6, "ed": ed, "pnl": pnl,
                "trend": trend, "choch_up_gap": (sig_i - choch_up_k) if choch_up_k is not None else None,
                "last_kind": last_kind})

print(f"有效回放: {len(res)}  无数据/过短: {miss}")

def st(rs):
    if not rs: return {"n": 0}
    pn = [x["pnl"] for x in rs]
    w = [x for x in pn if x > 0]; l = [x for x in pn if x <= 0]
    pf = round(sum(w)/abs(sum(l)), 2) if l and sum(l) else 99.0
    return {"n": len(rs), "avg": round(sum(pn)/len(pn), 2),
            "wr": round(len(w)/len(rs)*100, 1), "pf": pf}

out = {"n_total": len(res)}
up = [x for x in res if x["trend"] == "up"]
dn = [x for x in res if x["trend"] == "down"]
out["trend_up"] = st(up)
out["trend_down"] = st(dn)
for K in (5, 10, 20):
    rev = [x for x in res if x["trend"] == "up" or (x["choch_up_gap"] is not None and x["choch_up_gap"] <= K)]
    out[f"up_or_choch{K}"] = st(rev)
# 逐年
for y in ("2023", "2024", "2025", "2026"):
    out[f"up_{y}"] = st([x for x in up if x["ed"][:4] == y])
    out[f"dn_{y}"] = st([x for x in dn if x["ed"][:4] == y])

print(f"\n{'分组':<18}{'n':>6}{'avg':>8}{'WR':>7}{'PF':>7}")
for k in ("trend_up", "trend_down", "up_or_choch5", "up_or_choch10", "up_or_choch20"):
    s = out[k]
    if s.get("n"):
        print(f"{k:<18}{s['n']:>6}{s['avg']:>+7.2f}{s['wr']:>6.1f}{s['pf']:>7.2f}")
print("\n逐年 (up vs down avg):")
for y in ("2023", "2024", "2025", "2026"):
    su, sd = out[f"up_{y}"], out[f"dn_{y}"]
    if su.get("n") and sd.get("n"):
        print(f"  {y}: up {su['n']:>4}腿 {su['avg']:>+6.2f}  vs  down {sd['n']:>4}腿 {sd['avg']:>+6.2f}  Δ={su['avg']-sd['avg']:>+.2f}")

json.dump(out, open(os.path.join(HERE, "handover", "r54_e4_trend_shadow.json"), "w", encoding="utf-8"),
          ensure_ascii=False, indent=2)
print("\n写出 handover/r54_e4_trend_shadow.json")
