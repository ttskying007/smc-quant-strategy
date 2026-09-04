# -*- coding: utf-8 -*-
"""SMC technical deepening: swing-point quality via multi-lookback consensus.
Test if requiring confirmed swing low across multiple lookbacks (3/3 and 5/5)
improves TP2-R20 signal quality (stronger structural anchor)."""
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


def is_swing_low_consensus(ks, j):
    """swing low confirmed at multiple lookbacks: 3/3 and 5/5 both confirm."""
    if j < 5 or j + 5 >= len(ks):
        return False
    lo = ks[j]["l"]
    ok33 = lo < min(ks[k]["l"] for k in range(j - 3, j)) and lo <= min(ks[k]["l"] for k in range(j + 1, j + 4))
    ok55 = lo < min(ks[k]["l"] for k in range(j - 5, j)) and lo <= min(ks[k]["l"] for k in range(j + 1, j + 6))
    return ok33 and ok55


def build_consensus_seeds(sym, daily):
    """Same main line as build_seeds but swing lows require 3/3 AND 5/5 consensus."""
    seeds = []
    swing_lows = [j for j in range(5, len(daily) - 5) if is_swing_low_consensus(daily, j)]
    for i in range(20, len(daily) - 3):
        b = daily[i]
        swept = None
        for j in reversed(swing_lows):
            if j + 5 >= i:
                continue
            ssl = daily[j]["l"]
            if b["l"] <= ssl * (1 - we.SWEEP_PCT) and b["c"] > ssl:
                swept = j
                break
        if swept is None:
            continue
        rsp = i + 1
        if rsp >= len(daily) or not (daily[rsp]["c"] > b["h"]):
            continue
        win = daily[i - 5 + 1:i + 1]
        if not (win[-1]["h"] > win[0]["h"] and win[-1]["l"] > win[0]["l"]):
            continue
        ob_idx = None
        for k in range(rsp + 1, min(len(daily), rsp + 5)):
            if daily[k]["c"] < daily[k]["o"]:
                ob_idx = k
                break
        if ob_idx is None:
            continue
        ob = daily[ob_idx]
        zl = min(ob["o"], ob["c"], ob["l"])
        zh = min(max(ob["o"], ob["c"]), zl + (ob["h"] - zl) * 0.5)
        touched = False
        t_idx = None
        entry = None
        for k in range(ob_idx + 1, min(len(daily) - 1, ob_idx + 12)):
            bb = daily[k]
            if bb["l"] <= zl and bb["c"] <= zh:
                if touched:
                    break
                touched, t_idx = True, k
                continue
            if bb["c"] < zl:
                if touched:
                    break
                touched, t_idx = True, k
                continue
            if bb["l"] <= zh and bb["h"] >= zl:
                touched = True
                t_idx = t_idx if t_idx is not None else k
            if touched and k != t_idx and bb["c"] > zh:
                h3 = None
                for j in range(max(0, t_idx - 1), we.PIVOT_L - 1, -1):
                    if we.is_swing_high(daily, j) and daily[j]["h"] > zh:
                        h3 = daily[j]["h"]
                        break
                if h3 is not None and bb["c"] > h3:
                    entry_idx = k + 1
                    if entry_idx < len(daily):
                        entry = (entry_idx, k, t_idx)
                break
        if entry is None:
            continue
        entry_idx, reclaim_idx, touch_idx = entry
        entry_price = we.f(daily[entry_idx]["o"])
        # r20
        if entry_idx < 21:
            continue
        r20 = daily[entry_idx - 1]["c"] / daily[entry_idx - 21]["c"] - 1
        if not (0 <= r20 < 0.15):
            continue
        seeds.append({"symbol": sym, "entry_idx": entry_idx, "entry_date": daily[entry_idx]["t"],
                      "event_date": daily[i]["t"], "zone_low": zl, "zone_high": zh,
                      "entry_price": entry_price, "sweep_low": daily[swept]["l"],
                      "target": max(zh, daily[entry_idx - 1]["c"]), "r20": r20})
    return seeds


bar_cache = {}
def get_bars(sym):
    if sym not in bar_cache:
        bar_cache[sym] = bars(os.path.join(KT, sym.replace(".", "_") + "_daily_800.json"))
    return bar_cache[sym]


# build consensus seeds (note: target approximation; weekly BSL not used here)
seeds_c = []
n = 0
for p in sorted(os.listdir(KT)):
    if not p.endswith("_daily_800.json"):
        continue
    n += 1
    daily = bars(os.path.join(KT, p))
    if len(daily) < 400:
        continue
    sym = p.replace("_daily_800.json", "").replace("_", ".", 1)
    seeds_c.extend(build_consensus_seeds(sym, daily))
    if n % 1500 == 0:
        print(f"  {n} files, seeds {len(seeds_c)}", flush=True)
print(f"consensus seeds: {len(seeds_c)}")

trades = []
for sd in seeds_c:
    tr = we.replay_tp2(sd, get_bars(sd["symbol"]))
    if tr:
        trades.append(tr)
print("trades:", len(trades))
for t in trades:
    t["t1_violation"] = str(t.get("t1_violation", "")).lower() in ("true", "1", "yes")
gate = check_economic_gate(trades)
o = gate["overall"]
print(f"\n=== 共识摆动 TP2-R20 ===")
print(f"总体: n={o['n']} WR={o['wr']}% avg={o['avg']}% PF={o['pf']} payoff={o['payoff']}")
for y in ("2024", "2025", "2026"):
    ys = [t for t in trades if str(t["entry_date"]).startswith(y)]
    if ys:
        wy = sum(1 for t in ys if t["net_pnl_pct"] > 0)
        print(f"  {y}: n={len(ys)} WR={100*wy/len(ys):.0f}% avg={sum(t['net_pnl_pct'] for t in ys)/len(ys):+.2f}%")
print("\n对比基线（3/3 摆动）: n=558 WR=59.3% avg=+2.45% PF=1.61")
