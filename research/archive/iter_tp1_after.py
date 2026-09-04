# -*- coding: utf-8 -*-
"""TP1 触发后价格行为：TP1（swing high）触发后，价格继续到 TP2 vs 回落
验证"TP1 后 SL 移保本"设计的正确性（TP1 后继续 vs 回吐）"""
import io, json, os, sqlite3, sys
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


def stage_of(bs, i):
    if i < 91:
        return None
    w60 = bs[i - 60:i]
    ret60 = w60[-1]["c"] / w60[0]["c"] - 1
    v20 = sum(b["v"] for b in bs[i - 20:i]) / 20
    v60 = sum(b["v"] for b in bs[i - 60:i]) / 60
    vt = v20 / v60 if v60 else 1
    if ret60 < -0.15 and vt < 0.9:
        return "ACCUM"
    if ret60 > 0.30 and vt > 1.3:
        return "DISTRIB"
    if ret60 > 0.20 and vt > 1.1:
        return "MARKUP"
    return "UPTREND" if ret60 > 0 else "DOWNTREND"


# collect events with TP1 trigger analysis
stats = {"hit_tp1": 0, "continued_tp2": 0, "retraced_be": 0, "both": 0}
cur.execute("SELECT date, stock_code, title FROM announce WHERE title LIKE '%增持%' OR title LIKE '%回购%'")
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
    if d not in dates:
        continue
    i = dates.index(d)
    st = stage_of(bs, i)
    if st not in ("ACCUM", "DOWNTREND"):
        continue
    adx = adx14(bs, i)
    if adx is None or adx < 20:
        continue
    entry_idx = i + 1
    if entry_idx + 16 >= len(bs):
        continue
    ep = bs[entry_idx]["o"]
    if ep <= 0:
        continue
    highs = []
    lows = []
    for j in range(i - 1, max(0, i - 60), -1):
        if j < 3 or j + 3 >= i:
            continue
        if len(highs) < 3 and bs[j]["h"] > max(bs[k]["h"] for k in range(j - 3, j)) and bs[j]["h"] >= max(bs[k]["h"] for k in range(j + 1, j + 4)):
            highs.append(bs[j]["h"])
        if len(lows) < 2 and bs[j]["l"] < min(bs[k]["l"] for k in range(j - 3, j)) and bs[j]["l"] <= min(bs[k]["l"] for k in range(j + 1, j + 4)):
            lows.append(bs[j]["l"])
        if len(highs) >= 3 and len(lows) >= 2:
            break
    if not highs or not lows:
        continue
    highs.sort()
    tp1, tp2 = highs[0], (highs[1] if len(highs) > 1 else highs[0] * 1.05)
    sl1 = lows[0] * 0.99
    # find TP1 hit day
    tp1_day = None
    for k in range(entry_idx + 1, min(len(bs), entry_idx + 16)):
        if bs[k]["h"] >= tp1:
            tp1_day = k
            break
    if tp1_day is None:
        continue
    stats["hit_tp1"] += 1
    # after TP1: did price reach TP2 before dropping to BE?
    be = ep  # SL moves to breakeven
    reached_tp2 = False
    hit_be = False
    for k in range(tp1_day + 1, min(len(bs), entry_idx + 16)):
        if bs[k]["h"] >= tp2:
            reached_tp2 = True
            break
        if bs[k]["l"] <= be:
            hit_be = True
            break
    if reached_tp2:
        stats["continued_tp2"] += 1
    if hit_be:
        stats["retraced_be"] += 1
conn.close()

print("=== TP1 触发后价格行为（事件腿）===\n")
n = stats["hit_tp1"]
print(f"TP1 触发样本: {n}")
if n:
    print(f"  继续到 TP2: {stats['continued_tp2']} ({100*stats['continued_tp2']/n:.0f}%)")
    print(f"  回落至保本: {stats['retraced_be']} ({100*stats['retraced_be']/n:.0f}%)")
    print(f"  两者皆无(持有到期): {n - stats['continued_tp2'] - stats['retraced_be']} ({100*(n - stats['continued_tp2'] - stats['retraced_be'])/n:.0f}%)")
