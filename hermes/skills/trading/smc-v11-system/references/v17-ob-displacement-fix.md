# V17 OB Displacement 方向修复 (2026-05-12)

## 问题

V17 OB 检测中 displacement 方向与标准 SMC 理论相反。

**Pine 代码:**
```pinescript
disp = swing_low_ob - hist_low  // swing_low - OB_low
```

Pine 检测的是 **capitulation 模式**: OB candle 的 low 低于 swing low（恐慌抛售→反弹）。
此模式在 A 股日线上极为罕见（300bar 中 CMB 0 个 OB）。

**标准 SMC:**
- Bull OB: bearish candle ABOVE swing low → 价格下跌到 swing → 反转上涨
- Bear OB: bullish candle BELOW swing high → 价格上涨到 swing → 反转下跌

**V17 修复前:**
```python
disp = sl_price - bar['l']  # swing_low - OB_low (Pine capitulation)
```

**V17 修复后:**
```python
disp = bar['l'] - sl_price  # OB_low - swing_low (标准 SMC: OB 在 swing 上方)
```

## 影响

| 股票 | 修复前 OB | 修复后 OB |
|------|----------|----------|
| 600036.SH (招行) | 0 | 24 |
| 600519.SH (茅台) | 1 | 21 |
| 002594.SZ (比亚迪) | 0 | 19 |

全量 4800 回测: 42,123 笔 → 72,350 笔交易 (+72%)

## 教训

Pine 参考代码不等于 SMC 理论标准。Pine 实现可能针对特定市场模式优化。
逐行对比 Pine 时需同时对照 ICT/SMC 理论定义 — displacement 方向是理论正确性的基础。
