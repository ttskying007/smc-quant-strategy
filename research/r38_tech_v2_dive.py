# -*- coding: utf-8 -*-
"""r38_tech_v2_dive.py —— R38 技术腿 V2(量能确认)深入: 逐年/月序/与事件腿组合.
验证 V2 是否可作为正式技术腿候选(与事件腿合并扩池), 以及是否需叠加
regime 缩放而非过滤. 纯研究. """
import io, json, os, sys, bisect
from collections import defaultdict
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
sys.path.insert(0, r"E:\test\smc_project\research")

KT = r"E:\test\smc_project\hermes\kline_cache_tencent"
files = sorted(f for f in os.listdir(KT) if f.endswith("_daily_800.json"))
idx = json.load(open(r"E:\test\smc_project\research\_r38_index_sh000001.json", encoding="utf-8"))
idx.sort(key=lambda b: b["t"])
idates = [b["t"] for b in idx]; iclose = [b["c"] for b in idx]
def regime(d8):
    i = bisect.bisect_right(idates, d8) - 1
    if i < 20: return "MIX"
    ma20 = sum(iclose[i-19:i+1])/20; ma10 = sum(iclose[i-9:i+1])/10
    c = iclose[i]
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

trades = []
for path in files:
    try: bs = bars_of(path)
    except Exception: continue
    dates = [b["t"] for b in bs]
    for i in range(25, len(bs)-11):
        d = bs[i]["t"]
        if not ("20230901" <= d <= "20260831"): continue
        window = bs[max(0,i-20):i-3]
        if not window: continue
        prev_low = min(b["l"] for b in window)
        if not (bs[i]["l"] < prev_low*0.995 and bs[i+1]["c"] > prev_low and bs[i+1]["o"] > bs[i]["h"]):
            continue
        v20 = sum(b["v"] for b in bs[max(0,i-20):i])/20 if i >= 20 else 0
        if not (v20 > 0 and bs[i]["v"] > v20*1.5): continue   # 只保留量能确认
        ep = bs[i+1]["o"]; ex = bs[i+10]["c"]
        if ep <= 0: continue
        trades.append({"d": d, "ret": (ex/ep-1)*100, "reg": regime(d)})

print(f"技术腿 V2(量能确认)全周期: n={len(trades)}")
def st(ts):
    if not ts: return None
    rets = [t["ret"] for t in ts]
    w = [x for x in rets if x>0]; l = [x for x in rets if x<=0]
    pf = sum(w)/abs(sum(l)) if sum(l) else 99
    return dict(n=len(ts), avg=sum(rets)/len(rets), med=sorted(rets)[len(rets)//2],
                wr=100*len(w)/len(rets), pf=pf)

print("逐年:")
byy = defaultdict(list)
for t in trades: byy[t["d"][:4]].append(t)
for y in ("2023","2024","2025","2026"):
    s = st(byy.get(y, []))
    if s: print(f"  {y}: n={s['n']} avg={s['avg']:+.2f}% 胜率={s['wr']:.1f}% PF={s['pf']:.2f}")

print("\nregime 分桶(技术腿 V2):")
byr = defaultdict(list)
for t in trades: byr[t["reg"]].append(t)
for k in ("UP","MIX","DOWN"):
    s = st(byr.get(k, []))
    if s: print(f"  {k}: n={s['n']} avg={s['avg']:+.2f}% 胜率={s['wr']:.1f}% PF={s['pf']:.2f}")

print("\n月序(技术腿 V2):")
bym = defaultdict(list)
for t in trades: bym[t["d"][4:6]].append(t)
for mm in range(1,13):
    s = st(bym.get(f"{mm:02d}", []))
    if s: print(f"  {mm}月: n={s['n']} avg={s['avg']:+.2f}% PF={s['pf']:.2f}")

# 与事件腿合并的供给效应: 月笔数对比
print("\n供给对比(月均笔数): 事件腿基线≈46笔/月 vs 技术腿V2 ≈%.0f笔/月" % (len(trades)/36))
