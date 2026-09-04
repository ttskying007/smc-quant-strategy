# OB_Bull standalone WR=94.2% — the proof (2026-05-14)

## 全量验证

V11.2 8维度拆解, 4836只 × 全量回测:

| 策略 | WR | PnL | N |
|------|-----|-----|-----|
| Global + ALL zones | 79.1% | +1.09% | 60,384 |
| Global + OB_only | 94.0% | +2.58% | 15,738 |
| PerStock + OB_only | 94.2% | +2.59% | 13,198 |

OB-only vs ALL: +14.4% WR, +119% PnL

## 为什么OB_Bull不需要序列

V20 OB_Bull内部已有91% HH/HL/LL/LH摆动结构验证。
外部序列(LIQ→ZONE, CTX→ZONE)仅匹配5-23% OB_Bull且不提升WR。
序列对FVG_Bull有价值(71.9%→79.4%)但对OB_Bull冗余。

## OB_Bull vs FVG_Bull

| Zone | WR | SL率 | PnL |
|------|-----|------|-----|
| OB_Bull | 94.2% | 1% | +2.59% |
| FVG_Bull | 71.9% | 16% | +0.42% |

OB抗SL能力是FVG的16倍。

## 最优策略

```
OB_Bull出现 → T+1开盘买入 → SL=OB.lower×0.995 → TP=+3% → 5bar超时
```

不需要序列组合、趋势过滤、多周期确认。
