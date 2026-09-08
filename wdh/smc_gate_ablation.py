# -*- coding: utf-8 -*-
"""V1 蓝图迭代2前置：SMC 逐门消融（cascade ablation）
臂: full / -W1 / -sweepVol / -dispSig / -strongBOS
输出: 每臂 IS/OOS 笔数、avg、WR、PF → handover/SMC逐门消融.json
"""
import sys, os, csv, json, io, time
sys.path.insert(0, r"E:\test\smc_project\wdh")
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
import wdh_engine as W

OOS = "20250701"
ARMS = {
    "full":         {},
    "no_W1":        {"w1": False},
    "no_sweepVol":  {"sweep_vol": False},
    "no_dispSig":   {"disp_sig": False},
    "no_strongBOS": {"strong_bos": False},
}

def _stats(trs, oos):
    sel = [t for t in trs if t.get("net_pnl_pct") is not None and ((t["entry_date"] >= OOS) == oos)]
    if not sel:
        return {"n": 0, "avg": 0.0, "wr": 0.0, "pf": 0.0}
    pn = [t["net_pnl_pct"] for t in sel]
    w = [x for x in pn if x > 0]
    return {"n": len(pn), "avg": round(sum(pn)/len(pn), 3), "wr": round(len(w)/len(pn), 3),
            "pf": round(sum(w)/abs(sum(x for x in pn if x <= 0)), 2) if any(x <= 0 for x in pn) and sum(x for x in pn if x <= 0) != 0 else 99}

files = sorted(p for p in os.listdir(W.KLINE) if p.endswith("_daily_800.json"))
out = {"asof": time.strftime("%Y-%m-%d %H:%M:%S"), "oos_from": OOS, "arms": {}}
for name, gates in ARMS.items():
    t0 = time.time()
    seeds_n, trades = 0, []
    for p in files:
        daily = W.bars_for(os.path.join(W.KLINE, p))
        if len(daily) < 300:
            continue
        sym = p.replace("_daily_800.json", "").replace("_", ".", 1)
        for sd in W.build_seeds(sym, daily, gates):
            seeds_n += 1
            tr = W.replay(sd, daily)
            if tr:
                trades.append(tr)
    arms_stat = {"seeds": seeds_n, "IS": _stats(trades, False), "OOS": _stats(trades, True),
                 "seconds": round(time.time() - t0, 1)}
    out["arms"][name] = arms_stat
    print(f"{name}: seeds={seeds_n} IS={arms_stat['IS']} OOS={arms_stat['OOS']} ({arms_stat['seconds']}s)", flush=True)
    with open(os.path.join(W.OUT, f"ablation_trades_{name}.csv"), "w", newline="", encoding="utf-8-sig") as fh:
        w = csv.DictWriter(fh, fieldnames=["symbol","entry_date","net_pnl_pct","reason","hold_bars","t1_violation"])
        w.writeheader()
        for t in trades:
            w.writerow(t)

with open(r"E:\test\smc_project\research\handover\SMC逐门消融.json", "w", encoding="utf-8") as fh:
    json.dump(out, fh, ensure_ascii=False, indent=2)
print("已写 handover/SMC逐门消融.json")