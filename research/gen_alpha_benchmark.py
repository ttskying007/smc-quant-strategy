# -*- coding: utf-8 -*-
"""gen_alpha_benchmark.py — Jensen Alpha 基准表生成器(PF-后验反推)

从 combo_v22_trades.csv 读 EVENT 腿, 按 (trend_state, retrace_state, stage?) 切桶,
生成 research/alpha_benchmark.json。
口径纪律: 基准只用"上一数据周期"的回测腿 —— 此处即冻结 v22 表(数据至 2026-09-18);
后续随 gen_v22 重跑自动滚动。不重切冻结基线的引擎, 只做后验统计。
v22 无 stage 列(生产 stage 在 gate 层), 用 trend_state/retrace_state 两级桶,
stage 维以 ACCUM/DOWNTREND 未在腿级落列 —— 用 stage_span>=签阈值近似? 不, 保持诚实:
stage 维度走 trend 代理(ACCUM≈底部结构已含在 trend 信号中), 桶里去第三级即 |*|。
"""
import csv, json, os
from collections import defaultdict

HERE = r"E:\test\smc_project\research"
rows = [r for r in csv.DictReader(open(os.path.join(HERE, "combo_v22_trades.csv"),
                                      encoding="utf-8-sig")) if r["src"] == "EVENT"]

def f(x):
    try: return float(x)
    except Exception: return None

pnls = [f(r["net_pnl_pct"]) for r in rows]
pnls = [x for x in pnls if x is not None]
gavg = sum(pnls) / len(pnls)
print(f"EVENT legs={len(rows)} 全局平均={gavg:.3f}%")

# 三级桶: trend|retrace|*   + 退化级 trend|retrace|*, trend|*|*
buck = defaultdict(list)
for r in rows:
    p = f(r["net_pnl_pct"])
    if p is None: continue
    t = r["trend_state"]; rt = r["retrace_state"] or "no_retrace"
    buck[f"{t}|{rt}|*"].append(p)
    buck[f"{t}|*|*"].append(p)
    buck["*|*|*"].append(p)

out = {"generated_at": __import__("datetime").date.today().isoformat(),
       "source": "combo_v22_trades.csv EVENT legs (frozen window through 2026-09-18)",
       "global_avg": round(gavg, 3), "n": len(pnls), "buckets": {}}
for k, v in sorted(buck.items()):
    out["buckets"][k] = {"n": len(v), "avg": round(sum(v)/len(v), 3),
                         "wr": round(sum(1 for x in v if x > 0)/len(v)*100, 1)}

with open(os.path.join(HERE, "alpha_benchmark.json"), "w", encoding="utf-8") as fh:
    json.dump(out, fh, ensure_ascii=False, indent=2)
print(f"写出 alpha_benchmark.json: {len(out['buckets'])} buckets")
for k, v in sorted(out["buckets"].items(), key=lambda kv: kv[1]["avg"], reverse=True)[:8]:
    print(f"  {k}: n={v['n']} avg={v['avg']:+.2f}% WR={v['wr']}% α={v['avg']-gavg:+.2f}")
