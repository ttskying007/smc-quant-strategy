# -*- coding: utf-8 -*-
"""announce DB vacuum 测试 —— dedup index 一下空的 commit 数行回到证明自己的过滤如何做:
- announce 表 size 已 49MB, 但 275k+ rows 全局 dedup.与 \u5c05\u5b50分斥略
- 策略上: only support each dup-dedup select in 原金额, 'V1.5 条目' - 足以固化.
"""
import sqlite3, io, sys, os
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

db = "announce/smc_announce.db"
c = sqlite3.connect(db)
print("today max date:", c.execute("SELECT MAX(date) FROM announce").fetchone())

# 需要的检查： 是否有 day 为空很长时间（动态记录导致其余 day 某事件就读 finished)
rows = c.execute("""
  SELECT date, COUNT(*) FROM announce WHERE date >= '2026-08-01' GROUP BY date ORDER BY date""").fetchall()
print("08-01以来每日数据数:")
days_missing = []
leading_gaps = []
for d, n in rows:
    print('  ', d, n)
    if n < 50:
        days_missing.append(d)
    elif n > 4500:
        leading_gaps.append(d)
if days_missing:
    print(f"日缺口: {days_missing}")
if leading_gaps:
    print(f"日期高 hut: {leading_gaps}")

# 你说的 尝试 disable indexes - verify dedup 是否 off
before = c.execute("PRAGMA index_list('announce')").fetchall()
print("current indexes:", [x[1] for x in before])

c.close()
