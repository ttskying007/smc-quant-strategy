# V49 入场执行桶污染审计与端到端同步验收

## 触发场景

当用户指出“SMC 信号不准确”“回测/选股/K线不同步”“盈亏比太低但不能牺牲胜率”时，不要直接调 SL/TP，也不要只看聚合 WR/RR。必须先把问题拆成：

1. 信号定义是否正确（OB/FVG/Sweep/BOS/CHOCH/MSS 是否对齐 Pine/LuxAlgo）。
2. 组合链路是否正确（结构事件 → zone → retrace/confirm → entry）。
3. 入场执行路径是否污染了信号质量。
4. 出场是否卖早或真实止损过多。
5. 回测、选股、K线标识、分析复盘、API 是否全部同步。

## 本次关键发现

V49 的核心问题不是 OB/FVG 定义本身，而是入场执行路径污染：

| bucket | 现象 | 处理 |
|---|---|---|
| `ZONE_MID_EXECUTABLE` | 中区提前成交，缺少二次确认；全量 replay 显示胜率明显低、SL 率高，是拖累胜率和盈亏比的主污染桶 | 暂时全量拒绝，直到建立更严格的 mid-zone confirmation 模型并单独审计 |
| `FALLBACK_OLD_ENTRY_NO_DEEP_FILL` | 成交少但质量高，保留后胜率和 RR 明显改善 | 作为当前 production 可交易路径 |

经验：当 Pine/LuxAlgo 对齐后的 OB/FVG 看起来已经合理，但回测仍差，应优先分桶审计 `entry_mode` / execution path，而不是继续怀疑所有信号定义或直接调 TP/SL。

## 推荐审计顺序

1. **交易合同完整性**：逐笔检查 `symbol/entry_date/exit_date/signal_date/entry_price/exit_price/pnl_pct/entry_index/exit_index/raw_zone/display_zone/sl/exit_legs/zone_type/conf_type/sequence_kind`。
2. **信号锚定**：OB 必须带 `wave_turn_idx`，`wave_turn_distance <= 3`，`anchor_method` 应指向 wave turn/HH-HL-LH-LL 附近，而不是趋势中间任意反向蜡烛。
3. **入场路径分桶**：按 `entry_mode` / `entry_mode_v47_1` / `execution_zone_mode` / `raw_zone_width_pct` 分桶，看 WR、SL、avg loss、RR。弱桶应先剔除或降权。
4. **出场审计**：如果胜率已恢复但 MFE capture 低、sold_early_rate 高，再单独做 runner/trailing 实验；不要把出场实验和信号修复混在同一轮。
5. **同步验收**：必须验证 `/api/summary`、`/api/picks`、`/api/picks/contract`、`/api/kline?symbol=...`、`/backtest`、`/monitor`、`/analysis`、`/autopsy`。

## 前端/API 验收标准

最低验收项：

- `/api/summary` 返回 active version、交易数、胜率、均盈、信号分布。
- `/api/picks` 返回 active candidates，不得用历史交易伪装当前选股。
- `/api/picks/contract` 明确 active/historical/watch_only/rejected 数量。
- `/backtest` 显示完整交易笔数，不能因表格截断导致漏看；显示 RR、逐腿出场和 exit plan。
- `/api/kline?symbol=<active_pick>` 中：
  - `signal_count > 0`
  - `trade_count > 0`
  - `signals_list` 覆盖 OB/FVG/BOS/CHOCH/MSS/Sweep 等 family
  - active trade 有交易标记
  - OB 信号携带 wave-turn 信息
- `/monitor`、`/analysis`、`/autopsy` 无 Traceback/NameError，并显示当前 active version。

## 修复原则

- 优先删除或隔离污染桶，不要为了保留交易量牺牲信号正确性。
- 弱执行路径必须以全量 replay 分桶证据判定，不能凭单笔视觉判断。
- 修复后必须重新生成 trade/pick/report/autopsy 文件，并重启 `smc_unified.py`。
- 完成后必须保存机器可读审计 JSON，便于未来复核。
