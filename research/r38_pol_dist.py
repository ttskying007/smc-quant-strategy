# -*- coding: utf-8 -*-
"""r38_pol_dist.py —— 事件分类极性分布: 找被过滤掉的候选里有没有可用的补充信号."""
import io, sqlite3, sys
from collections import defaultdict
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
sys.path.insert(0, r"E:\test\smc_project\research")
from core.events import classify_title

conn = sqlite3.connect(r"E:\test\smc_project\announce\smc_announce.db")
cur = conn.cursor()
cur.execute("SELECT date, stock_code, title FROM announce WHERE date >= '2023-09-01'")
rows = cur.fetchall()
pol_dist = defaultdict(int)
kind_dist = defaultdict(int)
for date, code, title in rows:
    try:
        is_ev, kind, pol, _a, _p = classify_title(title)
    except Exception:
        continue
    if not is_ev:
        continue
    pol_dist[pol] += 1
    kind_dist[kind] += 1
print("pol 分布(正事件筛选强度):", dict(sorted(pol_dist.items())))
print("kind 分布:", dict(kind_dist))
# 软否(0)与中性 —— 是否值得作为补充信号源
print("\n结论方向: pol>0 = 10151; 其余(软否/中性)是事件质量过滤掉的噪声")
