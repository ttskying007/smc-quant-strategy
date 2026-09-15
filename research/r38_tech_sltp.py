# -*- coding: utf-8 -*-
"""r38_tech_sltp.py —— R38 技术腿同口径回测(与冻结基线完全同一退出结构).

目的: 技术腿 V2(扫损+FVG+量能确认) 之前只有 10 日固定持有(avg+5.28/PF2.63),
与事件腿(带 SL/TP + 15根持有) 非同口径 —— 不能直接比较/合并。

本脚本对技术腿复现 gen_v20f.py 的完整退出口径:
  入场: limit = signal_close×0.99, 次根 low<=limit 触价成交, 否则次根开盘兜底
  止损: sl1 = 60根内 swing low[0] - 0.5×ATR14
  止盈: tp1/tp2/tp3 = 60根内 swing highs (单调去重, 均 > ep)
  退出: core.execution.simulate(max_hold=15, partial_tp1=0.3, stop_to_be=True)
         → TIME_STOP / TP1+BE / TP2_RUNNER / SL_HIT / SL_GAP 同生产语义

对比: 技术腿(同口径) vs 技术腿(10日持有) vs 事件腿基线(n=1640 avg+3.51 PF3.20)
产出: r38_tech_sltp_cache.json (逐笔), 供前端同步复用。
纯研究, 不修改生产。
"""
import csv, io, json, os, sys, bisect
from collections import defaultdict
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
sys.path.insert(0, r"E:\test\smc_project\research")
from core.execution import simulate as _sim

KT = r"E:\test\smc_project\hermes\kline_cache_tencent"
HERE = r"E:\test\smc_project\research"
OUT_CACHE = os.path.join(HERE, "r38_tech_sltp_cache.json")
files = sorted(f for f in os.listdir(KT) if f.endswith("_daily_800.json"))

# ---- 指数 regime (仅用于分桶报告) ----
idx = json.load(open(os.path.join(HERE, "_r38_index_sh000001.json"), encoding="utf-8"))
idx.sort(key=lambda b: b["t"])
idates = [b["t"] for b in idx]; iclose = [b["c"] for b in idx]
def regime(d8):
    j = bisect.bisect_right(idates, d8) - 1
    if j < 20: return "MIX"
    ma20 = sum(iclose[j-19:j+1])/20; ma10 = sum(iclose[j-9:j+1])/10
    c = iclose[j]
    if c > ma20 and ma10 >= ma20: return "UP"
    if c < ma20 and ma10 <= ma20: return "DOWN"
    return "MIX"

def bars_of(path):
    raw = json.load(open(os.path.join(KT, path), encoding="utf-8"))
    bs = []
    for r in raw:
        t = "".join(x for x in str(r.get("t") or "") if x.isdigit())[:8]
        if t and r.get("o") and r.get("h") and r.get("l") and r.get("c") and r.get("v"):
            bs.append({"t": t, "o": float(r["o"]), "h": float(r["h"]), "l": float(r["l"]),
                       "c": float(r["c"]), "v": float(r["v"])})
    bs.sort(key=lambda b: b["t"])
    return bs

def swings(bs, i):
    """gen_v20f 同款: i 之前 60 根内各取 2 个 swing high / swing low."""
    highs, lows = [], []
    for j in range(i - 1, max(0, i - 60), -1):
        if j < 3 or j + 3 >= i:
            continue
        if len(highs) < 2 and bs[j]["h"] > max(bs[k]["h"] for k in range(j-3, j)) \
           and bs[j]["h"] >= max(bs[k]["h"] for k in range(j+1, j+4)):
            highs.append(bs[j]["h"])
        if len(lows) < 2 and bs[j]["l"] < min(bs[k]["l"] for k in range(j-3, j)) \
           and bs[j]["l"] <= min(bs[k]["l"] for k in range(j+1, j+4)):
            lows.append(bs[j]["l"])
        if len(highs) >= 2 and len(lows) >= 2:
            break
    return highs, lows

trades = []
n_files = 0
n_geom_skip = 0
for path in files:
    try: bs = bars_of(path)
    except Exception: continue
    n_files += 1
    code = path.split("_")[0]
    for i in range(25, len(bs) - 20):
        d = bs[i]["t"]
        if not ("20230901" <= d <= "20260831"): continue
        # ---- 技术信号: 扫损 + 收回 + FVG + 量能确认(V2) ----
        window = bs[max(0, i-20):i-3]
        if not window: continue
        prev_low = min(b["l"] for b in window)
        if not (bs[i]["l"] < prev_low*0.995 and bs[i+1]["c"] > prev_low
                and bs[i+1]["o"] > bs[i]["h"]):
            continue
        v20 = sum(b["v"] for b in bs[max(0, i-20):i])/20 if i >= 20 else 0
        if not (v20 > 0 and bs[i]["v"] > v20*1.5): continue
        # ---- 同口径入场(gen_v20f: limit = signal_close×0.99) ----
        entry_idx = i + 1
        if entry_idx + 17 >= len(bs): continue
        limit = bs[i]["c"] * 0.99
        ep = limit if bs[entry_idx]["l"] <= limit else bs[entry_idx]["o"]
        if ep <= 0: continue
        highs, lows = swings(bs, i)
        if not highs or not lows: continue
        highs_sorted = sorted(highs)
        tp1, tp2, tp3 = highs_sorted[0], (highs_sorted[1] if len(highs_sorted) > 1 else highs_sorted[0]*1.05), highs_sorted[-1]
        # ATR14 (与 gen_v20f 同)
        _atr = 0.0
        if i >= 15:
            trs = []
            for k in range(i-14, i):
                trs.append(max(bs[k]["h"]-bs[k]["l"], abs(bs[k]["h"]-bs[k-1]["c"]), abs(bs[k]["l"]-bs[k-1]["c"])))
            _atr = sum(trs)/14 if trs else 0.0
        sl1 = (lows[0] - 0.5*_atr) if _atr > 0 else lows[0]*0.99
        # TP 单调去重
        tps = sorted([x for x in (tp1, tp2, tp3) if x and x > ep])
        if not tps: continue
        tp1 = tps[0]; tp2 = tps[1] if len(tps) > 1 else tp1*1.05; tp3 = tps[2] if len(tps) > 2 else tp2*1.05
        if ep <= sl1:
            n_geom_skip += 1
            continue
        # ---- 同口径退出 ----
        r = _sim(bs, entry_idx, ep, sl1, tp1=tp1, tp2=tp2, tp3=tp3,
                 partial_tp1=0.3, stop_to_be=True, max_hold=15, code=code[:6])
        if r.get("skipped"): continue
        risk = ep - sl1
        trades.append({
            "s": code, "d": d, "buy": round(ep, 3), "sl": round(sl1, 3),
            "risk_pct": round(risk/ep*100, 2),
            "net": round(r.get("net_pnl_pct", 0.0), 3),
            "reason": r.get("reason", ""), "hold": r.get("hold_bars", 0),
            "rr": round((r.get("exit_price", ep)/ep - 1)/(risk/ep), 2) if risk > 0 else 0,
            "reg": regime(d),
        })

def stats(pnls):
    if not pnls: return None
    w = [x for x in pnls if x > 0]; l = [x for x in pnls if x <= 0]
    pf = sum(w)/abs(sum(l)) if sum(l) else 99
    return {"n": len(pnls), "avg": round(sum(pnls)/len(pnls), 2),
            "wr": round(100*len(w)/len(pnls), 1), "pf": round(pf, 2), "sum": round(sum(pnls), 0)}

print("="*84)
print(f"技术腿同口径回测 (扫损+FVG+量能确认, {n_files} 只, 2023-09~2026-08)")
print("="*84)
if not trades:
    print("无候选"); sys.exit(0)

nets = [t["net"] for t in trades]
s_all = stats(nets)
print(f"技术腿(同口径SL/TP): n={s_all['n']} avg={s_all['avg']:+.2f}% 胜率={s_all['wr']}% PF={s_all['pf']} 累计={s_all['sum']:+.0f}%")
print(f"  几何非法跳过(ep<=sl): {n_geom_skip}")

print("\n逐年:")
byy = defaultdict(list)
for t in trades: byy[t["d"][:4]].append(t["net"])
for y in ("2023", "2024", "2025", "2026"):
    s = stats(byy.get(y, []))
    if s: print(f"  {y}: n={s['n']} avg={s['avg']:+.2f}% 胜率={s['wr']}% PF={s['pf']}")

print("\nregime:")
byr = defaultdict(list)
for t in trades: byr[t["reg"]].append(t["net"])
for k in ("UP", "MIX", "DOWN"):
    s = stats(byr.get(k, []))
    if s: print(f"  {k}: n={s['n']} avg={s['avg']:+.2f}% 胜率={s['wr']}% PF={s['pf']}")

print("\n出场分解:")
byex = defaultdict(list)
for t in trades: byex[t["reason"] or "?"].append(t["net"])
for k, ps in sorted(byex.items(), key=lambda kv: -len(kv[1]))[:8]:
    s = stats(ps)
    print(f"  {k:<12} n={s['n']:>5} avg={s['avg']:+.2f}% 胜率={s['wr']}% PF={s['pf']}")

print("\nRR 分布:")
rrs = [t["rr"] for t in trades if t.get("rr") is not None]
if rrs:
    le = 100*sum(1 for x in rrs if x <= -1)/len(rrs)
    mid = 100*sum(1 for x in rrs if -1 < x < 1)/len(rrs)
    ge = 100*sum(1 for x in rrs if x >= 1)/len(rrs)
    print(f"  <=-1R {le:.1f}% | -1~1R {mid:.1f}% | >=1R {ge:.1f}%")

print("\n" + "="*84)
print("口径对比 (同一批技术腿候选):")
print(f"  10日固定持有:  n=2515 avg=+5.26% 胜率=65.3% PF=2.63")
print(f"  同口径SL/TP:   n={s_all['n']} avg={s_all['avg']:+.2f}% 胜率={s_all['wr']}% PF={s_all['pf']}")
print(f"  事件腿基线:    n=1640 avg=+3.51% 胜率=62.1% PF=3.20")

json.dump(trades, open(OUT_CACHE, "w", encoding="utf-8"), ensure_ascii=False)
print(f"\n→ 缓存 {len(trades)} 笔 → {OUT_CACHE}")