# 完整止盈止损方案设计 (2026-05-15)

## 设计哲学

SMC交易的核心是识别聪明钱的成本线(Cost Line)。止损必须锚定在这个成本线，止盈必须基于ATR波动率自适应。

## 止损 (Stop Loss)

### 方案: 聪明钱成本线 + ATR自适应

```python
def calc_sl(zone, atr, market_state):
    # 基础: OB下沿 = 聪明钱成本线
    cost_line = zone['lower']
    
    # ATR自适应倍率（按市场状态）
    atr_mults = {
        'trending_up':   1.2,   # 趋势中给空间
        'trending_down': 1.5,   # 逆势更宽
        'ranging':       0.8,   # 震荡中收紧
        'volatile':      1.0,   # 高波标准
    }
    mult = atr_mults.get(market_state, 1.0)
    
    # SL = 成本线 - ATR缓冲
    sl = cost_line * (1 - atr * mult / 100)
    
    # 安全界限
    sl = max(sl, cost_line * 0.95)   # 最多5%止损
    sl = min(sl, cost_line * 0.99)   # 至少1%空间
    
    return sl
```

### SL类型选择

| 信号 | SL锚点 | 说明 |
|------|--------|------|
| OB_Bull | OB下沿 | 聪明钱建仓成本线 |
| Sweep_SSL | 最近摆动低点 | 流动性猎杀后反转点 |
| Breaker_Bull | 原OB下沿 | 失败OB变为支撑 |

## 分批止盈 (Batch Take-Profit)

### 方案: 3级分批 (固定比例 + ATR自适应)

```python
def calc_tp_levels(entry, zone, atr):
    tp1 = entry * (1 + atr * 2.0 / 100)   # TP1 = 2x ATR以上
    tp2 = entry * (1 + atr * 4.0 / 100)   # TP2 = 4x ATR以上
    return {
        'tp1': {'price': tp1, 'pct': 0.50},  # 50%仓位
        'tp2': {'price': tp2, 'pct': 0.30},  # 30%仓位
        'trail': {'pct': 0.20},               # 20%跟踪
    }
```

### V11实测表现

| 级别 | 触发率 | 说明 |
|------|--------|------|
| TP1 (2xATR) | **80.7%** | 主力利润来源 |
| TP2 (4xATR) | 27.5% | 超额收益部分 |
| Trailing | ~18% | 余量长跑 |

## 动态跟踪止盈 (Dynamic Trailing)

### V11方案: 条件激活 + ATR自适应距离

```python
def calc_trail_stop(entry, extreme, atr, gain_pct, market_state):
    # 激活条件: 浮盈>=7% (由market_state调整)
    activation = {
        'trending_up': 0.03,   # 趋势中早激活
        'trending_down': 0.08, # 逆势等充分跑出
        'ranging': 0.05,       # 标准
        'volatile': 0.06,
    }[market_state]
    
    if gain_pct < activation * 100:
        return None  # 未激活
    
    # Trail距离 = ATR的倍数
    trail_dist = atr * {
        'trending_up': 1.2,   # 松trail让趋势跑
        'trending_down': 0.6, # 紧trail锁利
        'ranging': 0.8,
        'volatile': 0.5,      # 高波紧守
    }[market_state]
    
    return extreme * (1 - trail_dist / 100)
```

### 关键避免

1. **破除trailing死区** — 激活后每次bar都检查是否高于当前SL
2. **永不回退** — `sl = max(sl, new_trail_sl)` 只紧不松
3. **T+1兼容** — 同日K线更新SL但不exit

## 市场状态自适应 (Per-State Parameter Map)

| 参数 | trending_up | trending_down | ranging | volatile |
|------|------------|---------------|---------|----------|
| SL ATR mult | 1.2 | 1.5 | 0.8 | 1.0 |
| Trail activation | 3% | 8% | 5% | 6% |
| Trail distance (ATR×) | 1.2 | 0.6 | 0.8 | 0.5 |
| TP1 (ATR×) | 3.0 | 2.0 | 1.5 | 2.5 |
| TP2 (ATR×) | 5.0 | 3.5 | 2.5 | 4.0 |

## 市场状态检测

```python
def detect_market_state(ohlcv, lookback=20):
    close = ohlcv['c'][-lookback:]
    ma20 = np.mean(close)
    atr = calc_atr(ohlcv)
    trend_slope = (close[-1] - close[-lookback]) / close[-lookback]
    
    if atr > np.mean(atr[-60:]) * 1.5:
        return 'volatile'
    elif trend_slope > 0.05:
        return 'trending_up'
    elif trend_slope < -0.05:
        return 'trending_down'
    else:
        return 'ranging'
```

## 进一步迭代空间

1. **Per-Stock参数缓存** — 对每只股票学习最优ATR倍数
2. **时间止损** — 入场N bar无收益则退出（当前缺失）
3. **跳空保护** — 跳过跳空高开的入场日
4. **成交量确认** — 低量OB=弱支撑（当前缺失）
5. **Turtle Soup** — 假突破反转辅助确认
6. **多周期共振加权** — 日线+周线+60min信号叠加评分
