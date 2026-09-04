# -*- coding: utf-8 -*-
"""调试：8-18/19 强信号事件为何未被 paper_sim 选股"""
import io, json, os, sqlite3, sys
sys.path.insert(0, r"E:\test\smc_project\research")
import paper_sim as ps
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

conn = sqlite3.connect(r"E:\test\smc_project\announce\smc_announce.db")
cur = conn.cursor()
cur.execute("SELECT DISTINCT date FROM announce ORDER BY date DESC LIMIT 3")
print("paper_sim recent_days:", [r[0] for r in cur.fetchall()])

# check 8-18/19 strong events + their stage
cur.execute("SELECT date, stock_code, stock_name, title FROM announce WHERE date IN ('2026-08-18','2026-08-19') AND (title LIKE '%增持%' OR title LIKE '%回购%') AND title NOT LIKE '%完成%' AND title NOT LIKE '%进度%' AND title NOT LIKE '%前十名%'")
led = ps.load_ledger()
known = {(t["code"], t.get("signal_date", "")) for t in led}
for date, code, name, title in cur.fetchall():
    d8 = str(date).replace("-", "")
    if (code, str(date)) in known:
        print(f"  [已known] {code} {name} {date}")
        continue
    bs = ps.bars_of(code)
    if not bs:
        print(f"  [无K线] {code} {name} {date}")
        continue
    dates = [b["t"] for b in bs]
    if d8 not in dates:
        print(f"  [K线无此日] {code} {name} {date} (K线最新 {dates[-1] if dates else '?'})")
        continue
    i = dates.index(d8)
    print(f"  [候选] {code} {name} {date} K线日={d8} 最新={dates[-1]}")
conn.close()
