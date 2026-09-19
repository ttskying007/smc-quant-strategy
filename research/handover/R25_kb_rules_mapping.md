# R25: OpenMobius KB 规则 × R13 归因映射（grounded citations）
日期: 2026-09-20 来源: openmobius-skill knowledge_base (ICT/SMC 卡片, hybrid RRF 检索)

## 检索证据
- `stop_loss_placement` (ICT/SMC 合并卡, 4 源)
- `partial_profit_taking` (ICT)
- `body_invalidation` (ICT)
- 相关案例: 黄金15m/5m FVG 逐级缩小止损; ES 5m 高时间框架流动性

## R13 开放类 → KB 规则对照

### 1. LOSS_SL_TOO_WIDE (n=244, 46%) — 现状: CLOSED(设计意图)
KB 规则 stop_loss_placement Rule: "若完整止损不能达成2R, 则收紧至50%实体(mean threshold)" +
"若完整止损与身体止损均无法达成2R, 则等待延续性入场, 而非强行进场"。
**启示(预注册候选, 非立即改动)**: 当前 SL = 结构 invalidation - 1.5ATR, 属"完整止损"家族。
KB 明确给出第三种状态: **若 SL 距离导致 R:R < 2, 放弃该笔** —— 我们当前无此过滤。
→ **预注册实验提案 E2**: 入场前计算 (TP1 - entry) / (entry - SL), 若 < 2.0 则 REJECT_MIN_RR。
历史回测需重跑验证 OOS 不恶化 (参照 v2_delay reject 的教训: 必须先做 frozen A/B)。

### 2. LOSS_MFE_REVERSAL (n=47, 5.5%) — OPEN
KB partial_profit_taking Rule: "第一平仓位 = 最近摆动低点/小型 OB; 第二 = 更远 OB/FVG; 第三 = 摆动高点"。
我们已有 TP1/TP2/TP3 阶梯, 但 Rule: "第一目标达成即收回初始风险(移 BE)"。
→ **检查点**: 当前 paper_sim 是否在 TP1 触发后把 SL 移到 BE? 若无, 这是 MFE_REVERSAL 的直接可修路径。
→ 下一轮: grep paper_sim.py 确认 TP1→BE 移动逻辑存在性; 不存在则登记为 E3 候选。

### 3. LOSS_HIGH_RANK (n=94, 17.7%) — OPEN (悖论: rank≥4 亏损)
KB insight: "止损位置应结合 PD array; 订单块失效规则不可套用到其它 array"。
HIGH_RANK 高评分但亏损 ⇒ 评分(rank)对"信号质量"排序, 不评估"失效距离"。
→ **预注册假设 H4**: HIGH_RANK 亏损集中在 SL 距 > 2 ATR 的子集;
  测试方法: 用 v20f 回测 530 笔 EVENT 截 SL_TOO_WIDE ∩ rank≥4, 看占比是否显著超 base rate。
  若成立 → 正是 E2(min-R:R 过滤)的目标人群, 两线索收敛。
→ 测试脚本: research/r25_highrank_slwidth.py (下轮编写, 只读分析, 不改生产)

### 4. LOSS_TIME_LONG (n=30) — OPEN
KB: 时间止损未在检索卡中直接覆盖, 但持有过久多因目标不可达(R:R 结构性差)。
→ 与 E2 同源: 入场时拒绝 R:R<2 的交易天然压缩 TIME_LONG 尾部。

### 5. 入场时序 (SL_TOO_SHORT n=59, 已 CLOSED via delay-1bar REJECT)
KB 案例卡: "黄金 15m→5m FVG 逐级缩小止损" — 即多周期确认而非延迟入场。
→ 这从 KB 角度印证我们 REJECT delay-1bar 是正确的: 正确做法是降周期精化止损, 不是降时间入场。

## 下轮行动清单 (只读/预注册, 不动生产)
1. [ ] r25_highrank_slwidth.py: HIGH_RANK ∩ SL_WIDE 交叉统计 (530 笔 EVENT)
2. [x] grep paper_sim.py: TP1 触发后是否移动 SL→BE — **已存在** (paper_sim.py:1616 `sl_reason="TP1_MOVE_TO_BE"`, tp1_hit 分支)。MFE_REVERSAL 不能靠 BE 修复, 需另查(剩余 47 笔是 TP1 未达即回撤)。
3. [ ] E2 min-R:R gate 写入 research/handover/preregister_E2_minrr.md (假设+样本+判定阈值, 冻结后才可回测)
4. [ ] 等 09-22 daily run 验证 announce self-heal + R13 attribution 首笔 CLOSED 落账
