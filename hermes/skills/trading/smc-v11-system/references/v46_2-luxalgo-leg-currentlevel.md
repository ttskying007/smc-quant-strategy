# V46.2 LuxAlgo leg(size) currentLevel 对齐

## 触发场景

当用户指出 SMC 结构线、BOS/CHOCH/MSS、OB 锚点“不在高低点”“不像 Pine/LuxAlgo”“不是从发生的 K 线到突破 K 线”时，不能继续用普通 two-sided fractal pivot 调参。应先审计结构定义是否真正按 LuxAlgo `leg(size) -> currentLevel -> crossed` 执行。

## 正确定义

结构线不是向右延伸的支撑/压力线，而是表示：

```text
左侧 LuxAlgo currentLevel pivot  →  右侧第一次 close 突破/跌破该 level 的 K 线
```

### Bull BOS / Bull CHOCH

```text
起点 = current swingHigh/currentLevel 所在 bar
终点 = 第一次 close > currentLevel 的 break bar
价格 = currentLevel
```

### Bear BOS / Bear CHOCH

```text
起点 = current swingLow/currentLevel 所在 bar
终点 = 第一次 close < currentLevel 的 break bar
价格 = currentLevel
```

BOS/CHOCH 不由线本身决定，而由突破前 trend bias 决定：

```text
顺趋势突破 = BOS
逆趋势突破 = CHOCH
```

## 实现要点

1. `lux_leg_series(klines, size)` 先模拟 Pine `leg(size)`：
   - current bar `i` 确认历史 candidate `k=i-size`
   - `newLegHigh` -> `BEARISH_LEG`
   - `newLegLow` -> `BULLISH_LEG`
2. `lux_pivots()` 必须记录 active pivot：
   - `pivot_rule = luxalgo_leg_currentLevel`
   - `idx`, `confirm_idx`, `price`, `label`, `source_level`
3. `display_structure_lux()` 从左到右检测：
   - `prev_close <= high.currentLevel and close > high.currentLevel`
   - `prev_close >= low.currentLevel and close < low.currentLevel`
   - 首次突破后 `crossed=True`
4. 每个结构事件必须输出审计字段：
   - `pivot_bar_index`, `pivot_bar_time`, `pivot_confirm_index`, `pivot_rule`
   - `line_start_idx`, `line_start_price`
   - `line_end_idx`, `line_end_price`
   - `line_semantics`, `line_direction`, `from_left`, `to_right`
5. 前端 `markLine` 必须使用 `line_start_idx -> line_end_idx`，不能默认 `idx -> idx+20`。

## Wave/Pine 参考层

用户提到 Waves Ultimate / 波浪脚本时，不要把 wave/fractal 直接替换 active Lux currentLevel。正确做法：

```text
active structure = LuxAlgo leg(size) currentLevel
reference layer = wave/fractal left+right confirmed pivots
```

保留 `wave_swings` / `wave_two_sided_fractal_reference` 用于对照诊断：

- Lux currentLevel 是否选到视觉弱点
- wave/fractal 是否提示更合理的波段高低点
- 不要让 wave reference 直接污染回测 source_event，除非另开实验版本并全量验证

## 验证清单

每次修改后必须验证：

```text
1. K线 API 的 swings.rule 包含 LuxAlgo leg(size) currentLevel
2. BOS/CHOCH/MSS 的 source event 均有 pivot_rule=luxalgo_leg_currentLevel
3. markLine 使用 line_start_idx -> line_end_idx
4. 抽样检查 pivot_idx < break_idx，且 price == pivot/currentLevel
5. 全量 kept trades 的 source_event_idx 能在当前 Lux structure 中找到
6. 回测、选股、K线、复盘使用同一结构核心
```

建议输出审计：

```text
checked_source
missing_source_idx
not_lux_source
source_top
price_pnl_mismatch
```

## 已知后续坑

- 即使结构核心对齐 Lux currentLevel，交易层仍可能主要吃 BOS continuation；这不是画线问题，而是组合逻辑问题。
- 出场 `pnl_pct` 若使用分批/跟踪综合收益，不能再用单一 `exit_price` 反推；应拆出 `exit_price_effective`, `exit_price_final`, `partial_exit_prices`, `partial_exit_weights`, `realized_pnl_pct`。
- 不要宣称“完全对标 Pine”除非 source_event、K线画线、OB锚点、回测交易、选股和复盘全部通过同一 currentLevel 审计。
