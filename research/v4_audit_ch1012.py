# -*- coding: utf-8 -*-
"""v4_audit_ch1012.py —— 审计 §5.1 组合相关性 + §16.4 迭代5(独立评估)落档(预注册 #44)
审计要求: 事件腿收益/延续腿收益/组合收益/相关性/组合MDD/事件腿失效时延续腿可运行性。
数据: EVENT n=1640 + CONT n=113(同一 csv)。同日双腿收益可算月度相关性。
预注册:
  R1 双腿月度收益相关 ρ: |ρ|<0.3 → 低相关(组合有分散价值); >0.7 → 高相关(组合无增益)
  R2 组合 vs 单腿的月度 PF 对比
  R3 事件腿最差月(2024-02 除外)时延续腿同期表现(互补性检验)"""
import csv, io, json, sys
from collections import defaultdict
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

rows = list(csv.DictReader(open(r"E:\test\smc_project\research\combo_v20f_trades.csv",
                                encoding="utf-8-sig", errors="replace")))
legs = {"EVENT": defaultdict(list), "CONT": defaultdict(list)}
for r in rows:
    if not r.get("net_pnl_pct"):
        continue
    src = r.get("src")
    if src not in legs:
        continue
    m = str(r["entry_date"])[:10].replace("-", "")[:6]
    legs[src][m].append(float(r["net_pnl_pct"]))

months = sorted(set(legs["EVENT"]) | set(legs["CONT"]))
ev_m = [sum(legs["EVENT"].get(m, [])) / len(legs["EVENT"][m]) if legs["EVENT"].get(m) else None for m in months]
ct_m = [sum(legs["CONT"].get(m, [])) / len(legs["CONT"][m]) if legs["CONT"].get(m) else None for m in months]
# 双腿都有值的月
pairs = [(e, c, m) for e, c, m in zip(ev_m, ct_m, months) if e is not None and c is not None]
print(f"双腿共月: {len(pairs)}/{len(months)}(CONT 月覆盖 {len([c for c in ct_m if c is not None])})")

if len(pairs) >= 6:
    xs = [p[0] for p in pairs]; ys = [p[1] for p in pairs]
    n = len(xs)
    mx, my = sum(xs) / n, sum(ys) / n
    cov = sum((x - mx) * (y - my) for x, y in zip(xs, ys)) / n
    sx = (sum((x - mx) ** 2 for x in xs) / n) ** 0.5
    sy = (sum((y - my) ** 2 for y in ys) / n) ** 0.5
    rho = cov / (sx * sy) if sx and sy else 0
    print(f"R1 月度 avg 双腿 Pearson ρ = {rho:.3f} (n={n} 月)")
else:
    rho = None
    print("R1 样本不足")

# R2 组合 vs 单腿月度 PF
def pf_of(pnls):
    if not pnls:
        return None
    w = sum(x for x in pnls if x > 0); l_ = abs(sum(x for x in pnls if x <= 0))
    return round(w / l_, 2) if l_ > 0 else 99

all_ev = [p for m in months for p in legs["EVENT"].get(m, [])]
all_ct = [p for m in months for p in legs["CONT"].get(m, [])]
combo = all_ev + all_ct
print(f"R2 PF: EVENT {pf_of(all_ev)} | CONT {pf_of(all_ct)} | 组合 {pf_of(combo)}")

# R3 事件腿最差月 vs 延续腿同期
ev_worst = min((m for m in months if legs["EVENT"].get(m)), key=lambda m: sum(legs["EVENT"][m]) / len(legs["EVENT"][m]))
ct_same = legs["CONT"].get(ev_worst, [])
print(f"R3 事件腿最差月 {ev_worst}: avg={sum(legs['EVENT'][ev_worst])/len(legs['EVENT'][ev_worst]):.2f} | "
      f"CONT 同期: {[round(x,1) for x in ct_same] if ct_same else '无信号'}")

verdict = {
    "R1_月度双腿相关ρ": round(rho, 3) if rho is not None else "样本不足",
    "R1_低相关(组合分散价值)": bool(rho is not None and abs(rho) < 0.3),
    "R1_高相关(无增益)": bool(rho is not None and abs(rho) > 0.7),
    "R2_PF": {"EVENT": pf_of(all_ev), "CONT": pf_of(all_ct), "组合": pf_of(combo)},
    "R3_事件腿最差月CONT互补": {"月": ev_worst, "CONT同期": ct_same},
    "n_月对": len(pairs),
    "注": "CONT n=113 样本小于 EVENT 1640, R1 结论按月度均值对(非逐笔)解释",
}
print("\n预注册:", json.dumps(verdict, ensure_ascii=False))
json.dump(verdict, open(r"E:\test\smc_project\research\handover\V4_双腿相关性.json", "w",
                        encoding="utf-8"), ensure_ascii=False, indent=2)
print("已写 handover/V4_双腿相关性.json")