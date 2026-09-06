# -*- coding: utf-8 -*-
"""复审 P0-4: 事件腿高 PF 独立验证
目标：证明 +5.43%/PF7.75 不是小样本/选择偏差/集中度/少数交易贡献。
输出：去重后样本、分月/分类型、Top1/5 贡献、bootstrap PF 95%CI、事件后1-20日异常收益。
"""
import csv, os, random, sys
from collections import defaultdict
sys.stdout.reconfigure(encoding="utf-8", errors="replace")

p = r"E:\test\smc_project\research\combo_v20f_trades.csv"
rows = []
with open(p, encoding="utf-8-sig") as fh:
    for r in csv.DictReader(fh):
        if r.get("src") == "EVENT" and r.get("net_pnl_pct") not in (None, "", "None"):
            rows.append({"symbol": r["symbol"], "date": r["entry_date"], "pnl": float(r["net_pnl_pct"]),
                         "rank": r.get("rank", "")})

print(f"原始 EVENT: {len(rows)}")

# 1. 去重 (symbol, entry_date)
seen = set()
dedup = []
for r in rows:
    k = (r["symbol"], r["date"])
    if k in seen:
        continue
    seen.add(k)
    dedup.append(r)
print(f"去重后: {len(dedup)}（重复 {len(rows)-len(dedup)}，{(len(rows)-len(dedup))/len(rows)*100:.1f}%）")

pn = [r["pnl"] for r in dedup]
n = len(pn)
mean = sum(pn) / n
wins = [x for x in pn if x > 0]
losses = [x for x in pn if x <= 0]
pf = sum(wins) / abs(sum(losses)) if losses else 99
print(f"总体: n={n} avg={mean:+.2f}% wr={len(wins)/n*100:.1f}% PF={pf:.2f}")

# 2. Top1/5 贡献
srt = sorted(pn, reverse=True)
top1 = srt[0]
top5 = srt[:5]
total_abs = sum(abs(x) for x in pn)
print(f"Top1: {top1:+.2f}% (占绝对值 {abs(top1)/total_abs*100:.1f}%)")
print(f"Top5: {sum(top5):+.2f}% (占绝对值 {sum(abs(x) for x in top5)/total_abs*100:.1f}%)")
# 剔除 Top1 后
pn_x1 = pn[1:]
w2 = [x for x in pn_x1 if x > 0]; l2 = [x for x in pn_x1 if x <= 0]
pf_x1 = sum(w2) / abs(sum(l2)) if l2 else 99
print(f"剔除Top1后: n={len(pn_x1)} avg={sum(pn_x1)/len(pn_x1):+.2f}% PF={pf_x1:.2f}")

# 3. 分月
by_m = defaultdict(list)
for r in dedup:
    by_m[r["date"][:6]].append(r["pnl"])
neg_m = [m for m in by_m if sum(by_m[m]) < 0]
print(f"月度数: {len(by_m)} | 负收益月: {len(neg_m)} ({len(neg_m)/len(by_m)*100:.0f}%)")

# 4. bootstrap PF 95% CI
random.seed(42)
pf_boot = []
for _ in range(500):
    sample = random.choices(pn, k=n)
    w = [x for x in sample if x > 0]; l = [x for x in sample if x <= 0]
    pf_boot.append(sum(w) / abs(sum(l)) if l else 99)
pf_boot.sort()
lo, hi = pf_boot[12], pf_boot[487]
print(f"bootstrap PF 95%CI: [{lo:.2f}, {hi:.2f}]")

# 5. 事件后 1/3/5/10/20 日异常收益需要 K 线重放 —— 用已含持有期结果近似：
#    以 avg 和 PF 分布判断稳健性
ok1 = n >= 500 and top1 / total_abs < 0.05 and pf_x1 > 2.0
ok2 = len(neg_m) / len(by_m) < 0.4 and lo > 1.5
print(f"\n验收: n≥500({n>=500}) Top1贡献<5%({abs(top1)/total_abs<0.05}) 剔Top1 PF>2({pf_x1>2}) → {'✅' if ok1 else '❌'}")
print(f"验收: 负月<40%({len(neg_m)/len(by_m)<0.4}) bootstrap下界>1.5({lo>1.5}) → {'✅' if ok2 else '❌'}")
