# -*- coding: utf-8 -*-
"""r38_tech_sltp_search.py —— R38 技术腿独立 SL/TP 搜索.

问题(R38g): 直接套事件腿 SL 推导(swing low - 0.5×ATR) → 41% 候选 ep<=sl 几何
非法被跳过(扫损型入场价常低于/接近近期 swing low)。技术腿需要自己的 SL 锚点。

候选 SL 锚点(全部要求 sl < ep, 非法则跳过并计数):
  S1 sweep_low        : 扫损那根的低点 lows_sweep × 0.999
  S2 sweep_low_05atr  : 扫损低点 - 0.5×ATR14
  S3 ep_1atr          : ep - 1.0×ATR14
  S4 ep_2atr          : ep - 2.0×ATR14
  S5 ep_pct5          : ep × 0.95
  S6 prev_low_05atr   : 被扫的前低(prev_low) - 0.5×ATR14

TP 方案:
  T_swing : 60根 swing highs(同事件腿, tp1/tp2/tp3 分层)
  T_r     : 纯 R 倍数(tp1=1R, tp2=2R, tp3=3R)

组合评估: 6 SL × 2 TP = 12 变体, 每个记录 n/几何跳过/avg/WR/PF/累计/逐年/MIX桶。
退出统一 core.execution.simulate(max_hold=15, partial_tp1=0.3, stop_to_be=True)。
产出: r38_tech_sltp_search.json (最优变体逐笔, 供前端/接线复用)
纯研究, 不修改生产。
"""
import io, json, os, sys, bisect
from collections import defaultdict
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
sys.path.insert(0, r"E:\test\smc_project\research")
from core.execution import simulate as _sim

KT = r"E:\test\smc_project\hermes\kline_cache_tencent"
HERE = r"E:\test\smc_project\research"
files = sorted(f for f in os.listdir(KT) if f.endswith("_daily_800.json"))

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
    highs, lows = [], []
    for j in range(i - 1, max(0, i - 60), -1):
        if j < 3 or j + 3 >= i: continue
        if len(highs) < 2 and bs[j]["h"] > max(bs[k]["h"] for k in range(j-3, j)) \
           and bs[j]["h"] >= max(bs[k]["h"] for k in range(j+1, j+4)):
            highs.append(bs[j]["h"])
        if len(lows) < 2 and bs[j]["l"] < min(bs[k]["l"] for k in range(j-3, j)) \
           and bs[j]["l"] <= min(bs[k]["l"] for k in range(j+1, j+4)):
            lows.append(bs[j]["l"])
        if len(highs) >= 2 and len(lows) >= 2: break
    return highs, lows

SL_KEYS = ["S1_sweep_low", "S2_sweep_05atr", "S3_ep_1atr", "S4_ep_2atr", "S5_ep_pct5", "S6_prevlow_05atr"]
TP_KEYS = ["T_swing", "T_r"]
V = {f"{a}|{b}": {"nets": [], "skip": 0, "trades": []} for a in SL_KEYS for b in TP_KEYS}

n_files = 0
n_cand = 0
for path in files:
    try: bs = bars_of(path)
    except Exception: continue
    n_files += 1
    code = path.split("_")[0]
    for i in range(25, len(bs) - 20):
        d = bs[i]["t"]
        if not ("20230901" <= d <= "20260831"): continue
        window = bs[max(0, i-20):i-3]
        if not window: continue
        prev_low = min(b["l"] for b in window)
        if not (bs[i]["l"] < prev_low*0.995 and bs[i+1]["c"] > prev_low and bs[i+1]["o"] > bs[i]["h"]):
            continue
        v20 = sum(b["v"] for b in bs[max(0, i-20):i])/20 if i >= 20 else 0
        if not (v20 > 0 and bs[i]["v"] > v20*1.5): continue
        entry_idx = i + 1
        if entry_idx + 17 >= len(bs): continue
        n_cand += 1
        limit = bs[i]["c"] * 0.99
        ep = limit if bs[entry_idx]["l"] <= limit else bs[entry_idx]["o"]
        if ep <= 0: continue
        # ATR14
        _atr = 0.0
        if i >= 15:
            trs = []
            for k in range(i-14, i):
                trs.append(max(bs[k]["h"]-bs[k]["l"], abs(bs[k]["h"]-bs[k-1]["c"]), abs(bs[k]["l"]-bs[k-1]["c"])))
            _atr = sum(trs)/14 if trs else 0.0
        highs, lows = swings(bs, i)
        if not highs or not lows: continue
        hs = sorted(highs)
        # ---- SL 候选 ----
        sl_map = {
            "S1_sweep_low": bs[i]["l"] * 0.999,
            "S2_sweep_05atr": (bs[i]["l"] - 0.5*_atr) if _atr > 0 else bs[i]["l"]*0.99,
            "S3_ep_1atr": (ep - 1.0*_atr) if _atr > 0 else ep*0.97,
            "S4_ep_2atr": (ep - 2.0*_atr) if _atr > 0 else ep*0.94,
            "S5_ep_pct5": ep * 0.95,
            "S6_prevlow_05atr": (prev_low - 0.5*_atr) if _atr > 0 else prev_low*0.99,
        }
        # ---- TP 候选 ----
        # T_swing: 事件腿同款(swing highs 分层)
        sw = sorted([x for x in (hs[0], hs[1] if len(hs) > 1 else hs[0]*1.05, hs[-1]) if x and x > ep])
        tp_swing = (sw[0], sw[1] if len(sw) > 1 else sw[0]*1.05, sw[2] if len(sw) > 2 else (sw[1] if len(sw) > 1 else sw[0]*1.05)*1.05) if sw else None
        for slk, slv in sl_map.items():
            if not slv or slv >= ep:
                for tpk in TP_KEYS:
                    V[f"{slk}|{tpk}"]["skip"] += 1
                continue
            risk = ep - slv
            # T_r: 纯 R 倍数
            tp_r = (ep + 1.0*risk, ep + 2.0*risk, ep + 3.0*risk)
            for tpk, tps in (("T_swing", tp_swing), ("T_r", tp_r)):
                if not tps: continue
                r = _sim(bs, entry_idx, ep, slv, tp1=tps[0], tp2=tps[1], tp3=tps[2],
                         partial_tp1=0.3, stop_to_be=True, max_hold=15, code=code[:6])
                if r.get("skipped"):
                    V[f"{slk}|{tpk}"]["skip"] += 1
                    continue
                net = r.get("net_pnl_pct", 0.0)
                rec = {"s": code, "d": d, "net": round(net, 3), "reg": regime(d),
                       "reason": r.get("reason", ""), "risk_pct": round(risk/ep*100, 2)}
                V[f"{slk}|{tpk}"]["nets"].append(net)
                V[f"{slk}|{tpk}"]["trades"].append(rec)

def stats(pnls):
    if not pnls: return None
    w = [x for x in pnls if x > 0]; l = [x for x in pnls if x <= 0]
    pf = sum(w)/abs(sum(l)) if sum(l) else 99
    return {"n": len(pnls), "avg": round(sum(pnls)/len(pnls), 2),
            "wr": round(100*len(w)/len(pnls), 1), "pf": round(pf, 2), "sum": round(sum(pnls), 0)}

print("="*104)
print(f"技术腿独立 SL/TP 搜索 ({n_files} 只, 候选 {n_cand}, 2023-09~2026-08)")
print("事件腿参照: n=1640 avg+3.51% PF3.20 | 10日持有参照: n=2515 avg+5.26% PF2.63")
print("="*104)
print(f"{'SL':<20}{'TP':<10}{'n':>6}{'几何跳过':>9}{'平均%':>9}{'胜率':>8}{'PF':>7}{'累计%':>9}{'MIX桶PF':>9}")
rows = []
for slk in SL_KEYS:
    for tpk in TP_KEYS:
        k = f"{slk}|{tpk}"
        s = stats(V[k]["nets"])
        if not s or s["n"] == 0: continue
        # MIX 桶
        mix = [t["net"] for t in V[k]["trades"] if t["reg"] == "MIX"]
        mixpf = stats(mix)["pf"] if mix else 0
        print(f"{slk:<20}{tpk:<10}{s['n']:>6}{V[k]['skip']:>9}{s['avg']:>+8.2f}%{s['wr']:>7.1f}%{s['pf']:>7.2f}{s['sum']:>+9.0f}{mixpf:>9.2f}")
        rows.append((k, s, V[k]["skip"], mixpf))

print("\n最优变体(按 PF):")
rows.sort(key=lambda x: -x[1]["pf"])
for k, s, skip, mixpf in rows[:4]:
    print(f"  {k}: n={s['n']} avg={s['avg']:+.2f}% PF={s['pf']} 跳过={skip} MIX_PF={mixpf:.2f}")

# 最优变体逐年 + 出场
best_k = rows[0][0]
best_trades = V[best_k]["trades"]
print(f"\n最优变体 {best_k} 逐年:")
byy = defaultdict(list)
for t in best_trades: byy[t["d"][:4]].append(t["net"])
for y in ("2023", "2024", "2025", "2026"):
    s = stats(byy.get(y, []))
    if s: print(f"  {y}: n={s['n']} avg={s['avg']:+.2f}% 胜率={s['wr']}% PF={s['pf']}")

print(f"\n最优变体 {best_k} 出场分解:")
byex = defaultdict(list)
for t in best_trades: byex[t["reason"] or "?"].append(t["net"])
for kk, ps in sorted(byex.items(), key=lambda kv: -len(kv[1]))[:6]:
    s = stats(ps)
    print(f"  {kk:<12} n={s['n']:>5} avg={s['avg']:+.2f}% PF={s['pf']}")

print(f"\n最优变体 {best_k} regime 桶:")
byr = defaultdict(list)
for t in best_trades: byr[t["reg"]].append(t["net"])
for kk in ("MIX", "UP", "DOWN"):
    s = stats(byr.get(kk, []))
    if s: print(f"  {kk}: n={s['n']} avg={s['avg']:+.2f}% 胜率={s['wr']}% PF={s['pf']}")

out = {"best": best_k, "variants": {k: {"stats": s, "skip": sk, "mix_pf": mp} for k, s, sk, mp in rows},
       "best_trades": best_trades}
json.dump(out, open(os.path.join(HERE, "r38_tech_sltp_search.json"), "w", encoding="utf-8"), ensure_ascii=False)
print(f"\n→ r38_tech_sltp_search.json ({best_k}, {len(best_trades)} 笔)")