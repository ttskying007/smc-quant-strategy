# V17 Zigzag 反转摆动方法

## 问题: pivothigh/pivotlow 不适用于 SMC 结构检测

### pivothigh(5,5) 的问题

`ta.pivothigh(high, 5, 5)` 在 300 根日线 K 线上产生 ~25 个摆动点:
- `pivothigh(high, 5, 5)`: bar 是高点的条件是前后各 5 根 bar 的高点都低于它
- 这意味着任何 11-bar 窗口内的局部高点都被当作摆动点
- **问题**: 趋势中的小反弹会在 11-bar 窗口内成为"局部高点" → 假结构点
- 用户识别: "信号在趋势中间，不在结构转折点"

### consensus ≥4/6 的过度过滤

6 个 lookback [5,8,10,12,15,20] 取共识 ≥4 → 600519.SH 从 25 个点降至 13 个:
- 过滤了所有小摆动(包括一些真正的局部转折点)
- SWEEP 检测需要所有层级的摆动点(小结构也有流动性猎杀)
- CHOCH/BOS 过于稀疏(3-5个)，用户认为数量不足

### 为什么 zigzag 正确

SMC 交易者用眼睛识别 HH/HL/LL/LH — 他们看的是**显著的价格反转**，不是窗口大小。
zigzag 直接检测价格反转幅度:

```
if 价格从局部低点涨 ≥ 2% → 确认摆动低点 (swing_low)
if 价格从局部高点跌 ≥ 2% → 确认摆动高点 (swing_high)
```

## 实现

文件: `/root/.hermes/scripts/v11/zigzag_swings.py`

```python
def detect_zigzag_swings(ohlcv, reversal_pct=2.0):
    """
    基于价格反转幅度的摆动点检测。
    
    参数:
      reversal_pct: 确认反转所需的最小价格变动百分比
    
    返回:
      [(bar_idx, price, 'H'|'L'), ...] 按 bar_idx 排序
    """
```

### 600519.SH 300bar 结果

reversal_pct=2.0: 14 High + 15 Low = 29 swings
- 比 pivothigh(5,5) 的 25 个多 16%
- 比 consensus ≥4/6 的 13 个多 123%
- 每个点都是≥2%的真实反转，不是窗口局部高点

## 信号分配策略

不同的信号类型需要不同精度的摆动点:

| 信号类型 | 摆动方法 | 理由 |
|---------|---------|------|
| OB | zigzag 2% | OB 只在真正的趋势转折点有意义 |
| CHOCH/BOS | zigzag 2% | 结构转换只发生在主要转点 |
| SWEEP | zigzag bar_idx (not idx) | 流动性猎杀在极端 bar 处实时检测，不用等确认 bar |
| MSS | (3,3) internal | 微观结构需要更灵敏的检测 |
| EQL | zigzag 2% | 连续相等高点只比较主要结构 |
| FVG | zigzag 2% | FVG 自身检测不依赖摆动，但趋势对齐需要 |

## 已知限制

1. **2% 阈值是硬编码**: 适合 A 股日线(ATR ~2-3%)，不适用于美股或 60min
2. **没有回溯确认**: zigzag 直接在 bar 结束时确认，不像 pivothigh 有 right-bars 确认
3. **极端横盘**: 在 300bar 波动 <2% 的股票上 zigzag 可能产生 0 个摆动点

## 集成陷阱

见 `references/v17-zigzag-integration-pitfalls.md`:
1. **CHOCH/BOS**: zigzag 摆动翻转过快 → 全判 CHOCH。需用 label-based 趋势状态机。
2. **SWEEP**: zigzag idx(确认 bar)错过实时扫荡。需用 bar_idx(极端 bar)即时查找。
