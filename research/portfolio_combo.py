# -*- coding: utf-8 -*-
"""Portfolio: combine TP2-R20 (SMC momentum) + insider events (增持/回购).
Simple combination: merge trade sets, evaluate yearly. Two allocation modes:
A) 50/50 merge (each trade equal weight, combined pool)
B) separate evaluation + blended yearly (per-strategy yearly returns averaged)
"""
import csv, io, json, os, sqlite3, sys
from collections import defaultdict

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
sys.path.insert(0, r"E:\test\smc_project\smc_backtest_report")
from smc_gates import check_economic_gate

KT = r"E:\test\smc_project\hermes\kline_cache_tencent"
conn = sqlite3.connect(r"E:\test\smc_project\announce\smc_announce.db")
cur = conn.cursor()

# --- load TP2-R20 trades (momentum) ---
mom = []
with open(r"E:\test\smc_project\wdh\TP2_tencent_trades.csv", encoding="utf-8-sig") as fh:
    for r in csv.DictReader(fh):
        r["net_pnl_pct"] = float(r["net_pnl_pct"])
        # filter r20 [0,0.15)
        mom.append(r)
# recompute r20 for filtering
code2file = {}
for f in os.listdir(KT):
    if f.endswith("_daily_800.json"):
        code2file[f.split("_")[0]] = os.path.join(KT, f)
closes_cache = {}
def r20_of(symbol, entry_date):
    code = symbol.split(".")[0]
    if code not in closes_cache:
        p = code2file.get(code)
        if not p:
            closes_cache[code] = []
            return None
        raw = json.load(open(p, encoding="utf-8"))
        cl = [(("".join(x for x in str(r.get("t") or "") if x.isdigit())[:8]), float(r["c"])) for r in raw if r.get("t") and r.get("c")]
        cl.sort()
        closes_cache[code] = cl
    cl = closes_cache[code]
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

mom_f = []
for t in mom:
    r20 = r20_of(t["symbol"], str(t["entry_date"]))
    if r20 is not None and 0 <= r20 < 0.15:
        t["src"] = "SMC"
        mom_f.append(t)
print("SMC (TP2-R20) trades:", len(mom_f))

# --- load insider event trades ---
cache = {}
def bars_of(symbol):
    if symbol not in cache:
        p = code2file.get(symbol)
        if not p:
            cache[symbol] = None
            return None
        raw = json.load(open(p, encoding="utf-8"))
        bs = []
        for r in raw:
            t = "".join(x for x in str(r.get("t") or "") if x.isdigit())[:8]
            if t and r.get("o") and r.get("h") and r.get("l") and r.get("c"):
                bs.append({"t": t, "o": float(r["o"]), "h": float(r["h"]), "l": float(r["l"]), "c": float(r["c"])})
        bs.sort(key=lambda b: b["t"])
        cache[symbol] = bs
    return cache[symbol]


def event_trade(symbol, event_date, hold=10):
    bs = bars_of(symbol)
    if not bs:
        return None
    dates = [b["t"] for b in bs]
    nxt = [d for d in dates if d > event_date]
    if not nxt:
        return None
    i = dates.index(nxt[0])
    if i + hold >= len(bs):
        return None
    ep = bs[i]["o"]
    if ep <= 0:
        return None
    return {"symbol": symbol, "entry_date": bs[i]["t"], "exit_date": bs[i + hold]["t"],
            "net_pnl_pct": round((bs[i + hold]["c"] / ep - 1) * 100 - 0.20, 4),
            "reason": "EVENT", "hold_bars": hold, "t1_violation": "False", "src": "EVENT"}

ev = []
seen = set()
for q in ["SELECT date, stock_code FROM announce WHERE title LIKE '%增持%'",
          "SELECT date, stock_code FROM announce WHERE title LIKE '%回购%'"]:
    cur.execute(q)
    for date, code in cur.fetchall():
        d = str(date)[:10].replace("-", "")
        if (code, d) in seen:
            continue
        seen.add((code, d))
        tr = event_trade(code, d)
        if tr:
            ev.append(tr)
print("EVENT trades:", len(ev))

# --- combined pool (all trades, equal weight) ---
combined = mom_f + ev
for t in combined:
    t["t1_violation"] = str(t.get("t1_violation", "")).lower() in ("true", "1", "yes")
    t["year"] = str(t["entry_date"])[:4]
# save combined trades for reporting
with open(os.path.join(r"E:\test\smc_project\research", "combo_trades.csv"), "w", newline="", encoding="utf-8-sig") as fh:
    import csv as _csv
    w = _csv.DictWriter(fh, fieldnames=["symbol", "entry_date", "exit_date", "net_pnl_pct", "reason", "hold_bars", "t1_violation", "src", "year"])
    w.writeheader()
    for t in combined:
        w.writerow({k: t.get(k, "") for k in w.fieldnames})
print("combo trades saved")
print("\n=== 组合（SMC + EVENT 全池）===")
gate = check_economic_gate(combined)
o = gate["overall"]
print(f"总体: n={o['n']} WR={o['wr']}% avg={o['avg']}% PF={o['pf']} payoff={o['payoff']} gate={gate['gate_pass']}")
for y in ("2023", "2024", "2025", "2026"):
    ys = [t for t in combined if t["year"] == y]
    if ys:
        wy = sum(1 for t in ys if t["net_pnl_pct"] > 0)
        gp = sum(max(t["net_pnl_pct"], 0) for t in ys)
        gl = abs(sum(min(t["net_pnl_pct"], 0) for t in ys))
        print(f"  {y}: n={len(ys)} WR={100*wy/len(ys):.0f}% avg={sum(t['net_pnl_pct'] for t in ys)/len(ys):+.2f}% PF={gp/gl if gl else 0:.2f}")

# --- separate strategies yearly (50/50 allocation view) ---
print("\n=== 分策略年度（互补性视图）===")
for label, pool in [("SMC", mom_f), ("EVENT", ev)]:
    print(f"  {label}:")
    for y in ("2024", "2025", "2026"):
        ys = [t for t in pool if t["year"] == y]
        if ys:
            wy = sum(1 for t in ys if t["net_pnl_pct"] > 0)
            print(f"    {y}: n={len(ys)} WR={100*wy/len(ys):.0f}% avg={sum(t['net_pnl_pct'] for t in ys)/len(ys):+.2f}%")
conn.close()
