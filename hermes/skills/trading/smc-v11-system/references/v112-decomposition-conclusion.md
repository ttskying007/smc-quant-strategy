# V11.2 — 8维度拆解: 单信号 vs 序列 × OB vs ALL × per-stock vs global

## 结论: OB过滤是唯一显著因素

| 策略 | WR | PnL | Trades | TP率 |
|------|-----|-----|--------|------|
| Global+ALL_PATTERNS+ALL | 79.1% | +1.09% | 60,384 | 75% |
| Global+ZONE_ONLY+ALL | 79.0% | +1.09% | 45,632 | 75% |
| Global+ALL_PATTERNS+OB_only | 94.0% | +2.58% | 20,648 | 86% |
| Global+ZONE_ONLY+OB_only | 94.0% | +2.58% | 15,738 | 87% |
| PerStock+ALL_PATTERNS+ALL | 79.9% | +1.18% | 37,771 | 76% |
| PerStock+ZONE_ONLY+ALL | 78.7% | +1.08% | 34,623 | 75% |
| PerStock+ALL_PATTERNS+OB_only | 94.2% | +2.59% | 13,198 | 87% |
| PerStock+ZONE_ONLY+OB_only | 93.8% | +2.57% | 11,896 | 86% |

## 贡献度分解

- OB vs ALL: +15% WR ← 94%的改进来源
- PerStock vs Global: +0.2% WR
- Multi-pattern vs ZONE_ONLY: +0.0% WR

## 关键结论

1. OB_Bull单信号 = 所有复杂序列的等价替代
2. Per-stock自适应仅贡献0.2%，几乎可忽略
3. 81%股票最优模式是ZONE_ONLY
4. FVG_Bull在所有维度上都差于OB_Bull
5. 复杂组合（序列、自适应、多周期）的价值在于FVG_Bull的过滤
   如果直接用OB_Bull，就不需要这些复杂度
