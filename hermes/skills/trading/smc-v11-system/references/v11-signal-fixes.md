# V11.2 信号引擎修复 (2026-05-09)

## 背景

V36结构性SL/TP引擎(WR=84.0%, RR=3.09x, PF=24)基础上, 信号检测引擎本身有9个问题。修复后WR=86.0%, RR=3.46x, PF=30。

## 修复详情

### 1. FVG — C2实体要求 + 趋势对齐收紧

**问题**: 震荡市中FVG误报率太高。中间K线(C2)可以是极小的spinning top(实体<0.1%), 这种FVG在震荡市被频繁触发。

**修复**:
- C2实体 >= ATR * 60% 才视为有效FVG
- 趋势对齐阈值从1%收紧到0.5%

**代码位置**: signals_v11.py, detect_fvg_v11()函数, lines 207-208

### 2. OB — 完全重写为ICT OrderBlock

**问题**: 旧OB检测逻辑是"阴线后阳线=反转"(类似经典的吞没形态), 不是真正的ICT OrderBlock。

**修复**: True ICT OrderBlock = 趋势中最后一只与趋势方向相反的K线, 之后有2+ impulse:
- Bullish OB: 上涨趋势中的最后一只阴线
- Bearish OB: 下跌趋势中的最后一只阳线
- 必须有2根连续同向K线确认impulse

**代码位置**: signals_v11.py, detect_ob_v11()函数, lines 660-790

### 3. Sweep — 时间窗口过滤at_swing

**问题**: `_near_swing()`使用`swing_highs[-5:]`取全局最后5个摆动点, 导致以下问题:
- 用800根K线前的摆动点来确认当前的Sweep
- 摆动点应该在时间上接近Sweep才有意义

**修复**: 改为检查当前K线前后8根K线内的摆动点:
```python
def _near_swing(idx, price, is_high, window=8):
    # 只检查 idx-window 到 idx+window 范围内的摆动点
    for sh_idx, sh_price in swing_highs:
        if abs(sh_idx - idx) <= window and abs(price - sh_price) / max(sh_price, 0.01) < 0.005:
            return True
```

### 4. LiquidityVoid — 真正的跳空缺口

**问题**: 旧逻辑检测"宽幅低量K线"作为流动性真空, 这不是ICT定义。

**修复**: 检测连续K线之间的价格gap:
- Bullish gap: bar['l'] > prev['h'] (向上跳空)
- Bearish gap: bar['h'] < prev['l'] (向下跳空)
- 仅排除价格在ATR 0.3%以下的微小gap

### 5. MSS/CHOCH — 层级区分

**问题**: MSS和CHOCH检测高度重叠, 使用相同的摆动点逻辑, 两者之间没有明确层级区分。

**修复**:
- MSS: local_window=3 (微观预警), strength上限4, 标记为micro_structure
- CHOCH: 使用摆动点级别(lookback=12-20), 标记结构转换
- 新增 MSS-meso (local_window=6, 中间层)

### 6. IFVG/BPR/BreakerBlock — 动态评分

**问题**: strength全部硬编码为5.0, confidence硬编码为0.6。所有IFVG强度相同。

**修复**: strength和confidence基于原始FVG/CHOCH信号动态计算:
```python
strength = min(7.0, 3.0 + fvg.get('strength', 3.0) * 0.5)
confidence = min(0.7, 0.4 + fvg.get('confidence', 0.5) * 0.3)
```

### 7. OTE — 区间支持

**问题**: 只检测精确61.8%斐波那契回撤位, 实际价格很少精确到达。

**修复**: 支持0.5-0.68区间, 量缩验证:
- 价格到达区间内即算OTE
- 成交量萎缩 = 加分(趋势衰竭信号)
- 在区间内出现反转K线 = 确认

### 8. PO3 — ATR自适应ACC

**问题**: ACC(accumulation)范围固定3%价格范围, 高波股票易过, 低波股票难过。

**修复**: 
- ACC范围 = 1倍ATR百分比
- 高波ATR>3.5%: ACC范围~4%
- 低波ATR<1.5%: ACC范围~1.5%

## 验证

200只随机股票回测:
```
V36修复前: WR=84.0%, RR=3.09x, PF=24, P&L=+2.08%, 868 trades
V36修复后: WR=86.0%, RR=3.46x, PF=30, P&L=+2.41%, 829 trades
```

关键变化: 交易减少4.5%(从868->829)但WR提升2%, RR提升12%, PF提升25%。
