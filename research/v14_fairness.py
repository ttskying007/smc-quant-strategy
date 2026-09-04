# -*- coding: utf-8 -*-
"""v14 fairness check: event high-vol+trend leg WITHOUT 2024 (2025/2026 only).
If 2025/2026 still strong -> v14 real. If collapses -> 2024-special."""
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


def vol20_at(bs, i):
    if i < 20:
        return None
    w20 = bs[i - 20:i]
    return sum((b["h"] - b["l"]) / b["c"] for b in w20) / len(w20)


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


def is_strong(title):
    t = str(title or "")
    if "回购" in t:
        if "完成" in t or "进度" in t or "进展" in t or "结果" in t or "前十名" in t:
            return False
        return True
    if "增持" in t:
        return True
    return False


# v14 event leg (ACCUM/DOWNTREND + ADX>=20 + high-vol) with per-year stats
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
    v = vol20_at(bs, i)
    if v is None or i < 91:
        continue
    w90 = bs[i - 90:i]
    w20 = bs[i - 20:i]
    ret90 = w90[-1]["c"] / w90[0]["c"] - 1
    v20 = sum(b["v"] for b in w20) / len(w20)
    v90 = sum(b["v"] for b in w90) / len(w90)
    deep = ret90 < -0.20 and (v20 / v90 if v90 else 1) < 0.75
    hold = 20 if deep else 10
    if i + hold >= len(bs):
        continue
    ep = bs[i]["o"]
    if ep <= 0:
        continue
    cands.append({"entry_date": bs[i]["t"], "vol": v,
                  "net_pnl_pct": round((bs[i + hold]["c"] / ep - 1) * 100 - 0.20, 4)})
vols = sorted(c["vol"] for c in cands)
th = vols[len(vols) // 2]
hi = [c for c in cands if c["vol"] > th]
print(f"v14 事件腿（高波动）: {len(hi)} 笔")

by_y = defaultdict(list)
for c in hi:
    by_y[str(c["entry_date"])[:4]].append(c["net_pnl_pct"])
print("\n=== 逐年（不含2024视角）===")
for y in ("2023", "2024", "2025", "2026"):
    rs = by_y.get(y, [])
    if rs:
        w = sum(1 for x in rs if x > 0)
        print(f"  {y}: n={len(rs)} WR={100*w/len(rs):.0f}% avg={sum(rs)/len(rs):+.2f}%")

# 2025/2026 combined
rs25 = by_y.get("2025", [])
rs26 = by_y.get("2026", [])
both = rs25 + rs26
if both:
    w = sum(1 for x in both if x > 0)
    print(f"\n2025+2026 合计: n={len(both)} WR={100*w/len(both):.0f}% avg={sum(both)/len(both):+.2f}%")
# drop July 2026 (the concentration month)
rs26_no7 = [c["net_pnl_pct"] for c in hi if str(c["entry_date"]).startswith("2026") and str(c["entry_date"])[4:6] != "07"]
if rs26_no7:
    w = sum(1 for x in rs26_no7 if x > 0)
    print(f"2026 剔除7月: n={len(rs26_no7)} WR={100*w/len(rs26_no7):.0f}% avg={sum(rs26_no7)/len(rs26_no7):+.2f}%")
conn.close()
