# -*- coding: utf-8 -*-
"""任务1: 冻结重标旗舰数字 —— 在报告中标注 v20e/皇冠数字含前视/样本漂移，不可交易"""
import io, sys
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

# 1. v20d验证矩阵 标注
p1 = r"E:\test\smc_project\research\v20d验证矩阵.md"
txt = open(p1, encoding="utf-8").read()
if "冻结" not in txt:
    txt = "# ⚠️ 数字冻结公告（2026-08-22 红蓝对抗审计）\n\n> 以下数字含前视偏差（rank_score 放量特征用 T+1/T+2 量，决策时点不可得）+ 样本漂移（v20e 剔除 455 笔），**不可作为实盘决策依据**。无泄漏重跑结果出来前一律标注'待重算'。\n\n" + txt
    open(p1, "w", encoding="utf-8").write(txt)
    print(f"v20d验证矩阵: 已加冻结公告")

# 2. 组合v20e逐年逐月报告 标注
p2 = r"E:\test\smc_project\research\组合v20e逐年逐月报告.md"
txt2 = open(p2, encoding="utf-8").read()
if "冻结" not in txt2:
    txt2 = "# ⚠️ 数字冻结公告（2026-08-22 红蓝对抗审计）\n\n> v20e 数字含**前视偏差**（rank_score 放量/连续放量特征用 T+1/T+2 量）+ **样本漂移**（剔除 455 笔，真实回踩增益 +0.65pp 非 +1.20pp）。**不可作为实盘决策依据**，标注'待重算'。\n\n" + txt2
    open(p2, "w", encoding="utf-8").write(txt2)
    print(f"组合v20e报告: 已加冻结公告")

# 3. 资金方案 标注
p3 = r"E:\test\smc_project\research\v20c实盘资金方案.md"
txt3 = open(p3, encoding="utf-8").read()
if "冻结" not in txt3:
    txt3 = "# ⚠️ 数字冻结公告（2026-08-22 红蓝对抗审计）\n\n> 皇冠 +21.80%/PF60.40、v20e +8.03% 等数字含前视偏差 + 样本漂移，**待无泄漏重跑后更新**，当前不可用于资金决策。\n\n" + txt3
    open(p3, "w", encoding="utf-8").write(txt3)
    print(f"资金方案: 已加冻结公告")
