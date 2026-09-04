# -*- coding: utf-8 -*-
"""SMC 反转腿 TP 结构敏感性：TP1 部分比例 + TP2 倍数"""
import io, json, os, sys
from collections import defaultdict
sys.path.insert(0, r"E:\test\smc_project\wdh")
import wdh_engine as we

KT = r"E:\test\smc_project\hermes\kline_cache_tencent"

# monkey-patch replay_tp2 with configurable tp1_frac / tp2_mult
def replay_tp2_cfg(seed, daily, tp1_frac=0.40, tp2_mult=2.0):
    entry_idx = int(seed["entry_idx"])
    if entry_idx >= len(daily) - 1:
        return None
    ep = we.f(seed["entry_price"])
    zone_low = we.f(seed["zone_low"])
    sweep_low = we.f(seed.get("sweep_low"))
    sl_base = min(zone_low, sweep_low) if sweep_low else zone_low
    sl = sl_base * we.SL_BUFFER
    risk = ep - sl
    if risk <= 0:
        return None
    tp1 = ep + 1.0 * risk
    tp2 = ep + tp2_mult * risk
    remaining = 1.0
    pnl = 0.0
    be_active = False
    for k in range(entry_idx + 1, min(len(daily), entry_idx + we.MAX_HOLD + 1)):
        bb = daily[k]
        hi, lo = bb["h"], bb["l"]
        stop = (ep if be_active else sl)
        if lo <= stop and hi >= tp1 and not be_active:
            pnl += remaining * (sl / ep - 1) * 100
            remaining = 0
            break
        if lo <= stop:
            pnl += remaining * (stop / ep - 1) * 100
            remaining = 0
            break
        if not be_active and hi >= tp1:
            pnl += tp1_frac * (tp1 / ep - 1) * 100
            remaining = 1 - tp1_frac
            be_active = True
            continue
        if be_active and hi >= tp2:
            pnl += remaining * (tp2 / ep - 1) * 100
            remaining = 0
            break
    if remaining > 0:
        last = daily[min(len(daily), entry_idx + we.MAX_HOLD) - 1]["c"]
        pnl += remaining * (last / ep - 1) * 100
    return {"entry_date": daily[entry_idx + 1]["t"], "net_pnl_pct": round(pnl - we.FEE, 4)}


def run_cfg(tp1_frac, tp2_mult, limit=600):
    trades = []
    for f in sorted(os.listdir(KT)):
        if not f.endswith("_daily_800.json"):
            continue
        sym = f.replace("_daily_800.json", "").replace("_", ".", 1)
        daily = we.bars_for(os.path.join(KT, f))
        if len(daily) < 300:
            continue
        for sd in we.build_seeds(sym, daily):
            r20 = sd.get("r20")
            if r20 == "" or r20 is None or not (0 <= float(r20) < 0.15):
                continue
            tr = replay_tp2_cfg(sd, daily, tp1_frac, tp2_mult)
            if tr:
                trades.append(tr)
        if len(trades) > limit:
            break
    return trades


def report(label, trades):
    if len(trades) < 50:
        print(f"{label}: n={len(trades)} (过小)")
        return
    pnls = [t["net_pnl_pct"] for t in trades]
    wins = [x for x in pnls if x > 0]
    losses = [x for x in pnls if x <= 0]
    wr = 100 * len(wins) / len(pnls)
    avg = sum(pnls) / len(pnls)
    pf = (sum(wins) / abs(sum(losses))) if losses else 99
    print(f"{label}: n={len(pnls)} WR={wr:.1f}% avg={avg:+.2f}% PF={pf:.2f}")


print("=== SMC 反转腿 TP 结构敏感性 ===\n")
# TP1 fraction sweep (TP2=2R)
for frac in (0.30, 0.40, 0.50, 0.60):
    t = run_cfg(frac, 2.0)
    report(f"TP1={frac:.0%} (TP2=2R)", t)
print()
# TP2 multiplier sweep (TP1=40%)
for mult in (1.5, 2.0, 2.5, 3.0):
    t = run_cfg(0.40, mult)
    report(f"TP2={mult}R (TP1=40%)", t)
