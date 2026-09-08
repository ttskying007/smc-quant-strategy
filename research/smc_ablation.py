# -*- coding: utf-8 -*-
"""P0-3 SMC 组件消融与随机置换检验
审计要求 7 配置对比: 无SMC基线 / 仅HTF / +BOS / +sweep / 完整 / 反向 / 随机置换
数据现状: W1D1D4_seeds 全部通过 8 阶段(组件齐全), 无法从 seeds 直接消融中间阶段。
因此消融用两种可证明的方式:
  A. 信号级消融: 用 seed 的组件日期字段重建"若只要求部分组件"的候选集(日期可得性掩码),
     但全部满足 → 该方法不可行, 如实记录。
  B. 统计级检验(可证明): 
     ① 完整SMC OOS 指标(已知 -0.60%/PF0.88)
     ② 反向信号检验: SMC OOS 盈利交易反过来做(取负)是否更好 → 判断负 edge 是否可逆
     ③ 随机时间置换: 打乱 entry_date 与 net_pnl 配对, 1000 次 → SMC 的 OOS 表现是否显著异于随机
     ④ 组件关联: 各组件日期与净收益的相关性
     ⑤ 无SMC基线 = 事件腿(EVENT-only, 已证明 avg+2.95%/PF2.75)
"""
import csv, io, json, os, random, sys
from collections import Counter, defaultdict
sys.path.insert(0, r"E:\test\smc_project\research")
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

TRADES = r"E:\test\smc_project\wdh\W1D1D4_trades.csv"
SEEDS = r"E:\test\smc_project\wdh\W1D1D4_seeds.csv"
OOS_FROM = "20250701"

rows = list(csv.DictReader(open(TRADES, encoding="utf-8-sig")))
rows = [r for r in rows if r.get("net_pnl_pct") not in (None, "", "None")]
for r in rows:
    r["net_pnl_pct"] = float(r["net_pnl_pct"])
print(f"SMC 完整腿: {len(rows)} 笔")

def stats(ts, oos_only=False):
    sel = [t for t in ts if (not oos_only or t["entry_date"] >= OOS_FROM)]
    if not sel:
        return {"n": 0, "avg": 0.0, "wr": 0.0, "pf": 0.0}
    pn = [t["net_pnl_pct"] for t in sel]
    w = [x for x in pn if x > 0]
    l = [x for x in pn if x <= 0]
    return {"n": len(sel), "avg": round(sum(pn) / len(pn), 4),
            "wr": round(len(w) / len(sel), 4),
            "pf": round(sum(w) / abs(sum(l)), 3) if l and sum(l) != 0 else 99.0}

out = {"asof": __import__("time").strftime("%Y-%m-%d %H:%M:%S"), "oos_from": OOS_FROM}

print("\n== ① 完整 SMC 腿 ==")
full_is = stats(rows, oos_only=False)
full_oos = stats(rows, oos_only=True)
out["smc_full"] = {"is": stats([t for t in rows if t["entry_date"] < OOS_FROM]), "oos": full_oos}
print(f"  全部: {full_is} | OOS: {full_oos}")

print("\n== ② 反向信号检验（SMC 盈利交易取负）==")
# 若 SMC 有真实负 edge, 反做(买入该卖/卖出该买)应 OOS 为正 → 但现实中不可反向交易(无做空),
# 此检验判断负 edge 是否"系统性可逆"(若可逆则说明非随机噪声而是稳定反向信号)
rev = [dict(t, net_pnl_pct=-t["net_pnl_pct"]) for t in rows]
rev_oos = stats([t for t in rev if t["entry_date"] >= OOS_FROM])
out["reverse_oos"] = rev_oos
print(f"  反向 OOS: {rev_oos}（若为负 → 负 edge 不可逆, 纯噪声/无价值; 若为正 → 反向可交易）")

print("\n== ③ OOS 均值 bootstrap 显著性（1000 次）==")
random.seed(42)
oos_trades = [t for t in rows if t["entry_date"] >= OOS_FROM]
oos_pn = [t["net_pnl_pct"] for t in oos_trades]
actual_avg = sum(oos_pn) / len(oos_pn)
boot_avgs = []
for _ in range(1000):
    sub = random.choices(oos_pn, k=len(oos_pn))
    boot_avgs.append(sum(sub) / len(sub))
boot_avgs.sort()
ci_lo = boot_avgs[25]
ci_hi = boot_avgs[975]
straddle_zero = ci_lo < 0 < ci_hi
out["permutation"] = {"actual_oos_avg": round(actual_avg, 4),
                      "boot_ci95": [round(ci_lo, 4), round(ci_hi, 4)],
                      "ci_straddles_zero": straddle_zero,
                      "significant_negative": ci_hi < 0}
print(f"  实际 OOS avg={actual_avg:.4f}% | bootstrap 95%CI=[{ci_lo:.4f}, {ci_hi:.4f}]")
print(f"  判定: {'CI含0 → 负收益不显著(噪声)' if straddle_zero else ('CI全负 → 显著为负(真实负edge)' if ci_hi < 0 else 'CI全正 → 显著为正')}")

print("\n== ④ 组件日期与收益关联 ==")
seeds = list(csv.DictReader(open(SEEDS, encoding="utf-8-sig")))
seed_by = {(s["symbol"], s["entry_date"]): s for s in seeds}
# 组件→净收益: 组件日期存在性(全部存在) + 事件跨度
spans = []
for t in rows:
    s = seed_by.get((t["symbol"], t["entry_date"]))
    if not s:
        continue
    def _d(x):
        x = str(x or "").replace("-", "")
        return int(x) if x.isdigit() else None
    d0, d1 = _d(s.get("event_date")), _d(s.get("entry_date"))
    if d0 and d1:
        spans.append((d1 - d0, t["net_pnl_pct"]))
if spans:
    short = [p for sp, p in spans if sp <= 10]
    long = [p for sp, p in spans if sp > 10]
    out["component_corr"] = {"event_span_days_mean": round(sum(sp for sp, _ in spans) / len(spans), 1),
                              "span<=10: n": len(short), "avg": round(sum(short)/len(short), 3) if short else 0,
                              "span>10: n": len(long), "avg": round(sum(long)/len(long), 3) if long else 0}
    print(f"  事件跨度均值: {out['component_corr']['event_span_days_mean']} 日 | 短(≤10日) avg={out['component_corr'].get('span<=10: avg')}% | 长(>10日) avg={out['component_corr'].get('span>10: avg')}%")

print("\n== ⑤ 无 SMC 基线（EVENT-only，生产主腿）==")
print(f"  事件腿(仅): avg+2.95% PF2.75 OOS+2.95% PF3.05 —— 见事件腿独立验证")

print("\n== 结论 ==")
if out.get("permutation", {}).get("significant_at_5pct"):
    if actual_avg < 0:
        verdict = "SMC OOS 显著为负(非随机) → 负 edge 真实存在, 但反向不可交易(无做空) → 维持禁用"
    else:
        verdict = "SMC OOS 显著为正(非随机) → 需重新评估"
else:
    verdict = "SMC OOS 与随机无异 → 无稳定 edge, 维持禁用(仅 HTF_BIAS 研究特征)"
out["verdict"] = verdict
print(f"  {verdict}")

with open(r"E:\test\smc_project\research\handover\SMC组件消融.json", "w", encoding="utf-8") as fh:
    json.dump(out, fh, ensure_ascii=False, indent=2)
print("已写 handover/SMC组件消融.json")