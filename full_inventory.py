# -*- coding: utf-8 -*-
"""全面盘点：落盘/回测/前端/能力/同步状态"""
import csv, io, json, os, sys
from collections import Counter
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

RESEARCH = r"E:\test\smc_project\research"

print("=== 1. 研究落盘（记忆/参考）===")
mds = sorted([f for f in os.listdir(RESEARCH) if f.endswith(".md")])
print(f"研究报告: {len(mds)} 份")
key_docs = [f for f in mds if any(k in f for k in ("策略思路","综合报告","审计","验证矩阵","资金方案","逐年","自动化","评估"))]
for f in key_docs:
    print(f"  {f}")

print("\n=== 2. 回测数据（已生成版本）===")
for name in ("combo_v20c_trades.csv", "combo_v20d_trades.csv", "combo_v20e_trades.csv", "combo_v20f_trades.csv"):
    p = os.path.join(RESEARCH, name)
    if os.path.exists(p):
        with open(p, encoding="utf-8-sig") as fh:
            n = sum(1 for _ in fh) - 1
        print(f"  {name}: {n} 笔")

print("\n=== 3. v20f 详细回测（最新）===")
with open(os.path.join(RESEARCH, "combo_v20f_trades.csv"), encoding="utf-8-sig") as fh:
    rows = list(csv.DictReader(fh))
ev = [r for r in rows if r.get("src") == "EVENT"]
cont = [r for r in rows if r.get("src") == "CONT"]
print(f"  事件 {len(ev)} + 延续 {len(cont)} = {len(rows)} 笔")
for y in ("2024", "2025", "2026"):
    ys = [r for r in rows if str(r["entry_date"])[:4] == y]
    if ys:
        pnls = [float(r["net_pnl_pct"]) for r in ys]
        wins = [x for x in pnls if x > 0]
        pf = sum(wins) / abs(sum(x for x in pnls if x <= 0)) if any(x <= 0 for x in pnls) else 99
        print(f"  {y}: n={len(ys)} avg={sum(pnls)/len(pnls):+.2f}% WR={100*len(wins)/len(ys):.0f}% PF={pf:.2f}")
print(f"  个股覆盖: {len(set(r['symbol'] for r in rows))} 只")

print("\n=== 4. 前端镜像（已同步）===")
MIRROR = r"E:\root\.hermes\smc_monitor"
for f in ("combo_v20f_trades.csv", "combo_dashboard.json", "paper_ledger.json", "current_scanner_result.json"):
    p = os.path.join(MIRROR, f)
    print(f"  {f}: {'✅' if os.path.exists(p) else '❌'}")

print("\n=== 5. 模拟持仓 ===")
led = json.load(open(os.path.join(RESEARCH, "paper_ledger.json"), encoding="utf-8"))
print(f"  ledger: {dict(Counter(t.get('status') for t in led))}")
rk = sum(1 for t in led if t.get("rank_score") is not None)
print(f"  rank_score 覆盖: {rk}/{len(led)}")
