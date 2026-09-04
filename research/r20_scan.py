# -*- coding: utf-8 -*-
"""Scan R20 filter boundary: find sample-quality tradeoff. Research exploration."""
import csv, io, json, os, sys
from collections import Counter, defaultdict

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
sys.path.insert(0, r"E:\test\smc_project\smc_backtest_report")
from smc_gates import check_economic_gate

KT = r"E:\test\smc_project\hermes\kline_cache_tencent"
sys.path.insert(0, r"E:\test\smc_project\wdh")
import wdh_engine as we


def bars(path):
    try:
        raw = json.load(open(path, encoding="utf-8"))
    except Exception:
        return []
    out = []
    for r in raw if isinstance(raw, list) else []:
        t = "".join(c for c in str(r.get("t") or "") if c.isdigit())[:8]
        o, h, l, c = we.f(r.get("o")), we.f(r.get("h")), we.f(r.get("l")), we.f(r.get("c"))
        if t and o and h and l and c:
            out.append({"t": t, "o": o, "h": h, "l": l, "c": c})
    out.sort(key=lambda b: b["t"])
    return out


# build all seeds once with r20
all_seeds = []
n = 0
for p in sorted(os.listdir(KT)):
    if not p.endswith("_daily_800.json"):
        continue
    n += 1
    daily = bars(os.path.join(KT, p))
    if len(daily) < 400:
        continue
    sym = p.replace("_daily_800.json", "").replace("_", ".", 1)
    for sd in we.build_seeds(sym, daily):
        r20 = sd.get("r20")
        if r20 == "" or r20 is None:
            continue
        sd["r20v"] = float(r20)
        all_seeds.append((sd, daily))
    if n % 1500 == 0:
        print(f"  scan {n} files, seeds {len(all_seeds)}", flush=True)
print(f"total seeds with r20: {len(all_seeds)}")

# bucket by r20
from collections import defaultdict
buckets = defaultdict(list)
for sd, daily in all_seeds:
    r = sd["r20v"]
    b = int(r * 20) / 20  # 0.05 steps
    buckets[b].append((sd, daily))

print("\n=== R20 分布与单桶质量（TP2 回放）===")
for b in sorted(buckets):
    items = buckets[b]
    trs = []
    for sd, daily in items:
        tr = we.replay_tp2(sd, daily)
        if tr:
            trs.append(tr)
    if len(trs) < 20:
        print(f"  r20∈[{b:.2f},{b+0.05:.2f}): n={len(trs)} (过小)")
        continue
    w = sum(1 for t in trs if t["net_pnl_pct"] > 0)
    avg = sum(t["net_pnl_pct"] for t in trs) / len(trs)
    wins = sum(max(t["net_pnl_pct"], 0) for t in trs)
    losses = abs(sum(min(t["net_pnl_pct"], 0) for t in trs))
    pf = wins / losses if losses else 0
    print(f"  r20∈[{b:.2f},{b+0.05:.2f}): n={len(trs)} WR={100*w/len(trs):.1f}% avg={avg:+.2f}% PF={pf:.2f}")
