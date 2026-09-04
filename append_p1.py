# -*- coding: utf-8 -*-
import io, sys
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
p = r"E:\test\smc_project\research\策略思路全景与迭代框架.md"
txt = open(p, encoding="utf-8").read()
add = """

### P1 修复完成（2026-08-22，红蓝对抗路线图）
1. **止损重设**：SL = sweep low − 0.5×ATR（A股可执行，避免裸 swing low 超跌停不可触及）；距离>8% 降仓 50% 标记；5 交易日时间止损（未触 TP1 全仓离场）
2. **确认式入场**：回踩 ×0.99 确认（已落地）+ wdh SMC 腿周线权限（W1 已有）；事件腿 95% 周线 down 是抄底本质（周线空头禁入不适用事件腿）
3. **数据健康检查**：data_health_check.py（四源探测）+ 告警写入 data_health.json + 前端 /combo 显示；确认 sina/tencent OK / eastmoney 502 / netease SSL 失败；daily_combo_run 前置健康检查
4. **rank_score 落库**：模拟持仓缺失率 96.7% → 0%（回填 118 笔，rank 分布 1-4）
5. **一致性校验**：consistency_check.py（8/8 通过）—— src 无'?'/特征一致/无泄漏/报告数字一致/受控对比确认 v20d→v20f 增量 +0.65pp（回踩买点真实增量）
"""
open(p, "a", encoding="utf-8").write(add)
print("已追加")
