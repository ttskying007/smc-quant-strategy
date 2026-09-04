# -*- coding: utf-8 -*-
"""SMC technical deepening: volume confirmation on reclaim day.
Test: does adding volume-strength layering to TP2-R20 improve signal quality?
(Layered diagnostic, not a hard gate per v676 spirit.)"""
import csv, io, json, os, sys
from collections import defaultdict

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
sys.path.insert(0, r"E:\test\smc_project\wdh")
sys.path.insert(0, r"E:\test\smc_project\smc_backtest_report")
import wdh_engine as we
from smc_gates import check_economic_gate

KT = r"E:\test\smc_project\hermes\kline_cache_tencent"
OUT = r"E:\test\smc_project\research"


def bars(path):
    try:
        raw = json.load(open(path, encoding="utf-8"))
    except Exception:
        return []
    out = []
    for r in raw if isinstance(raw, list) else []:
        t = "".join(c for c in str(r.get("t") or "") if c.isdigit())[:8]
        o, h, l, c, v = we.f(r.get("o")), we.f(r.get("h")), we.f(r.get("l")), we.f(r.get("c")), we.f(r.get("v"))
        if t and o and h and l and c:
            out.append({"t": t, "o": o, "h": h, "l": l, "c": c, "v": v})
    out.sort(key=lambda b: b["t"])
    return out


# rebuild seeds with volume info: use wdh_engine build_seeds, then compute reclaim volume rank
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
        if 0 <= float(r20) < 0.15:
            # reclaim volume rank vs prior 20 bars (locate reclaim date in daily)
            rd = str(sd.get("reclaim_date") or "")
            ri = next((k for k, b in enumerate(daily) if b["t"] == rd), -1)
            if ri >= 20 and daily[ri].get("v"):
                prior = [daily[k].get("v", 0) for k in range(ri - 20, ri)]
                if prior:
                    rv = daily[ri]["v"]
                    rank = sum(1 for x in prior if x <= rv) / len(prior)
                    sd["vol_rank"] = rank
            all_seeds.append(sd)
    if n % 1500 == 0:
        print(f"  {n} files, seeds {len(all_seeds)}", flush=True)
print(f"total seeds: {len(all_seeds)}")


bar_cache = {}
def get_bars(sym):
    if sym not in bar_cache:
        bar_cache[sym] = bars(os.path.join(KT, sym.replace(".", "_") + "_daily_800.json"))
    return bar_cache[sym]


def run(label, filt):
    trades = []
    for sd in all_seeds:
        if not filt(sd):
            continue
        tr = we.replay_tp2(sd, get_bars(sd["symbol"]))
        if tr:
            trades.append(tr)
    if len(trades) < 200:
        print(f"{label}: n={len(trades)} (过小)")
        return
    for t in trades:
        t["t1_violation"] = str(t.get("t1_violation", "")).lower() in ("true", "1", "yes")
    gate = check_economic_gate(trades)
    o = gate["overall"]
    print(f"{label}: n={o['n']} WR={o['wr']}% avg={o['avg']}% PF={o['pf']} payoff={o['payoff']}")
    for y in ("2024", "2025", "2026"):
        ys = [t for t in trades if str(t["entry_date"]).startswith(y)]
        if ys:
            wy = sum(1 for t in ys if t["net_pnl_pct"] > 0)
            print(f"    {y}: n={len(ys)} WR={100*wy/len(ys):.0f}% avg={sum(t['net_pnl_pct'] for t in ys)/len(ys):+.2f}%")


print("\n=== 成交量分层（reclaim 日量能分位）===")
run("基线（无量能分层）", lambda sd: True)
run("vol_rank >= 0.5", lambda sd: sd.get("vol_rank") is not None and sd["vol_rank"] >= 0.5)
run("vol_rank >= 0.7", lambda sd: sd.get("vol_rank") is not None and sd["vol_rank"] >= 0.7)
run("vol_rank < 0.5（低量能）", lambda sd: sd.get("vol_rank") is not None and sd["vol_rank"] < 0.5)
