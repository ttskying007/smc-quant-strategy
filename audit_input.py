# -*- coding: utf-8 -*-
"""全面现状盘点：为多角色审计提供输入"""
import csv, io, json, os, sys
from collections import Counter
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

print("=== A. 回测数据 ===")
for name in ("combo_v20c_trades.csv", "combo_v20d_trades.csv", "combo_v20e_trades.csv"):
    p = os.path.join(r"E:\test\smc_project\research", name)
    if os.path.exists(p):
        with open(p, encoding="utf-8-sig") as fh:
            rows = list(csv.DictReader(fh))
        print(f"  {name}: {len(rows)} 笔 | 腿分布: {dict(Counter(r.get('src') for r in rows))}")

print("\n=== B. 模拟持仓 ===")
led = json.load(open(r"E:\test\smc_project\research\paper_ledger.json", encoding="utf-8"))
print(f"  ledger: {dict(Counter(t.get('status') for t in led))}")
active = [t for t in led if t.get("status") != "CLOSED"]
pnls = [t.get("mark_pnl_pct") for t in active if t.get("mark_pnl_pct") is not None]
if pnls:
    print(f"  活跃浮盈: avg {sum(pnls)/len(pnls):+.2f}% (n={len(pnls)})")

print("\n=== C. 研究报告文件 ===")
research = r"E:\test\smc_project\research"
mds = sorted([f for f in os.listdir(research) if f.endswith(".md")])
print(f"  {len(mds)} 份报告")

print("\n=== D. 关键代码文件 ===")
for p in [r"E:\test\smc_project\research\paper_sim.py", r"E:\test\smc_project\wdh\wdh_engine.py",
          r"E:\test\smc_project\research\continuation_scanner.py", r"E:\test\smc_project\research\daily_combo_run.py"]:
    if os.path.exists(p):
        size = os.path.getsize(p)
        print(f"  {os.path.basename(p)}: {size/1024:.0f}KB")

print("\n=== E. 数据状态 ===")
s = json.load(open(r"E:\test\smc_project\research\current_scanner_result.json", encoding="utf-8"))
print(f"  scanner: latest={s.get('latest_date')} coverage={s.get('coverage_pct')}%")

print("\n=== F. 待办 ===")
print("  ① 纸面裁决 8/27-9/1（58 笔 OPEN）")
print("  ② 8/24 数据推进 → 最新选股")
print("  ③ MAX_HOLD=5（SMC 腿已落地引擎，未重跑回测）")
