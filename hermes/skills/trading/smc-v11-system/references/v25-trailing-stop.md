# V25 — Trailing Stop Exit Strategy

## 核心原理

V23使用固定TP=3.0%, 即使大趋势也提前止盈。
V25改用追踪止盈, 让利润奔跑, 同时用摆动SL控制亏损。

## 退出算法

```
入场价 = entry_price
初始SL = 摆动点封顶0.5%(或固定0.3%)
最高价 = entry_price
持仓计数器 = 0

每根K线:
  更新highest = max(highest, bar.h)
  当前盈利% = (highest - entry_price) / entry_price * 100
  
  if 当前盈利% >= 1.5%:
    SL = max(SL, highest * 0.99)  // 追踪1%回撤
  elif 当前盈利% >= 1.0%:
    SL = max(SL, entry_price * 1.003)  // 保本+0.3%
  elif 当前盈利% >= 0.5%:
    SL = max(SL, entry_price * 0.999)  // 接近保本
  
  if bar.low <= SL: 退出(亏损或保本)
  if 持仓 > 60K线:  强制退出
```

## V25 结果 (200只, 289笔)

| 指标 | 值 |
|------|-----|
| **WR** | **91.0%** |
| **RR** | **55.81x** |
| **PF** | **757** |
| **P&L** | **+27.77%** |
| Swing SL WR | 98.4% |

## P&L 分布

| 区间 | 笔数 | 占比 |
|------|------|------|
| -5% ~ 0% | 26 | 9% |
| 0% ~ +2% | 10 | 3% |
| +2% ~ +5% | 26 | 9% |
| +5% ~ +10% | 43 | 15% |
| **+10% ~ +20%** | **70** | **24%** |
| **+20% ~ +50%** | **79** | **27%** |

79笔交易捕获20-50%利润 → 这才是趋势跟踪的真正威力。

## 核心代码

```python
# rolling_backtest_v25.py — calc_trailing_exit()
def calc_trailing_exit(ohlcv, entry_idx, entry_price, initial_sl, n, max_hold=60):
    sl = initial_sl
    highest = entry_price
    
    for j in range(entry_idx+1, min(entry_idx+max_hold+1, n)):
        bar = ohlcv[j]
        highest = max(highest, bar['h'])
        gain_pct = (highest - entry_price) / entry_price * 100
        
        if gain_pct >= 1.5:
            sl = max(sl, highest * 0.99)      # trail 1%
        elif gain_pct >= 1.0:
            sl = max(sl, entry_price * 1.003)  # breakeven+
        elif gain_pct >= 0.5:
            sl = max(sl, entry_price * 0.999)  # near breakeven
        
        if bar['l'] <= sl:
            return j, max(sl, bar['l']), exit_price > entry_price
    
    # Time exit
    return min(entry_idx+max_hold, n-1), ohlcv[exit_idx]['c'], ...
```

## 文件

引擎: `~/.hermes/scripts/v11/rolling_backtest_v25.py`
结果: `~/.hermes/smc_opt_v25/backtest_v25.json`
