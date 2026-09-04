# V118 信号偏少底层诊断：不要把“前端少”误判为“市场没信号”

## 触发场景

用户指出当前持仓/选股明显偏少，例如“当前持仓只有一只/前端只有几只”，并要求先做全面逻辑分析，不要直接调整策略。

## 必须先做的只读诊断

1. 区分数据源：
   - durable monitor positions：历史/实盘状态，不等同于当前生产候选。
   - scanner active/watch：当前全市场扫描源。
   - live API display：前端展示源，可能有额外时间窗口过滤。
   - production/backtest trades：历史审计源，不可伪装成当前选股。
2. 建漏斗，不先调参：
   - scanned symbols
   - raw/contract candidates
   - recent/watch rows
   - active-entry-window rows
   - live display rows
   - tradable live rows
   - production active rows
3. 分层统计每个 DNA / 组合：
   - event_type：如 `BOS_CONTINUATION`、`SSL_SWEEP_CHOCH_REVERSAL`
   - poi_type：如 `DEMAND_OB`、FVG、OB+FVG 等
   - family：CONTINUATION / REVERSAL
   - market_state / trend_regime
   - source_label / shadow_action
4. 统计事件顺序和间隔：
   - `sweep_idx → event_idx`
   - `event_idx → touch_idx`
   - `touch_idx → reclaim_idx`
   - `reclaim_idx → entry_idx`
   - `event_idx → entry_idx`
   - `zone_idx → entry_idx`
5. 资金/Smart Money 证据只能按字段强度表述：
   - 有 known BSL、sweep、CHOCH、POI reclaim、takeover valid：只能说有 SMC 价格行为痕迹。
   - 没有成交量/资金流字段时，不得声称“真实大资金流入已确认”。

## V118 关键教训

一次只读诊断发现：底层候选并不少，但生产/前端链路压缩过强。

| 层级 | 示例诊断口径 | 典型风险 |
|---|---|---|
| scanner | V90 全市场候选 920 | 说明不是“完全没信号” |
| recent/watch | 49 recent 全为 `WATCH_ONLY` | active 窗口把信号压掉 |
| active | `active_entry_window_candidates=0` | 当前无可交易 active |
| live | live 只显示 7 个观察上下文 | live 日历窗口与 scanner trading-bar 窗口不一致 |
| production | V102 active 仅 3 个，且只剩 reversal 组合 | 组合生产门槛过窄 |
| POI | V90 920 个全部 `DEMAND_OB` | FVG/OB+FVG/Pinbar 确认族结构性缺失 |

## 常见根因模式

1. **active 时间窗过窄**：例如 max_active_bars=3，导致 recent 候选全部 WATCH_ONLY。
2. **前端显示窗口与扫描窗口口径不一致**：scanner 用 trading bars，live 用日历 45 天，会进一步压缩展示数量。
3. **生产组合过窄**：只保留一个 reversal production combo，CONTINUATION/BOS 大量候选无法进入生产。
4. **POI 生成器单一化**：当前候选全是 DEMAND_OB，FVG、OB+FVG、Pinbar-confirmation 没有并行输出。
5. **shadow gate 不可硬上线**：如 V116 weak-source gate 如果从 shadow 改 hard reject，会继续显著减少候选；必须先做 dry-run diff。
6. **历史持仓污染认知**：monitor OPEN 很多不代表当前生产有很多可交易 active；必须按 current active source 判断。

## 报告格式要求

用户要求手机可读、表格化。报告必须包含：

- 核心漏斗表。
- DNA / 组合分布表。
- 事件顺序/间隔表。
- Top 组合行表。
- “大资金操作”证据分级表。
- 明确区分：底层候选不足、生产门槛过窄、前端展示压缩、历史持仓污染。

## 禁止事项

- 不要看到前端少就直接放宽 TP/SL 或调整 WR/RR。
- 不要把历史 trades/positions 当成当前选股源。
- 不要在只读诊断阶段改 production/API/frontend。
- 不要把 shadow/downgrade gate 直接 hard reject。
- 不要在缺少成交量/资金流字段时宣称“大资金已确认买入”。
