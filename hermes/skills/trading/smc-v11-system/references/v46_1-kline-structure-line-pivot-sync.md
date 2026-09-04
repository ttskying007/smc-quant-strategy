# V46.1 K线结构画线与 Pivot 同步语义

## 触发场景

当用户指出 BOS/CHOCH/MSS 画线“不在高低点”“不像 Pine”“不是全部向右延伸”“主要是表示趋势突破/反转发生在哪两个位置之间”时，按本参考处理。不要只解释，要同步检查核心事件字段、前端 markLine、tooltip 与 K线 swings 是否同源。

## 用户纠正后的核心语义

结构线不是向右延伸的支撑/压力线，而是结构突破关系线：

```text
从右往左找左侧前高/前低；
从左到右等待右侧第一根 close 突破/跌破；
画线表示“哪个旧结构点被哪根新K线突破”。
```

因此线段应表达：

```text
Bull BOS/CHOCH/MSS: previous high pivot bar -> first close above that high
Bear BOS/CHOCH/MSS: previous low pivot bar -> first close below that low
```

不是：

```text
break bar -> break bar + 20 bars
```

也不是所有信号都向右延伸。只有 OB/FVG 这类区域可向右显示有效区；结构突破线必须显示 pivot 与 break 两个位置之间的关系。

## 结构线字段要求

每个 BOS/CHOCH/MSS 事件应带完整线段字段：

```python
line_start_idx      # 被突破的前高/前低 pivot bar
line_start_date
line_start_price    # pivot price
line_end_idx        # 第一次 close crossover/crossunder 的 break bar
line_end_date
line_end_price      # 同一 pivot price，用于水平结构线
line_semantics      # previous high/low -> break bar
line_direction      # bearish_to_bullish / bullish_to_bearish / continuation
from_left           # confirmed previous high/low at pivot bar
to_right            # first close making new high/low beyond that level
```

前端 `markLine` 必须优先使用 `line_start_idx -> line_end_idx`，不能退回 `idx -> idx+20`。tooltip 必须展示：

- 左侧结构点 bar/date/price
- 右侧突破 K bar/date/close
- BOS/CHOCH/MSS 方向语义
- crossover/crossunder 规则

## BOS/CHOCH 判定

### Bullish break

```python
prev_close <= pivot_high
close > pivot_high
```

画线：

```text
pivot high bar @ pivot_high -> break bar @ pivot_high
```

标签：

```text
old trend bearish/unknown -> CHOCH or initial break
old trend bullish -> BOS
```

### Bearish break

```python
prev_close >= pivot_low
close < pivot_low
```

画线：

```text
pivot low bar @ pivot_low -> break bar @ pivot_low
```

标签：

```text
old trend bullish/unknown -> CHOCH or initial break
old trend bearish -> BOS
```

## Pivot / 高低点同步陷阱

如果结构事件来自 LuxAlgo/Pine core，但前端 swings 或折线来自旧 `pine_like` / `detect_smc_signals`，用户会看到“线不在高低点”。必须保证：

```text
signals_list.structure pivot_idx
swings list
markLine start point
tooltip pivot fields
```

全部来自同一个 core 的 pivot 数据。

在 `smc_unified.py` 中，V46_1 路径必须显式同步：

```python
sig_data['swings'] = lux_sigs.get('swings', sig_data.get('swings', {}))
sig_data['structure'] = lux_sigs.get('structure', [])
sig_data['swing_structure'] = lux_sigs.get('swing_structure', [])
sig_data['internal_structure'] = lux_sigs.get('internal_structure', [])
```

## Pine 对齐边界

不要轻易声称“完全对标 Pine”。当前若仍使用 two-sided fractal confirmed swing：

```text
high[k] > left(size) and high[k] > right(size)
low[k]  < left(size) and low[k]  < right(size)
```

它只对齐了“confirmed pivot + close crossover/crossunder”部分，不等于完整 LuxAlgo `leg(size)` currentLevel 模型。

完整 Pine/LuxAlgo 结构更接近：

```text
leg(size) 状态切换 -> 更新 currentLevel/currentBar
从左到右检测 ta.crossover/crossunder(close, currentLevel)
第一次突破后 crossed=true
line.new(pivot.barTime, pivot.currentLevel, time, pivot.currentLevel)
```

后续若继续修“高低点不像 Pine”，优先并行实现/验证 `leg(size) currentLevel` 模型，而不是继续调 fractal 参数。

## 验证样例

验证 API：

```bash
curl 'http://127.0.0.1:8890/api/kline_full?symbol=600519.SH&tf=daily&ver=V46_1'
```

结构事件应包含类似字段：

```json
{
  "type": "CHOCH_Bull",
  "idx": 41,
  "pivot_idx": 24,
  "pivot_price": 1602.668,
  "break_price": 1603.668,
  "line_start_idx": 24,
  "line_end_idx": 41,
  "line_semantics": "structure_break_level_between_previous_high_and_break_bar",
  "line_direction": "bearish_to_bullish",
  "from_left": "confirmed previous high at pivot bar",
  "to_right": "first close making new high above that level"
}
```

通过标准：

- `line_start_idx == pivot_idx`
- `line_end_idx == idx`
- Bull 线价格等于 `pivot_high`
- Bear 线价格等于 `pivot_low`
- 前端 tooltip 显示两个位置，而不是只显示发生 bar
- Sweep 不应画成右延结构线；它是单 bar wick reclaim marker
