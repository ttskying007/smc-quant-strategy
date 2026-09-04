# -*- coding: utf-8 -*-
"""Cross-year insider event strategy on available announcement data (with coverage gaps noted)."""
import glob, io, json, os, sqlite3, sys
from collections import defaultdict

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
sys.path.insert(0, r"E:\test\smc_project\smc_backtest_report")
from smc_gates import check_economic_gate

KT = r"E:\test\smc_project\hermes\kline_cache_tencent"
conn = sqlite3.connect(r"E:\test\smc_project\announce\smc_announce.db")
cur = conn.cursor()

cache = {}
# pre-build code -> kline file mapping once
code2file = {}
for f in os.listdir(KT):
    if f.endswith("_daily_800.json"):
        code2file[f.split("_")[0]] = os.path.join(KT, f)


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
    exit_price = bs[i + hold]["c"]
    gross = (exit_price / ep - 1) * 100
    return {"symbol": symbol, "entry_date": bs[i]["t"], "exit_date": bs[i + hold]["t"],
            "net_pnl_pct": round(gross - 0.20, 4), "reason": "EVENT_10D", "hold_bars": hold,
            "t1_violation": "False"}


# coverage per year: count announce dates by year
cur.execute("SELECT substr(date,1,4), COUNT(DISTINCT date) FROM announce GROUP BY 1 ORDER BY 1")
print("=== 公告数据覆盖（每年天数）===")
total_days = {"2023": 115, "2024": 244, "2025": 244, "2026": 152}  # approx trading days H2/2023..2026-08
for r in cur.fetchall():
    y = r[0]
    print(f"  {y}: {r[1]} 天 ({'约' + str(total_days.get(y, '?'))} 交易日)")

for name, q in [("增持", "SELECT date, stock_code FROM announce WHERE title LIKE '%增持%'"),
                ("回购", "SELECT date, stock_code FROM announce WHERE title LIKE '%回购%'")]:
    cur.execute(q)
    rows = cur.fetchall()
    trades = []
    seen = set()
    for date, code in rows:
        d = str(date)[:10].replace("-", "")
        key = (code, d)
        if key in seen:
            continue
        seen.add(key)
        tr = event_trade(code, d)
        if tr:
            trades.append(tr)
    print(f"\n=== {name} 事件策略（跨年）: 事件 {len(rows)}, 可交易 {len(trades)} ===")
    if not trades:
        continue
    for t in trades:
        t["t1_violation"] = str(t.get("t1_violation", "")).lower() in ("true", "1", "yes")
    gate = check_economic_gate(trades)
    o = gate["overall"]
    print(f"  总体: n={o['n']} WR={o['wr']}% avg={o['avg']}% PF={o['pf']} payoff={o['payoff']} gate={gate['gate_pass']}")
    for y in ("2023", "2024", "2025", "2026"):
        ys = [t for t in trades if str(t["entry_date"]).startswith(y)]
        if ys:
            wy = sum(1 for t in ys if t["net_pnl_pct"] > 0)
            print(f"    {y}: n={len(ys)} WR={100*wy/len(ys):.0f}% avg={sum(t['net_pnl_pct'] for t in ys)/len(ys):+.2f}% PF={sum(max(t['net_pnl_pct'],0) for t in ys)/abs(sum(min(t['net_pnl_pct'],0) for t in ys)) if sum(min(t['net_pnl_pct'],0) for t in ys) else 0:.2f}")
conn.close()
