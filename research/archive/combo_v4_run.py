# -*- coding: utf-8 -*-
"""DNA-optimal bucket: SMC leg restricted to 低波动+低流动 (small-cap stable).
Test combo with DNA-filtered SMC + strong events. Also check tradeability caveat."""
import csv, glob, io, json, os, sqlite3, sys
from collections import defaultdict

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
sys.path.insert(0, r"E:\test\smc_project\smc_backtest_report")
from smc_gates import check_economic_gate

KT = r"E:\test\smc_project\hermes\kline_cache_tencent"
conn = sqlite3.connect(r"E:\test\smc_project\announce\smc_announce.db")
cur = conn.cursor()


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


def dna_at(symbol, entry_date):
    code, ex = symbol.split(".")
    fn = f"{code}_{ex}_daily_800.json"
    p = os.path.join(KT, fn)
    if not os.path.exists(p):
        return None, None
    bs = bars(p)
    dates = [b["t"] for b in bs]
    if entry_date not in dates:
        prev = [d for d in dates if d < entry_date]
        if not prev:
            return None, None
        i = dates.index(prev[-1])
    else:
        i = dates.index(entry_date)
    if i < 25:
        return None, None
    win = bs[i - 20:i]
    if not win:
        return None, None
    vol = sum((b["h"] - b["l"]) / b["c"] for b in win) / len(win)
    liq = sum(b["v"] for b in win) / len(win)
    return vol, liq


# SMC leg
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

smc = []
dnas = []
for t in trades:
    r20 = r20_of(t["symbol"], str(t["entry_date"]))
    if r20 is None or not (0 <= r20 < 0.15):
        continue
    vol, liq = dna_at(t["symbol"], str(t["entry_date"]))
    if vol is None:
        continue
    dnas.append((vol, liq))
    t["vol20"], t["liq20"] = vol, liq
    smc.append(t)
vols = sorted(d[0] for d in dnas)
liqs = sorted(d[1] for d in dnas)
vmed, lmed = vols[len(vols)//2], liqs[len(liqs)//2]

# event leg (strong)
def is_strong(title):
    t = str(title or "")
    if "回购" in t:
        if "完成" in t or "进度" in t or "进展" in t or "结果" in t or "前十名" in t:
            return False
        return True
    if "增持" in t:
        return True
    return False

code2file = {}
for f in os.listdir(KT):
    if f.endswith("_daily_800.json"):
        code2file[f.split("_")[0]] = os.path.join(KT, f)

ev_cache = {}
def ev_bars(code):
    if code not in ev_cache:
        p = code2file.get(code)
        if not p:
            ev_cache[code] = []
            return ev_cache[code]
        raw = json.load(open(p, encoding="utf-8"))
        bs = []
        for r in raw:
            t = "".join(x for x in str(r.get("t") or "") if x.isdigit())[:8]
            if t and r.get("o") and r.get("h") and r.get("l") and r.get("c"):
                bs.append({"t": t, "o": float(r["o"]), "h": float(r["h"]), "l": float(r["l"]), "c": float(r["c"])})
        bs.sort(key=lambda b: b["t"])
        ev_cache[code] = bs
    return ev_cache[code]

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
    bs = ev_bars(code)
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
    ev.append({"symbol": code, "entry_date": bs[i]["t"],
               "net_pnl_pct": round((bs[i + 10]["c"] / ep - 1) * 100 - 0.20, 4), "src": "EVENT"})
print(f"SMC all: {len(smc)}, strong events: {len(ev)}, medians vol={vmed:.4f} liq={lmed:.0f}")


def combo_report(label, smc_leg):
    combined = smc_leg + ev
    for t in combined:
        t.setdefault("t1_violation", "False")
        t["t1_violation"] = str(t.get("t1_violation", "")).lower() in ("true", "1", "yes")
        t["year"] = str(t["entry_date"])[:4]
    gate = check_economic_gate(combined)
    o = gate["overall"]
    print(f"{label}: n={o['n']} WR={o['wr']}% avg={o['avg']}% PF={o['pf']} payoff={o['payoff']}")
    for y in ("2024", "2025", "2026"):
        ys = [t for t in combined if t["year"] == y]
        if ys:
            w = sum(1 for t in ys if t["net_pnl_pct"] > 0)
            print(f"    {y}: n={len(ys)} WR={100*w/len(ys):.0f}% avg={sum(t['net_pnl_pct'] for t in ys)/len(ys):+.2f}%")


print("\n=== 组合 v4（DNA 桶过滤 SMC + 强事件）===")
combo_report("v3基线（SMC全部）", smc)
combo_report("v4a（SMC低波动+低流动）", [t for t in smc if t["vol20"] <= vmed and t["liq20"] <= lmed])
combo_report("v4b（SMC低波动 任意流动）", [t for t in smc if t["vol20"] <= vmed])
combo_report("v4c（SMC低流动 任意波动）", [t for t in smc if t["liq20"] <= lmed])
conn.close()
