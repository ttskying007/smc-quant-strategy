# -*- coding: utf-8 -*-
"""Combo v8: SMC (steady/UPTREND behavior) + events ONLY in ACCUM/DOWNTREND stages.
The two legs are complementary: SMC follows markup majors, events follow accumulation.
This should lift 2026 (event ACCUM +6.45%) and keep 2024/2025."""
import csv, glob, io, json, os, sqlite3, sys
from collections import defaultdict

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
sys.path.insert(0, r"E:\test\smc_project\smc_backtest_report")
from smc_gates import check_economic_gate

KT = r"E:\test\smc_project\hermes\kline_cache_tencent"
conn = sqlite3.connect(r"E:\test\smc_project\announce\smc_announce.db")
cur = conn.cursor()

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


def stage_at(bs, i):
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


# events with stage filter (ACCUM/DOWNTREND only)
def is_strong(title):
    t = str(title or "")
    if "回购" in t:
        if "完成" in t or "进度" in t or "进展" in t or "结果" in t or "前十名" in t:
            return False
        return True
    if "增持" in t:
        return True
    return False

ev = []
seen = set()
cur.execute("SELECT date, stock_code, title FROM announce WHERE title LIKE '%增持%' OR title LIKE '%回购%'")
for date, code, title in cur.fetchall():
    if not is_strong(title):
        continue
    d = str(date)[:10].replace("-", "")
    if (code, d) in seen:
        continue
    seen.add((code, d))
    bs = bars_of(code)
    if not bs:
        continue
    dates = [b["t"] for b in bs]
    nxt = [x for x in dates if x > d]
    if not nxt:
        continue
    i = dates.index(nxt[0])
    if i + 10 >= len(bs):
        continue
    ep = bs[i]["o"]
    if ep <= 0:
        continue
    st = stage_at(bs, i)
    if st not in ("ACCUM", "DOWNTREND"):
        continue
    ev.append({"symbol": code, "entry_date": bs[i]["t"],
               "net_pnl_pct": round((bs[i + 10]["c"] / ep - 1) * 100 - 0.20, 4), "src": "EVENT"})
print("events (ACCUM+DOWNTREND):", len(ev))

# SMC leg: steady state
trades = []
with open(r"E:\test\smc_project\wdh\TP2_tencent_trades.csv", encoding="utf-8-sig") as fh:
    for r in csv.DictReader(fh):
        r["net_pnl_pct"] = float(r["net_pnl_pct"])
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


def stage_at_sym(symbol, entry_date):
    code, ex = symbol.split(".")
    fn = f"{code}_{ex}_daily_800.json"
    p = os.path.join(KT, fn)
    if not os.path.exists(p):
        return None
    bs = bars_of(code) if code in bar_cache else bars_of(code)
    dates = [b["t"] for b in bs]
    if entry_date not in dates:
        prev = [d for d in dates if d < entry_date]
        if not prev:
            return None
        i = dates.index(prev[-1])
    else:
        i = dates.index(entry_date)
    return stage_at(bs, i)

smc = []
for t in trades:
    r20 = r20_of(t["symbol"], str(t["entry_date"]))
    if r20 is None or not (0 <= r20 < 0.15):
        continue
    st = stage_at_sym(t["symbol"], str(t["entry_date"]))
    if st in ("UPTREND", "MARKUP"):  # follow markup majors
        smc.append(t)
print("SMC (UPTREND/MARKUP):", len(smc))

combined = smc + ev
for t in combined:
    t.setdefault("t1_violation", "False")
    t["t1_violation"] = str(t.get("t1_violation", "")).lower() in ("true", "1", "yes")
    t["year"] = str(t["entry_date"])[:4]

gate = check_economic_gate(combined)
o = gate["overall"]
print(f"\n=== 组合 v8（SMC跟拉升 + 事件逆势吸筹）===")
print(f"总体: n={o['n']} WR={o['wr']}% avg={o['avg']}% PF={o['pf']} payoff={o['payoff']} gate={gate['gate_pass']}")
for y in ("2024", "2025", "2026"):
    ys = [t for t in combined if t["year"] == y]
    if ys:
        w = sum(1 for t in ys if t["net_pnl_pct"] > 0)
        gp = sum(max(t["net_pnl_pct"], 0) for t in ys)
        gl = abs(sum(min(t["net_pnl_pct"], 0) for t in ys))
        print(f"  {y}: n={len(ys)} WR={100*w/len(ys):.0f}% avg={sum(t['net_pnl_pct'] for t in ys)/len(ys):+.2f}% PF={gp/gl if gl else 0:.2f}")
# save v8 trades
with open(r"E:\test\smc_project\research\combo_v8_trades.csv", "w", newline="", encoding="utf-8-sig") as fh:
    w8 = csv.DictWriter(fh, fieldnames=["symbol", "entry_date", "net_pnl_pct", "t1_violation", "year", "src"])
    w8.writeheader()
    for t in combined:
        w8.writerow({"symbol": t.get("symbol", ""), "entry_date": t.get("entry_date", ""),
                     "net_pnl_pct": t.get("net_pnl_pct", 0), "t1_violation": t.get("t1_violation", ""),
                     "year": t.get("year", ""), "src": t.get("src", "?")})
print("combo_v8 saved")
conn.close()
