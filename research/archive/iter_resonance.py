# -*- coding: utf-8 -*-
"""Multi-timeframe resonance: monthly x weekly state consistency as signal enhancer.
User direction: 不同周期组合混用. Test if aligned monthly+weekly trend states
improve TP2-R20 SMC quality."""
import csv, io, json, os, sys
from collections import defaultdict

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
sys.path.insert(0, r"E:\test\smc_project\smc_backtest_report")
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
        if t and r.get("o") and r.get("h") and r.get("l") and r.get("c"):
            out.append({"t": t, "o": float(r["o"]), "h": float(r["h"]), "l": float(r["l"]), "c": float(r["c"])})
    out.sort(key=lambda b: b["t"])
    return out


def agg(daily, key_fn):
    out = []
    cur = None
    for b in daily:
        k = key_fn(b["t"])
        if cur is None or cur["k"] != k:
            if cur:
                out.append(cur)
            cur = {"k": k, "h": b["h"], "l": b["l"], "c": b["c"]}
        else:
            cur["h"] = max(cur["h"], b["h"])
            cur["l"] = min(cur["l"], b["l"])
            cur["c"] = b["c"]
    if cur:
        out.append(cur)
    return out


def trend_state(agg_bars, ref_key, win=3):
    """Rising state: last win bars HH/HL."""
    prior = [x for x in agg_bars if x["k"] < ref_key]
    if len(prior) < win + 1:
        return None
    last = prior[-win:]
    rising = last[-1]["h"] > last[0]["h"] and last[-1]["l"] > last[0]["l"]
    return "UP" if rising else "DOWN"


def states_at(symbol, entry_date):
    code, ex = symbol.split(".")
    fn = f"{code}_{ex}_daily_800.json"
    p = os.path.join(KT, fn)
    if not os.path.exists(p):
        return None, None, None
    daily = bars(p)
    months = agg(daily, lambda t: t[:6])
    weeks = agg(daily, lambda t: t[:6] + "_" + t[6:8][:1])  # week approx by day tens
    m0, d0 = entry_date[:6], entry_date
    mstate = trend_state(months, m0)
    wstate = trend_state(weeks, d0[:8])
    return mstate, wstate, None


trades = []
with open(r"E:\test\smc_project\wdh\TP2_tencent_trades.csv", encoding="utf-8-sig") as fh:
    for r in csv.DictReader(fh):
        r["net_pnl_pct"] = float(r["net_pnl_pct"])
        r["t1_violation"] = str(r.get("t1_violation", "")).lower() in ("true", "1", "yes")
        trades.append(r)

# r20 filter + tag states
closes_cache = {}
def r20_of(symbol, entry_date):
    code, ex = symbol.split(".")
    fn = f"{code}_{ex}_daily_800.json"
    if fn not in closes_cache:
        p = os.path.join(KT, fn)
        if not os.path.exists(p):
            closes_cache[fn] = []
            return None
        raw = json.load(open(p, encoding="utf-8"))
        cl = [(("".join(x for x in str(r.get("t") or "") if x.isdigit())[:8]), float(r["c"])) for r in raw if r.get("t") and r.get("c")]
        cl.sort()
        closes_cache[fn] = cl
    cl = closes_cache[fn]
    ds = [c[0] for c in cl]
    if entry_date not in ds:
        prev = [d for d in ds if d < entry_date]
        if not prev:
            return None
        i = ds.index(prev[-1])
    else:
        i = ds.index(entry_date) - 1
    if i < 20:
        return None
    return cl[i][1] / cl[i - 20][1] - 1

tagged = []
for t in trades:
    r20 = r20_of(t["symbol"], str(t["entry_date"]))
    if r20 is None or not (0 <= r20 < 0.15):
        continue
    ms, ws, _ = states_at(t["symbol"], str(t["entry_date"]))
    t["mstate"], t["wstate"] = ms, ws
    tagged.append(t)
print("tagged:", len(tagged), "with states:", sum(1 for t in tagged if t["mstate"] and t["wstate"]))


def report(label, rs):
    if len(rs) < 60:
        print(f"{label}: n={len(rs)} (过小)"); return
    gate = check_economic_gate(rs)
    o = gate["overall"]
    print(f"{label}: n={o['n']} WR={o['wr']}% avg={o['avg']}% PF={o['pf']} payoff={o['payoff']}")
    for y in ("2024", "2025", "2026"):
        ys = [t for t in rs if str(t["entry_date"]).startswith(y)]
        if ys:
            wy = sum(1 for t in ys if t["net_pnl_pct"] > 0)
            print(f"    {y}: n={len(ys)} WR={100*wy/len(ys):.0f}% avg={sum(t['net_pnl_pct'] for t in ys)/len(ys):+.2f}%")


both = [t for t in tagged if t["mstate"] and t["wstate"]]
print("\n=== 多周期共振（月×周状态）===")
report("基线（全部）", tagged)
report("共振 UP（月UP+周UP）", [t for t in both if t["mstate"] == "UP" and t["wstate"] == "UP"])
report("共振 DOWN（月DOWN+周DOWN）", [t for t in both if t["mstate"] == "DOWN" and t["wstate"] == "DOWN"])
report("月UP 周DOWN（分歧）", [t for t in both if t["mstate"] == "UP" and t["wstate"] == "DOWN"])
report("月DOWN 周UP（分歧）", [t for t in both if t["mstate"] == "DOWN" and t["wstate"] == "UP"])
