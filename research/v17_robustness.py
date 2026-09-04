# -*- coding: utf-8 -*-
"""v17 hold sensitivity: non-deep hold 12/15/18 (deep stays 20)."""
import csv, glob, io, json, os, sqlite3, sys
from collections import defaultdict

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
sys.path.insert(0, r"E:\test\smc_project\smc_backtest_report")
from smc_gates import check_economic_gate

KT = r"E:\test\smc_project\hermes\kline_cache_tencent"
conn = sqlite3.connect(r"E:\test\smc_project\announce\smc_announce.db")
cur = conn.cursor()

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


def stage_and_deep(bs, i):
    if i < 91:
        return None, False
    w90 = bs[i - 90:i]
    w60 = bs[i - 60:i]
    w20 = bs[i - 20:i]
    ret90 = w90[-1]["c"] / w90[0]["c"] - 1
    ret60 = w60[-1]["c"] / w60[0]["c"] - 1
    v20 = sum(b["v"] for b in w20) / len(w20)
    v60 = sum(b["v"] for b in w60) / len(w60)
    v90 = sum(b["v"] for b in w90) / len(w90)
    vt60 = v20 / v60 if v60 else 1
    vt90 = v20 / v90 if v90 else 1
    deep = ret90 < -0.20 and vt90 < 0.75
    if ret60 < -0.15 and vt60 < 0.9:
        return "ACCUM", deep
    if ret60 > 0.30 and vt60 > 1.3:
        return "DISTRIB", deep
    if ret60 > 0.20 and vt60 > 1.1:
        return "MARKUP", deep
    if ret60 > 0:
        return "UPTREND", deep
    return "DOWNTREND", deep


def is_strong(title):
    t = str(title or "")
    if "回购" in t:
        if "完成" in t or "进度" in t or "进展" in t or "结果" in t or "前十名" in t:
            return False
        return True
    if "增持" in t:
        return True
    return False


# event candidates once (ACCUM/DOWNTREND + ADX>=20, depth flag)
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
    st, deep = stage_and_deep(bs, i)
    if st not in ("ACCUM", "DOWNTREND"):
        continue
    adx = adx14(bs, i)
    if adx is None or adx < 20:
        continue
    if i + 25 >= len(bs):
        continue
    ep = bs[i]["o"]
    if ep <= 0:
        continue
    cands.append({"entry_date": bs[i]["t"], "deep": deep, "i": i, "bs": bs, "ep": ep})
print("event candidates:", len(cands))


def run(non_deep, deep_hold):
    ev = []
    for c in cands:
        hold = deep_hold if c["deep"] else non_deep
        if c["i"] + hold >= len(c["bs"]):
            continue
        ev.append({"entry_date": c["entry_date"],
                   "net_pnl_pct": round((c["bs"][c["i"] + hold]["c"] / c["ep"] - 1) * 100 - 0.20, 4),
                   "t1_violation": "False"})
    for t in ev:
        t["year"] = str(t["entry_date"])[:4]
    gate = check_economic_gate(ev)
    o = gate["overall"]
    line = f"非DEEP={non_deep}/DEEP={deep_hold}: n={o['n']} avg={o['avg']:+.2f}% PF={o['pf']} WR={o['wr']}%"
    for y in ("2024", "2025", "2026"):
        ys = [t for t in ev if t["year"] == y]
        if ys:
            line += f" | {y}:{sum(t['net_pnl_pct'] for t in ys)/len(ys):+.2f}%"
    print(line)


print("\n=== v17 持有期敏感性 ===")
run(10, 20)
run(12, 20)
run(15, 20)
run(18, 20)
run(15, 25)
conn.close()
