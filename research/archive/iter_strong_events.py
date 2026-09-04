# -*- coding: utf-8 -*-
"""Test strong-signal event portfolio: 回购预案/首次实施 + 增持 (exclude 回购完成/进度/一般).
Goal: improve combo quality via signal-strength weighting (new semantic, not tuning)."""
import glob, io, json, os, sqlite3, sys
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


def is_strong(title):
    t = str(title or "")
    if "回购" in t:
        if "完成" in t or "进度" in t or "进展" in t or "结果" in t or "前十名" in t:
            return False  # weak (info digested / boilerplate)
        if "预案" in t or "方案" in t or "首次" in t or "实施" in t or "决议" in t:
            return True
        return True  # other 回购 (report book, etc) keep
    if "增持" in t:
        return True
    return False


def run(label, strong_only, hold=10):
    cur.execute("SELECT date, stock_code, title FROM announce WHERE title LIKE '%增持%' OR title LIKE '%回购%'")
    trades = []
    seen = set()
    for date, code, title in cur.fetchall():
        if strong_only and not is_strong(title):
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
                       "net_pnl_pct": round((bs[i + hold]["c"] / ep - 1) * 100 - 0.20, 4),
                       "t1_violation": "False"})
    for t in trades:
        t["t1_violation"] = str(t.get("t1_violation", "")).lower() in ("true", "1", "yes")
    gate = check_economic_gate(trades)
    o = gate["overall"]
    print(f"\n{label}: n={o['n']} WR={o['wr']}% avg={o['avg']}% PF={o['pf']} payoff={o['payoff']} gate={gate['gate_pass']}")
    for y in ("2024", "2025", "2026"):
        ys = [t for t in trades if str(t["entry_date"]).startswith(y)]
        if ys:
            w = sum(1 for t in ys if t["net_pnl_pct"] > 0)
            gp = sum(max(t["net_pnl_pct"], 0) for t in ys)
            gl = abs(sum(min(t["net_pnl_pct"], 0) for t in ys))
            print(f"  {y}: n={len(ys)} WR={100*w/len(ys):.1f}% avg={sum(t['net_pnl_pct'] for t in ys)/len(ys):+.2f}% PF={gp/gl if gl else 0:.2f}")


print("=== 信号强度分层组合 ===")
run("全部事件（当前组合）", False)
run("强信号事件（回购预案/首次/增持，排除回购完成/进度/前十名）", True)
conn.close()
