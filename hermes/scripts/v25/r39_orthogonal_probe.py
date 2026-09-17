# -*- coding: utf-8 -*-
"""r39_orthogonal_probe.py —— 正交信息维度探查(审计 Iteration 4).

审计 Iteration 4: "如果要寻找新 edge, 应优先引入带发布时间的正交信息维度"
候选方向: 公告数值变化 / 公司回购/增持条款 / 行业资金扩散 / 订单流.

本脚本探查 announce 库中可提取的正交数值特征:
  ① 标题中增持金额/占比/回购规模的可提取性(正则匹配)
  ② 按年的公告量分布(确认跨期覆盖)
  ③ 与事件腿基线的 join 可行性(需要 symbol + date)
纯只读探查, 不修改生产.
"""
import io
import os
import re
import sqlite3
import sys
from collections import Counter

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
db = r"E:\test\smc_project\announce\smc_announce.db"
con = sqlite3.connect(db)
cur = con.cursor()

print("=" * 90)
print("① 标题中正交数值特征的可提取性")
print("=" * 90)
# 抽样 5000 条含 增持/回购 的标题, 统计可提取特征
cur.execute("""SELECT date, stock_code, title FROM announce
               WHERE (title LIKE '%增持%' OR title LIKE '%回购%')
               ORDER BY date DESC LIMIT 8000""")
rows = cur.fetchall()

amount_re = re.compile(r"增持[\u4e00-\u9fff]*?([\d.,]+)\s*(亿|万|千|元)")
pct_re = re.compile(r"([\d.]+)\s*%")
buyback_re = re.compile(r"回购[\u4e00-\u9fff]*?([\d.,]+)\s*(亿|万|千|元)")
amt_hits = 0
pct_hits = 0
bb_hits = 0
samples = []
for d, code, title in rows:
    m1 = amount_re.search(str(title))
    m2 = pct_re.search(str(title))
    m3 = buyback_re.search(str(title))
    if m1:
        amt_hits += 1
    if m2:
        pct_hits += 1
    if m3:
        bb_hits += 1
    if len(samples) < 5 and (m1 or m3):
        samples.append((d, code, str(title)[:80]))
print("抽样 %d 条(含增持/回购): 增持金额=%d (%.0f%%) | 含%%=%d (%.0f%%) | 回购金额=%d (%.0f%%)"
      % (len(rows), amt_hits, 100 * amt_hits / len(rows),
         pct_hits, 100 * pct_hits / len(rows),
         bb_hits, 100 * bb_hits / len(rows)))
print("\n样例(含金额/占比):")
for d, c, t in samples:
    print("  %s %s: %s" % (d, c, t))

print("\n" + "=" * 90)
print("② 按年分布(跨期覆盖)")
print("=" * 90)
cur.execute("""SELECT substr(date,1,4), COUNT(*) FROM announce GROUP BY 1 ORDER BY 1""")
for y, n in cur.fetchall():
    print("  %s: %d" % (y, n))

print("\n" + "=" * 90)
print("③ 增持/回购公告总量")
print("=" * 90)
cur.execute("""SELECT COUNT(*) FROM announce WHERE title LIKE '%增持%' OR title LIKE '%回购%'""")
n = cur.fetchone()[0]
cur.execute("""SELECT COUNT(DISTINCT stock_code) FROM announce WHERE title LIKE '%增持%' OR title LIKE '%回购%'""")
nd = cur.fetchone()[0]
print("  增持/回购公告: %d 条, 覆盖 %d 只股票" % (n, nd))
con.close()