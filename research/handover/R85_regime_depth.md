# R85 — 熊市持续时间分层 + 市场宽度(基于 index 全历史)
bear_streak = 入场日往前, 上证连处于 bear regime 的连续 bar 数

## A. 熊市持续时间分层(bear_streak 桶)
| bear_streak (bar) | n | v22 avg | v22 PF | v24 avg | v24 PF |
|---|---|---|---|---|---|
| 非熊市 | 1406 | 4.33 | 3.69 | 6.1 | 6.58 |
| 熊<15bar(早期) | 382 | 1.63 | 1.69 | 2.44 | 2.1 |
| 熊15-30(加速) | 70 | 12.22 | 22.43 | 14.93 | 41.08 |

## B. 大盘宽度(全市场 close>MA20 的比例)
说明: 用缓存 2947 只会全计算太贵. 采样 N=120 只 ETF/+随机组合, 生成周宽度表.

### B1. 入场日广度桶 × 结果
| 广度 % (上证20MA上方股票比例) | n | v22 avg | v22 PF | v24 avg | v24 PF |
|---|---|---|---|---|---|
| <30% (极弱) | 525 | 1.63 | 1.69 | 3.41 | 2.86 |
| 30-50% (弱) | 400 | 4.11 | 3.36 | 5.23 | 4.64 |
| 50-70% (中) | 339 | 5.61 | 4.15 | 7.36 | 7.07 |
| ≥70% (强) | 594 | 5.33 | 5.8 | 7.04 | 10.95 |

## D. S15 反事实: 熊市加速段(bear_streak 15-30) 入场 ×1.25
| v24 | avg | PF |
|---|---|---|
| 当前 S1-S14 | 5.89 | 5.89 |
| 加 S15(熊加速段×1.25) | 5.95 | 5.96 |

## C. R86: 生产挂单影子标签审计
带 v23 标的订单: **2/146** (2026-09-21 起才有标签)

| code | 信号日 | 状态 | weight | flags |
|---|---|---|---|---|
| 002633 | 2026-09-23 | PENDING_ORDER | 0.21 | s1_choch:CHoCH↑<br>s5_risk_lt5<br>s7_up_trend |
| 301656 | 2026-09-22 | PENDING_ORDER | 0.42 | s5_risk_lt5<br>s6_whale_x1 |

带 Jev 判定的订单: 10
| code | kind | conf |
|---|---|---|
| 600860 | bottom_accumulation | - |
| 603040 | bottom_accumulation | - |
| 601633 | bottom_accumulation | - |
| 300408 | bottom_accumulation | - |
| 300789 | bottom_accumulation | - |
| 300307 | bottom_accumulation | - |
| 000157 | bottom_accumulation | - |
| 300808 | bottom_accumulation | - |
| 002633 | false_signal | - |
| 301656 | bottom_accumulation | - |