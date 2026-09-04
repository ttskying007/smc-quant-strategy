# Trailing Stop 关键Bug模式

## Bug: 高波动Bar自我触发退出

**症状**: trailing stop在激活后立即退出，捕获率极低(17%)

**根因**: 
```python
# 错误: 先更新watermark，再检查退出
if bk['h'] > high_watermark:
    high_watermark = bk['h']
    trail_sl = high_watermark * (1 - trail_dist)
    if bk['l'] <= trail_sl:      # ← 同一bar的high设置trail，同一bar的low触发
        exit
```

当一根bar同时有高波动(上影)和深回调(下影)时，自己设置的trail_sl被自己的low触发。

**修复**: 
```python
# 正确: 先检查退出(用上一bar的trail_sl)，再更新watermark
if trail_active and bk['l'] <= prev_trail_sl:  # ← 用上一bar的trail
    exit
if bk['h'] > high_watermark:                    # ← 然后更新
    high_watermark = bk['h']
    prev_trail_sl = high_watermark * (1 - trail_dist)
```

**效果**: 000070 OB_Bull: avgPnL +11.7% → +63.5% (捕获率 17% → 88%)

## Bug: MinHold缺失

入场bar的high极可能触发trail激活，然后下一bar即退出(持有1bar)。
修复: min_hold_bars=2 → 前2bar不检查trail，给价格喘息空间。

## 为什么2% TrailDist对A股日线偏紧

A股日线ATR=2-4%，2%固定trail = 价格正常波动范围内的噪音。
ATR自适应修复: TrailDist = max(1.5%, min(4%, ATR% × 0.7))
高ATR股票获得更宽trail，低ATR股票更紧trail。
