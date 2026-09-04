# ENTRY_AT_ZONE 入场价格过期 Bug (2026-05-13)

## 症状

- WR 虚高至 99.7%（实际应为 ~72%）
- 均 P&L 虚高至 +18.40%（实际应为 ~2%）
- 前端显示入场价格与 K 线 OHLC 完全不匹配
- 用户反馈："股票价格不准，在回测列表中显示的不对"

## 根因

V19 回测引擎中 `entry_price = sig.lower` 使用了信号区域价格（FVG.lower 或 OB.lower），但入场发生在 `sig.confirmed_at` bar。这个 confirmed_at bar 通常比信号 bar 晚数根 K 线，市场价格已经大幅变动。

**具体案例（600519.SH）**：
```
OB_Bull 信号检测: bar=240, zone_lower=1322.01
confirmed_at bar=245: o=1485.00, h=1533.27, l=1474.00, c=1525.00

修复前: entry_price = 1322.01  ← 在 bar 245 根本买不到！
修复后: entry_price = max(1322.01, 1485.00) = 1485.00  ← 实际市场价
```

在 bar 240 检测到 OB at 1322，但等到 bar 245 确认入场时，价格已涨到 1485+。用 1322 作为入场价意味着系统假设能在远低于市价的位置成交——这在现实中不可能。

## 修复

```python
# 修复前
entry_price = sig.lower

# 修复后
entry_price = max(sig.lower, ohlcv[entry_idx]['o'])
```

使用实际入场 K 线的开盘价作为保底——不可低于市场价买入。

## 影响

| 指标 | 修复前 | 修复后 | 变化 |
|------|--------|--------|------|
| 交易笔数 | 38,770 | 13,742 | -65% |
| WR | 99.7% | 71.9% | -27.8pp |
| 均 P&L | +18.40% | +2.05% | -89% |
| 均持仓 | 1.0 bar | 2.0 bar | +100% |
| TP 退出 | 99.7% | 71.7% | -28pp |
| SL 退出 | 0.3% | 28.0% | +27.7pp |

这是整个 V17-V19 系列中最关键的 bug 修复。之前所有版本（V17/V18/V19初版）的 WR 和 P&L 指标都被系统性高估了。

## 教训

1. **ENTRY_AT_ZONE 中 zone 价格只在 zone bar 有效**——在 confirmed_at bar 入场时，zone 价格已过期
2. **任何入场价格必须 ≤ 入场 bar 的最低市价**——`entry_price >= ohlcv[entry_idx]['l']` 和 `entry_price >= ohlcv[entry_idx]['o']`
3. **高 WR(>95%) + 高 P&L(>10%) 的组合高度可疑**——A 股日线 T+1 环境下这是不可能的
