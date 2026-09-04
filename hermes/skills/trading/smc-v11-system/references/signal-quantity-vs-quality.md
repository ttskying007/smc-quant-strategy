# Signal Quantity vs Quality — V13 Relaxed教训 (2026-05-12)

## 背景

User要求进一步放宽V13 fallback参数以提升覆盖(V11的178% OB/stock)。已完成并验证ok。但结果引发了User的反省: "交易笔数多未必是好事, 我们追求的是高胜率高盈亏比, 要求信号十足的准确性。"

## V13 Relaxed实验核心结论

V474全量4552结果:

| 指标 | V467 (V11) | V474 (V13 relaxed) | 变化 |
|------|:---------:|:-----------------:|:----:|
| 股票覆盖 | 630 | 755 | +20% |
| 交易数 | 1472 | 1769 | +20% |
| OB/stock | ~28 | ~51 | +82% |
| WR | 82.7% | 82.1% | -0.6pp |
| RR | 16.72x | 16.78x | ~0 |
| P&L | +4.58% | +4.59% | ~0 |

结论: 多82%的信号但只多20%的交易, WR下降。**V13 relaxed的额外信号是噪声, 不是真实交易机会。**

更深层分析见 `references/v13-7-layer-bias-analysis.md` —— V13 swing-backward有7层架构偏差, 即使修复所有参数也无法匹配V11纯度。

User的原始指令被再次验证: 信号正确性是唯一目标, WR/RR指标优化没有意义。V11 forward-scan OB虽然理论上不如swing-backward"纯粹", 但实用效果更好。

## "同时不同价"误解澄清

User观察到的"同个时间有两笔价格完全不同的订单"——经查V474输出中`confirmed_at=116`有125笔交易, 但这是125只不同股票都在它们的第116根bar入场。价格不同是正常的(不同股票不同价格)。

### 验证方法

1. 确认`confirmed_at`和`entry_idx`在V474输出中是bar索引(整数0-199), 不是时间戳
2. 跨股票分组: `groups[(confirmed_at, direction)]`会聚合所有股票——不同股票价格自然不同
3. 单股票验证: 股票内`used_bars = set()`第904行防重复entry_idx

### Dedup机制 (V474)

```python
# backtest_stock_v45() line 880-906:
trades = []
used_bars = set()

for sig in all_signals:
    ...
    result = evaluate_v45_entry(...)
    if result:
        if result['entry_idx'] in used_bars:
            continue    # 同一bar已入场, 跳过
        used_bars.add(result['entry_idx'])
        trades.append(result)
```

V473全量验证: 376只股票819笔交易, 仅1只股票(300112.SZ)有2笔同bar交易。单股票内重复基本不存在。

### 诊断工具

```python
# 检查: 跨股票 vs 单股票
from collections import defaultdict, Counter

# 跨股票: 按(confirmed_at, direction)分组
cross_stock = defaultdict(list)
for t in trades:
    cross_stock[(t['confirmed_at'], t['direction'])].append(t)

# 单股票: 需要symbol字段。V474 flat格式不含symbol,
# 需从stock_results重建或使用V473输出(v473_full_trades.json有symbol)
```

## 核心教训

1. **放松参数使所有信号都包含更多噪声, 不仅仅是"补上缺失的"**
2. **V13永远无法精确匹配V11的信号质量**: 两个OB检测逻辑根本不同(forward scan vs swing-backward+fallback)
3. **引擎分配应坚持**: V11=60min主引擎, V12/V13=日线研究
4. **追求信号正确性 = 拒绝覆盖诱惑**: 不要为了看到更多股票有交易而降低参数门槛
