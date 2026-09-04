# V13 60min Fallback Calibration & Swing Detection Methodology

## 问题背景

V12 swing-backward OB检测在60min数据上覆盖率仅为V11的42%。根本原因: swing-backward需要的pullback-impulse-OB三段式结构在60min噪声环境下过于苛刻。V13采用swing-backward(正确性)+forward fallback(覆盖)混合策略。

## 60min专用摆动检测: detect_swings_v13_60min

### 参数选择

| 参数 | V12 (日线) | V13 60min | 理由 |
|------|-----------|-----------|------|
| left | 8 | 10 | Pine pivothigh标准 |
| right | 3 | 2 | 60min噪声高, right=3过严(Waves Ultimate: right_bars=2) |
| ATR inversion | 2.0x | 1.0x | 60min波动小, 2.0x几乎无反转(h/l交换触发) |

### 实现细节

- 只在 `signals_v12.py` 中, 作为独立函数
- 使用相同算法结构(`left/right` 窗口比较 + ATR volatility inversion)
- ATR inversion threshold从2.0x降到1.0x: 意味着范围超过1倍ATR的bar会触发极值交换
- right=2匹配 Pine Script `ta.pivothigh(left, right)` 的right_bars参数

### 测试验证 (100只)

对100只V467可交易股票的OB数量对比:
- V11 baseline: 平均28.5 OB/stock, 100%覆盖
- V13 relaxed: 平均50.8 OB/stock, 100%覆盖
- V13/V11比率: ~178%

## Fallback Calibration 方法

### 校准框架

采用四参数灵敏度调节:

```python
levers = {
    'body_pct':      [0.08, 0.10, 0.12],  # 最小实体%
    'dis_ratio':     [0.5, 0.6, 0.7, 0.8],  # 位移/范围比率
    'near_sw':       [5, 6, 8, 10],         # 靠近摆动点的K线数
    'volume_filter': [None, 0.3, 0.5],      # vol > median * N (None=无过滤)
}
```

### 校准历史

| 版本 | body | dis | sw.range | vol | OB/stock | V11比率 | 覆盖率 |
|------|------|-----|----------|-----|----------|---------|--------|
| 原版V13 | 0.08 | 0.8 | +/-5 | 0.5x | ~9.4 | ~42% | ~60% stocks |
| v1 | 0.05 | 0.5 | 无 | 无 | ~78 | ~272% | 100% |
| v2 | 0.05 | 0.6 | +/-8 | 无 | ~75 | ~265% | 100% |
| v3 | 0.08 | 0.5 | +/-10 | 无 | ~67 | ~235% | 100% |
| v4 | 0.08 | 0.6 | +/-6 | 0.3x硬 | ~52 | ~184% | 100% |
| v5(final) | 0.10 | 0.7 | +/-5 | 0.3x硬 | ~51 | ~178% | 100% |

### 关键发现

1. **near_sw是最高影响参数**: 移除它会导致OB暴涨(~272% V11), 因为60min所有candle都在某个swing附近
2. **volume过滤效果有限**: 60min数据90% bars成交量>median*0.3, 所以vol filter主要过滤极端低量bar
3. **body_pct提升效果显著**: 0.08->0.10减少约15% OB
4. **V11 OB检测包含额外约束**: V11的前向扫描有隐式的directional bias / trend filter, 使得同等参数的简单forward fallback总是产出更多OB
5. **V13永远无法精确匹配V11**: 两者OB检测逻辑本质不同(V11 forward scan vs V13 swing-backward+fallback)

## 最终结果

V474(V13 relaxed)全量4552:
- 755 stocks (vs V11 630) -- +20%覆盖
- 1769 trades (vs V11 1472) -- +20%交易数
- WR=82.1% (vs V11 82.7%) -- 基本持平
- RR=16.78x (vs V11 16.72x) -- 基本持平

V13 relaxed版本成功达到甚至超越了V11的覆盖水平, 但V11仍然是推荐的60min主引擎, 因为:
1. V11经过更多版本迭代验证
2. V13 fallback信号质量未经长时间验证
3. V13只是实验性对比参考

## 文件清单

| 文件 | 用途 |
|------|------|
| `/root/.hermes/scripts/v11/signals_v12.py` | V13 60min函数(detect_ob_v13_60min, detect_all_signals_v13_60min, detect_swings_v13_60min) |
| `/root/.hermes/scripts/v11/v474_engine.py` | V474全量扫描引擎(V13 relaxed + V467退出) |
| `/root/.hermes/smc_opt_v474/v45_full.json` | V474全量结果(1769笔交易) |
| `/root/.hermes/scripts/v11/_v13_coverage_check.py` | OB覆盖率对比脚本 |
