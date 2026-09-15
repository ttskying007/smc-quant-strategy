# -*- coding: utf-8 -*-
"""r38_newtype_verdict.py —— R38 新事件类型最终裁定(退市偏差同口径对比).

r38_missing_attrib2 发现: 业绩预减组缺失主板股 44.8% 含退市公告(vs 对照组
22.5%) → 退市偏差。本脚本对**全部三个候选组**做同口径裁定:

  对每组: 缺失主板股数 / 含退市公告数 / 退市占比
  裁定线(预注册): 退市占比 > 对照组 1.5 倍 → 该组结论不可采信

同时给出"可采信组"的最终指标(来自 r38_newtype_verify 的 OOS 结果)。
纯研究, 不修改生产。
"""
import io, os, sqlite3, sys
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

KT = r"E:\test\smc_project\hermes\kline_cache_tencent"
cached = {f.split("_")[0] for f in os.listdir(KT) if f.endswith("_daily_800.json")}
conn = sqlite3.connect(r"E:\test\smc_project\announce\smc_announce.db")
cur = conn.cursor()

GROUPS = [
    ("业绩预增", "title LIKE '%业绩预增%'"),
    ("业绩预减", "title LIKE '%业绩预减%' OR title LIKE '%业绩预亏%'"),
    ("股权激励授予", "title LIKE '%股权激励%' AND title LIKE '%授予%'"),
    ("对照:股东增持", "title LIKE '%增持%' AND title LIKE '%股东%'"),
    ("对照:股份回购", "title LIKE '%回购%'"),
]

def is_main(c):
    return c.startswith("60") or c.startswith("00") or c.startswith("30") or c.startswith("68")

print("="*104)
print(f"{'分组':<16}{'去重股':>7}{'缺失主板':>9}{'含退市':>8}{'退市占比':>9}{'裁判':>28}")
print("="*104)
ref_ratio = None
results = {}
for name, where in GROUPS:
    cur.execute(f"SELECT DISTINCT stock_code FROM announce WHERE date >= '2023-09-01' AND ({where})")
    codes = {str(r[0])[:6] for r in cur.fetchall()}
    miss = {c for c in codes if c not in cached and is_main(c)}
    delist = 0
    for c in miss:
        cur.execute("SELECT COUNT(*) FROM announce WHERE stock_code LIKE ? AND "
                    "(title LIKE '%退市%' OR title LIKE '%终止上市%')", (c + "%",))
        if cur.fetchone()[0]:
            delist += 1
    ratio = delist / len(miss) if miss else 0
    results[name] = {"miss": len(miss), "delist": delist, "ratio": ratio, "codes": len(codes)}
    if name.startswith("对照:股东增持"):
        ref_ratio = ratio
    print(f"{name:<16}{len(codes):>7}{len(miss):>9}{delist:>8}{ratio*100:>8.1f}%")

print("-"*104)
print(f"对照组(股东增持)退市占比 = {ref_ratio*100:.1f}% (基线)")
print("\n裁定(预注册: 退市占比 > 基线×1.5 → 不可采信):")
final = []
for name in ("业绩预增", "业绩预减", "股权激励授予"):
    r = results[name]
    thr = ref_ratio * 1.5
    ok = r["ratio"] <= thr
    verdict = "✅ 可采信" if ok else "❌ 否决(退市偏差)"
    final.append((name, verdict, r))
    print(f"  {name:<14} 退市占比 {r['ratio']*100:.1f}% (阈值 {thr*100:.1f}%)  → {verdict}")

print("\n" + "="*104)
print("最终结论:")
for name, verdict, r in final:
    print(f"  {name}: {verdict}")
print("\n配套 OOS 指标(r38_newtype_verify):")
print("  业绩预增: OOS n=209 avg+6.61% PF3.56 (比1.38) | 逐年 2024 +5.39 / 2025 +7.70 / 2026 +3.00")
print("  业绩预减: OOS n=276 avg+3.48% PF2.28 (比1.36) | 逐年 2024 +1.11 / 2025 +6.95 / 2026 +0.93")
print("  股权激励: OOS n=65  avg+1.84% PF1.61 (比0.93) | 逐年 2024 +3.77 / 2025 +3.50 / 2026 -1.99")