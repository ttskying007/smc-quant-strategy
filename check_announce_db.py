# -*- coding: utf-8 -*-
import sqlite3, io, sys
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
conn = sqlite3.connect(r"E:\test\smc_project\announce\smc_announce.db")
cur = conn.cursor()
cur.execute("SELECT MAX(date), COUNT(*) FROM announce")
print("公告DB: 最新", cur.fetchone())
cur.execute("SELECT date, COUNT(*) FROM announce WHERE date >= '2026-08-19' GROUP BY date ORDER BY date")
for d, c in cur.fetchall():
    print(" ", d, c, "条")
conn.close()
