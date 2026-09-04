# V46.1 OB 必须锚定 Waves HH/HL/LH/LL 转折点

## 触发背景

用户指出：OB 数量下降不代表准确，很多 OB 仍然发生在上升/下降趋势段中间；正确的 OB 应该在回调反转或反转位置，靠近 HH/HL/LH/LL 波浪转折点。之前虽然参考了 Pine/LuxAlgo，但没有真正参考 Waves Ultimate，也没有在 K 线图中绘制波浪。

## 根因

旧逻辑常见模式：

```text
结构突破 BOS/CHOCH 出现
→ 从 pivot 到 break bar 之间找最近反向K
→ 生成 OB
```

即使加了 `displacement >= ATR * 1.5`，该逻辑仍会把趋势中段的普通反向K误识别为 OB。displacement 只能降低数量，不能保证 OB 位于波浪转折点。

## 正确修复原则

OB 生成必须同时满足：

1. 有结构确认：BOS/CHOCH；
2. break bar 有足够 displacement（当前为 ATR × 1.5）；
3. OB candle 是对应方向的反向K；
4. OB candle 必须贴近 Waves Ultimate 风格的 confirmed fractal pivot；
5. Bull OB 只允许锚定在 `HL/LL/L` 附近；
6. Bear OB 只允许锚定在 `HH/LH/H` 附近；
7. OB candle 与 wave turn 距离默认不超过 3 bars；
8. 若结构窗口内没有合法 wave turn，不要 fallback 到趋势中段极值或最近反向K，应放弃该 OB。

## 推荐实现形态

在 `v25/smc_core_luxalgo_v34.py` 中使用类似：

```python
wave_ref = wave_fractal_pivots(klines, 2, 'wave_ref')
```

即 Waves Ultimate 风格 `right_bars=2` 的 fractal pivots，而不是只用粗粒度 `swing_len=7`。

新增/维护独立锚点函数，例如：

```python
_wave_turn_ob_anchor(klines, start_idx, break_idx, direction, wave_ref, atr_values)
```

返回字段应包含：

```text
ob_idx
wave_turn_idx
wave_turn_date
wave_turn_label
wave_turn_price
wave_turn_confirm_idx
wave_turn_confirm_date
wave_turn_distance
anchor_method
```

其中 `anchor_method` 建议标明：

```text
wave_turn_opposite_candle_near_HH_HL_LH_LL
```

## 审计标准

全市场验证不能只看 OB 数量或回测 WR/RR。必须检查每个 OB 的波浪锚点：

```text
Bull OB: wave_turn_label ∈ {HL, LL, L} 且 distance <= 3
Bear OB: wave_turn_label ∈ {HH, LH, H} 且 distance <= 3
```

报告至少包含：

```text
total OB
ok OB
bad OB
bad_rate
按 wave_turn_label 分类计数
bad 样本明细(symbol/date/type/label/distance)
```

一次成功修复的参考结果：

```text
files 4650
OB total 60762
ok 60762
bad_rate 0.0
bull_HL 24880
bull_LL 16097
bull_L 62
bear_LH 11328
bear_HH 8312
bear_H 83
```

## 前端同步要求

K 线图不能只显示 OB/FVG 点位，还必须显示 Waves HH/HL/LH/LL：

1. API 输出 `wave_swings`；
2. 前端 `swings` 层优先使用 `wave_swings`，保留 `lux_swings` 备用；
3. `swings_list` 按 bar/index 排序后再连线；
4. ECharts 需要实际绘制：
   - 波浪折线；
   - HH/HL/LH/LL 标签；
   - OB tooltip/详情中显示 `wave_turn_label/date/distance`；
5. 修改 `smc_unified.py` 后必须重启 8890，并用 HTTP + 浏览器视觉双重验证。

## 完整闭环

这类修复不能停在“代码已改”。必须继续：

```text
核心信号审计
→ K线API字段验证
→ 8890重启
→ 浏览器确认波浪线和标签显示
→ 全量V46_1回测重跑
→ watchlist/picks/rejects重建
→ 逐笔检查信号、组合、入场价、出场价、P&L/RR
→ 前端summary/picks/K线/复盘页面全部同步
```

## 禁止模式

- 不要用“OB 数量下降”替代“OB 位置正确”。
- 不要用 WR/RR 聚合指标替代逐笔机制验证。
- 不要在找不到合法 wave turn 时 fallback 到趋势中段最近反向K。
- 不要只改后端不验证 K 线图绘制。
- 不要声称“已对标 Pine/Waves”，除非已经逐机制验证：结构、OB、FVG、Sweep、波浪绘制、前端字段全部同步。
