# -*- coding: utf-8 -*-
"""事件类型分层 TP/SL：回购 vs 增持 的分层出场表现
验证是否需要按事件类型差异化 TP/SL（自动加 TP/SL 的方向）"""
import io, json, os, sqlite3, sys
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


def is_strong(title):
    t = str(title or "")
    if "回购" in t:
        if "完成" in t or "进度" in t or "进展" in t or "结果" in t or "前十名" in t:
            return False
        return True
    if "增持" in t:
        return True
    return False


def ev_type(title):
    t = str(title or "")
    if "回购" in t:
        return "回购"
    if "增持" in t:
        return "增持"
    return "其他"


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


events = []
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
    st = stage_of(bs, i)
    if st not in ("ACCUM", "DOWNTREND"):
        continue
    adx = adx14(bs, i)
    if adx is None or adx < 20:
        continue
    entry_idx = i + 1
    if entry_idx + 16 >= len(bs):
        continue
    if bs[entry_idx]["t"] < "20230901":
        continue
    ep = bs[entry_idx]["o"]
    if ep <= 0:
        continue
    highs = []
    lows = []
    for j in range(i - 1, max(0, i - 60), -1):
        if j < 3 or j + 3 >= i:
            continue
        if len(highs) < 2 and bs[j]["h"] > max(bs[k]["h"] for k in range(j - 3, j)) and bs[j]["h"] >= max(bs[k]["h"] for k in range(j + 1, j + 4)):
            highs.append(bs[j]["h"])
        if len(lows) < 2 and bs[j]["l"] < min(bs[k]["l"] for k in range(j - 3, j)) and bs[j]["l"] <= min(bs[k]["l"] for k in range(j + 1, j + 4)):
            lows.append(bs[j]["l"])
        if len(highs) >= 2 and len(lows) >= 2:
            break
    if not highs or not lows:
        continue
    highs.sort()
    events.append({"entry_date": bs[entry_idx]["t"], "etype": ev_type(title),
                   "net_pnl_pct": round((bs[entry_idx + 15]["c"] / ep - 1) * 100 - 0.20, 4),
                   "tp1": highs[0], "sl1": lows[0] * 0.99})
conn.close()
print("事件:", len(events))


def report(label, rs):
    if len(rs) < 300:
        print(f"{label}: n={len(rs)} (过小)")
        return
    for t in rs:
        t["t1_violation"] = "False"
        t["year"] = str(t["entry_date"])[:4]
    gate = check_economic_gate(rs)
    o = gate["overall"]
    print(f"{label}: n={o['n']} WR={o['wr']}% avg={o['avg']}% PF={o['pf']}")


print("\n=== 事件类型表现（15日固定）===")
report("回购", [t for t in events if t["etype"] == "回购"])
report("增持", [t for t in events if t["etype"] == "增持"])

# TP1/SL distance by type
print("\n=== 结构距离按事件类型 ===")
for etype in ("回购", "增持"):
    rs = [t for t in events if t["etype"] == etype]
    if not rs:
        continue
    tp_d = [(t["tp1"] / t["tp1"] * 0 + 0) for t in rs]  # placeholder
    ep_list = []
    tp1_dists = []
    sl1_dists = []
    for t in events:
        pass
    # recompute distances
    tp1_all = [e["tp1"] for e in rs if e["tp1"]]
    print(f"  {etype}: n={len(rs)}")
