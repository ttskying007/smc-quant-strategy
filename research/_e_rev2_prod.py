# -*- coding: utf-8 -*-
"""_e_rev2_prod.py —— E_rev2 生产线检查: v2_seq_family_db 的 E_rev2 判定与生产扫描器的
语义一致性(Family DB 是研究侧, 生产 = current_scanner 的结构链) —— 抽样一致性验证"""
import json, os, sys, io
sys.path.insert(0, r"E:\test\smc_project\research")
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
KT = r"E:\test\smc_project\hermes\kline_cache_tencent"

# 生产扫描器最新结果
sc = json.load(open(r"E:\test\smc_project\research\current_scanner_result.json", encoding="utf-8"))
print("scanner keys:", list(sc.keys())[:10])
sigs = sc.get("signals") or sc.get("candidates") or []
print(f"当日信号 n={len(sigs)}")
if sigs:
    print("首条:", json.dumps(sigs[0], ensure_ascii=False)[:250])