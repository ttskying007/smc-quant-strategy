# -*- coding: utf-8 -*-
"""FVG confirmation test (historical hint: Sweep->FVG top pattern, but need frozen replay).
Add FVG (Fair Value Gap) presence between sweep and entry to the three-TF signal.
FVG = 3-bar gap: low[i] > high[i-2] (bullish FVG below, demand)."""
import io, json, os, sys
from collections import defaultdict

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
sys.path.insert(0, r"E:\test\smc_project\wdh")
sys.path.insert(0, r"E:\test\smc_project\smc_backtest_report")
import wdh_engine as we
from smc_gates import check_economic_gate

KT = r"E:\test\smc_project\hermes\kline_cache_tencent"


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


def has_bullish_fvg(daily, i, lookback=10):
    """bullish FVG (gap) within lookback bars before i: low[k] > high[k-2]."""
    for k in range(max(3, i - lookback), i):
        if daily[k]["l"] > daily[k - 2]["h"]:
            return True, k
    return False, None


def has_bearish_fvg(daily, i, lookback=10):
    """bearish FVG: high[k] < low[k-2] (gap above, supply) - noise signal."""
    for k in range(max(3, i - lookback), i):
        if daily[k]["h"] < daily[k - 2]["l"]:
            return True, k
    return False, None


bar_cache = {}
def get_bars(sym):
    if sym not in bar_cache:
        bar_cache[sym] = bars(os.path.join(KT, sym.replace(".", "_") + "_daily_800.json"))
    return bar_cache[sym]


# rebuild seeds + tag FVG presence between sweep and entry
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
        if not (0 <= float(r20) < 0.15):
            continue
        entry_idx = int(sd["entry_idx"])
        bf, bk = has_bullish_fvg(daily, entry_idx, 12)
        af, ak = has_bearish_fvg(daily, entry_idx, 12)
        sd["has_bull_fvg"] = bf
        sd["has_bear_fvg"] = af
        all_seeds.append(sd)
    if n % 1500 == 0:
        print(f"  {n} files, seeds {len(all_seeds)}", flush=True)
print(f"total seeds: {len(all_seeds)}")
print("bull FVG:", sum(1 for s in all_seeds if s["has_bull_fvg"]),
      "bear FVG:", sum(1 for s in all_seeds if s["has_bear_fvg"]))


def run(label, filt):
    trades = []
    for sd in all_seeds:
        if not filt(sd):
            continue
        tr = we.replay_tp2(sd, get_bars(sd["symbol"]))
        if tr:
            trades.append(tr)
    if len(trades) < 100:
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


print("\n=== FVG 确认（历史序列模式验证，冻结回放）===")
run("基线（TP2-R20）", lambda sd: True)
run("有牛市FVG（sweep后12bar内）", lambda sd: sd["has_bull_fvg"])
run("无牛市FVG", lambda sd: not sd["has_bull_fvg"])
run("有熊市FVG（上方缺口=供给）", lambda sd: sd["has_bear_fvg"])
