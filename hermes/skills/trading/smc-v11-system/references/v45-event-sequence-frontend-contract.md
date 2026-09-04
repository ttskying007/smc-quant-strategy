# V45 事件时序引擎与前端契约修复经验

## 触发场景
当 SMC 系统出现以下任一现象时，不能只调参数或只筛选高 WR 组合：
- 用户指出止损多，并追问是信号定义、组合方式、入场点、还是未到入场点。
- 前端“选股”显示接近全市场 4800+ 只。
- 回测资金曲线过度平滑、近似直线。
- 交易数巨大但平均持仓极短，且大量 `DIRECT_SIGNAL_CLOSE`/IFVG 类交易。

## 核心纠正
上一轮“禁止 chase + raw zone retouch + IFVG 不裸开”只是第一层修复，不够根本。真正修复必须把系统从“信号集合筛选器”升级为：

```text
事件账本 → 时序语法 → setup 生命周期 → POI 生命周期 → entry gate → 风险计划 → SL 归因 → 前端契约验证
```

必须能逐笔回答：
1. 这个交易属于哪条合法 SMC sequence？
2. liquidity → structure → POI → retest → confirmation 是否按时间发生？
3. POI 是否过期/失效/多次 mitigation？
4. 入场前 setup 是否已 ARMED？
5. 是否存在反向冲突事件？
6. 如果亏损，是正常结构失败还是系统性错误？

## 前端 4800 只“选股”问题
如果 `picks` 数量接近全市场，通常不是策略真的选出 4800 只，而是数据契约错了：

```text
historical per-symbol best trades 被当成 current active picks 展示
```

修复要求：
- `pick_scope`: `ACTIVE_CANDIDATE` / `HISTORICAL_BEST` / `WATCH_ONLY`
- `is_active_pick`
- `setup_status`
- `active_reason`
- `invalid_reason`

前端规则：
- `/api/picks` 默认只返回 `ACTIVE_CANDIDATE`。
- `/monitor` 没有 active picks 时显示 0，不允许 fallback 到历史 4800 只或 `picks[-50:]`。
- historical best 必须单独显示，不能标成“高质量选股”。

验收：
```json
{
  "active_picks_not_historical_all_market": true,
  "historical_best_separated": true,
  "monitor_does_not_show_4800_historical_stocks": true
}
```

## 回测直线问题
如果曲线近似直线，先审计是否存在以下错误：
- 每笔交易 `pnl_pct` 机械累加：`cum += pnl_pct`。
- V44/大文件为避免 OOM 跳过日期排序。
- 没有按 `exit_date` 聚合到日收益。
- 没有组合仓位/同日并发限制。

正确曲线至少输出三类：
1. `trade_cumulative_pnl`：交易级诊断线，必须按 exit_date 排序。
2. `daily_equal_weight_equity`：默认展示线；同日交易等权平均，复利递进。
3. `portfolio_capped_equity`：同日最多 N 笔，按质量分排序取前 N。

验收：
```json
{
  "curve_dates_unique": true,
  "curve_sorted_by_date": true,
  "daily_points_less_than_trade_count": true,
  "v44_no_unsorted_trade_curve": true
}
```

## V45 可执行阶段

### Phase 1 — baseline audit
冻结 V44/V当前版本，输出 baseline：
- total/window trades
- historical pick count
- active pick count
- frontend contract errors

### Phase 2 — event ledger
生成原子事件：
- `LIQUIDITY_SWEEP`, `LIQUIDITY_RECLAIM`
- `CHOCH`, `MSS`, `BOS`
- `OB_CREATED`, `FVG_CREATED`, `IFVG_CREATED`, `BREAKER_CREATED`
- `ZONE_MITIGATED`, `ZONE_INVALIDATED`
- `RAW_ZONE_RETESTED`, `ENTRY_CONFIRMATION`, `OPPOSITE_STRUCTURE_BREAK`

每个事件必须有 `event_id/symbol/index/date/event_type/direction/strength`；zone 事件必须有 raw/display split。

### Phase 3 — sequence compiler
不要用“窗口内信号集合”直接交易。至少编译：
- `SSL_RECLAIM_MSS_OB_RETEST_CONFIRM`
- `SSL_RECLAIM_MSS_FVG_RETEST_CONFIRM`
- `SSL_IFVG_FLIP_MSS_RETEST_CONFIRM`
- `RANGE_LOW_SWEEP_RECLAIM_INTERNAL_CHOCH_POI`
- `TREND_IMPULSE_POI_PULLBACK_CONFIRM`
- `FULL_ARBITRATION`

每条可交易 sequence 必须有：
```text
liquidity → structure → POI → raw retest → confirmation
```

### Phase 4 — setup lifecycle
状态机必须包括：
```text
DISCOVERED → WAITING_FOR_CONFIRMATION → WAITING_FOR_POI → WAITING_FOR_RETEST → RETESTED → ARMED → ENTERED → EXITED
```
以及失败态：
```text
INVALIDATED / EXPIRED / MISSED / CONFLICTED
```

验收：
- `entered_before_armed_count = 0`
- `expired_setup_traded_count = 0`
- `invalidated_setup_traded_count = 0`

### Phase 5 — POI lifecycle and selector
POI 优先级：
1. OB + FVG overlap
2. structure-anchored OB
3. IFVG flip zone + OB overlap
4. displacement FVG
5. breaker block
6. plain FVG
7. standalone IFVG 禁止

字段：`poi_age_bars`, `mitigation_count`, `first_touch`, `fresh_zone`, `poi_rank`, `poi_reject_reason`。

### Phase 6 — entry gate
正式交易只允许：
- `CONFIRM_WICK_RETOUCH_RAW_HIGH`
- `LIMIT_RETOUCH_RAW_HIGH`
- `RETEST_ENGULF`
- `RETEST_PINBAR_STRICT`

禁止：
- `DIRECT_SIGNAL_CLOSE`
- `CONTINUATION_SHALLOW_PULLBACK`
- 未到 raw zone 的 next open

验收：
- `direct_signal_close_trade_count = 0`
- `entry_above_raw_high_invalid_count = 0`
- `entry_gate_coverage = 100%`

### Phase 7 — SL attribution
每笔亏损必须归因，并区分可避免/不可避免：
- `PRE_ENTRY_INVALIDATION_MISSED`
- `ENTERED_BEFORE_ARMED`
- `ENTRY_WITHOUT_RAW_RETEST`
- `ENTRY_AFTER_SETUP_EXPIRED`
- `ENTRY_AFTER_ZONE_INVALIDATED`
- `ENTRY_IN_CONFLICTED_CONTEXT`
- `IFVG_STANDALONE_SEQUENCE_ERROR`
- `POI_SELECTION_WRONG`
- `SL_CAPPED_INSIDE_STRUCTURE`
- `STRUCTURE_VALID_BUT_NORMAL_LOSS`
- `TRAILING_PROFIT_STOP`

## 最终验收总表
最终报告必须包含这些布尔/数值项，而不是只报 WR：
```json
{
  "frontend_picks_contract_fixed": true,
  "equity_curve_contract_fixed": true,
  "event_ledger_full_market_done": true,
  "sequence_compiler_done": true,
  "setup_lifecycle_done": true,
  "entry_gate_done": true,
  "poi_lifecycle_done": true,
  "sl_attribution_coverage": 1.0,
  "direct_signal_close_trade_count": 0,
  "standalone_ifvg_trade_count": 0,
  "expired_setup_traded_count": 0,
  "invalidated_setup_traded_count": 0,
  "active_picks_not_historical_all_market": true,
  "daily_equity_curve_sorted_unique_dates": true
}
```

## 用户纠正带来的工作流要求
当用户追问“就这些就够了吗？有没有逻辑问题？”时，应主动回看方案缺口，不要防御性确认原方案。必须补上：
- 时间序列组合，而非窗口集合。
- setup 生命周期。
- zone/POI 过期与失效。
- 多信号冲突仲裁。
- 前端数据契约与回测曲线契约。
- 每一步可执行、可验证、可验收。
