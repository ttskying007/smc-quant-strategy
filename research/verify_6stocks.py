# -*- coding: utf-8 -*-
"""规范第4步：6只不同波动股票 × 周期一致性验证
选 高/中/低 波动各 2 只，验证 8 阶段信号时间序产生信号、IS/OOS 指标方向一致。
"""
import io, json, os, sys
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, r"E:\test\smc_project\wdh")

import wdh_engine as WE
import core.execution as EX
from core.metrics import stats_of, fmt

KLINE = r"E:\test\smc_project\hermes\kline_cache"
# 6 只不同波动代表股（高：创业板/科创 30x/68x；中：沪深主板；低：大盘蓝筹）
CASES = ["300750_SZ", "688981_SH", "000858_SZ", "600519_SH", "000002_SZ", "601318_SH"]

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

def atr_pct(bs):
    # 平均 ATR%（衡量波动）
    if len(bs) < 15:
        return 0
    vals = []
    for k in range(len(bs) - 15, len(bs)):
        tr = max(bs[k]["h"] - bs[k]["l"], abs(bs[k]["h"] - bs[k - 1]["c"]), abs(bs[k]["l"] - bs[k - 1]["c"]))
        vals.append(tr / bs[k]["c"])
    return sum(vals) / len(vals) * 100

print("=== 6 只不同波动股票 8阶段信号时间序验证 ===")
for code in CASES:
    path = os.path.join(KLINE, code + "_daily_750.json")
    if not os.path.exists(path):
        print(f"{code}: 无数据")
        continue
    daily = load_daily(path)
    if len(daily) < 300:
        print(f"{code}: 数据不足")
        continue
    sym = code.replace("_", ".", 1)
    av = atr_pct(daily)
    seeds = WE.build_seeds(sym, daily)
    # 重放
    pn = []
    for sd in seeds:
        entry_idx = int(sd["entry_idx"])
        if entry_idx >= len(daily):
            continue
        ep = WE.f(sd["entry_price"]); zl = WE.f(sd["zone_low"]); sw = WE.f(sd.get("sweep_low"))
        sl = min(zl, sw) if sw else zl; sl *= WE.SL_BUFFER
        tgt = WE.f(sd.get("weekly_target")) or WE.f(sd.get("target"))
        risk = ep - sl
        if risk <= 0 or tgt <= ep:
            continue
        tgt = max(tgt, ep + 1.5 * risk)
        r = EX.simulate(daily, entry_idx, ep, sl, tp2=tgt, max_hold=WE.MAX_HOLD)
        if not r.get("skipped") and r.get("net_pnl_pct") is not None:
            pn.append(r["net_pnl_pct"])
    s = stats_of(pn)
    # IS/OOS
    if len(pn) > 10:
        cut = int(len(pn) * 0.7)
        s_is, s_oos = stats_of(pn[:cut]), stats_of(pn[cut:])
        oos_txt = "IS%s OOS%s" % (("avg%+.2f" % s_is["avg"]) if s_is else "-", ("avg%+.2f" % s_oos["avg"]) if s_oos else "-")
    else:
        oos_txt = "样本不足"
    print(f"{sym} | ATR%={av:.2f} | seeds={len(seeds)} trades={len(pn)} | " + (fmt(s) if s else "无交易") + f" | {oos_txt}")

print("\n注：一致性判断 = 各波动档均能产生信号，且收益方向一致（正/负）；低波动档信号较少属正常（扫损/位移更少）。")