# V7.6 ATR自适应Trailing Stop

## 核心机制

```
SL  = zone_low × (1 - max(3%, ATR% × SL_ATR_MUL))
TrailAct = entry_price × (1 + max(2%, ATR% × ACT_ATR_MUL))
TrailDist = max(1.5%, min(4%, ATR% × DIST_ATR_MUL))
MinHold = 2 bars (前2bar不检查trail退出)
```

## 参数

| 参数 | 值 | 含义 |
|------|-----|------|
| SL_ATR_MUL | 1.5 | SL宽度 = ATR% × 1.5, 最小3% |
| ACT_ATR_MUL | 1.0 | Trail激活 = 入场价 × (1 + ATR%), 最小2% |
| DIST_ATR_MUL | 0.7 | Trail距离 = ATR% × 0.7, 范围[1.5%, 4%] |
| MIN_HOLD | 2 | 前2bar不检查trail, 防入場bar噪声触发 |

## 退出检查顺序 (关键!)

```python
for k in range(entry_bar + 1, n):
    bk = daily[k]
    
    # 1. 先检查退出 (用PREVIOUS bar的trail_sl)
    if trail_active and bk['l'] <= prev_trail_sl:
        exit  # trail_stop
    
    # 2. 更新watermark (为NEXT bar计算trail_sl)
    if bk['h'] > high_watermark:
        high_watermark = bk['h']
    
    # 3. 激活trail
    if not trail_active and high_watermark >= trail_activation:
        trail_active = True
    
    # 4. 计算下次退出价
    prev_trail_sl = high_watermark × (1 - trail_dist)
```

修复了V7.3的bug: 高波动bar自我触发退出(同bar更新hwm又检查l ≤ trail_sl)

## 回测结果

Best: MW3_SLatr1.5_ACTatr1.0_DISTatr0.7
809笔 WR=82.1% avgPnL=+13.11% cum=+10,607%

OB_Bull: 442笔 WR=97.7% avg=+19.48%
BOS→FVG: 104笔 WR=51.0% avg=+6.49%

## vs V7.3固定参数

| 指标 | V7.3固定 | V7.6 ATR | 变化 |
|------|---------|----------|------|
| avgPnL | +9.11% | +13.11% | +44% |
| OB_Bull avg | +12.17% | +19.48% | +60% |
| WR | 88.4% | 82.1% | 略降 |
| 交易数 | 1,309 | 809 | 周线过滤减少 |
