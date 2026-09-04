# A股 T+1 强制退出 — 实现技术

## 背景

A股T+1规则: 当日买入的股票当日无法卖出。60min回测中, V476有71.8%的交易是同日exit (entry和exit在同一交易日), 实际不可执行。

## 解决方案

在 `calc_v38_trailing()` 函数中修改循环结构: **同日K线上继续更新extreme价格和trailing SL阈值, 但跳过exit判断。**

### 核心模式

```python
entry_date = ohlcv[entry_idx].get('date', '')[:10]  # '2026-02-24'

for j in range(entry_idx + 1, min(entry_idx + max_hold + 1, n)):
    bar = ohlcv[j]
    bar_date = bar.get('date', '')[:10]
    is_same_day = (bar_date == entry_date and bar_date != '')
    
    # ============ 始终执行: 价格跟踪 ============
    if is_bear:
        if bar['l'] < extreme:
            extreme = bar['l']
        gain_pct = (entry_price - extreme) / entry_price * 100
    else:
        if bar['h'] > extreme:
            extreme = bar['h']
        gain_pct = (extreme - entry_price) / entry_price * 100
    
    # ============ 始终执行: SL阈值更新 ============
    # TP proximity lock
    if tp_price and extreme >= tp_price * 0.90:
        sl = max(sl, entry_price * (1 + tp_pct * 0.6 / 100))
        if extreme >= tp_price * 0.98:
            if is_same_day:
                continue  # T+1: 不放行
            ...
    
    # 渐进式BE锁
    for min_hold, min_gain in PROGRESSIVE_BE:
        if j >= entry_idx + min_hold and gain_pct < min_gain:
            sl = max(sl, entry_price)
            break
    
    # Trailing threshold updates
    if gain_pct >= 6.0:
        sl = max(sl, extreme * (1 - 2.5/100))
    ...
    
    # ============ T+1检查: 跳过退出 ============
    if bar['l'] <= sl:
        if is_same_day:
            continue  # 同日: 不退出, 继续循环
        return j, max(sl, bar['l']), exit_price > entry_price
```

### 关键原则

1. **extreme价格必须同日更新**: 否则次日trailing SL会从初始entry_price开始, 完全忽略同日的价格运动
2. **SL阈值必须同日更新**: BE锁和trailing收紧在同日价格已经证明了有效性, 应该延用到次日
3. **仅跳过exit return语句**: TP lock、SL hit都继续循环而非返回

### 全量结果 (V476 vs V477)

| 指标 | V476 (可当日卖) | V477 (T+1强制) | 变化 |
|------|:------------:|:-------------:|:----:|
| WR | 86.3% | **89.0%** | **+2.7pp** |
| RR均值 | 23.32x | **24.59x** | **+1.27x** |
| PnL | +4.18% | **+4.48%** | **+0.29%** |
| Hold中位 | 1.0bar | **3.0bars** | +2.0bars |
| 平均亏损 | -0.15% | -0.13% | 更小 |
| W/L比率 | 26.9x | **39.6x** | +47% |

## 实现注意

- **OHLCV数据必须有date字段**: `bar.get('date', '')[:10]` 得到YYYY-MM-DD格式。60min数据中每根K线的date格式为 `'2026-02-24 10:30:00'`。
- **空date保护**: `and bar_date != ''` 防止date字段缺失时所有bar被误判为同日
- **所有exit点都需要检查**: TP lock(SL收紧后的立即返回), SL hit, BE锁全部要加is_same_day: continue

## 反直觉发现

T+1强制没有降低RR, 反而提高了WR和RR。根因:
- 83%的1bar退出是trailing提前锁利, 并非价格反转
- 强制hold到次日让趋势继续跑出更大收益
- 0.19% adaptive SL足够紧, 隔夜风险可控(平均亏损仅-0.13%)

## V477文件

- 引擎: `/root/.hermes/scripts/v11/v477_engine.py`
- 结果: `/root/.hermes/smc_opt_v477/v477_full.json`
