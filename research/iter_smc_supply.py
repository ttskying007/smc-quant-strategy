# -*- coding: utf-8 -*-
"""SMC supply recovery: relax filters layer by layer to restore SMC leg volume.
Current v13 SMC leg = 31 trades (0.6%). Test supply at each filter level:
  A) base TP2 (1276) -> B) +R20 (558) -> C) +stage UPTREND/MARKUP -> D) +bearFVG -> E) +ADX
Show trade count + quality at each layer."""
import csv, io, json, os, sys
from collections import defaultdict

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
sys.path.insert(0, r"E:\test\smc_project\smc_backtest_report")
from smc_gates import check_economic_gate

KT = r"E:\test\smc_project\hermes\kline_cache_tencent"

code2file = {}
for f in os.listdir(KT):
    if f.endswith("_daily_800.json"):
        code2file[f.split("_")[0]] = os.path.join(KT, f)

bar_cache = {}
def bars_of(code):
    if code not in bar_cache:
        p = code2file.get(code)
        if not p:
            bar_cache[code] = []
            return bar_cache[code]
        raw = json.load(open(p, encoding="utf-8"))
        bs = []
        for r in raw:
            t = "".join(x for x in str(r.get("t") or "") if x.isdigit())[:8]
            if t and r.get("o") and r.get("h") and r.get("l") and r.get("c") and r.get("v"):
                bs.append({"t": t, "o": float(r["o"]), "h": float(r["h"]), "l": float(r["l"]), "c": float(r["c"]), "v": float(r["v"])})
        bs.sort(key=lambda b: b["t"])
        bar_cache[code] = bs
    return bar_cache[code]


def adx14(bs, i):
    if i < 30:
        return None
    plus_dm = minus_dm = tr_sum = 0.0
    for k in range(i - 14, i):
        h, l, pc = bs[k]["h"], bs[k]["l"], bs[k - 1]["c"]
        up = h - bs[k - 1]["h"]
        dn = bs[k - 1]["l"] - l
        plus_dm += up if (up > dn and up > 0) else 0
        minus_dm += dn if (dn > up and dn > 0) else 0
        tr = max(h - l, abs(h - pc), abs(l - pc))
        tr_sum += tr
    if tr_sum <= 0:
        return None
    pdi = 100 * plus_dm / tr_sum
    mdi = 100 * minus_dm / tr_sum
    if pdi + mdi == 0:
        return None
    return 100 * abs(pdi - mdi) / (pdi + mdi)


def stage_at(bs, i):
    if i < 61:
        return None
    w60 = bs[i - 60:i]
    w20 = bs[i - 20:i]
    ret = w60[-1]["c"] / w60[0]["c"] - 1
    v20 = sum(b["v"] for b in w20) / len(w20)
    v60 = sum(b["v"] for b in w60) / len(w60)
    vt = v20 / v60 if v60 else 1
    if ret < -0.15 and vt < 0.9:
        return "ACCUM"
    if ret > 0.30 and vt > 1.3:
        return "DISTRIB"
    if ret > 0.20 and vt > 1.1:
        return "MARKUP"
    if ret > 0:
        return "UPTREND"
    return "DOWNTREND"


def has_bear_fvg(bs, i, lookback=12):
    for k in range(max(3, i - lookback), i):
        if bs[k]["h"] < bs[k - 2]["l"]:
            return True
    return False


trades = []
with open(r"E:\test\smc_project\wdh\TP2_tencent_trades.csv", encoding="utf-8-sig") as fh:
    for r in csv.DictReader(fh):
        r["net_pnl_pct"] = float(r["net_pnl_pct"])
        trades.append(r)

closes_cache = {}
def r20_of(symbol, entry_date, hi=0.15):
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


# tag all trades
for t in trades:
    t["r20"] = r20_of(t["symbol"], str(t["entry_date"]))
    code = t["symbol"].split(".")[0]
    bs = bars_of(code)
    dates = [b["t"] for b in bs]
    ed = str(t["entry_date"])
    i = dates.index(ed) if ed in dates else None
    if i is None:
        prev = [d for d in dates if d < ed]
        if not prev:
            i = None
        else:
            i = dates.index(prev[-1])
    t["idx"] = i
    t["stage"] = stage_at(bs, i) if i is not None else None
    t["adx"] = adx14(bs, i) if i is not None else None
    t["fvg"] = has_bear_fvg(bs, i) if i is not None else False


def report(label, rs):
    if len(rs) < 50:
        print(f"{label}: n={len(rs)} (过小)")
        return
    for t in rs:
        t["t1_violation"] = "False"
        t["year"] = str(t["entry_date"])[:4]
    gate = check_economic_gate(rs)
    o = gate["overall"]
    print(f"{label}: n={o['n']} avg={o['avg']:+.2f}% PF={o['pf']} WR={o['wr']}%")


print("=== SMC 腿逐层过滤（供应 vs 质量）===")
report("A) 基础 TP2 全部", trades)
report("B) +R20[0,0.15)", [t for t in trades if t["r20"] is not None and 0 <= t["r20"] < 0.15])
report("B2) +R20[0,0.20) 放宽", [t for t in trades if t["r20"] is not None and 0 <= t["r20"] < 0.20])
report("C) +stage UPTREND/MARKUP", [t for t in trades if t["r20"] is not None and 0 <= t["r20"] < 0.15 and t["stage"] in ("UPTREND", "MARKUP")])
report("D) +bearFVG", [t for t in trades if t["r20"] is not None and 0 <= t["r20"] < 0.15 and t["stage"] in ("UPTREND", "MARKUP") and t["fvg"]])
report("E) +ADX<20 (v13)", [t for t in trades if t["r20"] is not None and 0 <= t["r20"] < 0.15 and t["stage"] in ("UPTREND", "MARKUP") and t["fvg"] and t["adx"] is not None and t["adx"] < 20])
report("C2) R20放宽[0,0.20)+stage", [t for t in trades if t["r20"] is not None and 0 <= t["r20"] < 0.20 and t["stage"] in ("UPTREND", "MARKUP")])
