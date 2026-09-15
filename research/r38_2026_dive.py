# -*- coding: utf-8 -*-
"""r38_2026_dive.py —— R38 2026 特异性深挖: 事件供给为何崩(选股量少核心).
检查: ①2026 公告正事件月分布 vs 2024/2025 ②通过率变化 ③市场环境(指数).
纯研究. """
import io, sqlite3, sys
from collections import defaultdict
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
sys.path.insert(0, r"E:\test\smc_project\research")
from core.events import classify_title

conn = sqlite3.connect(r"E:\test\smc_project\announce\smc_announce.db")
cur = conn.cursor()
cur.execute("SELECT date, stock_code, title FROM announce WHERE date >= '2023-09-01'")
rows = cur.fetchall()
by_year_ev = defaultdict(int)
by_year_all = defaultdict(int)
for date, code, title in rows:
    y = str(date)[:4]
    by_year_all[y] += 1
    try:
        is_ev, kind, pol, _a, _p = classify_title(title)
    except Exception:
        continue
    if is_ev and pol > 0:
        by_year_ev[y] += 1
print("年度公告总量 vs 正事件数:")
for y in ("2023", "2024", "2025", "2026"):
    print(f"  {y}: 公告 {by_year_all.get(y,0)} | 正事件 {by_year_ev.get(y,0)} "
          f"({100*by_year_ev.get(y,0)/by_year_all.get(y,0):.2f}%)")

# 月度正事件(2026 vs 2024) —— 季节性 vs 供给收缩
m_ev = defaultdict(lambda: defaultdict(int))
for date, code, title in rows:
    y, m = str(date)[:4], str(date)[5:7]
    try:
        is_ev, kind, pol, _a, _p = classify_title(title)
    except Exception:
        continue
    if is_ev and pol > 0:
        m_ev[y][m] += 1
print("\n正事件月分布 (2024 vs 2026):")
print(f"{'月':>4}{'2024':>8}{'2025':>8}{'2026':>8}")
for mm in range(1, 13):
    m = f"{mm:02d}"
    print(f"{mm:>4}{m_ev['2024'].get(m,0):>8}{m_ev['2025'].get(m,0):>8}{m_ev['2026'].get(m,0):>8}")
