# -*- coding: utf-8 -*-
import sqlite3, io, sys

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
conn = sqlite3.connect(r"E:\test\smc_project\announce\smc_announce.db")
cur = conn.cursor()
cur.execute("SELECT COUNT(*), COUNT(DISTINCT date), MIN(date), MAX(date) FROM announce")
print("公告 DB:", cur.fetchone())
cur.execute("SELECT COUNT(*) FROM announce WHERE title LIKE '%业绩预告%' OR title LIKE '%预增%' OR title LIKE '%预减%' OR title LIKE '%扭亏%' OR title LIKE '%首亏%'")
print("业绩类公告:", cur.fetchone()[0])
cur.execute("SELECT COUNT(*) FROM announce WHERE title LIKE '%回购%' OR title LIKE '%减持%' OR title LIKE '%解禁%' OR title LIKE '%增持%'")
print("回购/减持/解禁/增持:", cur.fetchone()[0])
cur.execute("SELECT date, title FROM announce WHERE title LIKE '%业绩预告%' LIMIT 5")
for r in cur.fetchall():
    print("  ", r[0], "|", str(r[1])[:70])
conn.close()
