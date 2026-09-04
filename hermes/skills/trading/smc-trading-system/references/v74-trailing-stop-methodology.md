# V7.3-V7.4 Trailing Stop 完整方法论

## 核心机制

替换固定TP为动态Trailing Stop:
- Hard SL = zone_low × SL_MUL (始终有效, 硬保底)
- Trail激活 = price > entry_price × TRAIL_ACT (默认1.03, +3%)
- Trail退出 = price从最高点回落 TRAIL_DIST (默认0.02, 2%)

## 关键Bug: prev_trail_sl 延迟1bar (2026-05-15)

### 问题
高波动bar自我触发exit: 当前bar更新watermark后立即检查当前bar low，导致同一bar内大幅波动触发退出。

### 症状
000070 OB_Bull: 入场后第一bar h=10.45 l=9.28 → 立即触发trail_stop @10.24 → P&L=+11.7%
但后续涨到15.82(+72%)完全踏空。

### 修复
```python
# ❌ 旧代码: 更新→立即检查
for k in range(entry_bar+1, n):
    if bk['h'] > hwm: hwm = bk['h']
    trail_sl = hwm * (1 - dist)
    if bk['l'] <= trail_sl: exit  # 同bar自我触发!

# ✅ 新代码: 先检查(用prev)→后更新(给下一bar)
prev_trail_sl = entry * (1 - dist)
for k in range(entry_bar+1, n):
    if trail_active and bk['l'] <= prev_trail_sl: exit  # 用上一bar的trail_sl
    if bk['h'] > hwm: hwm = bk['h']
    if trail_active: prev_trail_sl = hwm * (1 - dist)  # 更新给下一bar
```

### 效果
000070: P&L +11.7% → +63.5% (捕获率17%→87.6%)

## 参数网格

```python
MAX_WAITS = [3, 5]
SL_MULS = [0.95, 0.96]
TRAIL_ACTIVATIONS = [1.03]    # +3%
TRAIL_DISTANCES = [0.02]      # 2%
# = 4 configs, ~50s
```

## V7.3 vs V7.4 演变

| 版本 | 交易 | WR | avgPnL | cum | 关键变化 |
|------|------|-----|--------|-----|---------|
| V7.2 | 119 | 82.4% | +3.25% | +387% | 固定TP+5% |
| V7.3 | 618 | 75.9% | +4.51% | +2,789% | Trail+prev_sl bugfix |
| V7.4 | 1,874 | 82.4% | +6.84% | +12,827% | +蜡烛形态 +OB过滤+15 |

## 文件
- 引擎: /root/.hermes/scripts/v11/backtest_v63_full.py (lines 121-170)
- 前端渲染: /root/.hermes/scripts/smc_unified.py (lines 403-428, Trail/SL/Peak线)
