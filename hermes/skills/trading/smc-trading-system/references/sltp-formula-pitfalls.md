# SL/TP 公式陷阱 — 乘法顺序导致SL虚高

## Bug根因 (V17首轮回测)

`SmartMoneySLTP.calc_sl()` 中, quality_mult和volatility_mult被**错误地乘在SL价格上**, 而非SL百分比上。

```python
# ❌ 错误: multiplier applied to PRICE
base_sl = cost_line * (1 - sl_initial_pct)  # e.g. 6.90 * 0.95 = 6.555
sl = base_sl * quality_sl_mult * volatility_sl_mult  # 6.555 * 1.3 * 2.0 = 17.04
# SL = 17.04 远超入场价6.83 → "止损"实际上是"止盈"
```

```python
# ✅ 正确: multiplier applied to PERCENTAGE
adj_pct = sl_initial_pct * quality_sl_mult * volatility_sl_mult  # 0.05 * 1.3 * 2.0 = 0.13
sl = cost_line * (1 - adj_pct)  # 6.90 * 0.87 = 6.003
# SL = 6.003 略低于入场价6.83 → 正确止损
```

## 症状

- 435笔交易中430笔以"SL"退出, 但avg=+107.25% ← 完全不合理
- hold=1.0bar ← 所有交易当天"止损"
- 实际SL远高于入场价, hitting SL = 盈利退出

## 检测方法

```python
# 怀疑时快速检测
sl_pct_expected = sl_initial_pct * quality_mult * volatility_mult  # 应为百分比
# 如果sl_pct_expected > 0.30 (30%), SL公式有问题
```

## 预防

在 `calc_sl()` 入口加断言:
```python
sl_pct = adj_pct if using_correct_path else base_pct * qm * vm
assert sl_pct < 0.30, f"SL% unrealistic: {sl_pct:.1%}"
```
