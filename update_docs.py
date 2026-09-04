# -*- coding: utf-8 -*-
import io, sys
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

# 每日自动化说明补最新版本
p = r"E:\test\smc_project\research\每日自动化说明.md"
txt = open(p, encoding="utf-8").read()
if "v20f" not in txt:
    add = """
# - 2026-08-22 强市过滤：_market_proxy（200只采样20日）proxy>2% 事件跳过（弱市是抄底甜蜜区）
# - 2026-08-22 延续腿 VWAP 10%→9% + 支撑新鲜度≤5天
# - 2026-08-22 v20f 生产：无泄漏 rank 7特征 + 新SL(sweep low−0.5ATR) + 强市过滤
"""
    open(p, "a", encoding="utf-8").write(add)
    print("每日自动化说明: 已补 v20f 版本")
else:
    print("每日自动化说明: 已含 v20f")
