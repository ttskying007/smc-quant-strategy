# -*- coding: utf-8 -*-
"""r38_prein_sltp.py —— R38 业绩预增事件在冻结基线口径下的回测(含 OOS).

R38i 用纯持有测试筛出业绩预增(20日 avg+5.15%/PF3.02, IS2.58→OOS3.56,
退市偏差 6.5% 可采信)。本脚本把它放进 **gen_v20f 完全同一口径** 重测:
  过滤: stage_of in (ACCUM, DOWNTREND) + 旧版 adx14 >= 20 (非平滑)
  入场: limit = disc_close×0.99, T+1 low<=limit 触价成交, 否则 T+1 open
  止损: sl1 = 60根内 swing low[0] - 0.5×ATR14
  止盈: tp1/tp2/tp3 = 60根内 swing highs (单调去重)
  退出: core.execution.simulate(max_hold=15, partial_tp1=0.3, stop_to_be=True)

对比: 事件腿基线(n=1640 avg+3.51% PF3.20, 同一口径)
分段: IS<=2025-06-30 / OOS>2025-06-30
纯研究, 不修改生产。
"""
import csv, io, json, os, sqlite3, sys
from collections import defaultdict
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
sys.path.insert(0, r"E:\test\smc_project\research")
from core.execution import simulate as _sim

KT = r"E:\test\smc_project\hermes\kline_cache_tencent"
HERE = r"E:\test\smc_project\research"
conn = sqlite3.connect(r"E:\test\smc_project\announce\smc_announce.db")
cur = conn.cursor()
code2file = {f.split("_")[0]: os.path.join(KT, f) for f in os.listdir(KT) if f.endswith("_daily_800.json")}
bar_cache = {}
def bars_of(code):
    if code not in bar_cache:
        p = code2file.get(code)
        if not p:
            bar_cache[code] = []
            return bar_cache[code]
        raw = json.load(open(p, encoding="utf-8"))
        bs = []
        for r in raw:
            t = "".join(x for x in str(r.get("t") or "") if x.isdigit())[:8]
            if t and r.get("o") and r.get("h") and r.get("l") and r.get("c") and r.get("v"):
                bs.append({"t": t, "o": float(r["o"]), "h": float(r["h"]), "l": float(r["l"]),
                           "c": float(r["c"]), "v": float(r["v"])})
        bs.sort(key=lambda b: b["t"])
        bar_cache[code] = bs
    return bar_cache[code]

def adx14(bs, i):
    if i < 30:
        return None
    plus_dm = minus_dm = tr_sum = 0.0
    for k in range(i - 14, i):
        h, l, pc = bs[k]["h"], bs[k]["l"], bs[k - 1]["c"]
        up = h - bs[k - 1]["h"]
        dn = bs[k - 1]["l"] - l
        plus_dm += up if (up > dn and up > 0) else 0
        minus_dm += dn if (dn > up and dn > 0) else 0
        tr = max(h - l, abs(h - pc), abs(l - pc))
        tr_sum += tr
    if tr_sum <= 0:
        return None
    pdi = 100 * plus_dm / tr_sum
    mdi = 100 * minus_dm / tr_sum
    if pdi + mdi == 0:
        return None
    return 100 * abs(pdi - mdi) / (pdi + mdi)

def stage_of(bs, i):
    if i < 91:
        return None
    w60 = bs[i - 60:i]
    ret60 = w60[-1]["c"] / w60[0]["c"] - 1
    v20 = sum(b["v"] for b in bs[i - 20:i]) / 20
    v60 = sum(b["v"] for b in bs[i - 60:i]) / 60
    vt = v20 / v60 if v60 else 1
    if ret60 < -0.15 and vt < 0.9:
        return "ACCUM"
    if ret60 > 0.30 and vt > 1.3:
        return "DISTRIB"
    if ret60 > 0.20 and vt > 1.1:
        return "MARKUP"
    return "UPTREND" if ret60 > 0 else "DOWNTREND"

ev = []
seen = set()
cur.execute("SELECT date, stock_code, title FROM announce WHERE date >= '2023-09-01' "
            "AND title LIKE '%业绩预增%'")
rows = cur.fetchall()
print(f"业绩预增公告(原始): {len(rows)}")
for date, code, title in rows:
    code6 = str(code)[:6]
    d = str(date)[:10].replace("-", "")
    if (code6, d) in seen:
        continue
    seen.add((code6, d))
    bs = bars_of(code6)
    if not bs:
        continue
    dates = [b["t"] for b in bs]
    if d not in dates:
        continue
    i = dates.index(d)
    st = stage_of(bs, i)
    if st not in ("ACCUM", "DOWNTREND"):
        continue
    adx = adx14(bs, i)
    if adx is None or adx < 20:
        continue
    entry_idx = i + 1
    if entry_idx + 17 >= len(bs) or entry_idx < 130:
        continue
    if bs[entry_idx]["t"] < "20230901":
        continue
    ep_open = bs[entry_idx]["o"]
    disc_close = bs[i]["c"]
    if ep_open <= 0:
        continue
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
    if not highs or not lows:
        continue
    highs.sort()
    limit = disc_close * 0.99
    ep = limit if bs[entry_idx]["l"] <= limit else ep_open
    tp1, tp2, tp3 = highs[0], (highs[1] if len(highs) > 1 else highs[0]*1.05), highs[-1]
    _atr = 0.0
    if i >= 15:
        _trs = []
        for _k in range(i-14, i):
            _trs.append(max(bs[_k]["h"]-bs[_k]["l"], abs(bs[_k]["h"]-bs[_k-1]["c"]), abs(bs[_k]["l"]-bs[_k-1]["c"])))
        _atr = sum(_trs)/14 if _trs else 0.0
    sl1 = (lows[0] - 0.5*_atr) if _atr > 0 else lows[0]*0.99
    _tps = sorted([x for x in (tp1, tp2, tp3) if x and x > ep])
    if not _tps:
        continue
    tp1 = _tps[0]; tp2 = _tps[1] if len(_tps) > 1 else tp1*1.05; tp3 = _tps[2] if len(_tps) > 2 else tp2*1.05
    r = _sim(bs, entry_idx, ep, sl1, tp1=tp1, tp2=tp2, tp3=tp3,
             partial_tp1=0.3, stop_to_be=True, max_hold=15, code=code6)
    if r.get("skipped"):
        continue
    risk = ep - sl1
    ev.append({"s": code6, "d": d, "net": round(r.get("net_pnl_pct", 0.0), 4),
               "reason": r.get("reason", ""), "hold": r.get("hold_bars", 0),
               "risk_pct": round(risk/ep*100, 2) if risk > 0 else 0,
               "rr": round((r.get("exit_price", ep)/ep - 1)/(risk/ep), 2) if risk > 0 else 0,
               "stage": st})

def stats(ts):
    if not ts: return None
    pnls = [t["net"] for t in ts]
    w = [x for x in pnls if x > 0]; l = [x for x in pnls if x <= 0]
    pf = sum(w)/abs(sum(l)) if sum(l) else 99
    return {"n": len(ts), "avg": round(sum(pnls)/len(pnls), 2),
            "wr": round(100*len(w)/len(pnls), 1), "pf": round(pf, 2), "sum": round(sum(pnls), 0)}

print("="*88)
print("业绩预增 @ gen_v20f 同口径 (stage ACCUM/DOWNTREND + adx>=20 + SL/TP + max_hold=15)")
print("事件腿基线参照: n=1640 avg+3.51% 胜率62.1% PF3.20")
print("="*88)
sa = stats(ev)
if not sa:
    print("无样本"); sys.exit(0)
print(f"全样本: n={sa['n']} avg={sa['avg']:+.2f}% 胜率={sa['wr']}% PF={sa['pf']} 累计={sa['sum']:+.0f}%")

IS_END = "20250630"
si = stats([t for t in ev if t["d"] <= IS_END])
so = stats([t for t in ev if t["d"] > IS_END])
print(f"IS  (≤2025-06): n={si['n']} avg={si['avg']:+.2f}% 胜率={si['wr']}% PF={si['pf']}" if si else "IS: 无")
print(f"OOS (>2025-06): n={so['n']} avg={so['avg']:+.2f}% 胜率={so['wr']}% PF={so['pf']}" if so else "OOS: 无")
if si and so:
    ratio = so["pf"]/si["pf"] if si["pf"] else 0
    print(f"OOS/IS PF 比 = {ratio:.2f} → {'✅ 通过' if (so['pf'] > 1.5 and ratio > 0.5) else '❌ 未过线'}")

print("\n逐年:")
byy = defaultdict(list)
for t in ev: byy[t["d"][:4]].append(t)
for y in sorted(byy):
    s = stats(byy[y])
    print(f"  {y}: n={s['n']} avg={s['avg']:+.2f}% 胜率={s['wr']}% PF={s['pf']}")

print("\n出场分解:")
byex = defaultdict(list)
for t in ev: byex[t["reason"] or "?"].append(t)
for k, ts in sorted(byex.items(), key=lambda kv: -len(kv[1]))[:7]:
    s = stats(ts)
    print(f"  {k:<12} n={s['n']:>4} avg={s['avg']:+.2f}% PF={s['pf']}")

print("\nstage 分布:")
bys = defaultdict(list)
for t in ev: bys[t["stage"]].append(t)
for k, ts in bys.items():
    s = stats(ts)
    print(f"  {k:<10} n={s['n']} avg={s['avg']:+.2f}% PF={s['pf']}")

print("\nRR 分布:")
rrs = [t["rr"] for t in ev]
le = 100*sum(1 for x in rrs if x <= -1)/len(rrs)
print(f"  <=-1R {le:.1f}% (事件腿基线 23.5%)")

json.dump(ev, open(os.path.join(HERE, "r38_prein_sltp.json"), "w", encoding="utf-8"), ensure_ascii=False)
print(f"\n→ r38_prein_sltp.json ({len(ev)} 笔)")