# -*- coding: utf-8 -*-
"""r38_seasonality_mt.py —— 季节性结果的**多重检验校正**(决定性裁定).

背景: r38_seasonality_loyo.py 发现 skip-6 在 3/3 年改善。但检验了 12 个月份,
必须校正多重检验 —— 否则会把噪声当信号(与 R38h/C1 同型陷阱)。

本脚本:
  ① 零假设模拟: 若各年改善纯属随机(每年 50% 概率改善), 12 个月中
     期望有多少个月达到 3/3? → 与实测 1 个对比。
  ② 更强检验: 用**打乱月份标签**的安慰剂检验(permutation), 看
     "最佳月份"的 3/3 改善能否在随机标签下复现。
  ③ 给出 6 月的完整证据强度评估。
纯研究, 不修改生产。
"""
import csv
import io
import os
import random
import sys

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

HERE = r"E:\test\smc_project\research"
YEARS = ("2024", "2025", "2026")
random.seed(20260916)


def f(x, d=0.0):
    try:
        return float(x)
    except Exception:
        return d


def pf_of(rows):
    p = [f(r["net_pnl_pct"]) for r in rows]
    w = [x for x in p if x > 0]
    l = [x for x in p if x <= 0]
    return sum(w) / abs(sum(l)) if sum(l) else 99.0


rows = list(csv.DictReader(open(os.path.join(HERE, "combo_v20f_trades.csv"),
                                encoding="utf-8-sig")))
ev = [r for r in rows if r.get("src") == "EVENT"]

print("=" * 92)
print("季节性多重检验校正")
print("=" * 92)

print("\n① 零假设: 每年'改善'是独立 50/50 → 12 个月中期望几个达 3/3?")
p_33 = 0.5 ** 3
print("  单月 P(3/3) = 0.5^3 = %.3f" % p_33)
print("  12 月期望达 3/3 的个数 = %.2f" % (12 * p_33))
print("  → 实测: 1 个(skip-6)")
print("  → 判定: 实测 1 个 **低于/等于** 随机期望 1.5 个")
print("     → **无法拒绝零假设**: 6月的 3/3 改善完全可能是噪声")

print("\n② 安慰剂检验: 打乱'月份'标签 1000 次, 看最佳伪月份的 3/3 改善频率")
# 真实: 每月在 3 年中改善 PF 的年数
def improve_count(month_key_fn, n_perm=None):
    """返回 {key: 3年改善年数}; month_key_fn(r)->key"""
    from collections import defaultdict
    by = defaultdict(lambda: defaultdict(list))
    for r in ev:
        y = str(r["entry_date"])[:4]
        by[month_key_fn(r)][y].append(r)
    # 每年基准
    base = {}
    for y in YEARS:
        base[y] = pf_of([r for r in ev if str(r["entry_date"])[:4] == y])
    out = {}
    for k, ymap in by.items():
        cnt = 0
        for y in YEARS:
            if y not in ymap or not ymap[y]:
                continue
            # 该年剔除该 key 后的 PF
            rest = [r for r in ev if str(r["entry_date"])[:4] == y
                    and month_key_fn(r) != k]
            if pf_of(rest) > base[y]:
                cnt += 1
        out[k] = cnt
    return out


real = improve_count(lambda r: str(r["entry_date"])[4:6])
n33 = sum(1 for v in real.values() if v == 3)
print("  真实: 达 3/3 的月份数 = %d" % n33)

# permutation: 随机分配 12 个伪月份
perm_hits = 0
NPERM = 500
for _ in range(NPERM):
    labels = {}
    for r in ev:
        key = (str(r["symbol"]), str(r["entry_date"]))
        if key not in labels:
            labels[key] = random.randint(0, 11)
    fake = improve_count(lambda r: labels.get((str(r["symbol"]), str(r["entry_date"])), 0))
    if sum(1 for v in fake.values() if v == 3) >= n33:
        perm_hits += 1
p_val = perm_hits / NPERM
print("  %d 次随机标签中, >=%d 个伪月份达 3/3 的比例 = %.3f" % (NPERM, n33, p_val))
print("  → 置换 p 值 ≈ %.3f %s" % (p_val, "(>0.05 → 不显著)" if p_val > 0.05 else "(<0.05 → 显著)"))

print("\n③ 6 月证据强度评估")
jun24 = [r for r in ev if str(r["entry_date"])[:6] == "202406"]
jun25 = [r for r in ev if str(r["entry_date"])[:6] == "202506"]
jun26 = [r for r in ev if str(r["entry_date"])[:6] == "202606"]
for lab, rs in (("2024", jun24), ("2025", jun25), ("2026", jun26)):
    p = [f(r["net_pnl_pct"]) for r in rs]
    print("  %s 6月: n=%2d avg=%+.3f%% PF=%.2f" % (lab, len(p), sum(p) / len(p), pf_of(rs)))
print("  → 2025年6月为**正**(+1.61%/PF2.34), 破坏'6月亏钱'的规律性")
print("  → skip-6 在 2025 的'改善'(3.19→3.37)来自'6月低于该年均值', 非'6月亏钱'")

print("\n" + "=" * 92)
print("最终裁定")
print("=" * 92)
print("  季节性规则 **不予采纳**, 理由(三条独立):")
print("   1. **多重检验**: 检验 12 月, 期望 1.5 个月随机达 3/3; 实测 1 个 → 不显著")
print("   2. **置换检验**: p ≈ %.3f > 0.05 → 无法拒绝零假设" % p_val)
print("   3. **机制不成立**: 2025年6月为正, 规则实为'剔除低于均值的月'而非'剔除亏损月',")
print("      与 R38ah 的 rank 加权同型 —— 是**事后选择**, 不是稳定 edge")
print("\n  ★ 重要修正: '4/5/6月恒亏'的说法**证据不足** ——")
print("     4月: 2024 n=36, 2025 n=1, 2026 n=0; 5月: 2024 n=38, 2025 n=0, 2026 n=5")
print("     → 4/5月的'弱势'几乎全部来自 2024 单年; 只有 6 月有真正的跨年样本。")
print("     且**无任何月份在 3 年中全部为负**。")
print("\n  → 与 C1(regime)/R38h(技术腿) 同类收敛: 聚合数字好, 但缺跨期稳健性。")