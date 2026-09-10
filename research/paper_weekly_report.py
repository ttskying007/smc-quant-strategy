# -*- coding: utf-8 -*-
"""paper_weekly_report.py —— PAPER 台账周期报告(SAMPLED_PAPER 观察期监控)
职责: 每日跑, 生成:
  ① 台账进度 vs 七道门(30/60/100 closed 里程碑 + days 累计)
  ② E-score 环境分布(信号在什么环境产生 —— 验证观察期代表性)
  ③ 家族/退出原因分布(结构均衡性监控)
  ④ 异常预警(fill 偏离/负收益集中/单一股票集中)
输出: handover/paper_weekly_report.json + 控制台摘要。可由 daily_combo_run 调度。"""
import io, json, os, sys, time
from collections import Counter, defaultdict
sys.path.insert(0, r"E:\test\smc_project\research")
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

LEDGER = r"E:\test\smc_project\research\handover\setup_engine_paper_ledger.json"
OUT = r"E:\test\smc_project\research\handover\paper_weekly_report.json"

led = {"signals": [], "summary": {}}
if os.path.exists(LEDGER):
    try:
        led = json.load(open(LEDGER, encoding="utf-8"))
    except Exception:
        pass
sigs = led.get("signals", [])
closed = [s for s in sigs if s.get("ret_pct") is not None]
open_ = [s for s in sigs if s.get("ret_pct") is None]
summary = led.get("summary", {})
days = summary.get("days_accum", 0)

# ① 里程碑
milestone = {"days_accum": days, "closed": len(closed),
             "next_gate": "G7 30closed+20d" if len(closed) < 30 else
                          ("60closed" if len(closed) < 60 else "100closed")}
progress = {"pct_to_30": round(len(closed) / 30 * 100, 1)}

# ② E 分布
es = [s.get("escore") for s in sigs if s.get("escore") is not None]
bands = Counter()
for e in es:
    bands["low" if e < 0.33 else "mid" if e < 0.54 else "high"] += 1
es_stats = {"n_with_e": len(es), "bands": dict(bands),
            "avg_e": round(sum(es) / len(es), 3) if es else None}

# ③ 家族/退出分布
fam_c = Counter(s.get("family", "?") for s in sigs)
exit_c = Counter(s.get("exit_reason") or s.get("status", "OPEN") for s in sigs)

# ④ 异常预警
alerts = []
codes = Counter(s.get("code") for s in sigs)
top_code, top_n = (codes.most_common(1)[0] if codes else (None, 0))
if top_n > len(sigs) * 0.5 and len(sigs) > 10:
    alerts.append(f"单一股票占比过高: {top_code} {top_n}/{len(sigs)}")
neg = [s for s in closed if (s.get("ret_pct") or 0) < 0]
if closed and len(neg) / len(closed) > 0.6:
    alerts.append(f"负收益集中: {len(neg)}/{len(closed)} closed 为负")
if len(closed) >= 5:
    avg = sum(s["ret_pct"] for s in closed) / len(closed)
    if avg < -1.0:
        alerts.append(f"观察期平均负: {avg:.2f}%")
fills = [s for s in closed if s.get("filled_price") and s.get("optimal_entry")]
if fills:
    dev = [abs(s["filled_price"] - s["optimal_entry"]) / s["optimal_entry"] * 100 for s in fills]
    if max(dev) > 5:
        alerts.append(f"fill 偏离 optimal 超 5%: max {max(dev):.2f}%")

report = {"generated_at": time.strftime("%Y-%m-%d %H:%M:%S"),
          "milestone": {**milestone, **progress},
          "escore_dist": es_stats,
          "family_dist": dict(fam_c), "exit_dist": dict(exit_c),
          "alerts": alerts,
          "raw": {"total": len(sigs), "closed": len(closed), "open": len(open_)}}
json.dump(report, open(OUT, "w", encoding="utf-8"), ensure_ascii=False, indent=2)
print(f"== PAPER 周期报告 {report['generated_at']} ==")
print(f"  进度: days={days} closed={len(closed)}/30 → {progress['pct_to_30']}%  下一门: {milestone['next_gate']}")
print(f"  E 分布: {es_stats['bands']} avg={es_stats['avg_e']}")
print(f"  家族: {dict(fam_c)}")
print(f"  退出: {dict(exit_c)}")
if alerts:
    print(f"  ⚠ 预警: {alerts}")
else:
    print("  无预警")