# V46.2 LuxAlgo currentLevel 全量核准与出场审计修复

## 触发场景
用户指出 SMC 信号仍不准确，要求从 Pine/LuxAlgo 语义、组合信号、回测、选股、K线图表、复盘同步做全量核准。此类任务不能只看 WR/RR，必须验证“定义 → 实现 → 交易 source → 入场 → 出场 → 前端显示”的闭环。

## 关键结论
1. Active pivot 不能继续用普通 two-sided fractal 作为交易结构核心；应采用 LuxAlgo/Pine 风格：`leg(size) -> currentLevel -> crossed`。
2. two-sided fractal / Waves Ultimate 风格 pivot 可保留为 `wave_reference`，用于对照和诊断，但不能混入 active BOS/CHOCH/OB/MSS source。
3. BOS/CHOCH/MSS 结构线必须表示“哪个旧结构点被哪个新 K 线突破”：`pivot bar -> break bar`，不是从 signal bar 向右延伸。
4. 回测逐笔复盘中，分批止盈/跟踪止损会导致 `pnl_pct != (exit_price_final / entry_price - 1)`。必须区分：
   - `exit_price_final`: 最后一笔退出价格；
   - `exit_price_effective`: 可由综合 `pnl_pct` 反推的等效退出价；
   - `exit_legs`: 每次部分出场明细；
   - `exit_weight_sum`: 应为 1.0。
5. 选股 API 如果 watchlist-first 返回 `v46_1_layer=REJECT` 的 active candidates，前端默认展示会误导用户；默认交易列表应只展示 PASS/A/B，REJECT 应进入“观察/拒绝原因”视图。

## 推荐全量核准清单

### 1. 信号不变量
对全市场 K 线缓存逐文件检查：
- `pivot_rule == luxalgo_leg_currentLevel` for active structure。
- Bull structure: `pivot_price == pivot_bar.high`。
- Bear structure: `pivot_price == pivot_bar.low`。
- Bull break: `prev_close <= currentLevel && close > currentLevel`。
- Bear break: `prev_close >= currentLevel && close < currentLevel`。
- `line_start_idx == pivot_bar_index`。
- `line_end_idx == break/index`。
- OB 必须位于 `pivot_bar <= ob_bar < break_bar`。
- Bull OB 必须是 break 前最近 bearish candle；Bear OB 必须是 break 前最近 bullish candle。
- MSS 必须来自 internal structure，且有同方向 recent sweep（如 14 bar 内）。

### 2. 交易 source 回链
对 kept trades 逐笔检查：
- `source_event_idx` 能在当前 core 的 `signals.structure` 中找到。
- source event 的 `pivot_rule` 必须是 `luxalgo_leg_currentLevel`。
- source line 必须满足 `pivot -> break`。
- 不允许 kept trade 回链旧 fractal/source。

### 3. 出场审计
每笔交易必须满足：
```text
sum(exit_leg.weight) == 1.0
pnl_pct == sum(exit_leg.weight * ((exit_leg.price - entry_price) / entry_price * 100))
exit_price_effective == entry_price * (1 + pnl_pct/100)
```
不要再用 `exit_price_final` 反推综合收益。

### 4. 前端同步
重启 8890 后用 HTTP 验证：
- `/api/kline_full?symbol=...&tf=daily&ver=V46_1` 返回结构信号且 line 字段完整。
- `/api/summary?ver=V46_1` 指标来自最新回测结果。
- `/api/picks?ver=V46_1` 区分 active candidate、quality PASS/A/B、REJECT。
- K线 tooltip 应显示 pivot_date、break_date、line_semantics、source_level、pivot_rule。

## 实现位置参考
- Core: `/root/.hermes/scripts/v25/smc_core_luxalgo_v34.py`
- 回测/出场审计: `/root/.hermes/scripts/v25/v41_final_engine.py`
- Layered full run: `/root/.hermes/scripts/v25/v46_1_layered_3y.py`
- 前端/API: `/root/.hermes/scripts/smc_unified.py`

## 已验证过的审计输出形态
一次合格核准应能报告类似字段：
```json
{
  "missing_fields": 0,
  "price_pnl_mismatch": 0,
  "exit_leg_bad": 0,
  "source_miss": 0,
  "source_not_lux": 0,
  "line_bad": 0
}
```

## 坑点
- 聚合 WR/RR 不能证明 SMC 信号正确；必须逐笔 source 回链。
- “所有结构线都向右延伸”是前端画法错误，不是 Pine/LuxAlgo 语义。
- `exit_price` 字段若既表示最后退出价又用于综合收益反推，会污染复盘和盈亏比诊断。
- continuation BOS 交易表现好，不代表 reversal 分支已经正确；需要单独拆 `LIQ -> CHOCH/MSS -> OB/FVG -> retest -> confirmation`。
