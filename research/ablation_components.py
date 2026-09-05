# -*- coding: utf-8 -*-
"""迭代五-真组件消融：build_seeds 组件开关（每轮只关一个，独立种子集）
全开(生产) vs 关vol vs 关disp vs 关poi vs 关retest → 找增量贡献最大的组件。
固定数据集(300只) × 固定执行(TP>=1.5R)。
"""
import io, json, os, sys
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, r"E:\test\smc_project\wdh")

import wdh_engine as WE
import core.execution as EX
from core.metrics import stats_of

KLINE = r"E:\test\smc_project\hermes\kline_cache"
LIMIT = 500

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

def run_variant(daily_map, kwargs, tag):
    pn = []
    n_seed = 0
    for code, daily in daily_map.items():
        sym = code[:6] + (".SH" if code.startswith("6") else ".SZ")
        try:
            seeds = WE.build_seeds(sym, daily, **kwargs)[:40]
        except Exception as e:
            print(f"  {tag} {code} err {e}", flush=True)
            continue
        n_seed += len(seeds)
        for sd in seeds:
            entry_idx = int(sd["entry_idx"])
            if entry_idx >= len(daily) - 1:
                continue
            ep = WE.f(sd["entry_price"])
            zl = WE.f(sd["zone_low"])
            sw = WE.f(sd.get("sweep_low"))
            sl = (min(zl, sw) if sw else zl) * WE.SL_BUFFER
            risk = ep - sl
            if risk <= 0:
                continue
            tgt = max(WE.f(sd.get("weekly_target")) or WE.f(sd.get("target")), ep + 1.5 * risk)
            r = EX.simulate(daily, entry_idx, ep, sl, tp2=tgt, max_hold=WE.MAX_HOLD)
            if not r.get("skipped") and r.get("net_pnl_pct") is not None:
                pn.append(r["net_pnl_pct"])
    return n_seed, stats_of(pn)

def fmt(s):
    return "n=%d avg=%+.2f%% wr=%.0f%% PF=%.2f payoff=%.2f" % (
        s["n"], s["avg"], s["win"]*100, s["pf"], s["payoff"]) if s else "n=0"

if __name__ == "__main__":
    # 信号充足分散池（顺序取前 N 只常为低波动 000xxx，信号少；间隔抽样覆盖各代码段）
    files = sorted(f for f in os.listdir(KLINE) if f.endswith("_daily_750.json"))[::11]
    daily_map = {}
    for p in files:
        daily = load_daily(os.path.join(KLINE, p))
        if len(daily) >= 300:
            daily_map[p.split("_")[0]] = daily
    print(f"数据: {len(daily_map)} 只", flush=True)

    variants = [
        ("全开(生产)", dict()),
        ("关vol量能", dict(vol_filter=False)),
        ("关displacement位移", dict(displacement_filter=False)),
        ("关poi回踩等待", dict(poi_filter=False)),
        ("关retest守位", dict(retest_filter=False)),
    ]
    print("\n=== 真组件消融（每轮只关一个）===")
    out = []
    for tag, kw in variants:
        n_seed, s = run_variant(daily_map, kw, tag)
        out.append({"variant": tag, "seeds": n_seed, "stats": s})
        print(f"  {tag}: seeds={n_seed} | {fmt(s)}", flush=True)

    # 汇总 + 增量判断
    print("\n=== 组件增量（相对全开）===")
    base = out[0]["stats"]
    if base and base["n"] > 0:
        base_avg = base["avg"]
        for o in out[1:]:
            s = o["stats"]
            if s and s["n"] > 0:
                delta = s["avg"] - base_avg
                # 关组件后 avg 下降越多 → 该组件贡献越大
                print(f"  关 {o['variant']}: avg {s['avg']:+.2f}% (Δ{delta:+.2f}pp vs 全开 {base_avg:+.2f}%) → "
                      f"{'组件有正贡献' if delta < -0.2 else ('组件无贡献/可移除' if delta > 0.2 else '中性')}")
            else:
                print(f"  关 {o['variant']}: 无交易（该组件是必要门槛）")

    with open(os.path.join(os.path.dirname(os.path.abspath(__file__)), "handover", "SMC组件消融结果.json"), "w", encoding="utf-8") as fh:
        json.dump([{"variant": o["variant"], "seeds": o["seeds"],
                    "stats": {k: (round(v, 4) if isinstance(v, float) else v) for k, v in (o["stats"] or {}).items()}} for o in out],
                  fh, ensure_ascii=False, indent=1)
    print("\n结果已存 handover/SMC组件消融结果.json")
