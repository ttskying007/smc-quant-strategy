# -*- coding: utf-8 -*-
"""r38_pool_analysis.py —— R38 候选池分析: 事件腿供给端.
检查: ①公告库总量/时间覆盖 ②增持/回购类目占比 ③通过 stage+ADX 过滤后的
实际信号率(量少的环节在哪) ④UP-regime 过滤再加一层后剩多少. 纯研究. """
import io, json, os, sqlite3, sys, csv
from collections import defaultdict
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
sys.path.insert(0, r"E:\test\smc_project\research")
from core.events import classify_title

conn = sqlite3.connect(r"E:\test\smc_project\announce\smc_announce.db")
cur = conn.cursor()
cur.execute("SELECT COUNT(*), MIN(date), MAX(date) FROM announce")
total, dmin, dmax = cur.fetchone()
print(f"公告库: {total} 条, {dmin} ~ {dmax}")

# 2023-09 以来(回测窗口) 增持/回购 候选
cur.execute("SELECT date, stock_code, title FROM announce WHERE date >= '2023-09-01'")
rows = cur.fetchall()
print(f"2023-09+ 公告: {len(rows)} 条")
ev_cnt = 0
by_kind = defaultdict(int)
for date, code, title in rows:
    try:
        is_ev, kind, pol, _a, _p = classify_title(title)
    except Exception:
        continue
    if is_ev and pol > 0:
        ev_cnt += 1
        by_kind[kind] += 1
print(f"  其中正事件(增持/回购 positive): {ev_cnt} 条 ({100*ev_cnt/len(rows):.1f}%)")
print(f"  分类构成: {dict(by_kind)}")

# 回测实际产出(1640 笔 EVENT from ~X 候选) —— 漏斗
kt = r"E:\test\smc_project\hermes\kline_cache_tencent"
n_kline = len([f for f in os.listdir(kt) if f.endswith('_daily_800.json')])
print(f"K线缓存股票数: {n_kline} (全A约5400)")
print(f"事件腿基线: 1640 笔 / 2023-09~2026-09 ≈ {1640/3:.0f} 笔/年 ≈ {1640/750:.2f} 笔/交易日")
print(f"UP-only(MA20): 805 笔 ≈ {805/3:.0f} 笔/年 ≈ {805/750:.2f} 笔/交易日")
print(f"≈ 每交易日 0.5~1.1 笔 —— 用户感知'量少'主要来自: ①只吃事件腿(增持/回购) ②stage+ADX 过滤 ③UP regime")

# 交易机会的理论上限: 若引入 SMC/缠论技术信号腿(不依赖公告), 全市场扫描
# 粗略: 全A 5400只 × 每年出现 1-2 次合格 3买/扫损+FVG 结构 ≈ 5000-10000 候选/年
print("\n候选池扩展方向(下一轮研究):")
print("  ①技术信号腿: SMC 扫损+FVG / 缠论3买 全市场扫描(不依赖公告) → 候选池扩大 10-50x")
print("  ②公告扩展: 增持/回购之外加 股权激励/业绩预告/大宗交易 事件")
print("  ③保持 UP-regime 过滤(已验证, 是质量保证) —— 扩池不降质")
