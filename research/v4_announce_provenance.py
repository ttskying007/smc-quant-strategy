# -*- coding: utf-8 -*-
"""v4_announce_provenance.py —— 完整版: P1 未来日 / P2 溯源抽样 / P3 生产日期窗语义"""
import json, os, sqlite3, sys, io, datetime
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
DB = r"E:\test\smc_project\announce\smc_announce.db"
today = datetime.date.today().strftime("%Y%m%d")
con = sqlite3.connect(DB)
cur = con.cursor()

# P1: D 分布(格式/未来日)
cur.execute("SELECT MIN(date), MAX(date) FROM announce")
mn, mx = cur.fetchone()
print(f"P1 日期范围: {mn} ~ {mx} (今天={today})")
cur.execute("SELECT COUNT(*) FROM announce WHERE date > ?", (today,))
fut = cur.fetchone()[0]
print(f"   未来日期行: {fut} ({'⚠污染!' if fut else '无 ✓'})")
# 0911 当日行
cur.execute("SELECT COUNT(*) FROM announce WHERE date = '2026-09-11'")
print(f"   2026-09-11 行: {cur.fetchone()[0]}")

# P2: 溯源抽样 5 条近期增持
cur.execute("SELECT date, stock_code, stock_name, title FROM announce WHERE title LIKE '%增持%' AND date >= '2026-09-08' ORDER BY date DESC LIMIT 5")
print("\nP2 近期增持抽样:")
for d, c, n, t in cur.fetchall():
    print(f"  {d} {c} {n}: {t[:48]}")

# P3: 生产查询链的日期窗(检查 paper_sim 怎么取 announce)
import subprocess
r = subprocess.run(["powershell", "-Command",
    "Select-String -Path E:\\test\\smc_project\\research\\paper_sim.py -Pattern 'announce|smc_announce|date.*>=|D\\+1|valid_from' | Select-Object -First 14 LineNumber,Line"],
    capture_output=True, text=True, encoding="utf-8")
print("\nP3 paper_sim 日期窗代码:")
print(r.stdout[:2600])
con.close()