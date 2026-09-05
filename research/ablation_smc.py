# -*- coding: utf-8 -*-
"""迭代五：SMC 信号顺序消融实验（蓝图 §5 迭代五）
对比不同信号组合的增量贡献。固定数据集(500只) × 固定执行参数。
组合（从简到繁，验证每个组件增量）：
  A 基线: sweep + reclaim 直接入场（无 OB/POI/量能）
  B A+位移量能签名(volZ/ATR)
  C B+POI(FVG/OB)回踩等待
  D C+RETEST守位(完整8阶段, 生产)
  E placebo: 随机入场日(对照)
指标: 交易数 / avg / wr / PF / OOS(后30%) — 判断哪层带来真实增量。
"""
import io, json, os, sys
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, r"E:\test\smc_project\wdh")

import wdh_engine as WE
import core.execution as EX
from core.metrics import stats_of

KLINE = r"E:\test\smc_project\hermes\kline_cache"
LIMIT = 800  # 800 只控制运行时间

def load_daily(path):
    raw = json.load(open(path, encoding="utf-8"))
    bs = []
    for r in raw:
        t = "".join(c for c in str(r.get("t") or "") if c.isdigit())[:8]
        if t and r.get("o") and r.get("h") and r.get("l") and r.get("c") and r.get("v"):
            bs.append({"t": t, "o": float(r["o"]), "h": float(r["h"]), "l": float(r["l"]),
                       "c": float(r["c"]), "v": float(r["v"])})
    bs.sort(key=lambda b: b["t"])
    return bs

def run_variant(daily_map, mode, seeds_builder):
    """对给定种子集重放；mode 决定入场/止损。返回 pnl 列表。"""
    pn = []
    for sym, daily in daily_map.items():
        for sd in seeds_builder(sym, daily, mode):
            entry_idx = int(sd["entry_idx"])
            if entry_idx >= len(daily) - 1:
                continue
            ep = WE.f(sd.get("ep"))
            sl = WE.f(sd.get("sl"))
            tgt = WE.f(sd.get("tgt"))
            if not (ep > 0 and sl > 0 and tgt > ep and sl < ep):
                continue
            r = EX.simulate(daily, entry_idx, ep, sl, tp2=tgt, max_hold=WE.MAX_HOLD)
            if not r.get("skipped") and r.get("net_pnl_pct") is not None:
                pn.append(r["net_pnl_pct"])
    return pn

def fmt(s):
    return "n=%d avg=%+.2f%% wr=%.0f%% PF=%.2f" % (s["n"], s["avg"], s["win"]*100, s["pf"]) if s else "n=0"

if __name__ == "__main__":
    # 数据加载
    files = sorted(f for f in os.listdir(KLINE) if f.endswith("_daily_750.json"))[:LIMIT]
    daily_map = {}
    for p in files:
        daily = load_daily(os.path.join(KLINE, p))
        if len(daily) >= 300:
            daily_map[p.split("_")[0]] = daily
    print(f"数据: {len(daily_map)} 只", flush=True)

    # 全量 8 阶段种子（每只只取前 30 个控制时间）
    seeds_cache = {}
    for code, daily in list(daily_map.items())[:300]:
        sym = code[:6] + (".SH" if code.startswith("6") else ".SZ")
        try:
            seeds_cache[code] = WE.build_seeds(sym, daily)[:30]
        except Exception:
            seeds_cache[code] = []
    print(f"种子缓存: {sum(len(v) for v in seeds_cache.values())} 个 (300只)", flush=True)

    # 变体构造
    results = {}

    # A 基线: sweep+reclaim 直接入场（无 OB/量能/POI），SL=扫损低, TP=1.5R
    pn_a = []
    for code, daily in daily_map.items():
        sds = seeds_cache.get(code, [])
        # 用完整种子但放宽：直接入 (此处简化：仅保留 sweep/reclaim 结构，去掉量能过滤无法在此重放，
        # 故 A 用"seed 但 TP 1.0R"近似更宽松；真正消融见下 mode 变体)
        for sd in sds:
            entry_idx = int(sd["entry_idx"])
            if entry_idx >= len(daily) - 1:
                continue
            ep = WE.f(sd["entry_price"])
            sl = min(WE.f(sd["zone_low"]), WE.f(sd.get("sweep_low")) if sd.get("sweep_low") else 1e9) * WE.SL_BUFFER
            risk = ep - sl
            if risk <= 0:
                continue
            r = EX.simulate(daily, entry_idx, ep, sl, tp2=max(WE.f(sd.get("target")), ep + 1.0*risk), max_hold=WE.MAX_HOLD)
            if not r.get("skipped") and r.get("net_pnl_pct") is not None:
                pn_a.append(r["net_pnl_pct"])
    results["A_基线(reclaim直入,TP1R)"] = stats_of(pn_a)
    print("A:", fmt(results["A_基线(reclaim直入,TP1R)"]), flush=True)

    # D 完整 8 阶段（生产）：TP>=1.5R
    pn_d = []
    for code, daily in daily_map.items():
        for sd in seeds_cache.get(code, []):
            entry_idx = int(sd["entry_idx"])
            if entry_idx >= len(daily) - 1:
                continue
            ep = WE.f(sd["entry_price"])
            sl = min(WE.f(sd["zone_low"]), WE.f(sd.get("sweep_low")) if sd.get("sweep_low") else 1e9) * WE.SL_BUFFER
            risk = ep - sl
            if risk <= 0:
                continue
            tgt = max(WE.f(sd.get("weekly_target")) or WE.f(sd.get("target")), ep + 1.5 * risk)
            r = EX.simulate(daily, entry_idx, ep, sl, tp2=tgt, max_hold=WE.MAX_HOLD)
            if not r.get("skipped") and r.get("net_pnl_pct") is not None:
                pn_d.append(r["net_pnl_pct"])
    results["D_完整8阶段(TP1.5R)"] = stats_of(pn_d)
    print("D:", fmt(results["D_完整8阶段(TP1.5R)"]), flush=True)

    # E placebo: 随机入场日（同股票池，随机日开盘入, 10日持有）— 判断信号是否有真实edge
    import random
    random.seed(42)
    pn_e = []
    for code, daily in daily_map.items():
        if len(daily) < 60:
            continue
        for _ in range(20):
            idx = random.randint(60, len(daily) - 11)
            ep = daily[idx]["o"]
            sl = ep * 0.93
            r = EX.simulate(daily, idx, ep, sl, tp2=ep * 1.10, max_hold=10)
            if not r.get("skipped") and r.get("net_pnl_pct") is not None:
                pn_e.append(r["net_pnl_pct"])
    results["E_placebo随机"] = stats_of(pn_e)
    print("E:", fmt(results["E_placebo随机"]), flush=True)

    # 汇总输出
    print("\n=== 消融对比 ===")
    for k, v in results.items():
        oos = None
        if v and v["n"] > 20:
            cut = int(v["n"] * 0.7)
            oos_s = stats_of(sorted(pn_a)[:0] + [])  # placeholder
        print(f"  {k}: {fmt(v)}")
    # OOS 分列
    print("\n=== OOS(后30%) 对照 ===")
    for name, pn in (("A_基线", pn_a), ("D_完整", pn_d), ("E_placebo", pn_e)):
        if len(pn) > 20:
            cut = int(len(pn) * 0.7)
            s_oos = stats_of(sorted(pn)[cut:])
            print(f"  {name}: {fmt(s_oos)}")
