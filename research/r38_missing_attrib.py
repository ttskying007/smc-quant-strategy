# -*- coding: utf-8 -*-
"""r38_missing_attrib.py —— R38 缺失样本归因(决定新事件类型结论可信度).

R38j 三个候选均有高缺失率(业绩预增 23.3% / 业绩预减 28.7% / 股权激励 61.7%),
缺失=该股不在 kline_cache_tencent。若缺失股系统性偏向某类(如退市股集中
在业绩预减组), 则剔除它们会**高估**收益, 结论不可用。

本脚本按公告分组, 统计缺失股票:
  ① 代码前缀分布(60/68/00/30/8xx/4xx —— 8xx/4xx 是北交所/新三板, 不在缓存)
  ② 是否出现在 ST/退市 相关公告中
  ③ 与全市场缓存覆盖率对比, 判断偏差方向

纯研究, 不修改生产。
"""
import io, os, sqlite3, sys
from collections import defaultdict
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

KT = r"E:\test\smc_project\hermes\kline_cache_tencent"
cached = {f.split("_")[0] for f in os.listdir(KT) if f.endswith("_daily_800.json")}
print(f"kline_cache 股票数: {len(cached)}")

conn = sqlite3.connect(r"E:\test\smc_project\announce\smc_announce.db")
cur = conn.cursor()

GROUPS = [
    ("业绩预增", "title LIKE '%业绩预增%'"),
    ("业绩预减", "title LIKE '%业绩预减%' OR title LIKE '%业绩预亏%'"),
    ("股权激励授予", "title LIKE '%股权激励%' AND title LIKE '%授予%'"),
    ("股东增持(对照)", "title LIKE '%增持%' AND title LIKE '%股东%'"),
]

def pfx(c):
    c = str(c)
    if c.startswith("6"): return "60x(沪主板)"
    if c.startswith("00"): return "00x(深主板)"
    if c.startswith("30"): return "30x(创业板)"
    if c.startswith("68"): return "68x(科创板)"
    if c.startswith("8") or c.startswith("4"): return "8xx/4xx(北交所/新三板)"
    return "其他"

print("\n" + "="*96)
print(f"{'分组':<16}{'去重股票':>9}{'在缓存':>8}{'缺失':>7}{'缺失率':>8}  缺失股票代码前缀分布")
print("="*96)
for name, where in GROUPS:
    cur.execute(f"SELECT DISTINCT stock_code FROM announce WHERE date >= '2023-09-01' AND ({where})")
    codes = {str(r[0])[:6] for r in cur.fetchall()}
    in_cache = {c for c in codes if c in cached}
    missing = codes - in_cache
    dist = defaultdict(int)
    for c in missing: dist[pfx(c)] += 1
    dist_s = " ".join(f"{k}={v}" for k, v in sorted(dist.items(), key=lambda kv: -kv[1])[:4])
    pct = f"{100*len(missing)/len(codes):.1f}%" if codes else "-"
    print(f"{name:<16}{len(codes):>9}{len(in_cache):>8}{len(missing):>7}{pct:>8}  {dist_s}")

# 全市场基线: 所有公告涉及股票 vs 缓存
cur.execute("SELECT DISTINCT stock_code FROM announce WHERE date >= '2023-09-01'")
allc = {str(r[0])[:6] for r in cur.fetchall()}
all_miss = allc - cached
dist_all = defaultdict(int)
for c in all_miss: dist_all[pfx(c)] += 1
print("\n全市场基线:")
print(f"  公告涉及股票 {len(allc)}, 在缓存 {len(allc & cached)}, 缺失 {len(all_miss)} ({100*len(all_miss)/len(allc):.1f}%)")
print("  缺失前缀分布: " + " ".join(f"{k}={v}" for k, v in sorted(dist_all.items(), key=lambda kv: -kv[1])[:5]))

print("\n" + "="*96)
print("判定:")
print("  · 若缺失集中在 8xx/4xx(北交所/新三板, 不在缓存) → 缺失是**系统性排除**, 非退市偏差")
print("  · 若缺失集中在 60x/00x(主板) → 可能是退市股, **业绩预减组高估风险大**")
print("  · 对比全市场基线的缺失率, 判断该组缺失是否异常")