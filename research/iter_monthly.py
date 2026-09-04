# -*- coding: utf-8 -*-
"""Dimension A: monthly layer for the SMC state machine.
Monthly trend permission (rising monthly HH/HL) + monthly BSL as TP reference.
Tests if adding monthly structure improves the daily three-TF engine (TP2-R20)."""
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


def monthly_agg(daily):
    """Aggregate daily -> monthly bars (YYYYMM)."""
    months = []
    cur = None
    for b in daily:
        m = b["t"][:6]
        if cur is None or cur["m"] != m:
            if cur:
                months.append(cur)
            cur = {"m": m, "t": b["t"], "o": b["o"], "h": b["h"], "l": b["l"], "c": b["c"]}
        else:
            cur["h"] = max(cur["h"], b["h"])
            cur["l"] = min(cur["l"], b["l"])
            cur["c"] = b["c"]
    if cur:
        months.append(cur)
    return months


def monthly_permission(months, day_date):
    """Monthly trend: last 3 monthly bars form rising structure (HH/HL) OR at least
    monthly close above its 6-month range midpoint. Uses only months strictly before current."""
    m0 = day_date[:6]
    prior = [m for m in months if m["m"] < m0]
    if len(prior) < 6:
        return False, "INSUFFICIENT"
    last = prior[-3:]
    if last[-1]["h"] > last[0]["h"] and last[-1]["l"] > last[0]["l"]:
        return True, "MONTHLY_HH_HL"
    # close above 6-month midpoint
    win = prior[-6:]
    mid = min(w["l"] for w in win) + (max(w["h"] for w in win) - min(w["l"] for w in win)) * 0.5
    if prior[-1]["c"] > mid:
        return True, "MONTHLY_ABOVE_MID"
    return False, "NO_MONTHLY_PERMISSION"


def monthly_bsl(months, day_date, minimum):
    """Monthly BSL (liquidity pool high) before current month, above minimum."""
    m0 = day_date[:6]
    best = None
    for m in reversed(months):
        if m["m"] >= m0:
            continue
        if m["h"] > minimum:
            return m["h"]
    return best


bar_cache = {}
def get_bars(sym):
    if sym not in bar_cache:
        bar_cache[sym] = bars(os.path.join(KT, sym.replace(".", "_") + "_daily_800.json"))
    return bar_cache[sym]


# build seeds with monthly layer: run wdh build_seeds (already r20 filtered), tag with monthly permission
# and use monthly BSL as TP if higher than weekly BSL
import csv
seeds = []
with open(r"E:\test\smc_project\wdh\W1D1D4_seeds.csv", encoding="utf-8-sig") as fh:
    for r in csv.DictReader(fh):
        k = {kk.lstrip("\ufeff"): v for kk, v in r.items()}
        seeds.append(k)
print("base seeds:", len(seeds))

# tag each seed: monthly permission + monthly BSL
tagged = []
for sd in seeds:
    sym = sd["symbol"]
    daily = get_bars(sym)
    if not daily:
        continue
    months = monthly_agg(daily)
    entry_date = str(sd["entry_date"])
    ok, why = monthly_permission(months, entry_date)
    # monthly BSL above zone
    mbsl = monthly_bsl(months, entry_date, we.f(sd.get("zone_high")))
    sd["monthly_perm"] = ok
    sd["monthly_why"] = why
    sd["monthly_bsl"] = mbsl
    # effective TP = max(weekly_target, monthly_bsl)
    wt = we.f(sd.get("weekly_target"))
    tp = max(wt, mbsl) if (wt or mbsl) else wt
    sd["tp_eff"] = tp if tp else sd.get("target")
    tagged.append(sd)
print("tagged seeds:", len(tagged))


def run(label, filt):
    trades = []
    for sd in tagged:
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


print("\n=== 月线层增强 ===")
run("基线（周+日，无月线）", lambda sd: sd.get("r20") != "" and 0 <= we.f(sd.get("r20")) < 0.15)
run("月线权限（月线HH/HL或>mid）", lambda sd: sd.get("monthly_perm") is True and sd.get("r20") != "" and 0 <= we.f(sd.get("r20")) < 0.15)
