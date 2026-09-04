# -*- coding: utf-8 -*-
"""v8 oracle: behavior-stage reproducibility check.
Independent implementation (different window/threshold logic) re-derives stage;
verify event leg stage assignment is stable (not implementation-specific)."""
import glob, io, json, os, sqlite3, sys
from collections import defaultdict, Counter

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


def stage_base(bs, i, win=60, acc=-0.15, mark=0.20, dist=0.30, va=0.9, vm=1.1, vd=1.3):
    if i < win + 1:
        return None
    w60 = bs[i - win:i]
    w20 = bs[i - 20:i]
    ret = w60[-1]["c"] / w60[0]["c"] - 1
    v20 = sum(b["v"] for b in w20) / len(w20)
    v60 = sum(b["v"] for b in w60) / len(w60)
    vt = v20 / v60 if v60 else 1
    if ret < acc and vt < va:
        return "ACCUM"
    if ret > dist and vt > vd:
        return "DISTRIB"
    if ret > mark and vt > vm:
        return "MARKUP"
    if ret > 0:
        return "UPTREND"
    return "DOWNTREND"


def stage_oracle(bs, i):
    """Independent: 40-bar window, different logic (midpoint + volume slope)."""
    if i < 41:
        return None
    w = bs[i - 40:i]
    ret = w[-1]["c"] / w[0]["c"] - 1
    # volume slope: compare first 20 vs last 20 avg vol
    v_first = sum(b["v"] for b in w[:20]) / 20
    v_last = sum(b["v"] for b in w[20:]) / 20
    slope = v_last / v_first if v_first else 1
    if ret < -0.10 and slope < 0.95:
        return "ACCUM"
    if ret > 0.25 and slope > 1.2:
        return "MARKUP"
    if ret > 0:
        return "UPTREND"
    return "DOWNTREND"


# sample events and compare base vs oracle stage
cur.execute("SELECT date, stock_code FROM announce WHERE title LIKE '%增持%' OR title LIKE '%回购%' LIMIT 2000")
matched = total = 0
disagree = Counter()
samples = []
for date, code in cur.fetchall():
    d = str(date)[:10].replace("-", "")
    bs = bars_of(code)
    if not bs:
        continue
    dates = [b["t"] for b in bs]
    nxt = [x for x in dates if x > d]
    if not nxt:
        continue
    i = dates.index(nxt[0])
    sb = stage_base(bs, i)
    so = stage_oracle(bs, i)
    if sb is None or so is None:
        continue
    total += 1
    if sb == so:
        matched += 1
    else:
        disagree[(sb, so)] += 1
        if len(samples) < 5:
            samples.append((code, d, sb, so))
print(f"oracle 对比: 一致 {matched}/{total} = {100*matched/total:.1f}%")
print("不一致类型:", dict(disagree.most_common(6)))
for c, d, sb, so in samples:
    print(f"  {c} {d}: base={sb} oracle={so}")
conn.close()
