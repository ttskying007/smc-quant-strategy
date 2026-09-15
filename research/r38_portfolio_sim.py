# -*- coding: utf-8 -*-
"""r38_portfolio_sim.py —— 简化两腿合并评估(R38 第五轮第二波).
用已有候选数据对比: 事件腿(n=1640, 已有 entry/sell 价) vs 技术腿(全市场扫损+FVG+量能确认, n=2509).
合并策略: 事件腿 100% 保留(稀有), 技术腿按日最多 max_tech=3 补充(等权 1/10 仓位).
不做复杂组合模拟 —— 直接对比两条腿表现, 判断合并是否有意义.
纯研究, 不修改生产. """
import csv, io, json, os, sys
from collections import defaultdict
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
sys.path.insert(0, r"E:\test\smc_project\research")

KT = r"E:\test\smc_project\hermes\kline_cache_tencent"
files = sorted(f for f in os.listdir(KT) if f.endswith("_daily_800.json"))
MAX_POS = 10

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

# 事件腿基线(生产冻结基线 combo_v20f_trades.csv EVENT 腿): 1640 笔
evbase = list(csv.DictReader(open(r"E:\test\smc_project\research\combo_v20f_trades.csv", encoding="utf-8-sig")))
events = [{"symbol": r["symbol"].split(".")[0], "entry_date": r["buy_date"],
           "pnl_pct": float(r["net_pnl_pct"]), "risk_pct": float(r["risk_pct"] or 5.0)}
          for r in evbase if r.get("src") == "EVENT"]
print(f"事件腿: n={len(events)} 平均PnL={sum(x['pnl_pct'] for x in events)/len(events):+.2f}%")

# 技术腿 V2(扫损+FVG+量能确认, 全市场扫描) —— 生成详细候选名单, 每笔 10 日持有
tech = []
for path in files:
    try: bs = bars_of(KT+"\\"+path)
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
        if not (v20 > 0 and bs[i]["v"] > v20*1.5): continue   # 量能闸(V2)
        ep = bs[i+1]["o"]; ex = bs[i+10]["c"]
        if ep <= 0: continue
        tech.append({"symbol": path.split("_")[0], "entry_date": d, "entry_price": ep,
                     "exit_price": ex, "v_20": v20, "v_sweep": bs[i]["v"]})
tech.sort(key=lambda x: x["entry_date"])
pnls_t = [{"net": (t["exit_price"]/t["entry_price"]-1)*100, "date": t["entry_date"]} for t in tech]
w = [x["net"] for x in pnls_t if x["net"]>0]; l = [x["net"] for x in pnls_t if x["net"]<=0]
pf_t = sum(w)/abs(sum(l)) if sum(l) else 99
print(f"技术腿(V2,量确): n={len(tech)} avg={sum(x['net'] for x in pnls_t)/len(pnls_t):+.2f}% 胜率={100*len(w)/len(pnls_t):.1f}% PF={pf_t:.2f}")

# 两腿合并: 简化拼接 PnL 分布 - 不给组合仓位排他约束(两腿并存)
combined_leg = events + tech
n_ev, n_tech = len(events), len(tech)
print(f"\n两腿合并: 事件{n_ev} + 技术{n_tech} = 总计{len(combined_leg)} 候选")

# 简化合并统计
tot_pnl = sum(x["pnl_pct"] for x in events) + sum(x["net"] for x in pnls_t)
print("合并统计: 事件PnL=" + str(sum(round(x["pnl_pct"],2) for x in events)))
print("合并统计: 技术PnL=" + str(round(sum(x["net"] for x in pnls_t), 2)))
print("总合并PnL={:+.0f}%, 平均={:+.2f}%, 中位={:+.2f}%".format(
    tot_pnl, tot_pnl/len(combined_leg), sorted([t["pnl_pct"] for t in events]+[t["net"] for t in pnls_t])[len(combined_leg)//2]))

# 按 regime 分析合并贡献再测一次
idx_map_path = r"E:\test\smc_project\research\_r38_index_sh000001.json"
idx_data = json.load(open(idx_map_path, encoding="utf-8"))
idx_sorted = sorted([(x["t"], x["c"]) for x in idx_data], key=lambda x: x[0])
idates = [x[0] for x in idx_sorted]
icloses = [x[1] for x in idx_sorted]
import bisect
def regime_f(d8):
    j = bisect.bisect_right(idates, d8) - 1
    if j < 20: return "MIX"
    ma20 = sum(icloses[j-19:j+1])/20
    ma10 = sum(icloses[j-9:j+1])/10
    c = icloses[j]
    if c > ma20 and ma10 >= ma20: return "UP"
    if c < ma20 and ma10 <= ma20: return "DOWN"
    return "MIX"

# 连环: 按 regime 拆分(使用 regime_f)
byr = defaultdict(lambda: {"n": 0, "sum": 0.0})
for x in events:
    r = regime_f(x["entry_date"].replace("-", ""))
    byr[r]["n"] += 1
    byr[r]["sum"] += x["pnl_pct"]
for t in tech:
    r = regime_f(t["entry_date"])
    byr[r]["n"] += 1
    byr[r]["sum"] += (t["exit_price"]/t["entry_price"]-1)*100
print("\n全集 regime 分布:")
for k in ("UP", "MIX", "DOWN"):
    b = byr.get(k, {"n": 0, "sum": 0})
    if b["n"]: print(f"  {k}: n={b['n']} avg={b['sum']/b['n']:+.2f}%")

# 分 regime 拆解
print("\n分 regime 拆解:")
for k in ("UP", "MIX", "DOWN"):
    ev_r = [x for x in events if regime_f(x["entry_date"].replace("-", "")) == k]
    tech_r = [t for t in tech if regime_f(t["entry_date"]) == k]
    if ev_r:
        pnls = [x["pnl_pct"] for x in ev_r]
        w = [x for x in pnls if x > 0]; l = [x for x in pnls if x <= 0]
        pf = sum(w)/abs(sum(l)) if sum(l) else 99
        print(f"  事件腿 {k}: n={len(ev_r)} avg={sum(pnls)/len(pnls):+.2f}% PF={pf:.2f}")
    if tech_r:
        pnls = [(t["exit_price"]/t["entry_price"]-1)*100 for t in tech_r]
        w = [x for x in pnls if x > 0]; l = [x for x in pnls if x <= 0]
        pf = sum(w)/abs(sum(l)) if sum(l) else 99
        print(f"  技术腿 {k}: n={len(tech_r)} avg={sum(pnls)/len(pnls):+.2f}% PF={pf:.2f}")
