# -*- coding: utf-8 -*-
import sqlite3, io, sys

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
conn = sqlite3.connect(r"E:\test\smc_project\margin\smc_margin.db")
cur = conn.cursor()
cur.execute("SELECT COUNT(DISTINCT date), MIN(date), MAX(date) FROM margin_daily")
print("日期覆盖:", cur.fetchone())
cur.execute("SELECT COUNT(DISTINCT scode) FROM margin_daily")
print("标的数:", cur.fetchone()[0])
cur.execute("SELECT date, COUNT(*) FROM margin_daily GROUP BY date ORDER BY date LIMIT 1")
print("首日:", cur.fetchone())
cur.execute("SELECT date, COUNT(*) FROM margin_daily GROUP BY date ORDER BY date DESC LIMIT 1")
print("末日:", cur.fetchone())
cur.execute("SELECT COUNT(*) FROM margin_daily WHERE rzye IS NULL OR rzye=0")
print("rzye 为 0/空:", cur.fetchone()[0])
cur.execute("SELECT COUNT(DISTINCT scode) FROM margin_daily WHERE rchange5dcp IS NOT NULL")
print("有5日变化数据标的:", cur.fetchone()[0])
cur.execute("SELECT market, COUNT(*) FROM margin_daily GROUP BY market")
for r in cur.fetchall():
    print("  market:", r)
# yearly row counts
cur.execute("SELECT substr(date,1,4) y, COUNT(*), COUNT(DISTINCT scode) FROM margin_daily GROUP BY y")
print("分年:")
for r in cur.fetchall():
    print("  ", r)
conn.close()
