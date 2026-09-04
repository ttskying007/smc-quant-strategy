# -*- coding: utf-8 -*-
"""事件 alpha 时间曲线：入场后 1/3/5/10/15/20/30 日平均收益（最优持有与衰减点）"""
import io, json, os, sqlite3, sys
from collections import defaultdict

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

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


# collect events with entry info (T+1 open)
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
    if d not in dates:
        continue
    i = dates.index(d)
    st, deep = stage_and_deep(bs, i)
    if st not in ("ACCUM", "DOWNTREND"):
        continue
    adx = adx14(bs, i)
    if adx is None or adx < 20:
        continue
    if i + 31 >= len(bs):
        continue
    cands.append({"i": i + 1, "bs": bs})  # entry index = T+1
conn.close()
print("events:", len(cands))

# avg pnl at horizons
print("\n=== 事件 alpha 时间曲线（T+1 入场后各日收益）===")
for h in (1, 3, 5, 10, 15, 20, 30):
    pnls = []
    for c in cands:
        i = c["i"]
        if i + h >= len(c["bs"]):
            continue
        ep = c["bs"][i]["o"]
        if ep <= 0:
            continue
        pnls.append((c["bs"][i + h]["c"] / ep - 1) * 100)
    if pnls:
        w = sum(1 for p in pnls if p > 0)
        print(f"  T+{h}: avg={sum(pnls)/len(pnls):+.2f}% WR={100*w/len(pnls):.0f}% n={len(pnls)}")
