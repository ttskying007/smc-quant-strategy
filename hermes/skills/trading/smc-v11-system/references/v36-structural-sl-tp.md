# V36 — SMC结构性SL/TP详细报告

## 设计原理

V28使用固定百分比SL(0.3%) + breakeven trailing, 虽然WR=76.6%但有两个根本问题:
1. SL位置与信号自身SMC结构无关(85.5%是固定SL)
2. 没有结构止盈, 只有被动的trailing退出

V36修复: SL放在"信号失效"的位置, TP放在"前方结构阻力"的位置。

## 核心函数

### calc_structural_sl

```python
def calc_structural_sl(ohlcv, entry_idx, entry_price, signal, all_signals):
```

三级止损优先级:
1. FVG_Bull → SL = FVG lower (缺口下沿, 跌破=信号已填充=失效)
2. OB_Bull → SL = OB lower (订单块低点, 跌破=大资金离场)
3. 摆动低点回退 (改进自V28, 取0.10%-0.70%范围的摆动低点)
4. ATR自适应保底 (0.15%-0.80%, 基于近期波动率)

### calc_structural_tp

```python
def calc_structural_tp(ohlcv, entry_idx, entry_price, signal, all_signals):
```

三级止盈优先级:
1. 前方CHOCH_Bull (最可靠的结构转换点, 突破后前方无阻力)
2. 前方摆动高点 (次选, 清晰可识别的前高)
3. 无结构TP → 返回None, 使用宽松trailing

### calc_trailing_v36

```python
def calc_trailing_v36(ohlcv, entry_idx, entry_price, initial_sl,
                       structural_tp, n, max_hold=60):
```

结构感知trailing:
- 有TP且价格接近TP的95%时 → 收紧trailing锁定利润
- 价格触及TP → 直接止盈
- 无TP → 使用V28宽松trailing (0.2%/0.5%/1%/2%/4%档位)

## 全量交易分析

### 为什么V36 WR提升了7.4%?

1. **ATR自适应SL代替固定0.3%**: 高波动股票SL更宽避免被噪音扫掉, 低波动股票SL更紧。ATR动态SL的WR=84.8% > 固定0.3%SL。

2. **结构TP提供明确目标**: 78%交易有swing_high作为TP, WR=96.0%。这意味着如果前方有一个清晰的前高, 价格大概率会到达。这个洞察比任何信号时序更重要。

3. **过滤了模糊交易**: 19%无结构TP的交易WR=33.1%, 这些交易方向不明确但被允许入场。如果过滤这些, 整体WR可超90%。

### 为什么结构FVG SL只用了1.4%?

A股日线FVG的gap通常非常小(0.1-0.3%), FVG下边界距离entry_price往往不足0.08%, 低于结构SL的最小允许值。这是A股日线数据特征导致的, 不是逻辑错误。

## 200只验证结果 (2026-05-09)

### 整体对比

| 指标 | V28 (基线) | V36 (结构SL/TP) | 变化 |
|------|-----------|----------------|------|
| 可交易 | 131/200 (65.5%) | 150/200 (75%) | +14.5% |
| 交易数 | 693 | 868 | +25% |
| WR | 76.6% | **84.0%** | **+7.4%** |
| RR | 5.94x | 3.09x | -47% (SL更宽) |
| PF | 27 | 24 | -3 |
| P&L | +1.59% | **+2.08%** | **+31%** |
| WR>=80% | 70 | 104 | +49% |
| 平均持有 | 1.0 bars | 1.0 bars | 不变 |

### SL类型表现

| SL类型 | 占比 | WR | avgP&L |
|--------|------|----|--------|
| adaptive (ATR动态) | 82.6% | 84.8% | +2.25% |
| swing (摆动低点) | 14.9% | 79.8% | +1.29% |
| structure_fvg (FVG下边界) | 1.4% | 75.0% | +0.98% |
| structure_ob (OB下边界) | 1.2% | 90.0% | +1.36% |

### TP类型表现 (核心发现)

| TP类型 | 占比 | WR | avgP&L | 说明 |
|--------|------|----|--------|------|
| **swing_high** (摆动高点) | **78%** | **96.0%** | **+2.64%** | ⭐ 黄金TP: 前方有前高则必到 |
| choch (CHOCH break) | 3% | 89.3% | +1.27% | 优秀但出现频率低 |
| none (无结构TP) | **19%** | **33.1%** | **-0.13%** | 亏损源: 应过滤此19%的交易 |

### 关键洞察

1. **结构TP = 游戏改变者**: 78%交易有swing_high TP, WR=96.0%。只要前方有清晰的前高阻力位, 交易几乎必赢。这是比任何信号时序更强大的信号。

2. **无TP的交易 = 随机噪声**: 19%交易WR=33.1%。如果过滤这些交易, 剩余81%交易的WR=~96% → 整体超90%。

3. **ATR自适应SL优于固定0.3%**: 82.6%交易WR=84.8% vs V28固定SL的74.2%。

### 下一轮改进方向

A) 过滤无结构TP的交易(19%亏损源), 预期WR>90%
B) 全量4800扫描V36, 确认全市场效果
C) 结合V34 POI回调场景(WR=87%) + V36结构TP(WR=96%)

## 文件

| 文件 | 位置 |
|------|------|
| V36引擎 | `/root/.hermes/scripts/v11/rolling_backtest_v36.py` |
| 回测结果 | `/root/.hermes/smc_opt_v36/backtest_v36.json` |

## 对比V28关键差异

```python
# V28: 固定百分比SL + 非结构化trailing
init_sl, sl_pct, sl_type = calc_initial_sl(...)  # 0.3%固定或摆动
exit_idx, exit_price, won = calc_trailing_exit(...)  # 无条件trailing

# V36: 结构SL + 结构TP + 结构感知trailing
init_sl, sl_type, sl_pct = calc_structural_sl(...)  # 信号相关的SL位置
tp_price, tp_type, tp_pct, tp_idx = calc_structural_tp(...)  # 前方目标
exit_idx, exit_price, won = calc_trailing_v36(..., structural_tp=(tp_price, ...))  # 目标感知
```
