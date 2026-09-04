# -*- coding: utf-8 -*-
"""验证公告噪声过滤：比较 LIKE 增持/回购 原始 vs 过滤后（审计修复）"""
import sqlite3, sys
sys.stdout.reconfigure(encoding="utf-8", errors="replace")

conn = sqlite3.connect(r"E:\test\smc_project\announce\smc_announce.db")
cur = conn.cursor()
cur.execute("SELECT DISTINCT date FROM announce ORDER BY date DESC LIMIT 5")
recent = [r[0] for r in cur.fetchall()]
_neg = ("终止", "完毕", "解除", "取消", "结束", "调整", "变更", "进展", "补充协议", "届满", "减持")
total_raw = total_clean = 0
print(f"最近交易日: {recent}")
for dd in recent:
    cur.execute("SELECT stock_code, stock_name, title FROM announce WHERE date=? AND (title LIKE '%增持%' OR title LIKE '%回购%')", (dd,))
    rows = cur.fetchall()
    clean = [r for r in rows if not any(n in str(r[2]) for n in _neg)]
    total_raw += len(rows)
    total_clean += len(clean)
    print(f"  {dd}: 原始 {len(rows)} → 过滤后 {len(clean)}（滤除 {len(rows)-len(clean)} 噪声）")
    # 展示滤除的噪声示例
    noise = [r for r in rows if any(n in str(r[2]) for n in _neg)]
    for r in noise[:3]:
        print(f"    噪声示例: {r[0]} {r[1]}: {str(r[2])[:45]}")
print(f"\n合计: 原始 {total_raw} → 过滤后 {total_clean}（滤除 {total_raw-total_clean} 条噪声）")
conn.close()
