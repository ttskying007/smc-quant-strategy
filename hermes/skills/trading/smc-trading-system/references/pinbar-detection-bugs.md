# Pinbar Detection: 4 Code-Level Bugs (2026-05-15)

**位置**: `/root/.hermes/scripts/v11/scan_LD_v6.py` 行38-53 `detect_pinbars()`

## 当前代码

```python
def detect_pinbars(daily):
    for i in range(20, len(daily)):
        b = daily[i]; o, h, l, c = b['o'], b['h'], b['l'], b['c']
        if c <= o or h == l: continue          # Bug 1
        body = c - o; range_hl = h - l
        lower_wick = o - l; upper_wick = h - c
        # Strict Hammer
        if lower_wick > body * 2.5 and lower_wick > range_hl * 0.6 \
           and upper_wick < range_hl * 0.15:   # Hammer conditions
            if c > (o + l) / 2:                # Bug 2
                results.append(Signal('Pinbar_Bull', i, 'bull', 
                                      lower=l, upper=c, price=c))
    return results
```

## Bug 1: `c <= o` 跳过阴线Pinbar (行45)

```python
if c <= o or h == l: continue  # ← 跳过所有 bearish-body candles
```

真正的Pinbar下影极长但实体可以是阴线（close < open，即bearish-body hammer）。在A股市场中，很多有效Hammer的实体是阴线（收盘略低于开盘但远高于最低价）。

**修正**: 移除 `c <= o` 条件，用绝对body大小判断。
```python
body = abs(c - o)  # 用绝对值
if h == l: continue  # 仅跳过一字线
```

## Bug 2: 收盘位置判断错误 (行51)

```python
if c > (o + l) / 2:  # ← 收盘在上半部？
```

`(o + l) / 2` 是开盘和最低价的中点，不是K线的上半部。Pinbar的关键特征是收盘接近**最高价**，不是接近开盘+最低价的中点。

**示例**: o=10.0, l=9.0, h=10.5, c=10.1
- `(o+l)/2 = 9.5` → c=10.1 > 9.5 ✓ 通过
- 但 c=10.1 离 h=10.5 差4%，这不是Pinbar（长上影）

**修正**: 
```python
if c > h - range_hl * 0.3:  # close在最高价30%以内
```

## Bug 3: 无PD Array上下文 (缺失)

SMC Pinbar必须出现在PD Array（OB/FVG）处才有意义。孤立的Pinbar只是随机K线形态，无SMC含义。

**修正**: 传入all_signals检查Pinbar bar附近是否有OB或FVG。
```python
def detect_pinbars(daily, all_signals):
    ob_fvg_bars = {s.idx for s in all_signals if 'OB' in s.type or 'FVG' in s.type}
    ...
    if i in ob_fvg_bars or any(abs(i - b) <= 2 for b in ob_fvg_bars):
        results.append(...)
```

## Bug 4: 缺失Shooting Star (看跌Pinbar)

只检测Hammer（看涨），无Shooting Star（看跌）。做空方向完全无Pinbar确认。

**修正**: 添加对称的Shooting Star检测：
```python
# Shooting Star: long upper wick, small lower, close near low
if upper_wick > body * 2.5 and upper_wick > range_hl * 0.6 \
   and lower_wick < range_hl * 0.15:
    if c < l + range_hl * 0.3:  # close near low
        results.append(Signal('Pinbar_Bear', i, 'bear', upper=h, lower=c, price=c))
```

## 更致命的问题: Pinbar在V477中完全缺失

V477引擎使用 `signals_v20.py` 做信号检测，但 `signals_v20.py` 中**完全没有Pinbar检测代码**（grep count = 0）。V477全量2124笔交易100%为OB_Bull。

Pinbar仅在 `scan_LD_v6.py` 中检测（V7.6日线系统），且该文件中明确标注：
```
ZONE_TYPES = ['OB_Bull', 'FVG_Bull']  # Pinbar is entry confirmation at PD Array, not standalone zone
```

即Pinbar仅用于可视化，不参与信号生成。所以当前系统中Pinbar完全不产生交易信号。

## 修正优先级

1. Fix Bug 1+2（消除假阳性，当前识别出的"Pinbar"大部分不准确）
2. Fix Bug 3（添加上下文，过滤孤立的无效Pinbar）
3. Add Bug 4（Shooting Star，做空方向需要）
4. 考虑是否应该让Pinbar参与信号生成（当前纯装饰）
