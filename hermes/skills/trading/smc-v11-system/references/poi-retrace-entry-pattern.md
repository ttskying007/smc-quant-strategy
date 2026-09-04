# POI Retrace Entry 入场模式

## 核心改进（Phase 2 已落地到 daily_scan.py）

**旧逻辑（错误的突破模式）**：
```python
entry_idx = c.bar + 1          # 入场 = 确认bar的下一根
if entry_idx != latest_idx:    # 只找最新的bar
    continue                   # 即：昨天BOS/CHOCH，今天立即入场
entry_price = klines[entry_idx].get('o')  # 开盘入场
```
**结果**：100% 无回撤。28% 的入场在 zone 上方追入，无 SMC 入场质量。

**新逻辑（真正的 POI 回撤）**：
```python
# 今日K线必须触碰 zone
bar_touching_zone = (curr_lo <= zone_high) and (curr_hi >= zone_low)
if not bar_touching_zone:
    continue  # 价格没回来，不入场
# 入场 = 今日收盘价（回撤后的位置）
entry_price = curr_close
```
**结果**：100% 回撤入场（20260609 验证 844/844），SL_HIT 减少 25%。

## 入场链对比

| 模式 | 入场链 | SMC 真实度 |
|---|---|---|
| 突破系统（旧） | Structure_break → Entry(immediate) | 30% |
| POI 回撤（新） | Structure_break → POI_retrace(touch zone) → Entry | 80% |
| 完整 SMC（未实现） | Sweep → Structure_break → POI_retrace → Confirm_Candle → Entry | 100% |

## 代码关键位置

- `daily_scan.py` 的 `scan_last_bars()` 函数
- 搜索 `bar_touching_zone` 找到 Phase 2 逻辑
- `had_retrace=True` 是新的 metadata 字段

## 适用场景

适合所有"触发事件 → 等待回撤 → 在支撑位入场"的交易系统：
- SMC (Order Block / FVG / Breaker)
- 突破后回踩 (Breakout Pullback)
- 均线回踩 (Moving Average Retest)

**关键判断**：今日 bar 必须触碰支撑区，而不仅是价格接近。

## 历史数据回填

对于历史 V66 trades 的验证：
```python
for check_i in range(c.bar + 1, min(c.bar + 6, n)):
    bar_lo = float(klines[check_i].get('l', 0))
    bar_hi = float(klines[check_i].get('h', 0))
    if bar_lo <= zone_high and bar_hi >= zone_low:
        had_retrace = True
        break
```
