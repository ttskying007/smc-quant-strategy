# -*- coding: utf-8 -*-
"""r38_frontend_sync.py —— R38 研究结果前端同步生成器.
聚合 回测/选股/复盘 三类结果 → 紧凑 JSON(E:\test\smc_project\research\r38_frontend.json),
由 web_server /api/r38 端点提供给前端面板(轮询实时同步)。
- 事件腿聚合: 从 combo_v20f_trades.csv 现算(快, ~2000行)
- 技术腿: 从 r38_tech_cache.json 加载; 缺失时全市场扫描一次并缓存(慢, ~4-5分钟)
- 复盘: 迭代日志/结论(每轮研究后由本脚本常量更新)
用法: python r38_frontend_sync.py [--rescan-tech]
"""
import csv, io, json, os, sys, bisect
from collections import defaultdict
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
sys.path.insert(0, r"E:\test\smc_project\research")

HERE = r"E:\test\smc_project\research"
OUT = os.path.join(HERE, "r38_frontend.json")
TECH_CACHE = os.path.join(HERE, "r38_tech_cache.json")
KT = r"E:\test\smc_project\hermes\kline_cache_tencent"
RESCAN = "--rescan-tech" in sys.argv

# ---------- 指数 regime ----------
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

def stats(pnls):
    if not pnls: return None
    w = [x for x in pnls if x > 0]; l = [x for x in pnls if x <= 0]
    pf = round(sum(w)/abs(sum(l)), 2) if sum(l) else 99
    return {"n": len(pnls), "avg": round(sum(pnls)/len(pnls), 2),
            "wr": round(100*len(w)/len(pnls), 1), "pf": pf, "sum": round(sum(pnls), 1)}

# ---------- 事件腿(冻结基线 EVENT) ----------
rows = list(csv.DictReader(open(os.path.join(HERE, "combo_v20f_trades.csv"), encoding="utf-8-sig")))
ev = [r for r in rows if r.get("src") == "EVENT"]
def f(x, d=0.0):
    try: return float(x)
    except: return d

bt = {"base": stats([f(r["net_pnl_pct"]) for r in ev])}
byy = defaultdict(list); bym = defaultdict(list); byex = defaultdict(list)
byreg = defaultdict(list); rrs = []
for r in ev:
    p = f(r["net_pnl_pct"]); d8 = r.get("entry_date") or ""
    byy[d8[:4]].append(p); bym[d8[4:6]].append(p)
    byex[r.get("reason") or "?"].append(p)
    byreg[regime(d8)].append(p)
    rr = r.get("rr_exit")
    if rr:
        try: rrs.append(float(rr))
        except: pass
bt["yearly"] = {y: stats(ps) for y, ps in sorted(byy.items())}
bt["monthly"] = {m: stats(ps) for m, ps in sorted(bym.items())}
bt["exits"] = {k: stats(ps) for k, ps in sorted(byex.items(), key=lambda kv: -len(kv[1]))[:8]}
bt["regime"] = {k: stats(ps) for k, ps in sorted(byreg.items())}
if rrs:
    bt["rr"] = {"le_m1": round(100*sum(1 for x in rrs if x <= -1)/len(rrs), 1),
                "mid": round(100*sum(1 for x in rrs if -1 < x < 1)/len(rrs), 1),
                "ge_1": round(100*sum(1 for x in rrs if x >= 1)/len(rrs), 1)}

# ---------- 技术腿 V2(量能确认) ----------
def scan_tech():
    files = sorted(fn for fn in os.listdir(KT) if fn.endswith("_daily_800.json"))
    out = []
    for path in files:
        try:
            raw = json.load(open(os.path.join(KT, path), encoding="utf-8"))
        except Exception:
            continue
        bs = []
        for r in raw:
            t = "".join(x for x in str(r.get("t") or "") if x.isdigit())[:8]
            if t and r.get("o") and r.get("h") and r.get("l") and r.get("c") and r.get("v"):
                bs.append({"t": t, "o": float(r["o"]), "h": float(r["h"]), "l": float(r["l"]),
                           "c": float(r["c"]), "v": float(r["v"])})
        bs.sort(key=lambda b: b["t"])
        for i in range(25, len(bs)-11):
            d = bs[i]["t"]
            if not ("20230901" <= d <= "20260831"): continue
            window = bs[max(0, i-20):i-3]
            if not window: continue
            prev_low = min(b["l"] for b in window)
            if not (bs[i]["l"] < prev_low*0.995 and bs[i+1]["c"] > prev_low and bs[i+1]["o"] > bs[i]["h"]):
                continue
            v20 = sum(b["v"] for b in bs[max(0, i-20):i])/20 if i >= 20 else 0
            if not (v20 > 0 and bs[i]["v"] > v20*1.5): continue
            ep = bs[i+1]["o"]; ex = bs[i+10]["c"]
            if ep <= 0: continue
            out.append({"s": path.split("_")[0], "d": d, "p": round((ex/ep-1)*100, 2)})
    return out

if RESCAN or not os.path.exists(TECH_CACHE):
    print("技术腿全市场扫描(首次/强制)…")
    tech = scan_tech()
    json.dump(tech, open(TECH_CACHE, "w", encoding="utf-8"), ensure_ascii=False)
    print(f"缓存 {len(tech)} 笔 → {TECH_CACHE}")
else:
    tech = json.load(open(TECH_CACHE, encoding="utf-8"))

tech_pnls = [t["p"] for t in tech]
sel = {"tech_v2": stats(tech_pnls)}
sel["pool"] = {"total_announce": 982443, "positive_events": 10151, "positive_pct": 1.1,
               "event_baseline": 1640, "tech_candidates": len(tech),
               "merged": 1640 + len(tech), "merged_per_day": round((1640+len(tech))/750, 1)}
tbyy = defaultdict(list); tbyreg = defaultdict(list)
for t in tech:
    tbyy[t["d"][:4]].append(t["p"]); tbyreg[regime(t["d"])].append(t["p"])
sel["tech_yearly"] = {y: stats(ps) for y, ps in sorted(tbyy.items())}
sel["tech_regime"] = {k: stats(ps) for k, ps in sorted(tbyreg.items())}
sel["tech_top"] = sorted(tech, key=lambda t: -t["p"])[:20]

# ---------- 两腿合并 ----------
merged_pnls = [f(r["net_pnl_pct"]) for r in ev] + tech_pnls
merged = {"combined": stats(merged_pnls), "event_pnl": bt["base"]["sum"], "tech_pnl": sel["tech_v2"]["sum"]}
mreg = defaultdict(list)
for r in ev: mreg[regime(r.get("entry_date") or "")].append(f(r["net_pnl_pct"]))
for t in tech: mreg[regime(t["d"])].append(t["p"])
merged["regime"] = {k: stats(ps) for k, ps in sorted(mreg.items())}

# ---------- 复盘(迭代日志, 每轮研究后更新) ----------
review = {
    "verdicts": [
        {"id": "A1", "name": "缠论3买分层(事件腿)", "result": "证伪",
         "detail": "3买型 avg+1.26/PF1.82 < 非3买 +3.92/3.45 —— 事件驱动≠趋势突破"},
        {"id": "B1", "name": "Wyckoff spring 止损", "result": "证伪",
         "detail": "70%触发但 avg-0.14pp —— 收紧SL打掉回摆单"},
        {"id": "C1", "name": "指数UP-regime过滤", "result": "修正废弃",
         "detail": "生产_market_proxy分桶: 弱市信号最好(PF3.98) —— C1方向相反, 2024-25通过是样本巧合"},
        {"id": "V2", "name": "技术腿量能确认", "result": "验证通过",
         "detail": "vol>1.5×20日均: PF1.53→2.63, avg+5.28% —— Volume Analysis扫损需参与度"},
        {"id": "MERGE", "name": "两腿合并", "result": "互补确认",
         "detail": "事件腿吃UP趋势市(PF5.54), 技术腿吃MIX震荡市(PF7.13) —— 每 regime 都有强信号源"},
    ],
    "production": [
        "生产 _market_proxy 弱市加仓机制正确保持(已验证 PF3.20→3.64)",
        "生产候选: 事件腿×生产proxy加权(现状)",
        "下一候选: 技术腿V2×量能确认×regime仓位系数(MIX满/UP减/DOWN停)——待审计",
    ],
    "iterations": [
        {"round": "R38a", "commit": "351ebd8", "content": "三维复盘+多学派诊断+A1/B1证伪+C1初验"},
        {"round": "R38b", "commit": "017f964", "content": "C1敏感性+组合闸+候选池边界"},
        {"round": "R38c", "commit": "5535160", "content": "仓位缩放+2026特异性+技术腿可行性"},
        {"round": "R38d", "commit": "9f673a3", "content": "C1修正废弃(生产proxy正确)+量能闸验证+000157断言状态化"},
        {"round": "R38e", "commit": "7fbae53", "content": "两腿合并评估(信号×环境互补)"},
        {"round": "R38f", "commit": "-", "content": "前端同步+技术腿SL/TP同口径回测(进行中)"},
    ],
    "schools": {"ICT/SMC": 1250, "PriceAction": 229, "ChanLun缠论": 110, "Indicator": 214,
                "OrderFlow": 34, "Volume/VSA": 10, "Wyckoff": 5, "ElliottWave": 8, "TheStrat": 4},
}

data = {"updated": __import__("datetime").datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "backtest": bt, "selection": sel, "merged": merged, "review": review}
json.dump(data, open(OUT, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
print(f"→ {OUT} ({os.path.getsize(OUT)} bytes)")
print(f"  事件腿 n={bt['base']['n']} PF={bt['base']['pf']} | 技术腿 n={sel['tech_v2']['n']} PF={sel['tech_v2']['pf']}")
print(f"  合并 n={merged['combined']['n']} avg={merged['combined']['avg']}%")
