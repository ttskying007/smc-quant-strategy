# -*- coding: utf-8 -*-
"""信号时间顺序分析（用户核心）：同一股票 事件 → 延续 信号的时间间隔
大资金操作顺序：事件（底部确认）→ 延续（趋势维护）的时间距离"""
import io, json, os, sqlite3, sys
from collections import defaultdict, Counter

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

KT = r"E:\test\smc_project\hermes\kline_cache_tencent"
# load event dates
conn = sqlite3.connect(r"E:\test\smc_project\announce\smc_announce.db")
cur = conn.cursor()
cur.execute("SELECT stock_code, date FROM announce WHERE title LIKE '%增持%' OR title LIKE '%回购%'")
ev_map = defaultdict(list)
for code, d in cur.fetchall():
    ev_map[code].append(str(d)[:10].replace("-", ""))
conn.close()

# load continuation signal dates (from v20c trades src=CONT)
cont_map = defaultdict(list)
with open(r"E:\test\smc_project\research\combo_v20c_trades.csv", encoding="utf-8-sig") as fh:
    import csv
    for r in csv.DictReader(fh):
        if r.get("src") == "CONT":
            cont_map[r["symbol"].split(".")[0]].append(str(r["entry_date"]))

# for stocks with both: interval event -> continuation (calendar days)
intervals = []
for code, conts in cont_map.items():
    evs = sorted(ev_map.get(code, []))
    if not evs:
        continue
    for cdate in conts:
        # most recent event before continuation
        prev_ev = [e for e in evs if e <= cdate]
        if prev_ev:
            gap = (int(cdate[:4]) - int(prev_ev[-1][:4])) * 365 + \
                  (int(cdate[4:6]) - int(prev_ev[-1][4:6])) * 30 + \
                  (int(cdate[6:8]) - int(prev_ev[-1][6:8]))
            intervals.append(gap)

print("事件→延续 时间间隔分析")
print(f"有延续信号且有事件: {len(intervals)} 笔")
if intervals:
    intervals.sort()
    print(f"间隔(交易日近似): min={intervals[0]} med={intervals[len(intervals)//2]} max={intervals[-1]}")
    buckets = Counter()
    for g in intervals:
        if g <= 30:
            buckets["0-30天"] += 1
        elif g <= 90:
            buckets["31-90天"] += 1
        elif g <= 180:
            buckets["91-180天"] += 1
        else:
            buckets["180+天"] += 1
    print("分布:", dict(buckets))
    total = len(intervals)
    for k, v in sorted(buckets.items()):
        print(f"  {k}: {v} 笔 ({100*v/total:.0f}%)")
