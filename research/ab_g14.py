# -*- coding: utf-8 -*-
"""G14/G16 实验：SL分板块ATR化 + BOS严格(已确认摆动高) 对信号量/质量的影响（A/B，不碰生产）
用 build_seeds 输出的 seeds + core.execution 重放，替换 SL/TP 计算对比。
"""
import io, json, os, sys
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
sys.path.insert(0, r"E:\test\smc_project\research")
sys.path.insert(0, r"E:\test\smc_project\wdh")
import wdh_engine as WE
import core.execution as EX

KLINE = r"E:\test\smc_project\hermes\kline_cache"

def load(path):
    raw = json.load(open(path, encoding="utf-8"))
    bs = []
    for r in raw:
        t = "".join(c for c in str(r.get("t") or "") if c.isdigit())[:8]
        if t and r.get("o") and r.get("h") and r.get("l") and r.get("c") and r.get("v"):
            bs.append({"t": t, "o": float(r["o"]), "h": float(r["h"]), "l": float(r["l"]),
                       "c": float(r["c"]), "v": float(r["v"])})
    bs.sort(key=lambda b: b["t"])
    return bs

def board_k(code):
    return 0.8 if code.startswith(("300", "301", "688")) else (1.0 if code.startswith(("4", "8", "9")) else 0.5)

def run(daily_map, sl_mode):
    pn = []
    tot = 0
    for code, d in daily_map.items():
        sym = code + (".SH" if code.startswith("6") else ".SZ")
        seeds = WE.build_seeds(sym, d)
        tot += len(seeds)
        for sd in seeds:
            ei = int(sd["entry_idx"])
            if ei >= len(d) - 1:
                continue
            ep = WE.f(sd["entry_price"]); zl = WE.f(sd["zone_low"]); sw = WE.f(sd.get("sweep_low"))
            if sl_mode == "min99":
                sl = (min(zl, sw) if sw else zl) * 0.99
            else:  # atr_k: POI下沿 − k×ATR（分板块 k）
                _atr = WE.atr_of(d, ei - 1) or 0
                k = board_k(code)
                sl = zl - k * _atr
            risk = ep - sl
            if risk <= 0:
                continue
            tgt = max(WE.f(sd.get("weekly_target")) or WE.f(sd.get("target")), ep + 1.5 * risk)
            r = EX.simulate(d, ei, ep, sl, tp2=tgt, max_hold=WE.MAX_HOLD)
            if not r.get("skipped") and r.get("net_pnl_pct") is not None:
                pn.append(r["net_pnl_pct"])
    if pn:
        n = len(pn); mean = sum(pn) / n
        wins = [x for x in pn if x > 0]
        p = sum(wins) / abs(sum(x for x in pn if x <= 0)) if any(x <= 0 for x in pn) else 99
        return tot, n, mean, len(wins) / n, p
    return tot, 0, 0, 0, 0

if __name__ == "__main__":
    files = sorted(f for f in os.listdir(KLINE) if f.endswith("_daily_750.json"))[::9][:300]
    daily_map = {}
    for p in files:
        d = load(os.path.join(KLINE, p))
        if len(d) >= 300:
            daily_map[p.split("_")[0]] = d
    print(f"数据: {len(daily_map)} 只（间隔抽样）")
    for mode in ("min99", "atr_k"):
        t, n, a, w, p = run(daily_map, mode)
        print(f"SL={mode}: seeds={t} trades={n} avg={a:+.2f}% wr={w*100:.0f}% PF={p:.2f}")
