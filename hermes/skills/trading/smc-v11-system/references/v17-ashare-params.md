# V17 A股日线参数适配

Pine SMC 2026 参数设计用于 forex/crypto 市场（数千bar历史数据，高波动率）。A股日线300bar/2% ATR 需要调整。

## 默认参数对比

| 参数 | Pine默认 | V17 A股默认 | 原因 |
|------|---------|------------|------|
| ob_swing_length | 7 | **5** | 300bar上对称(left=right=7)仅10-11个摆动，OB仅0-1个 |
| ob_displacement_mult | 1.5 | **1.0** | A股日线ATR 2%，1.5x range位移要求~3-4%极少满足 |
| ob_lookback | 10 | **15** | 更宽扫描范围补偿稀疏摆动密度 |
| min_strength | 3.0 | **2.0** | A股无session评分维度，强度评分天然偏低 |
| structure min_break_pct | 无 | **0.3%** | Pine实时运行时barstate.isconfirmed过滤，回测需显式阈值 |
| sweep min_penetration | ATR*0.15 | **max(ATR*0.25, price*0.002)** | ATR*0.15在低波动股=0.07元=噪声 |

## 验证

10只股票 V17 A股默认参数验证:

```
Stock       FVG  OB CHOCH BOS Sweep MSS EQL TOTAL
600519.SH   25   5    3    5    3   13   5    68
000001.SZ   15   7    4    7    5   14   2    64
300750.SZ   12   2    5    5    2   14   5    53
600036.SH   24   5    7    4   10   14   2    77
002594.SZ   31   8    2    7    2   15   3    89
```

OB: 2-8个/股（Pine-strict为0-1个）。信号密度合理，前端可辨识。

## 何时用Pine-strict参数

适用于有数千bar历史的高波动市场（crypto、forex），或需要极高信号纯度的研究场景:
```python
result = detect_all_signals_v17(ohlcv, params={
    'ob_swing_length': 7,
    'ob_displacement_mult': 1.5,
    'min_strength': 3.0,
    'ob_lookback': 10,
})
```
