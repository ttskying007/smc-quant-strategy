# -*- coding: utf-8 -*-
"""DNA 自动化：行为阶段识别（ACCUM/DOWNTREND/MARKUP）窗口敏感性
窗口 45/60/75/90 天的阶段识别一致性 + 各阶段事件表现"""
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


def stage_at(bs, i, win):
    if i < win + 20:
        return None
    w = bs[i - win:i]
    ret = w[-1]["c"] / w[0]["c"] - 1
    v20 = sum(b["v"] for b in bs[i - 20:i]) / 20
    vw = sum(b["v"] for b in bs[i - win:i]) / win
    vt = v20 / vw if vw else 1
    if ret < -0.15 and vt < 0.9:
        return "ACCUM"
    if ret > 0.30 and vt > 1.3:
        return "DISTRIB"
    if ret > 0.20 and vt > 1.1:
        return "MARKUP"
    return "UPTREND" if ret > 0 else "DOWNTREND"


# collect events + stage at different windows
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
    adx = adx14(bs, i)
    if adx is None or adx < 20:
        continue
    entry_idx = i + 1
    if entry_idx + 16 >= len(bs) or entry_idx < 130:
        continue
    if bs[entry_idx]["t"] < "20230901":
        continue
    ep = bs[entry_idx]["o"]
    if ep <= 0:
        continue
    stages = {}
    for win in (45, 60, 75, 90):
        stages[win] = stage_at(bs, i, win)
    events.append({"entry_date": bs[entry_idx]["t"],
                   "net_pnl_pct": round((bs[entry_idx + 15]["c"] / ep - 1) * 100 - 0.20, 4),
                   "stages": stages})
conn.close()
print("事件:", len(events))

# consistency: stage agreement across windows
from collections import Counter
agree_all = sum(1 for e in events if len(set(e["stages"].values())) == 1)
agree_60_90 = sum(1 for e in events if e["stages"][60] == e["stages"][90])
print(f"\n阶段识别一致性:")
print(f"  45/60/75/90 全一致: {100*agree_all/len(events):.0f}%")
print(f"  60 vs 90 一致: {100*agree_60_90/len(events):.0f}%")

# stage performance by window
print("\n=== 各窗口的 ACCUM/DOWNTREND 事件表现（15日）===")
for win in (60, 90):
    for stage in ("ACCUM", "DOWNTREND"):
        rs = [{"entry_date": e["entry_date"], "net_pnl_pct": e["net_pnl_pct"]} for e in events if e["stages"][win] == stage]
        if len(rs) < 300:
            print(f"  win={win} {stage}: n={len(rs)} (过小)")
            continue
        for t in rs:
            t["t1_violation"] = "False"
            t["year"] = str(t["entry_date"])[:4]
        gate = check_economic_gate(rs)
        o = gate["overall"]
        print(f"  win={win} {stage}: n={o['n']} avg={o['avg']:+.2f}% PF={o['pf']}")
