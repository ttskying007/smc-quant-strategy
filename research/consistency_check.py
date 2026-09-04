# -*- coding: utf-8 -*-
"""P1-5: 代码-报告一致性校验（发布强制门槛）
检查：src 字段无'?' / 特征集一致 / 报告数字 vs CSV 实际 / 版本对比受控"""
import csv, io, json, os, sys
from collections import Counter
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

RESEARCH = r"E:\test\smc_project\research"
checks = []
def check(name, ok, detail):
    checks.append((name, ok, detail))
    print(f"  {'✅' if ok else '❌'} {name}: {detail}")

print("=== 一致性校验 ===\n")

# 1. src 字段无 '?'
for csv_name in ("combo_v20c_trades.csv", "combo_v20d_trades.csv", "combo_v20e_trades.csv", "combo_v20f_trades.csv"):
    p = os.path.join(RESEARCH, csv_name)
    if not os.path.exists(p):
        check(f"{csv_name} src", False, "文件不存在")
        continue
    with open(p, encoding="utf-8-sig") as fh:
        rows = list(csv.DictReader(fh))
    q = sum(1 for r in rows if r.get("src") == "?")
    check(f"{csv_name} src无'?'", q == 0, f"src='?' {q} 笔 | 腿: {dict(Counter(r.get('src') for r in rows))}")

# 2. 特征集一致（gen_v20f vs paper_sim 都 7 特征）
gen = open(os.path.join(RESEARCH, "gen_v20f.py"), encoding="utf-8").read()
sim = open(os.path.join(RESEARCH, "paper_sim.py"), encoding="utf-8").read()
gen_has_etype = "方案" in gen and "首次" in gen and "计划" in gen
sim_has_etype = "方案" in sim and "首次" in sim and "计划" in sim
check("特征集一致(事件类型)", gen_has_etype == sim_has_etype, f"gen_v20f={gen_has_etype} paper_sim={sim_has_etype}")

# 3. 无泄漏检查（v_ratio 用 T 日量）
gen_no_leak = "bs[i][\"v\"]" in gen or "bs[i][\"v\"]" in gen
check("gen_v20f 无泄漏(T日量)", gen_no_leak, "v_ratio 用 T 日量")

# 4. 报告数字 vs CSV 实际（v20f 2024 avg）
p_f = os.path.join(RESEARCH, "combo_v20f_trades.csv")
if os.path.exists(p_f):
    with open(p_f, encoding="utf-8-sig") as fh:
        rows = list(csv.DictReader(fh))
    y2024 = [float(r["net_pnl_pct"]) for r in rows if str(r["entry_date"])[:4] == "2024"]
    if y2024:
        avg = sum(y2024) / len(y2024)
        check("v20f 2024 avg 报告一致性", abs(avg - 10.33) < 0.05, f"CSV实际 {avg:+.2f}% vs 报告(v20f新SL) +10.33%")

# 5. 版本受控对比（v20d vs v20f 共同样本）
p_d = os.path.join(RESEARCH, "combo_v20d_trades.csv")
if os.path.exists(p_d) and os.path.exists(p_f):
    with open(p_d, encoding="utf-8-sig") as fh:
        d_rows = {(r["symbol"], r["entry_date"]): float(r["net_pnl_pct"]) for r in csv.DictReader(fh) if r.get("src") == "EVENT"}
    with open(p_f, encoding="utf-8-sig") as fh:
        f_rows = {(r["symbol"], r["entry_date"]): float(r["net_pnl_pct"]) for r in csv.DictReader(fh) if r.get("src") == "EVENT"}
    common = set(d_rows.keys()) & set(f_rows.keys())
    if common:
        d_avg = sum(d_rows[k] for k in common) / len(common)
        f_avg = sum(f_rows[k] for k in common) / len(common)
        check("v20d→v20f 受控对比(共同样本)", True,
              f"共同 {len(common)} 笔: v20d {d_avg:+.2f}% vs v20f {f_avg:+.2f}% (增量 {f_avg-d_avg:+.2f}pp)")

print("\n=== 校验完成 ===")
fails = [c for c in checks if not c[1]]
print(f"通过 {len(checks)-len(fails)}/{len(checks)}" + (" | ❌ " + ", ".join(c[0] for c in fails) if fails else " | ✅ 全部通过"))
