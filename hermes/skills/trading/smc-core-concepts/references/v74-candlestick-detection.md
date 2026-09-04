# 增强蜡烛形态检测 (V7.4, 2026-05-15)

补充到 SMC core concepts 的 Pinbar 章节。V7.4 在日线OHLCV上实现6种蜡烛形态检测。

## 检测算法

所有形态在日线数据上检测 (起始于bar 20):

### 1. Hammer (锤子线/Pinbar_Bull)
```python
is_bull = c > o
lower_wick = o - l
upper_wick = h - c
if is_bull and lower_wick > body*2 and lower_wick > range*0.5 and upper_wick < range*0.25
```
意义: 空头打压失败，多头反击，长下影=支撑确认

### 2. Shooting Star (流星/Pinbar_Bear)
```python
not is_bull and upper_wick > body*2 and upper_wick > range*0.5 and lower_wick < range*0.25
```
意义: 多头推高失败，长上影=阻力确认

### 3. Bullish Engulfing (吞没/Engulf_Bull)
```python
prev_bear = pb_c < pb_o
current_bull = c > o
engulfs = c > pb_o and o < pb_c
```
意义: 空头完全被多头吞没，强反转信号

### 4. Bullish Harami (孕线/Harami_Bull)
```python
prev_bear = pb_c < pb_o
small_body = body < pb_body * 0.5
inside = o > pb_c and c < pb_o
```
意义: 空头动能衰竭，空孕=反转前兆

### 5. Piercing Line (刺透/Pierce_Bull)
```python
prev_bear = pb_c < pb_o
gap_down = o < pb_c
close_above_mid = c > (pb_c+pb_o)/2
not_full_engulf = c < pb_o
```
意义: 开盘跳空低开后强势收回，介于Harami和Engulf之间

## 入场模式
所有蜡烛形态使用 retrace entry (类比OB):
- 等价格回调到形态下沿 (zone_low)
- MAX_WAIT = 3 bars
- Hard SL = zone_low × 0.95
- Trail激活 = entry_price × 1.03
- Trail距离 = 2%

## V7.4 回测表现
| Pattern | n | WR | avgPnL |
|---------|---|-----|--------|
| OB_Bull | 1,560 | 91.7% | +8.44% |
| EQL→Harami_Bull | 11 | 100% | +5.97% |
| EQL→Pinbar_Bull | 27 | 100% | +5.20% |
| Sweep→Harami_Bull | 101 | 73.3% | +3.48% |
| MSS→Engulf_Bull | 16 | 75.0% | +3.16% |

Harami_Bull在所有形态中表现最佳(WR=100%)，但样本量小(11笔)。
Engulf_Bull/Engulf_Bear量最大但WR中等(50-65%)，需要强CTX上下文过滤。
Pierce_Bull信号量适中，WR=71-86%表现稳健。
