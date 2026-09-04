# V19 LuxAlgo leg() 摆动检测方法

## 为什么 pivothigh/zigzag 不适用

- **pivothigh(5,5)**: 300根A股日线产~25个点，~50%是趋势中反弹（非真实HH/HL/LL/LH）
- **zigzag 2%**: 产~29个点，每个价格反转都标记，含噪声
- **共识摆动(≥4/6)**: 过度过滤(25→13)，信号太少

## LuxAlgo leg(size) 原理

```python
# Pine equivalent:
leg(size) =>
    newLegHigh = high[size] > ta.highest(size)
    newLegLow  = low[size]  < ta.lowest(size)
    if newLegHigh → BEARISH_LEG (swing high)
    if newLegLow  → BULLISH_LEG (swing low)
startOfNewLeg = ta.change(leg) != 0
```

**语义**: `high[20] > ta.highest(20)` — 20根K线前的最高点超过后续20根K线所有高点 → 确认为真正的结构摆动高点。这保证了摆动点必须是"未被后续价格超越"的极值。

## A股适配参数

| 参数 | Pine默认(外汇) | A股适配 |
|------|-------------|---------|
| leg_size | 20 | **20** (300bar日线~18摆动点) |
| ob_swing_length | 7 | **5-7** |
| ob_displacement_mult | 1.5 | **0.7** (A股位移较小) |
| structure_spacing | 20 | **15** |
| eql_threshold | ATR×0.1 | **avg_price×0.5%** (高价股适配) |

## HH/HL/LL/LH 标注

```python
# 每检测到新摆动点时:
if leg == -1:  # 新摆动高点
    label = 'HH' if price > last_high.price else 'LH'
if leg == 1:   # 新摆动低点
    label = 'LL' if price < last_low.price else 'HL'
```

600519.SH 300bar leg(20) 结果: 18个摆动点
LL→HH→HL→LH→LL→LH→HL→HH→HL→LH→HL→LH→LL→HH→HL→LH→HL→LH

## 关键差异: LuxAlgo OB 存储时机

LuxAlgo **不在每个摆动点预设OB**，而是在 CHOCH/BOS 发生时回溯:

```python
# Pine: storeOrdeBlock()
# CHOCH_Bull 触发时:
#   从 pivot.barIndex 到 bar_index 之间找最低点
#   该最低点K线即为 Order Block
# CHOCH_Bear 触发时:
#   从 pivot.barIndex 到 bar_index 之间找最高点
```

这确保OB**只出现在结构转换点**，而非每个摆动点。
