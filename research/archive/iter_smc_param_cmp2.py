# -*- coding: utf-8 -*-
"""SMC 参数对比回测 v2：OLD vs NEW(confirmed BOS + 1.5% sweep)"""
import io, json, os, sys, importlib
from collections import defaultdict

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
sys.path.insert(0, r"E:\test\smc_project\wdh")
import wdh_engine as we

KT = r"E:\test\smc_project\hermes\kline_cache_tencent"
new_pivot, new_sweep, new_strong = we.PIVOT_L, we.SWEEP_PCT, we.STRONG_BOS

def run_all(limit=500):
    trades = []
    for f in sorted(os.listdir(KT)):
        if not f.endswith("_daily_800.json"): continue
        if len(trades) > limit: break
        sym = f.replace("_daily_800.json", "").replace("_", ".", 1)
        daily = we.bars_for(os.path.join(KT, f))
        if len(daily) < 300: continue
        for sd in we.build_seeds(sym, daily):
            r20 = sd.get("r20")
            if r20 == "" or r20 is None or not (0 <= float(r20) < 0.15): continue
            tr = we.replay_tp2(sd, daily)
            if tr:
                trades.append({"entry_date": str(tr["entry_date"]), "net_pnl_pct": tr["net_pnl_pct"]})
    return trades

def report(label, trades):
    if len(trades) < 30: print(f"{label}: n={len(trades)} (过小)"); return
    pnls = [t["net_pnl_pct"] for t in trades]
    wins = [x for x in pnls if x > 0]; losses = [x for x in pnls if x <= 0]
    wr = 100 * len(wins) / len(pnls)
    avg = sum(pnls) / len(pnls)
    pf = (sum(wins) / abs(sum(losses))) if losses else 99
    by_y = defaultdict(list)
    for t in trades: by_y[str(t["entry_date"])[:4]].append(t["net_pnl_pct"])
    line = f"{label}: n={len(pnls)} WR={wr:.1f}% avg={avg:+.2f}% PF={pf:.2f}"
    for y in ("2024", "2025", "2026"):
        if by_y.get(y): line += f" | {y}:{sum(by_y[y])/len(by_y[y]):+.2f}%"
    print(line)

# OLD v1
we.PIVOT_L = we.PIVOT_R = 3; we.SWEEP_PCT = 0.003; we.STRONG_BOS = False
o1 = run_all()
report("OLD(P3/S0.3/close-BOS)", o1)

# NEW v2 (pivot5, sweep1.0%, confirmed BOS)
we.PIVOT_L = we.PIVOT_R = 5; we.SWEEP_PCT = 0.01; we.STRONG_BOS = True
n1 = run_all()
report("NEW(P5/S1.0/confirmed-BOS)", n1)

# NEW v3 (pivot5, sweep1.5%, confirmed BOS)
we.PIVOT_L = we.PIVOT_R = 5; we.SWEEP_PCT = 0.015; we.STRONG_BOS = True
n2 = run_all()
report("NEW(P5/S1.5/confirmed-BOS)", n2)

# NEW v4 (pivot7, sweep1.0%, confirmed BOS)
we.PIVOT_L = we.PIVOT_R = 7; we.SWEEP_PCT = 0.01; we.STRONG_BOS = True
n3 = run_all()
report("NEW(P7/S1.0/confirmed-BOS)", n3)

we.PIVOT_L = we.PIVOT_R = new_pivot; we.SWEEP_PCT = new_sweep; we.STRONG_BOS = new_strong
print("done")