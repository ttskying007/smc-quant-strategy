# -*- coding: utf-8 -*-
"""SMC 反转腿参数对比回测：OLD(3/0.3%/close-BOS) vs NEW(5/1.5%/strong-BOS)
用 wdh_engine 两套参数跑 2024-2026，对比信号质量"""
import io, json, os, sys, importlib
from collections import defaultdict

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
sys.path.insert(0, r"E:\test\smc_project\wdh")
import wdh_engine as we

KT = r"E:\test\smc_project\hermes\kline_cache_tencent"

# save current (NEW) params
new_pivot, new_sweep, new_strong = we.PIVOT_L, we.SWEEP_PCT, we.STRONG_BOS

def run_all(limit=400):
    """Run SMC reversal leg with current params; returns trades."""
    trades = []
    n_files = 0
    for f in sorted(os.listdir(KT)):
        if not f.endswith("_daily_800.json"):
            continue
        n_files += 1
        if n_files > limit:
            break
        sym = f.replace("_daily_800.json", "").replace("_", ".", 1)
        daily = we.bars_for(os.path.join(KT, f))
        if len(daily) < 300:
            continue
        for sd in we.build_seeds(sym, daily):
            r20 = sd.get("r20")
            if r20 == "" or r20 is None or not (0 <= float(r20) < 0.15):
                continue
            tr = we.replay_tp2(sd, daily)
            if tr:
                trades.append({"entry_date": str(tr["entry_date"]), "net_pnl_pct": tr["net_pnl_pct"]})
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
    by_y = defaultdict(list)
    for t in trades:
        by_y[str(t["entry_date"])[:4]].append(t["net_pnl_pct"])
    line = f"{label}: n={len(pnls)} WR={wr:.1f}% avg={avg:+.2f}% PF={pf:.2f}"
    for y in ("2024", "2025", "2026"):
        if by_y.get(y):
            line += f" | {y}:{sum(by_y[y])/len(by_y[y]):+.2f}%"
    print(line)


print("=== OLD 参数 (Pivot3 / Sweep0.3% / close-BOS) ===")
we.PIVOT_L = we.PIVOT_R = 3
we.SWEEP_PCT = 0.003
we.STRONG_BOS = False
old = run_all()
report("OLD", old)

print("\n=== NEW 参数 (Pivot5 / Sweep1.5% / strong-BOS) ===")
we.PIVOT_L = we.PIVOT_R = 5
we.SWEEP_PCT = 0.015
we.STRONG_BOS = True
new = run_all()
report("NEW", new)

# restore
we.PIVOT_L = we.PIVOT_R = new_pivot
we.SWEEP_PCT = new_sweep
we.STRONG_BOS = new_strong
print("\n完成 (参数已恢复)")
