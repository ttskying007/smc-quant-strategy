# -*- coding: utf-8 -*-
"""全链路盘点：落盘/前端/回测/分析状态"""
import csv, io, json, os, sys
from collections import Counter
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

print("=== 1. 研究落盘 ===")
research = r"E:\test\smc_project\research"
mds = sorted([f for f in os.listdir(research) if f.endswith(".md")])
print(f"研究报告 {len(mds)} 份:")
for f in mds:
    print(f"  {f}")

print("\n=== 2. 回测数据 ===")
for name in ("combo_v20c_trades.csv", "combo_v20d_trades.csv"):
    p = os.path.join(research, name)
    if os.path.exists(p):
        with open(p, encoding="utf-8-sig") as fh:
            n = sum(1 for _ in fh) - 1
        print(f"  {name}: {n} 笔")
    else:
        print(f"  {name}: 不存在")

print("\n=== 3. 逐年逐月报告 ===")
for f in mds:
    if "逐年逐月" in f or "验证矩阵" in f:
        print(f"  {f}")

print("\n=== 4. 前端数据源 ===")
frontend = r"E:\root\.hermes\smc_monitor"
for f in os.listdir(frontend):
    print(f"  {f}")
