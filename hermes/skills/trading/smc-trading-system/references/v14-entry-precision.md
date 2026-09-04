# V14 入场精度与信号组合全量扫描结果 (2026-05-15)

## 扫描矩阵: 40组配置

### 维度
- **5种信号组合**: OB_only / OB+Sweep / OB+CHOCH / OB+Breaker / OB+Pinbar
- **2种SL模式**: sl_fixed (ATR×1.2) / sl_capped (max 8%)
- **2种TP模式**: tp_atr (满仓4×ATR) / tp_swing (结构目标前高/前低)
- **2种入场方式**: zone_retrace (zone上沿入) / zone_bottom (zone底部精确入)

### 全量: 4,905只, zone过滤后~3,800只, age≤120

## 核心发现

### 1. 多信号组合全部劣于 OB_only

| 信号组合 | 交易笔数 | WR | 均盈 | RR |
|----------|----------|-----|------|-----|
| **OB_only** | **766** | **97.9%** | **+8.40%** | **1.33x** |
| OB+Sweep | 344 | 97.7% | +7.65% | 0.99x |
| OB+CHOCH | 720 | 97.5% | +8.12% | 1.08x |
| OB+Breaker | 766 | 97.9% | +8.40% | 1.33x |
| OB+Pinbar | 801 | 97.6% | +8.28% | 1.08x |

**结论**: Sweep/CHOCH/Pinbar在OB入场上下文中均降低RR。Breaker信号极少(实际等同OB_only)。
叠加信号=叠加虚假过滤, 消除正确入场机会但未消除假信号。

### 2. 入场位置是RR第一决定因素

| 入场方式 | RR | WR | 均盈 |
|----------|-----|-----|------|
| zone_retrace | 1.07x | 97.8% | +8.96% |
| **zone_bottom** | **1.33x** | 97.9% | +8.40% |

zone_bottom精确入场: RR提升24%, 均盈下降0.56pp(交易量从1,399降至766, 牺牲45%机会换RR)

### 3. SL capped 降低RR

| SL模式 | RR | 说明 |
|--------|-----|------|
| sl_fixed (ATR×1.2) | 1.33x | 动态SL, 尊重波动率 |
| sl_capped (max 8%) | 0.94x | 简单上限导致更多止损 |

capped SL导致更多止损出场——市场需要呼吸空间

### 4. tp_swing 无改善

tp_atr (固定ATR倍数) ≈ tp_swing (结构目标), 因trailing stop在结构目标触达前即激活。

## 最优配置 (V14)

```
信号: OB_only (单信号, 未击穿Demand Zone)
SL: sl_fixed = zone_low × (1 - ATR% × 1.2)
TP: tp_atr = entry + 4×ATR + 3×ATR trailing
入场: zone_bottom (精确zone底部入场, 不等待回撤)
zone年龄: ≤120
CHOCH: 不需要
```

**结果**: 766笔 / 644只 / WR=97.9% / 均盈+8.40% / RR=1.33x

## V13 vs V14 对比

| 指标 | V13 (zone_retrace) | V14 (zone_bottom) | 变化 |
|------|-------------------|-------------------|------|
| 交易 | 1,399 | 766 | -45% |
| 股票 | 1,083 | 644 | -41% |
| WR | 97.3% | 97.9% | +0.6pp |
| 均盈 | +11.31% | +8.40% | -2.91pp |
| RR | 1.43x | 1.33x | -0.10x |
| 稳定性 | 0.6pp | TBD | — |

V13 zone_retrace 综合优于 V14 zone_bottom (更多交易+更高均盈+更高RR)。
V14 zone_bottom 在理论入口更精确但牺牲交易量。
推荐保持 V13 zone_retrace 为基线, zone_bottom 作为可选精确模式。
