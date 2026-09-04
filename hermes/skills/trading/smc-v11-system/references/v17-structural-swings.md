# V17 结构摆动过滤 (2026-05-12)

## 问题

Pine `ta.pivothigh(high, 5, 5)` 在 300bar A 股日线上产生 25 个摆动点，
但其中多数是趋势中的小反弹/回调，不是真正的 HH/HL/LL/LH 结构点。

当 CHOCH/BOS/SWEEP 使用(5,5)摆动时，信号出现在非结构位置。

## 解决

CHOCH/BOS 使用更长的 lookback (10,10) 只保留主要结构摆动。

| Lookback | 600519.SH 摆动 | CHOCH+BOS |
|----------|:---:|:---:|
| (5,5) | 25 (14H+11L) | 8 |
| (8,8) | 20 (10H+10L) | 6 |
| (10,10) | 17 (9H+8L) | **5** |
| (15,15) | 11 (6H+5L) | — |

(10,10) 过滤掉了 1528, 1465, 1496, 1470 等小摆动，保留了 1658, 1645, 1499, 1538 等主要结构点。

## 实现

```python
# 在 detect_all_signals_v17 中:
structure_swing_length = 10  # CHOCH/BOS 专用
structure_swings = detect_swings_v17(ohlcv, left=10, right=10)
structure = detect_structure_v17(ohlcv, swings=structure_swings, ...)

# SWEEP/MSS 保留较短 lookback 检测所有层级流动性
swings = detect_swings_v17(ohlcv, left=5, right=5)
```

## 教训

SMC 理论要求摆动必须在结构上有效。数学 pivot ≠ 视觉结构点。
更长 lookback 是让算法产出的摆动更接近人眼判断的结构点的简单有效方法。
