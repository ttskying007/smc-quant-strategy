# V98 前端字段修复 + 入场/出场逐笔审计模式

适用场景：SMC 选股页/实时页字段修复后，用户要求“全量验证、回测验证、每年详细数据、逐笔检查买入/卖出早晚高低，再决定下一步修复”。

## 必须先做的闭环验证

1. **数据源确认**
   - 当前生产候选源必须明确，例如 `v98_structural_trades.json`、`v98_active_picks.json`、`v98_report.json`。
   - 分清历史回测交易、active picks、live-prices API，不要把历史交易伪装成当前选股。

2. **字段合同验证**
   - `/api/picks` 和 `/api/live-prices` 都要查。
   - 用户本次关心字段：`pick_date` / `选股日期`、`join_date` / `加入日期`、`engine`、`zone_type`、`zone`、`cost_line`、`volatility_pct` / `volatility`。
   - 对实时页不要用不相关字段误判失败；例如 live API 可能只展示 `tp1` 而不展示 `tp2/tp3`，若用户问题是成本线/波动/zone，则验证这些请求字段即可。

3. **T+1 与索引一致性**
   - 检查 `entry_date != exit_date` 且 `exit_idx > entry_idx`。
   - 检查 `entry_date` 与 K 线 `entry_idx` 日期一致、`exit_date` 与 K 线 `exit_idx` 日期一致。
   - 核心字段缺失数必须为 0。

## 年度回测输出格式

至少按 `entry_year` 输出：

| 年份 | 笔数 | 胜率 | SL率 | TP命中率 | 平均收益 | 中位收益 | 累计收益 | 平均持仓 | TP数 | SL数 |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|

不要只报总胜率。2023/2024/2025/2026 这类年份分化是判断系统是否稳定的关键。

## 逐笔入场审计维度

每笔交易至少计算：

- `entry_pos_in_zone = (entry_price - zone_low) / (zone_high - zone_low)`
- `entry_timing_delta_reclaim = entry_idx - reclaim_idx`
- 入场后 10 bar 的最低价/最高价相对 risk 的 R 值
- 是否有以下标签：
  - `ENTRY_PRICE_HIGH_IN_ZONE`：入场在 zone 高位
  - `ENTRY_ABOVE_ZONE_CHASE`：入场高于 zone，追高
  - `ENTRY_BEFORE_RECLAIM_EARLY`：入场早于 reclaim
  - `ENTRY_TOO_EARLY_FAST_SL`：入场后很快 SL
  - `ENTRY_TIME_LATE_AFTER_RECLAIM`：reclaim 后很久才入场
  - `ENTRY_EARLY_BETTER_LOWER_FILL_WITHOUT_SL`：后续有更低可成交价且未先触 SL

### V98 关键教训

V98 审计发现：

- 没有“买高”问题：`ENTRY_PRICE_HIGH_IN_ZONE` / `ENTRY_ABOVE_ZONE_CHASE` 为 0。
- 少量“买晚”反而质量高。
- 大量交易实际是 **pre-reclaim zone_mid limit anticipation**，字段语义却写成 `NEXT_OPEN_AFTER_POI_RECLAIM`。
- 机械改成 reclaim 后入场会显著变差：当前 V98 WR 62.97%，reclaim 后次日开盘仅约 30%，reclaim 后回踩 zone_mid/zone_low 约 26~29%。

因此：**不要看到 `entry_idx < reclaim_idx` 就直接修成 reclaim 后入场**。先做影子回测；如果后确认入场崩盘，应修字段语义/分层，而不是改有效执行。

建议语义：

```text
entry_semantic = PRE_RECLAIM_ZONE_MID_LIMIT_ANTICIPATION
entry_layer = L1_ANTICIPATION
confirmation_status = RECLAIM_CONFIRMED_AFTER_ENTRY / RECLAIM_PENDING
```

## 逐笔出场审计维度

每笔交易至少计算：

- `mfe_r` / `mae_r`
- exit 后 40 bar 的最大上行 R / 最大下行 R
- 是否后续达到 TP2/TP3
- 出场标签：
  - `EXIT_EARLY_TP2_THEN_TP3_WITHIN_40B`
  - `EXIT_EARLY_TP2_LEFT_2R_PLUS`
  - `EXIT_TOO_LATE_GAVE_BACK_2R_TO_SL`
  - `EXIT_TOO_LATE_GAVE_BACK_5R_TO_SL`
  - `EXIT_FAST_SL_SIGNAL_OR_ENTRY_FAIL`
  - `EXIT_OK_TP2`
  - `EXIT_OK_STRUCTURAL_SL`

### V98 出场关键教训

V98 表面上大量 TP2 后还能到 TP3，像是“卖早”；但影子验证 `20% TP1 + 50% TP2 + 30% runner to TP3 / BE` 后，平均收益从 +3.0708% 降到 +2.8551%。

所以：**不要只因 TP2 后继续上涨就直接加 runner**。需要做加权腿影子回测。

真正优先级更高的问题是：亏损单里大量曾经达到 2R/5R 浮盈后又回到 SL：

- `MFE >= 2R` 后回到 SL：应测试 BE/+0.5R 保护。
- `MFE >= 5R` 后回到 SL：应测试 +2R 或结构 HL trailing。

保护逻辑必须逐 bar 模拟，不能用最终 `mfe_r` 做未来函数决策。

## 下一步修复顺序建议

1. **优先影子验证浮盈保护出场**：V98 信号/入场保持不变，测试逐 bar `MFE>=2R` 提 BE 或 +0.5R，`MFE>=5R` 提 +2R/结构 HL trailing。
2. **修正入场语义字段**：把当前有效执行标为 pre-reclaim anticipation，而非 post-reclaim confirmation。
3. **弱环境轻降级**：重点看 `RECOVERY + 非 DEEP_DISCOUNT`、`BEAR_RISK + DISCOUNT + 非窄 Zone`；不要一刀切禁用 MIXED，因为 V98 中 MIXED 是最高胜率桶。

## 报告要求

用户偏好手机可读表格。输出必须包括：

- 全量样本/生产样本/审计样本数量
- T+1/字段/日期一致性验证表
- 年度回测表
- 市场状态、PD Zone、事件类型分桶表
- 入场问题计数与结论
- 出场问题计数与结论
- 影子修复矩阵结果
- 最终只给明确下一步，不要让用户选择
