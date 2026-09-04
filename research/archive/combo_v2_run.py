# -*- coding: utf-8 -*-
"""Updated combo: SMC TP2-R20 + STRONG-signal events (回购预案/首次/增持, exclude weak).
Compare vs original combo. New semantic (signal-strength layering)."""
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


# SMC TP2-R20 trades
sys.path.insert(0, r"E:\test\smc_project\wdh")
import wdh_engine as we
smc_trades = []
with open(r"E:\test\smc_project\wdh\TP2_tencent_trades.csv", encoding="utf-8-sig") as fh:
    for r in csv.DictReader(fh):
        r["net_pnl_pct"] = float(r["net_pnl_pct"])
        smc_trades.append(r)
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

smc_f = []
for t in smc_trades:
    r20 = r20_of(t["symbol"], str(t["entry_date"]))
    if r20 is not None and 0 <= r20 < 0.15:
        smc_f.append(t)
print("SMC TP2-R20 trades:", len(smc_f))


def is_strong(title):
    t = str(title or "")
    if "回购" in t:
        if "完成" in t or "进度" in t or "进展" in t or "结果" in t or "前十名" in t:
            return False
        return True
    if "增持" in t:
        return True
    return False


def strong_events(hold=10):
    cur.execute("SELECT date, stock_code, title FROM announce WHERE title LIKE '%增持%' OR title LIKE '%回购%'")
    trades = []
    seen = set()
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
        if i + hold >= len(bs):
            continue
        ep = bs[i]["o"]
        if ep <= 0:
            continue
        trades.append({"symbol": code, "entry_date": bs[i]["t"],
                       "net_pnl_pct": round((bs[i + hold]["c"] / ep - 1) * 100 - 0.20, 4)})
    return trades


ev = strong_events()
print("strong event trades:", len(ev))
combined = smc_f + ev
for t in combined:
    t.setdefault("t1_violation", "False")
    t["t1_violation"] = str(t.get("t1_violation", "")).lower() in ("true", "1", "yes")
    t["year"] = str(t["entry_date"])[:4]

gate = check_economic_gate(combined)
o = gate["overall"]
print(f"\n=== 更新组合（SMC + 强信号事件）===")
print(f"总体: n={o['n']} WR={o['wr']}% avg={o['avg']}% PF={o['pf']} payoff={o['payoff']} gate={gate['gate_pass']}")
for y in ("2024", "2025", "2026"):
    ys = [t for t in combined if t["year"] == y]
    if ys:
        w = sum(1 for t in ys if t["net_pnl_pct"] > 0)
        gp = sum(max(t["net_pnl_pct"], 0) for t in ys)
        gl = abs(sum(min(t["net_pnl_pct"], 0) for t in ys))
        print(f"  {y}: n={len(ys)} WR={100*w/len(ys):.1f}% avg={sum(t['net_pnl_pct'] for t in ys)/len(ys):+.2f}% PF={gp/gl if gl else 0:.2f}")

# save updated combo
with open(r"E:\test\smc_project\research\combo_v2_trades.csv", "w", newline="", encoding="utf-8-sig") as fh:
    w = csv.DictWriter(fh, fieldnames=["symbol", "entry_date", "net_pnl_pct", "t1_violation", "year", "src"])
    w.writeheader()
    for t in combined:
        w.writerow({"symbol": t.get("symbol", ""), "entry_date": t.get("entry_date", ""),
                    "net_pnl_pct": t.get("net_pnl_pct", 0), "t1_violation": t.get("t1_violation", ""),
                    "year": t.get("year", ""), "src": t.get("src", "?" )})
print("combo_v2 saved")
conn.close()
