# -*- coding: utf-8 -*-
"""Event leg entry optimization: exec audit found entry-day low med -1.4% (bought early).
Test: T+1 open vs T+1 close vs T+2 open entry (with hold from entry)."""
import glob, io, json, os, sqlite3, sys
from collections import defaultdict

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
sys.path.insert(0, r"E:\test\smc_project\smc_backtest_report")
from smc_gates import check_economic_gate

KT = r"E:\test\smc_project\hermes\kline_cache_tencent"
conn = sqlite3.connect(r"E:\test\smc_project\announce\smc_announce.db")
cur = conn.cursor()
FEE = 0.20

code2file = {f.split("_")[0]: os.path.join(KT, f) for f in os.listdir(KT) if f.endswith("_daily_800.json")}
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
            if t and r.get("o") and r.get("h") and r.get("l") and r.get("c"):
                bs.append({"t": t, "o": float(r["o"]), "h": float(r["h"]), "l": float(r["l"]), "c": float(r["c"]), "v": float(r.get("v") or 0)})
        bs.sort(key=lambda b: b["t"])
        bar_cache[code] = bs
    return bar_cache[code]


def is_strong(title):
    t = str(title or "")
    if "回购" in t:
        if "完成" in t or "进度" in t or "进展" in t or "结果" in t or "前十名" in t:
            return False
        return True
    if "增持" in t:
        return True
    return False


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


# collect events with entry index i (T+1)
cands = []
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
    st = stage_at(bs, i)
    if st not in ("ACCUM", "DOWNTREND"):
        continue
    adx = adx14(bs, i)
    if adx is None or adx < 20:
        continue
    if i + 16 >= len(bs):
        continue
    cands.append({"entry_date": bs[i]["t"], "i": i, "bs": bs})
conn.close()
print("event candidates:", len(cands))


def run(entry_offset, hold):
    """entry_offset: 0=T+1 open, 1=T+1 close, 2=T+2 open. hold bars after entry."""
    trades = []
    for c in cands:
        i = c["i"]
        bs = c["bs"]
        if entry_offset == 0:
            ep = bs[i]["o"]
            ei = i
        elif entry_offset == 1:
            ep = bs[i]["c"]
            ei = i
        else:
            ep = bs[i + 1]["o"]
            ei = i + 1
        if ep <= 0 or ei + hold >= len(bs):
            continue
        trades.append({"entry_date": bs[ei]["t"],
                       "net_pnl_pct": round((bs[ei + hold]["c"] / ep - 1) * 100 - FEE, 4), "t1_violation": "False"})
    for t in trades:
        t["year"] = str(t["entry_date"])[:4]
    gate = check_economic_gate(trades)
    o = gate["overall"]
    line = f"{label}: n={o['n']} avg={o['avg']:+.2f}% PF={o['pf']} WR={o['wr']}%"
    for y in ("2024", "2025", "2026"):
        ys = [t for t in trades if t["year"] == y]
        if ys:
            line += f" | {y}:{sum(t['net_pnl_pct'] for t in ys)/len(ys):+.2f}%"
    print(line)


print("\n=== 事件腿入场方式（持有15日）===")
for label, off in [("T+1开盘", 0), ("T+1收盘", 1), ("T+2开盘", 2)]:
    run_off = off
    trades = []
    for c in cands:
        i = c["i"]
        bs = c["bs"]
        if off == 0:
            ep, ei = bs[i]["o"], i
        elif off == 1:
            ep, ei = bs[i]["c"], i
        else:
            ep, ei = bs[i + 1]["o"], i + 1
        if ep <= 0 or ei + 15 >= len(bs):
            continue
        trades.append({"entry_date": bs[ei]["t"],
                       "net_pnl_pct": round((bs[ei + 15]["c"] / ep - 1) * 100 - FEE, 4), "t1_violation": "False"})
    for t in trades:
        t["year"] = str(t["entry_date"])[:4]
    gate = check_economic_gate(trades)
    o = gate["overall"]
    line = f"{label}: n={o['n']} avg={o['avg']:+.2f}% PF={o['pf']} WR={o['wr']}%"
    for y in ("2024", "2025", "2026"):
        ys = [t for t in trades if t["year"] == y]
        if ys:
            line += f" | {y}:{sum(t['net_pnl_pct'] for t in ys)/len(ys):+.2f}%"
    print(line)
