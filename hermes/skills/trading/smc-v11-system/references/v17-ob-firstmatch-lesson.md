# OB First-Match 逻辑 (V17 最关键的修复)

## 问题: displacement 硬过滤跳过正确蜡烛

### Pine 参考
```
Pine: 从 swing_high 向后扫描，取第一个反向(bearish)蜡烛作为 OB
```

### V17 原始 bug
```
V17 代码: 扫描 swing-1 到 swing-ob_lookback, 在全部候选蜡烛中
         取 displacement 最大的一个
         且 displacement < 阈值 → 丢弃
```

### A 股日线的独特问题

A 股日线上，swing 前最近的蜡烛通常 displacement 很小:
- swing_high 前 bar25: 阴线高度仅 0.5%(displacement=0.34)
- swing_high 前 bar22: 阴线高度 2.5%(displacement=2.94)

Pine 的 displacement>1.5 过滤:
- bar22 通过(displacement=2.94)
- bar25 被拒绝(displacement=0.34)

但 bar25 是**正确位置**(最靠近 swing、真正的 OB 蜡烛)。
bar22 在错误位置(离 swing 太远、中间隔了 2 根阳线)。

### 修复

```python
# 修复 (first-match):
for hist in candidates:
    if hist['close'] < hist['open']:  # 第一个 bearish 蜡烛
        ob_candle = hist
        break  # 只取第一个，不继续扫描

# displacement 仅用于评分:
strength += _score_displacement(ob_candle, swing_info)
proximity_bonus = 1.0 / max(1, abs(ob_candle['idx'] - swing_idx))
```

### 效果 (600519.SH)
- 修复前: displacement 硬过滤 → OB=16 (bar22 错误位置)
- 修复后: first-match → OB=27 (bar25 正确位置 + 更多有效摆动点)

### 教训

1. **displacement 是质量评分，不是存在性判断**: Pine 的 displacement 用于计算 strength (分级渲染)，不用于过滤 OB
2. **A 股日线的 displacement 天然小**: 日线波动 2%，bar 回撤通常 <1%。Pine 的 1.5x 阈值设计用于数千 bar 高波动市场
3. **proximity 比 displacement 更重要**: 离 swing 最近的蜡烛是正确的 OB，即使 displacement 小
4. **用户可以一眼看出位置不对**: bar22 vs bar25 的偏差用户能从 K 线图上直接识别
