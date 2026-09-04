# -*- coding: utf-8 -*-
"""Operator-switch detection: detect behavior-stage transitions (new major entering).
Stage shift e.g. DOWNTREND->UPTREND or ACCUM->UPTREND signals a NEW operator.
Test: SMC signals right AFTER a stage switch (new-money early phase) vs steady state."""
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
        if t and r.get("o") and r.get("h") and r.get("l") and r.get("c") and r.get("v"):
            out.append({"t": t, "o": float(r["o"]), "h": float(r["h"]), "l": float(r["l"]), "c": float(r["c"]), "v": float(r["v"])})
    out.sort(key=lambda b: b["t"])
    return out


def stage_at_idx(bs, i):
    """stage at bar index i (60d window ending at i-1, PIT)."""
    if i < 61:
        return None
    w60 = bs[i - 60:i]
    w20 = bs[i - 20:i]
    ret60 = w60[-1]["c"] / w60[0]["c"] - 1
    v20 = sum(b["v"] for b in w20) / len(w20)
    v60 = sum(b["v"] for b in w60) / len(w60)
    vt = v20 / v60 if v60 else 1
    if ret60 < -0.15 and vt < 0.9:
        return "ACCUM"
    if ret60 > 0.30 and vt > 1.3:
        return "DISTRIB"
    if ret60 > 0.20 and vt > 1.1:
        return "MARKUP"
    if ret60 > 0:
        return "UPTREND"
    return "DOWNTREND"


def switch_info(symbol, entry_date, lookback=10):
    """Was there a stage switch within lookback bars before entry? Return (switched, from, to)."""
    code, ex = symbol.split(".")
    fn = f"{code}_{ex}_daily_800.json"
    p = os.path.join(KT, fn)
    if not os.path.exists(p):
        return None
    bs = bars(p)
    dates = [b["t"] for b in bs]
    if entry_date not in dates:
        prev = [d for d in dates if d < entry_date]
        if not prev:
            return None
        i = dates.index(prev[-1])
    else:
        i = dates.index(entry_date)
    # stages for the last lookback+1 bars
    st = []
    for k in range(max(0, i - lookback), i):
        s = stage_at_idx(bs, k)
        if s:
            st.append(s)
    if len(st) < 2:
        return None
    switched = False
    frm = st[0]
    to = st[-1]
    for a, b_ in zip(st, st[1:]):
        if a != b_:
            switched = True
            frm, to = a, b_
            break
    return switched, frm, to


trades = []
with open(r"E:\test\smc_project\wdh\TP2_tencent_trades.csv", encoding="utf-8-sig") as fh:
    for r in csv.DictReader(fh):
        r["net_pnl_pct"] = float(r["net_pnl_pct"])
        r["t1_violation"] = str(r.get("t1_violation", "")).lower() in ("true", "1", "yes")
        trades.append(r)

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
    sw = switch_info(t["symbol"], str(t["entry_date"]))
    if sw is None:
        continue
    t["switched"], t["sw_from"], t["sw_to"] = sw
    tagged.append(t)
print("tagged:", len(tagged))
from collections import Counter
sws = [t for t in tagged if t["switched"]]
print(f"切换样本: {len(sws)}/{len(tagged)}")
print("切换类型:", dict(Counter(f"{t['sw_from']}->{t['sw_to']}" for t in sws)))


def report(label, rs):
    if len(rs) < 50:
        print(f"{label}: n={len(rs)} (过小)"); return
    gate = check_economic_gate(rs)
    o = gate["overall"]
    print(f"{label}: n={o['n']} WR={o['wr']}% avg={o['avg']}% PF={o['pf']} payoff={o['payoff']}")
    for y in ("2024", "2025", "2026"):
        ys = [t for t in rs if str(t["entry_date"]).startswith(y)]
        if ys:
            wy = sum(1 for t in ys if t["net_pnl_pct"] > 0)
            print(f"    {y}: n={len(ys)} WR={100*wy/len(ys):.0f}% avg={sum(t['net_pnl_pct'] for t in ys)/len(ys):+.2f}%")


print("\n=== 换庄检测（阶段切换后信号）===")
report("基线（全部）", tagged)
report("切换后（近10日有阶段变化）", sws)
report("稳态（无切换）", [t for t in tagged if not t["switched"]])
# bullish switches into uptrend/markup
bull = [t for t in sws if t["sw_to"] in ("UPTREND", "MARKUP")]
report("转多切换（->UPTREND/MARKUP）", bull)
