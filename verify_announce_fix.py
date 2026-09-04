# -*- coding: utf-8 -*-
import sqlite3, io, sys
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
conn = sqlite3.connect(r"E:\test\smc_project\announce\smc_announce.db")
cur = conn.cursor()
# check code format correctness
cur.execute("SELECT stock_code, stock_name, title FROM announce WHERE date='2026-08-19' AND (title LIKE '%增持%' OR title LIKE '%回购%') LIMIT 8")
print("8-19 增持/回购公告（修复后）:")
for c, n, t in cur.fetchall():
    print(f"  {c} {n}: {str(t)[:50]}")
conn.close()
