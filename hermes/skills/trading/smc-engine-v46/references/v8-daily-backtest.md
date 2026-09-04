# V8 日线全量回测方法论

## 运行环境

- 日线数据: `/root/.hermes/kline_cache/` (4905只, 300bar/只)
- 周线数据: 同目录 `*_weekly_200.json`
- 数据周期: 2024-06 ~ 2026-05 (23个月)
- 信号引擎: `signals_v20.py` → `detect_all_signals_v20()`

## V2 参数 (SL=3-8%)

```python
MAX_WAIT = 3        # 最多等3根bar回调到OB zone
MIN_HOLD_BARS = 1    # 最小持bar
WEEKLY_FILTER = True # 价格须在周MA20上>2%

# SL: entry-based, ATR-adaptive, 3-8% range
atr_pct = calc_atr(closes, 14) / close * 100
sl_pct = max(3.0, min(8.0, atr_pct * 2.0))  # ~1-2x daily ATR
sl = entry_price * (1 - sl_pct / 100)

# Trailing: activate at +5%, trail distance = ATR*0.8 (2-4%)
trail_act = entry * 1.05
trail_dist = max(2.0, atr_pct * 0.8)

# TP: nearest swing high within 20 bars, min +5% gain
# TP hit: 56.2% of exits — TP is actually reachable on daily!
```

## 结果

| 指标 | 值 |
|------|-----|
| 可交易股票 | 1596/4905 (32.5%) |
| 总交易 | 3420 |
| WR | 99.8% (6 losses) |
| avg PnL | +9.00% |
| avg SL | 7.78% |
| avg RR (真实) | 1.2 |
| avg Hold | 4.4 bars |
| TP exits | 56.2% |
| Trailing exits | 43.8% |
| PnL range | -8.00% ~ +109.84% |

## 与 60min 对比

| 维度 | 60min V477 | 日线 V8 V2 |
|------|:----------:|:----------:|
| 数据周期 | 2.5月 | 23月 |
| SL | 0.17% (无意义) | 7.78% (有意义) |
| RR | 24.59x (幻觉) | 1.2 (真实) |
| TP命中 | 0% (TP太远) | 56.2% (TP可达) |
| 系统身份 | scalp (93%日内) | swing (4.4天) |

## 关键教训

1. **日线上的 swing_high TP 是可达的** — TP装饰性问题只在60min存在
2. **SL必须有结构意义** — SL/ATR 比率应在0.3-1.0x范围
3. **RR是SL的函数** — 对比不同策略时，必须先归一化SL
4. **数据周期决定可信度** — 23个月 vs 2.5个月是质的区别
