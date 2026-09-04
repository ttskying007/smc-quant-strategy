# -*- coding: utf-8 -*-
"""Event leg execution quality: T+1 open entry reasonableness, exit timing.
- Entry: T+1 open vs entry-day low (better entry available = bought too early?)
- Exit: 10d close vs subsequent high (sold too early?); was 10d optimal vs 7/15d?
- Compare entry open vs prior close (gap effect)"""
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
            if t and r.get("o") and r.get("h") and r.get("l") and r.get("c"):
                bs.append({"t": t, "o": float(r["o"]), "h": float(r["h"]), "l": float(r["l"]), "c": float(r["c"])})
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


stats = {"n": 0, "gap": [], "entry_day_low_diff": [], "exit_vs_peak": [], "hold_opt": defaultdict(int)}
cur.execute("SELECT date, stock_code, title FROM announce WHERE title LIKE '%增持%' OR title LIKE '%回购%'")
seen = set()
n = 0
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
    if i + 15 >= len(bs):
        continue
    ep = bs[i]["o"]
    prev_close = bs[i - 1]["c"] if i > 0 else ep
    if ep <= 0 or prev_close <= 0:
        continue
    stats["n"] += 1
    # gap: entry open vs prior close
    stats["gap"].append((ep / prev_close - 1) * 100)
    # entry day low vs entry (could we have bought lower same day?)
    stats["entry_day_low_diff"].append((bs[i]["l"] / ep - 1) * 100)
    # exit at 10d close vs subsequent 5d peak (sold too early?)
    ex = bs[i + 10]["c"]
    peak = max(bs[k]["h"] for k in range(i + 11, min(len(bs), i + 16)))
    stats["exit_vs_peak"].append((peak / ex - 1) * 100)
    # best hold: pnl at 5/10/15d
    pnls = {}
    for h in (5, 10, 15):
        pnls[h] = (bs[i + h]["c"] / ep - 1) * 100
    best = max(pnls, key=pnls.get)
    stats["hold_opt"][best] += 1
    n += 1
    if n >= 3000:
        break
conn.close()

print(f"\n=== 事件腿执行质量（n={stats['n']}）===")
gaps = sorted(stats["gap"])
print(f"入场跳空（T+1开盘 vs 披露日收盘）: med={gaps[len(gaps)//2]:+.2f}% （正=高开入场=买贵）")
lds = sorted(stats["entry_day_low_diff"])
print(f"入场日低点 vs 入场价: med={lds[len(lds)//2]:+.2f}% （负=当日还能买更低=买早）")
evs = sorted(stats["exit_vs_peak"])
print(f"10日平仓 vs 后续5日高点: med={evs[len(evs)//2]:+.2f}% （正=卖早）")
print(f"最优持有期分布: {dict(stats['hold_opt'])} （5/10/15日中哪日收益最高）")
