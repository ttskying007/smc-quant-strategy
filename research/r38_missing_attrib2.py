# -*- coding: utf-8 -*-
"""r38_missing_attrib2.py —— R38 缺失归因精查: "其他"代码性质 + 退市偏差量化.

r38_missing_attrib 发现缺失中"其他"前缀占多数(前缀非 6/00/30/68/8/4),
且业绩预减组缺失中 60x 沪主板占比 41%(全市场基线 11%) —— 退市偏差警示。
本脚本:
  ① 打印"其他"类代码样本, 弄清其真实格式(5位? 带后缀? 9xx?)
  ② 对业绩预减组的缺失主板股, 查其是否出现在 退市/ST/终止上市 公告中
  ③ 给出偏差方向判定
纯研究, 不修改生产。
"""
import io, os, sqlite3, sys
from collections import defaultdict
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

KT = r"E:\test\smc_project\hermes\kline_cache_tencent"
cached = {f.split("_")[0] for f in os.listdir(KT) if f.endswith("_daily_800.json")}

conn = sqlite3.connect(r"E:\test\smc_project\announce\smc_announce.db")
cur = conn.cursor()

# ① "其他" 代码样本
cur.execute("SELECT DISTINCT stock_code FROM announce WHERE date >= '2023-09-01' LIMIT 4000")
allc = {str(r[0]) for r in cur.fetchall()}
def pfx(c):
    c = str(c)
    if c.startswith("6"): return "60x"
    if c.startswith("00"): return "00x"
    if c.startswith("30"): return "30x"
    if c.startswith("68"): return "68x"
    if c.startswith("8") or c.startswith("4"): return "8xx/4xx"
    return "其他"
other = [c for c in allc if pfx(c) == "其他"]
print(f"stock_code 去重总数: {len(allc)}")
print(f"'其他'类样本(前 20): {sorted(other)[:20]}")
print(f"'其他'类长度分布: " + str({len(c): sum(1 for x in other if len(x) == len(c)) for c in set(other)}))
print(f"'其他'类前2位分布: " + str(dict(sorted({c[:2]: sum(1 for x in other if x[:2] == c[:2]) for c in other}.items(), key=lambda kv: -kv[1])[:8])))

# ② 业绩预减组缺失主板股 → 是否退市/ST
print("\n" + "="*88)
cur.execute("SELECT DISTINCT stock_code FROM announce WHERE date >= '2023-09-01' "
           "AND (title LIKE '%业绩预减%' OR title LIKE '%业绩预亏%')")
codes = {str(r[0])[:6] for r in cur.fetchall()}
missing_main = {c for c in codes if c not in cached and (c.startswith("60") or c.startswith("00") or c.startswith("30"))}
print(f"业绩预减组: 去重 {len(codes)} 股, 缺失主板股 {len(missing_main)} 只")
delist_cnt = 0
st_cnt = 0
for c in sorted(missing_main)[:200]:
    cur.execute("SELECT COUNT(*) FROM announce WHERE stock_code LIKE ? AND "
                "(title LIKE '%退市%' OR title LIKE '%终止上市%')", (c + "%",))
    d = cur.fetchone()[0]
    cur.execute("SELECT COUNT(*) FROM announce WHERE stock_code LIKE ? AND title LIKE '%ST%'", (c + "%",))
    s = cur.fetchone()[0]
    if d: delist_cnt += 1
    if s: st_cnt += 1
print(f"  其中含退市/终止上市公告: {delist_cnt} 只 ({100*delist_cnt/max(1,len(missing_main)):.1f}%)")
print(f"  其中含 ST 相关公告:      {st_cnt} 只 ({100*st_cnt/max(1,len(missing_main)):.1f}%)")

# ③ 对照组(股东增持)同口径
cur.execute("SELECT DISTINCT stock_code FROM announce WHERE date >= '2023-09-01' AND title LIKE '%增持%' AND title LIKE '%股东%'")
cc = {str(r[0])[:6] for r in cur.fetchall()}
cm = {c for c in cc if c not in cached and (c.startswith("60") or c.startswith("00") or c.startswith("30"))}
cd = 0
for c in sorted(cm)[:200]:
    cur.execute("SELECT COUNT(*) FROM announce WHERE stock_code LIKE ? AND (title LIKE '%退市%' OR title LIKE '%终止上市%')", (c + "%",))
    if cur.fetchone()[0]: cd += 1
print(f"\n对照组(股东增持): 缺失主板股 {len(cm)} 只, 含退市公告 {cd} 只 ({100*cd/max(1,len(cm)):.1f}%)")

print("\n" + "="*88)
print("判定:")
if len(missing_main) and delist_cnt/max(1,len(missing_main)) > 0.15:
    print("  ⚠ 业绩预减组缺失主板股中退市/ST 占比显著 → **高估风险确认**,")
    print("    业绩预减候选不可采信(剔除了系统性下跌/退市样本)。")
else:
    print("  ✅ 退市占比不显著 → 缺失主要是数据源覆盖问题, 偏差方向可控。")