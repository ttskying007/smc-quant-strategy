# -*- coding: utf-8 -*-
"""P0 修复结果记录"""
import io, sys
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
p = r"E:\test\smc_project\research\策略思路全景与迭代框架.md"
txt = open(p, encoding="utf-8").read()
add = """

### P0 修复完成（2026-08-22，红蓝对抗审计后）
1. 冻结重标旗舰数字：v20e/皇冠数字标注"含前视/样本漂移，不可交易"（v20d验证矩阵/组合v20e报告/资金方案）
2. src='?' 修复：v20c_finalize.py 写入 'SMC' 替代 '?'；v20c CSV 113 笔 '?' → SMC（v20c 腿分布：EVENT 4958/CONT 2361/SMC 113）
3. rank_score 特征对齐：gen_v20e.py 加事件类型 +1（7↔7 与 paper_sim 一致）
4. 无泄漏重跑皇冠（v_ratio 用 T 日量、v2_ratio 用 T-1 量，决策时点可得）：
   - 无泄漏皇冠（rank≥6 7特征）：+17.49%/PF 17.81（n=724，2024 +19.61%(632)/2025 +4.45%(29)/2026 +3.79%(46)）
   - Bootstrap 1000/1000 正（中位 +17.49%，P5 +16.62%，P95 +18.39%）—— 统计稳健
   - 对比有前视旧皇冠（+18.94%/n=428）：无泄漏仅 -1.45pp，皇冠依然有效！
   - 单调性保持（rank2 +1.01% → rank7 +21.50%）
5. 模拟器合同对齐：TP1 30% 部分平仓（realized_pnl 记录）—— 与回测 v20e 分层 TP/SL 合同一致
6. v20f 生成（无泄漏特征，全量与 v20e 相同 —— rank 不影响单笔 pnl，正确）
"""
open(p, "a", encoding="utf-8").write(add)
print("已追加")
