# V45 前端契约 + 事件账本审计经验

## 触发场景
当 SMC 前端出现“选股 4800+ 只/几乎全市场都入选”、回测曲线近似直线，或用户质疑止损多到底是信号、入场点、SMC 定义、组合方式、未到点位哪一类问题时，必须先做数据契约与事件生命周期审计，再谈调参。

## 核心结论
1. **picks 文件不等于当前选股**：如果 `picks_count ≈ trade_unique_symbols ≈ 4800+`，通常是“历史每股最佳/代表交易”被误当作当前 active picks。
2. **/monitor 禁止 fallback 到历史 picks**：没有 `ACTIVE_CANDIDATE` 时就显示 0 和原因，不能回退到 `picks[-50:]` 或历史全市场列表。
3. **交易级 pnl_pct 累加不是资金曲线**：23 万笔交易逐笔 `cum += pnl_pct` 会生成机械直线；必须按日期聚合并定义组合仓位。
4. **先审计入场生命周期**：大量止损不一定是 SL 参数问题。若出现 `DIRECT_SIGNAL_CLOSE`、未触及 `raw_zone`、未进入 `ARMED` 就交易，应归因到入场/时序契约错误。

## 前端 picks 契约修复
新增/统一字段：
- `pick_scope`: `ACTIVE_CANDIDATE` / `HISTORICAL_BEST` / `WATCH_ONLY`
- `pick_date`
- `setup_status`
- `is_active_pick`
- `active_reason`
- `invalid_reason`

接口建议：
- `/api/picks`：只返回 `ACTIVE_CANDIDATE`。
- `/api/picks/history`：返回 historical best，供分析，不进当前选股页。
- `/api/picks/contract`：返回 active/historical/raw 计数和契约说明。

验收：
```json
{
  "active_picks_not_historical_all_market": true,
  "monitor_does_not_show_4800_historical_stocks": true,
  "historical_best_separated": true
}
```

## 回测曲线契约修复
必须分离三条曲线：
1. `daily_equal_weight_equity`：默认展示；按 `exit_date` 聚合，同日交易等权平均，`equity *= (1 + daily_return)`。
2. `portfolio_capped_equity`：同日最多 N 笔，按质量分排序取前 N，模拟组合容量。
3. `trade_cumulative_pnl`：交易级累计，只能作为诊断线，不能称为资金曲线。

验收：
```json
{
  "curve_dates_unique": true,
  "curve_sorted_by_date": true,
  "daily_points_less_than_trade_count": true
}
```

## V45 事件账本审计骨架
当旧版本交易无法证明“为什么能入场”时，先从交易反推审计账本，暴露问题；正式策略再从 K 线原生生成事件。

事件类型至少包含：
- `LIQUIDITY_SWEEP`
- `LIQUIDITY_RECLAIM`
- `CHOCH` / `MSS` / `BOS`
- `OB_CREATED` / `FVG_CREATED` / `IFVG_CREATED`
- `RAW_ZONE_RETESTED`
- `ENTRY_CONFIRMATION`
- `ENTERED`
- `EXITED`

sequence 必须验证：
- liquidity → structure → POI → raw-zone retest → confirmation → entry
- `DIRECT_SIGNAL_CLOSE` 不允许进入正式交易。
- standalone IFVG 不允许作为完整 sequence。
- entry 必须在 raw zone 内或明确容忍范围内。

## 关键诊断指标
必须输出：
- `direct_signal_close_trade_count`
- `entry_without_raw_retest_count`
- `standalone_ifvg_trade_count`
- `invalidated_setup_traded_count`
- `sl_attribution_coverage`
- `entry_mode_counts`
- `reject_reason_counts`

如果审计出现：
```json
{
  "DIRECT_SIGNAL_CLOSE": 161877,
  "ENTRY_WITHOUT_RAW_RETEST": 238564
}
```
结论应是：止损多的首要根因是入场生命周期/原始 zone retest 缺失，而不是优先调 SL 参数。

## 推荐输出文件
- `/root/.hermes/smc_opt_v45/events_v45.json`
- `/root/.hermes/smc_opt_v45/sequences_v45.json`
- `/root/.hermes/smc_opt_v45/setups_v45.json`
- `/root/.hermes/smc_opt_v45/sl_attribution_v45.json`
- `/root/.hermes/smc_opt_v45/v45_event_lifecycle_report.json`
- `/root/.hermes/smc_opt_v45/v45_frontend_validation.json`

## Pitfalls
- 不要把 `state: ACTIVE` 当真；旧版本可能把历史 picks 全部写成 ACTIVE。
- 不要在 `/monitor` 无 active picks 时“为了好看”显示历史数据。
- 不要把交易累计收益曲线命名为资金曲线。
- 不要在尚未通过 sequence/entry gate 时接入前端选股。
- 不要只报告 WR/平均收益；必须报告机制不合格数量。
