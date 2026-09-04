# V7.4 增强蜡烛形态检测 (2026-05-15)

## 覆盖的6种形态

### 1. Hammer (锤子线 / Pinbar_Bull)
- 收阳 (c > o)
- 下影 > 实体 × 2
- 下影 > 振幅 × 50%
- 上影 < 振幅 × 25%
- Entry: retrace到 low (zone_low), 测试支撑

### 2. Shooting Star (流星线 / Pinbar_Bear)  
- 收阴 (c < o)
- 上影 > 实体 × 2
- 上影 > 振幅 × 50%
- 下影 < 振幅 × 25%
- Entry: retrace到 high (zone_high)

### 3. Bullish Engulfing (吞没 / Engulf_Bull)
- 前一根阴线 (pb_c < pb_o)
- 当前阳线完全吞没前一根: c > pb_o AND o < pb_c
- zone: lower=min(l, pb_l), upper=max(h, pb_h)
- Entry: retrace到 zone_low

### 4. Bearish Engulfing (吞没↓ / Engulf_Bear)
- 前一根阳线
- 当前阴线完全吞没前一根

### 5. Bullish Harami (孕线上破 / Harami_Bull)
- 前一根大阴线
- 当前小阳线在前阴线内部: body < pb_body × 0.5
- o > pb_c AND c < pb_o
- Entry: retrace到 zone_low

### 6. Piercing Line (刺透 / Pierce_Bull)
- 前一根阴线
- 当前开低于前收 (o < pb_c)
- 当前收高于前中点 (c > (pb_c+pb_o)/2)
- c < pb_o (未完全吞没, 区别于Engulf)

## 检测位置

两个文件中的检测必须保持一致:

1. `/root/.hermes/scripts/smc_unified.py` — 前端K线图显示用
   - lines 115-173: build_v21() 中的内联检测
   - 使用 Signal() 对象

2. `/root/.hermes/scripts/v11/scan_LD_v6.py` — 扫描回测用
   - lines 38-72: detect_pinbars() 函数
   - 使用 Signal() 对象

## 入场规则

所有蜡烛形态均使用 retrace 入场 (等价格回调到 zone_low):
- RETRACE_SIGNALS = {OB_Bull, Pinbar_Bull, Engulf_Bull, Harami_Bull, Pierce_Bull}
- MAX_WAIT = 3 bar
- Hard SL = zone_low × 0.95

## 扫描集成

ZONE_TYPES = ['OB_Bull', 'FVG_Bull', 'Pinbar_Bull', 'Engulf_Bull', 'Harami_Bull', 'Pierce_Bull']

新增型与CTX(SSL/EQL/BOS/CHOCH/MSS)组合产生combo信号:
- Sweep_SSL→Engulf_Bull: 287个
- Sweep_SSL→Harami_Bull: 201个
- EQL→Harami_Bull: 162个
- BOS_Bull→Engulf_Bull: 120个

## 回测表现 (V7.4 MW3_SL0.95_ACT1.03_DIST0.02)

| Pattern | n | WR | avgPnL |
|---------|---|-----|--------|
| EQL→Harami_Bull | 11 | 100% | +5.97% |
| EQL→Pinbar_Bull | 27 | 100% | +5.20% |
| Sweep→Harami_Bull | 101 | 73.3% | +3.48% |
| MSS→Engulf_Bull | 16 | 75.0% | +3.16% |
| EQL→Engulf_Bull | 13 | 92.3% | +1.77% |
| Sweep→Engulf_Bull | 89 | 65.2% | +1.25% |
