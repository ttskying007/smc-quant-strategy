# -*- coding: utf-8 -*-
"""对回填的 09-15..09-19 announce 数据立即跑 funnel 事件计数,验证我们把数据带回了正确的量
- 非 production 路径, paper_sim 只扫 declare days 1-5 里候选.
- 因此先对 announce DB **按子集统计汇总** console (date, 含增持回购被分类 event, dup, missing_data → orders 数量)。
"""
import sys, io, sqlite3, os
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
sys.path.insert(0, r'research')
import config as CFG
from core.events import classify_title_detailed

days = ['2026-09-15', '2026-09-16', '2026-09-17', '2026-09-18', '2026-09-19']
c = sqlite3.connect(CFG.ANNOUNCE_DB)
print(f"{'日期':>12s} {'raw_announce':>12s} {'含增回':>10s} {'EVENT':>7s} {'HARD':>6s} {'SOFT':>5s} {'SOFT_Δ':>8s} {'去重后端口径':>10s}")
all_stats = {}
for d in days:
    # 全体 raw announce = date
    raw = c.execute("SELECT COUNT(*) FROM announce WHERE date=?", (d,)).fetchone()[0]
    # 标题含增持/回购类 (与 paper_sim 同检查)
    buyback = c.execute("SELECT COUNT(*) FROM announce WHERE date=? AND (title LIKE '%增持%' OR title LIKE '%回购%')", (d,)).fetchone()[0]
    # 分类:
    rows = c.execute("SELECT title FROM announce WHERE date=? AND (title LIKE '%增持%' OR title LIKE '%回购%')", (d,)).fetchall()
    ev = hard = soft = soft_delta = 0
    for (t,) in rows:
        lab = classify_title_detailed(t)
        if isinstance(lab, (list, tuple)):
            lvl = lab[5]
        else:
            lvl = lab
        if lvl == 'EVENT':
            ev += 1
        elif lvl == 'HARD_REJECT':
            hard += 1
        elif lvl == 'PROGRESS_WITH_DELTA':
            soft_delta += 1
        elif lvl == 'SOFT_REJECT':
            soft += 1
    # 去重 (每股每日唯一) -- 用 paper_sim 中类似的逻辑: 这里是近似统计
    print(f"{d} {raw:>12d} {buyback:>10d} {ev:>7d} {hard:>6d} {soft:>5d} {soft_delta:>8d}")
    all_stats[d] = {'raw': raw, 'buyback': buyback, 'EVENT': ev, 'HARD': hard, 'SOFT': soft, 'SOFT_delta': soft_delta}
import json as j
j_dump = {"asof": __import__('time').strftime("%Y-%m-%d %H:%M:%S"), "days": all_stats}
j.dump(j_dump, open(r'research/handover/announce_funnel_post_gap.json', 'w', encoding='utf-8'), ensure_ascii=False, indent=2, default=str)
c.close()
print("\nwrote research/handover/announce_funnel_post_gap.json (announce 数据回填后评估)")
