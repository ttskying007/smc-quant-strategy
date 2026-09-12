# -*- coding: utf-8 -*-
"""v4_stress_event.py —— 事件腿冻结基线压力测试(预注册 #41, 审计 §13.4 补全)
基线: EVENT n=1640 / avg +3.72% / PF 3.45 / OOS +4.03% (registry MD5 锁定态)
已覆盖: 费 3 倍(SHADOW 0.6 口径)
本实验补(预注册判据, 全部在 EVENT 腿逐笔净收益上):
  T1 去最赚 5 笔  → avg 仍 >+2.0 → PASS(不靠单笔)
  T2 去最赚月    → avg 仍 >+2.0 → PASS(不靠单月)
  T3 入场恶化 0.5pp(每笔 ret −0.5) → avg 仍 >+1.0 → PASS
  T4 信号延迟 1bar 近似(每笔 ret −1.0pp, A股次日开盘本来就 T+1, 再延迟=更晚入场的
     保守近似; 若基线连 −1pp 都扛不住 → 执行时点敏感性过高, FAIL)
判据线取基线 avg 的 ~54%/27%: 基线 3.72 → T1/T2 线 2.0 / T3 线 1.0。"""
import csv, io, json, sys
from collections import defaultdict
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

rows = list(csv.DictReader(open(r"E:\test\smc_project\research\combo_v20f_trades.csv",
                                encoding="utf-8", errors="replace")))
ev = [(str(r.get("entry_date") or "")[:10].replace("-", ""), float(r["net_pnl_pct"]))
      for r in rows if r.get("src") == "EVENT" and r.get("net_pnl_pct")]
n = len(ev)
rets = [p for _, p in ev]
avg0 = sum(rets) / n
print(f"基线: n={n} avg={avg0:.3f}")

# T1: 去最赚 5 笔
t1 = sorted(rets)[:-5]
avg_t1 = sum(t1) / len(t1)
# T2: 去最赚月
by_m = defaultdict(list)
for d8, p in ev:
    by_m[d8[:6]].append(p)
m_avg = {m: sum(v) / len(v) for m, v in by_m.items()}
drop_m = max(m_avg, key=m_avg.get)
t2 = [p for d8, p in ev if d8[:6] != drop_m]
avg_t2 = sum(t2) / len(t2)
# T3: 入场恶化 0.5pp
avg_t3 = avg0 - 0.5
# T4: 延迟近似 −1pp
avg_t4 = avg0 - 1.0

verdict = {
    "T1_去最赚5笔": {"avg": round(avg_t1, 3), "PASS线": 2.0,
                    "结果": "PASS" if avg_t1 > 2.0 else "FAIL"},
    "T2_去最赚月": {"drop": drop_m, "avg": round(avg_t2, 3), "PASS线": 2.0,
                    "结果": "PASS" if avg_t2 > 2.0 else "FAIL"},
    "T3_入场恶化0.5pp": {"avg": round(avg_t3, 3), "PASS线": 1.0,
                         "结果": "PASS" if avg_t3 > 1.0 else "FAIL"},
    "T4_延迟近似−1pp": {"avg": round(avg_t4, 3), "PASS线": 1.0,
                        "结果": "PASS" if avg_t4 > 1.0 else "FAIL"},
    "基线": {"n": n, "avg": round(avg0, 3)},
}
allp = all(v["结果"] == "PASS" for k, v in verdict.items() if k != "基线")
verdict["_结论"] = ("四项全过 — 冻结基线在压力场景下稳健" if allp
                  else "存在 FAIL 项 — 如实记录, 评估是否影响 REAL MONEY 准入")
print(json.dumps(verdict, ensure_ascii=False, indent=1))
json.dump(verdict, open(r"E:\test\smc_project\research\handover\V4_事件腿压力测试.json", "w",
                        encoding="utf-8"), ensure_ascii=False, indent=2)
print("已写 handover/V4_事件腿压力测试.json")