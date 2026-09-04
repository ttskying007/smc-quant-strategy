# -*- coding: utf-8 -*-
"""DEEP-accumulation robustness: threshold sensitivity for depth classification.
Test ret90/vt variations keep the DEEP event edge."""
import glob, io, json, os, sqlite3, sys
from collections import defaultdict, Counter

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


def is_strong(title):
    t = str(title or "")
    if "回购" in t:
        if "完成" in t or "进度" in t or "进展" in t or "结果" in t or "前十名" in t:
            return False
        return True
    if "增持" in t:
        return True
    return False


# pre-collect all strong events with (ret90, vt) at entry
cur.execute("SELECT date, stock_code, title FROM announce WHERE title LIKE '%增持%' OR title LIKE '%回购%'")
events = []
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
    if i + 10 >= len(bs) or i < 91:
        continue
    w90 = bs[i - 90:i]
    w20 = bs[i - 20:i]
    ret90 = w90[-1]["c"] / w90[0]["c"] - 1
    v20 = sum(b["v"] for b in w20) / len(w20)
    v90 = sum(b["v"] for b in w90) / len(w90)
    vt = v20 / v90 if v90 else 1
    ep = bs[i]["o"]
    if ep <= 0:
        continue
    events.append({"symbol": code, "entry_date": bs[i]["t"], "ret90": ret90, "vt": vt,
                   "net_pnl_pct": round((bs[i + 10]["c"] / ep - 1) * 100 - 0.20, 4),
                   "t1_violation": "False"})
print("events:", len(events))


def test(label, ret_th, vt_th):
    rs = [t for t in events if t["ret90"] < ret_th and t["vt"] < vt_th]
    if len(rs) < 100:
        print(f"{label}: n={len(rs)} (过小)"); return
    for t in rs:
        t["t1_violation"] = str(t.get("t1_violation", "")).lower() in ("true", "1", "yes")
    gate = check_economic_gate(rs)
    o = gate["overall"]
    line = f"{label}: n={o['n']} WR={o['wr']}% avg={o['avg']}% PF={o['pf']}"
    for y in ("2024", "2025", "2026"):
        ys = [t for t in rs if str(t["entry_date"]).startswith(y)]
        if ys:
            line += f" | {y}:{sum(t['net_pnl_pct'] for t in ys)/len(ys):+.2f}%"
    print(line)


print("\n=== DEEP 阈值敏感性 ===")
test("基线 (-0.20, 0.75)", -0.20, 0.75)
test("(-0.15, 0.85) 宽松", -0.15, 0.85)
test("(-0.25, 0.65) 严格", -0.25, 0.65)
test("(-0.20, 0.85) 只变量能", -0.20, 0.85)
test("(-0.15, 0.75) 只变回撤", -0.15, 0.75)
conn.close()
