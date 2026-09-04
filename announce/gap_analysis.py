# -*- coding: utf-8 -*-
"""Analyze announcement data gap distribution - random or systematic?
Check: missing days per month/year; if gaps cluster (e.g., all of a month missing),
event stats may be biased."""
import io, json, os, sqlite3, sys
from collections import Counter, defaultdict

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

conn = sqlite3.connect(r"E:\test\smc_project\announce\smc_announce.db")
cur = conn.cursor()
cur.execute("SELECT DISTINCT date FROM announce")
have = {r[0] for r in cur.fetchall()}
conn.close()

# trading days from kline
p = r"E:\test\smc_project\hermes\kline_cache\600519_SH_daily_750.json"
raw = json.load(open(p, encoding="utf-8"))
trading = set()
for r in raw:
    t = "".join(c for c in str(r.get("t") or "") if c.isdigit())
    if len(t) >= 8 and "20230101" <= t[:8] <= "20260814":
        trading.add(f"{t[:4]}-{t[4:6]}-{t[6:8]}")

missing = sorted(trading - have)
have_cnt = len(trading) - len(missing)
print(f"总交易日: {len(trading)}, 有公告: {have_cnt} ({100*have_cnt/len(trading):.0f}%), 缺失: {len(missing)}")

# monthly gap distribution
by_month = defaultdict(lambda: [0, 0])  # month -> [have, total]
for d in trading:
    m = d[:7]
    by_month[m][1] += 1
    if d in have:
        by_month[m][0] += 1
print("\n=== 月度覆盖（2024 年起）===")
for m in sorted(by_month):
    if m < "2024-01":
        continue
    h, t = by_month[m]
    if h < t:
        print(f"  {m}: {h}/{t} 天 ({100*h/t:.0f}%) {'<<< 密集缺失' if h/t < 0.5 else ''}")
