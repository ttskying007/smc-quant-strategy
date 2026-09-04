# -*- coding: utf-8 -*-
import io, sys
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
p = r"E:\test\smc_project\research\策略思路全景与迭代框架.md"
txt = open(p, encoding="utf-8").read()
add = """

### 自适应策略研究（2026-08-28，按市场时期自适应参数）
- 分年研究：2024（反弹）+12.22% 持20日最优 / 2025（弱市）+3.31% 持15日 / 2026（震荡）+3.60% 持15日
- 放量特征：反弹市≥1.5x +16.77% / 震荡市≥1.2x +3.74% / 弱市放量特征弱(限幅)
- 落地：adaptive_hold(proxy) —— 反弹市(proxy>2%)持20日 / 震荡市(-2%~2%)持12日 / 弱市(proxy<-2%)持20日
- 延续腿 HOLD_EXIT 自适应持有期（paper_sim realtime_monitor）
- 强市过滤（proxy>2% 跳过事件腿）已有
"""
open(p, "a", encoding="utf-8").write(add)
print("已追加")