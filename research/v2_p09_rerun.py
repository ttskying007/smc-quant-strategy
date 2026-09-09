# -*- coding: utf-8 -*-
"""P0-9 重跑(V2): SMC 骨架(Entry+B3退出) × 事件先验 边际贡献
上一轮 P0-9 用生产 wdh 种子(硬门槛) → 欠功效(交集4-16笔)。
本轮用新引擎 READY 链(无硬门槛, 897 笔) × 事件先验(announce 披露在结构链附近):
  A臂 = READY 全集(基线: Entry+B3)
  B臂 = READY∩EVENT(结构链期间 ±45 天内有该股真回购/增持披露)
  C臂 = READY∖EVENT(无事件先验)
若 B > C(OOS) → 事件先验对结构链有真实边际(蓝图 §12 Event=先验+SMC=确认 的组合逻辑成立)
方法: 全部用 core 模块(无前视), B3 退出(宽SL+时间15根), Entry Zone 撮合。
"""
import csv, glob, io, json, os, random, sqlite3, sys
from collections import defaultdict
from datetime import date as _d
sys.path.insert(0, r"E:\test\smc_project\research")
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

import core.liquidity as LQ
import core.displacement as DS
import core.mss as MSS
import core.fvg_ob as FO
import core.entry as EN
import core.risk as RK
import core.events as EV

KL = r"E:\test\smc_project\hermes\kline_cache_tencent"
OOS = "20250701"
FEE = 0.20
WINDOW_EVENT = 45  # 结构链±45天内的事件先验
files = sorted(glob.glob(KL + os.sep + "*_daily_800.json"))[::5][:800]

# 事件日期索引(code → [d8...]) —— 纯净分类器
conn = sqlite3.connect(r"E:\test\smc_project\announce\smc_announce.db")
cur = conn.cursor()
cur.execute("SELECT stock_code, date, title FROM announce WHERE title LIKE '%增持%' OR title LIKE '%回购%'")
ev_by_code = defaultdict(list)
for code, d, t in cur.fetchall():
    if EV.classify_title(t)[0]:
        ev_by_code[str(code)].append(str(d)[:10].replace("-", ""))
conn.close()
for c in ev_by_code:
    ev_by_code[c].sort()
ev_dates = {c: set(v) for c, v in ev_by_code.items()}

def has_event_near(code, d8, window=WINDOW_EVENT):
    """结构日 d8 前后 window 天内该股有真事件披露。"""
    e = _d(int(d8[:4]), int(d8[4:6]), int(d8[6:8]))
    for dd8 in ev_by_code.get(code, []):
        dd = _d(int(dd8[:4]), int(dd8[4:6]), int(dd8[6:8]))
        if abs((e - dd).days) <= window:
            return True
    return False

def sim_b3(daily, q, zone, wide=1.5):
    """B3 退出(宽SL+无TP+15根收盘)。"""
    f = EN.fill_in_zone(daily, q, zone, max_bars=6)
    if f is None or f["fill_price"] is None:
        return None
    k0, px = f["fill_idx"], f["fill_price"]
    if k0 + 15 >= len(daily):
        return None
    try:
        from core.structure import atr_of
        a_ = atr_of(daily, k0) or px * 0.025
    except Exception:
        a_ = px * 0.025
    sl = zone["invalid_price"] - wide * a_
    for k in range(k0 + 1, min(len(daily), k0 + 16)):
        if daily[k]["l"] <= sl:
            return ((sl / px - 1) * 100) - FEE
    return ((daily[min(len(daily) - 1, k0 + 15)]["c"] / px - 1) * 100) - FEE

# ---- READY 收集 + Entry+B3 模拟 ----
arm_all, arm_ev, arm_noev = [], [], []
for fp in files:
    try:
        raw = json.load(open(fp, encoding="utf-8"))
    except Exception:
        continue
    if len(raw) < 150:
        continue
    code = os.path.basename(fp).split("_")[0]
    daily = [{"t": str(b.get("t"))[:8], "o": float(b["o"]), "h": float(b["h"]),
              "l": float(b["l"]), "c": float(b["c"]), "v": float(b.get("v") or 0)} for b in raw]
    n = len(daily)
    for i in range(150, n):
        if daily[i]["t"] < "20230701":
            continue
        pools = LQ.liquidity_pools(daily, i)
        ssl = [p for p in pools if p["side"] == "SSL" and p["score"] >= 40]
        if not ssl:
            continue
        b = daily[i]
        try:
            from core.structure import atr_of
            a_ = atr_of(daily, i - 1) or 0
        except Exception:
            a_ = 0
        atr_pct = (a_ / (daily[i-1]["c"] or 1)) if a_ else 0.02
        tol = max(0.003, atr_pct * 0.5)
        pool = ssl[0]["price"]
        if b["l"] <= pool * (1 - tol) and b["c"] > pool:
            ph = max(x["h"] for x in daily[max(0, i-5):i]) if i >= 5 else b["h"]
            for k in range(i + 1, min(n, i + 6)):
                if daily[k]["c"] > ph:
                    sc = DS.displacement_score(daily, k)
                    if sc["score"] >= 50:
                        for m in range(k, min(n, k + 13)):
                            s5 = MSS.structure_shift(daily, m)
                            if s5 and s5["direction"] == "LONG":
                                f6 = FO.fvg_at(daily, m)
                                ob6 = FO.order_block(daily, m, "BULL")
                                if f6 or ob6:
                                    poi = f6 if f6 else ob6
                                    for q in range(m + 1, min(n, m + 11)):
                                        if poi["low"] <= daily[q]["l"] <= poi["high"] * 1.02:
                                            z = EN.entry_zone(poi, price=daily[q]["c"],
                                                              invalid_price=poi["low"] * 0.97, atr_pct=atr_pct)
                                            if z is None:
                                                break
                                            p = sim_b3(daily, q, z)
                                            d8 = daily[q]["t"]
                                            if p is not None:
                                                arm_all.append((code, d8, p))
                                                if has_event_near(code, d8):
                                                    arm_ev.append((code, d8, p))
                                                else:
                                                    arm_noev.append((code, d8, p))
                                            break
                                        if daily[q]["c"] < poi["low"] * 0.97:
                                            break
                                break
                        break
                elif daily[k]["c"] < pool * (1 - 2 * tol):
                    break

random.seed(42)
def stats(arm, oos):
    sel = [p for c, d, p in arm if (d >= OOS) == oos]
    if not sel:
        return {"n": 0}
    w = [x for x in sel if x > 0]
    l_ = [x for x in sel if x <= 0]
    return {"n": len(sel), "avg": round(sum(sel)/len(sel), 3), "wr": round(len(w)/len(sel), 3),
            "pf": round(sum(w)/abs(sum(l_)), 2) if l_ else 99}

def boot(arm, oos, iters=2000):
    sel = [p for c, d, p in arm if (d >= OOS) == oos]
    if len(sel) < 15:
        return None
    ms = []
    for _ in range(iters):
        s = random.choices(sel, k=len(sel))
        ms.append(sum(s)/len(s))
    ms.sort()
    return [round(ms[int(0.025*len(ms))], 3), round(ms[int(0.975*len(ms))], 3)]

out = {"n_all": len(arm_all), "n_with_event": len(arm_ev), "n_without": len(arm_noev),
       "A_ALL": {"IS": stats(arm_all, False), "OOS": stats(arm_all, True), "OOS_ci": boot(arm_all, True)},
       "B_WITH_EVENT": {"IS": stats(arm_ev, False), "OOS": stats(arm_ev, True), "OOS_ci": boot(arm_ev, True)},
       "C_NO_EVENT": {"IS": stats(arm_noev, False), "OOS": stats(arm_noev, True), "OOS_ci": boot(arm_noev, True)}}
print(f"结构链(Entry+B3): 总 {len(arm_all)} | 有事件先验 {len(arm_ev)} | 无事件 {len(arm_noev)}")
print(f"\n== P0-9 重跑(新引擎) ==")
for k in ("A_ALL", "B_WITH_EVENT", "C_NO_EVENT"):
    v = out[k]
    print(f"  {k:14s}: IS={v['IS']}")
    print(f"  {'':14s}  OOS={v['OOS']} CI={v['OOS_ci']}")
b, c = out["B_WITH_EVENT"]["OOS"], out["C_NO_EVENT"]["OOS"]
verdict = {"B_sample_ok": b.get("n", 0) >= 30,
           "B_beats_C_avg": b.get("avg", -99) > c.get("avg", -99),
           "B_beats_C_pf": b.get("pf", 0) > c.get("pf", 0)}
verdict["event_prior_has_marginal"] = all(verdict.values())
out["verdict"] = verdict
print(f"\n== 预注册判定 ==")
print(f"  B样本>=30: {verdict['B_sample_ok']} (n={b.get('n')})")
print(f"  B > C OOS avg: {verdict['B_beats_C_avg']} ({b.get('avg')} vs {c.get('avg')})")
print(f"  B > C OOS PF: {verdict['B_beats_C_pf']} ({b.get('pf')} vs {c.get('pf')})")
print(f"  → 事件先验有边际贡献: {verdict['event_prior_has_marginal']}")

json.dump(out, open(r"E:\test\smc_project\research\handover\P09重跑_新引擎事件先验.json", "w", encoding="utf-8"),
          ensure_ascii=False, indent=2, default=str)
print("\n已写 handover/P09重跑_新引擎事件先验.json")