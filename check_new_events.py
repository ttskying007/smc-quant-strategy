# -*- coding: utf-8 -*-
import sqlite3, io, sys
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
conn = sqlite3.connect(r"E:\test\smc_project\announce\smc_announce.db")
cur = conn.cursor()
cur.execute("SELECT date, COUNT(*) FROM announce WHERE (title LIKE '%增持%' OR title LIKE '%回购%') AND date>='2026-08-15' GROUP BY date ORDER BY date")
print("增持/回购公告（8-15起）:")
for d, c in cur.fetchall():
    print(f"  {d}: {c} 条")
cur.execute("SELECT date, COUNT(*) FROM announce WHERE (title LIKE '%增持%' OR title LIKE '%回购%') AND title NOT LIKE '%完成%' AND title NOT LIKE '%进度%' AND title NOT LIKE '%前十名%' AND title NOT LIKE '%进展%' AND date>='2026-08-15' GROUP BY date ORDER BY date")
print("--- 强信号（排除完成/进度/前十名/进展）---")
for d, c in cur.fetchall():
    print(f"  {d}: {c} 条")
conn.close()
