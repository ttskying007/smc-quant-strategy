# V17 OB扫描范围bug — Pine历史偏移vs摆动点参考系

## 根因

Pine SMC 2026的OB检测使用 `close[i]` 相对 `bar_index`(当前bar)的历史偏移:

```pinescript
swing_low_ob = ta.pivotlow(low, 7, 7)  // pivot在 bar_index - 7
for i = 8 to 17:
    hist_close = close[i]    // close[8] = bar_index - 8
```

Pine扫描的是 `[bar_index-8, bar_index-17]`。摆动点在 `bar_index-7`。
相对摆动点: `[摆动点-1, 摆动点-10]`。

## V17原始bug

```python
start_back = ob_swing_length + 1  # = 8
end_back = ob_swing_length + ob_lookback + 3  # = 20
for back_offset in range(start_back, end_back + 1):
    back = sl_bar - back_offset
```

相对摆动点: `[摆动点-8, 摆动点-20]`。偏差7个bar。

## 症状

- 扫描范围偏移7bar导致OB检测在完全错误的蜡烛上
- Pine扫描swing前1-10根K线, V17扫描swing前8-20根K线
- 位移检查(displacement > rng * 1.5)在错误范围通过/失败

## 修复

```python
start_back = 1  # swing - 1 (Pine: i=8, bar_index-8, swing-1)
end_back = ob_lookback  # swing - ob_lookback (Pine: i=17, bar_index-17, swing-10)
```

## 教训

Pine的 `close[i]` 是**相对bar_index的偏移**, 不是相对摆动点的偏移。
V17代码使用 `sl_bar - back_offset` 作为绝对位置, 需要 `back_offset` 直接对应Pine偏移与摆动点的关系:

```
Pine offset i → 相对摆动点 = (bar_index - i) - (bar_index - 7) = 7 - i
V17 offset back → 相对摆动点 = -back_offset
```

令 `7 - i = -back_offset` → `back_offset = i - 7`

对于 `i=8`: `back_offset = 1` (Pine `close[8]` = 摆动点-1)
对于 `i=17`: `back_offset = 10` (Pine `close[17]` = 摆动点-10)
