# -*- coding: utf-8 -*-
"""r38_tech_leg_q.py —— R38 技术腿质量升级: 多学派质量闸叠加对比.
对全市场扫描 扫损+FVG 基础模式, 叠加不同质量闸, 一次遍历算全部变体:
  V0 裸模式(基线, 参照 r38_tech_leg_bt: avg+1.81 PF1.53)
  V1 +UP-regime(上证20MA)
  V2 +量能确认(扫损日成交量 > 20日均量 ×1.5 —— Volume Analysis: 扫损需参与度)
  V3 +缠论中枢3买结构(中枢形成 + 突破 + 回踩不破上沿)
  V4 +UP +量能
  V5 +UP +中枢
  V6 +UP +量能 +中枢(三重)
判据: 各变体 avg/PF/胜率/笔数 vs 事件腿基线(+3.51/3.20/62.1%).
每只股票扫一遍, 记录每笔的 (日期, 10日收益, regime, 量能flag, 中枢flag).
纯研究, 不修改生产. """
import io, json, os, sys, bisect
from collections import defaultdict
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
sys.path.insert(0, r"E:\test\smc_project\research")

KT = r"E:\test\smc_project\hermes\kline_cache_tencent"
files = sorted(f for f in os.listdir(KT) if f.endswith("_daily_800.json"))

# 指数 regime
idx = json.load(open(r"E:\test\smc_project\research\_r38_index_sh000001.json", encoding="utf-8"))
idx.sort(key=lambda b: b["t"])
idates = [b["t"] for b in idx]; iclose = [b["c"] for b in idx]
def is_up(d8):
    i = bisect.bisect_right(idates, d8) - 1
    if i < 20: return True
    ma20 = sum(iclose[i-19:i+1])/20; ma10 = sum(iclose[i-9:i+1])/10
    return iclose[i] > ma20 and ma10 >= ma20

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

def has_zhongshu_3buy(bs, i):
    """缠论简化: 披露/触发日前 40 根内形成横向中枢(双低夹双高, 宽度<25%),
    触发日突破中枢上沿, 次日回踩不破上沿 → 3买候选."""
    lo = max(0, i-40)
    highs, lows = [], []
    for j in range(max(1, lo), min(i, len(bs)-1)):
        if bs[j]["h"] > bs[j-1]["h"] and bs[j]["h"] >= bs[j+1]["h"]:
            highs.append(j)
        if bs[j]["l"] < bs[j-1]["l"] and bs[j]["l"] <= bs[j+1]["l"]:
            lows.append(j)
    if len(highs) < 2 or len(lows) < 2:
        return False
    hs = sorted(bs[j]["h"] for j in highs)
    ls = sorted(bs[j]["l"] for j in lows)
    h_cut = hs[max(0, len(hs)//5): len(hs)*4//5] if len(hs) >= 5 else hs
    l_cut = ls[max(0, len(ls)//5): len(ls)*4//5] if len(ls) >= 5 else ls
    if not h_cut or not l_cut: return False
    top = sum(h_cut)/len(h_cut); bot = sum(l_cut)/len(l_cut)
    if top <= bot or (top-bot)/bot > 0.25: return False
    # 触发日突破上沿 + 次日低点不破上沿
    return bs[i]["c"] > top*1.005 and i+1 < len(bs) and bs[i+1]["l"] >= top*0.995

# 变体累积器
V = {k: [] for k in ("V0", "V1", "V2", "V3", "V4", "V5", "V6")}
n_files = 0
for path in files:
    try: bs = bars_of(path)
    except Exception: continue
    n_files += 1
    dates = [b["t"] for b in bs]
    for i in range(25, len(bs)-11):
        d = bs[i]["t"]
        if not ("20230901" <= d <= "20260831"): continue
        window = bs[max(0,i-20):i-3]
        if not window: continue
        prev_low = min(b["l"] for b in window)
        if not (bs[i]["l"] < prev_low*0.995 and bs[i+1]["c"] > prev_low and bs[i+1]["o"] > bs[i]["h"]):
            continue
        ep = bs[i+1]["o"]; ex = bs[i+10]["c"]
        if ep <= 0: continue
        ret = (ex/ep-1)*100
        up = is_up(d)
        # 量能: 扫损日量 > 20日均量×1.5
        v20 = sum(b["v"] for b in bs[max(0,i-20):i])/20 if i >= 20 else 0
        vol_ok = v20 > 0 and bs[i]["v"] > v20*1.5
        zs3 = has_zhongshu_3buy(bs, i)
        rec = {"d": d, "ret": ret, "up": up, "vol": vol_ok, "zs": zs3}
        V["V0"].append(rec)
        if up: V["V1"].append(rec)
        if vol_ok: V["V2"].append(rec)
        if zs3: V["V3"].append(rec)
        if up and vol_ok: V["V4"].append(rec)
        if up and zs3: V["V5"].append(rec)
        if up and vol_ok and zs3: V["V6"].append(rec)

def stats(recs):
    if not recs: return None
    rets = [r["ret"] for r in recs]
    w = [x for x in rets if x > 0]; l = [x for x in rets if x <= 0]
    pf = sum(w)/abs(sum(l)) if sum(l) else 99
    return dict(n=len(recs), avg=sum(rets)/len(rets), med=sorted(rets)[len(rets)//2],
                wr=100*len(w)/len(rets), pf=pf)

print("="*88)
print("技术腿质量闸叠加 (全市场扫损+FVG, %d 只, 2023-09~2026-08)" % n_files)
print("事件腿参照: n=1640 avg=+3.51%% PF=3.20 胜率=62.1%%")
print("="*88)
print(f"{'变体':<26}{'n':>7}{'平均%':>9}{'中位%':>8}{'胜率':>8}{'PF':>7}")
desc = {
    "V0": "裸模式",
    "V1": "+UP-regime",
    "V2": "+量能(vol>1.5x20日均)",
    "V3": "+缠论中枢3买",
    "V4": "+UP+量能",
    "V5": "+UP+中枢",
    "V6": "+UP+量能+中枢(三重)",
}
for k in ("V0", "V1", "V2", "V3", "V4", "V5", "V6"):
    s = stats(V[k])
    if not s: continue
    print(f"{desc[k]:<26}{s['n']:>7}{s['avg']:>+8.2f}%{s['med']:>+8.2f}%{s['wr']:>7.1f}%{s['pf']:>7.2f}")

# 三重变体逐年
print("\nV6(三重)逐年:")
byy = defaultdict(list)
for r in V["V6"]: byy[r["d"][:4]].append(r["ret"])
for y in ("2023", "2024", "2025", "2026"):
    ps = byy.get(y, [])
    if not ps: continue
    w2 = [x for x in ps if x>0]; l2 = [x for x in ps if x<=0]
    pf2 = sum(w2)/abs(sum(l2)) if sum(l2) else 99
    print(f"  {y}: n={len(ps)} avg={sum(ps)/len(ps):+.2f}% 胜率={100*len(w2)/len(ps):.1f}% PF={pf2:.2f}")

# 中枢命中率(说明缠论闸的覆盖率)
zs_n = len(V["V3"])
print(f"\n中枢3买命中率: {zs_n}/{len(V['V0'])} = {100*zs_n/max(1,len(V['V0'])):.1f}% 的裸模式票有中枢结构")
