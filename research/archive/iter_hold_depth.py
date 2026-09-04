# -*- coding: utf-8 -*-
"""Event hold-period x accumulation-depth cross.
Deep-accumulation events (bottom layout by major) may need LONGER hold to capture bounce.
Test hold 5/10/15/20 for DEEP vs non-DEEP strong events."""
import glob, io, json, os, sqlite3, sys
from collections import defaultdict

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

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


def is_deep(bs, i):
    if i < 91:
        return False
    w90 = bs[i - 90:i]
    w20 = bs[i - 20:i]
    ret90 = w90[-1]["c"] / w90[0]["c"] - 1
    v20 = sum(b["v"] for b in w20) / len(w20)
    v90 = sum(b["v"] for b in w90) / len(w90)
    vt = v20 / v90 if v90 else 1
    return ret90 < -0.20 and vt < 0.75


# collect strong events with depth flag
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
    if i + 20 >= len(bs):
        continue
    ep = bs[i]["o"]
    if ep <= 0:
        continue
    events.append({"code": code, "entry_date": bs[i]["t"], "i": i, "bs": bs, "ep": ep,
                   "deep": is_deep(bs, i)})
print("strong events:", len(events), "deep:", sum(1 for e in events if e["deep"]))


def pnl_at(e, hold):
    bs = e["bs"]
    i = e["i"]
    if i + hold >= len(bs):
        return None
    return (bs[i + hold]["c"] / e["ep"] - 1) * 100 - 0.20


print("\n=== 事件持有期 × 深度 ===")
for grp, label in [(None, "全部"), (True, "DEEP吸筹"), (False, "非DEEP")]:
    pool = [e for e in events if grp is None or e["deep"] == grp]
    if len(pool) < 100:
        print(f"{label}: 样本不足 {len(pool)}")
        continue
    for h in (5, 10, 15, 20):
        pnls = []
        for e in pool:
            p = pnl_at(e, h)
            if p is not None:
                pnls.append(p)
        if not pnls:
            continue
        avg = sum(pnls) / len(pnls)
        w = sum(1 for p in pnls if p > 0)
        by_y = defaultdict(list)
        for e in pool:
            p = pnl_at(e, h)
            if p is not None:
                by_y[str(e["entry_date"])[:4]].append(p)
        ys = " ".join(f"{y}:{sum(v)/len(v):+.1f}" for y, v in sorted(by_y.items()) if len(v) >= 20)
        print(f"  {label} hold={h}: n={len(pnls)} WR={100*w/len(pnls):.0f}% avg={avg:+.2f}% | {ys}")
conn.close()
