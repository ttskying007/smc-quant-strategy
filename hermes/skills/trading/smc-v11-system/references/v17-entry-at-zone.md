# ENTRY_AT_ZONE — SMC入场架构关键突破

## 发现

CLOSE入场 vs ZONE入场的回测对比(200只):

| 指标 | CLOSE | ZONE | 提升 |
|------|-------|------|------|
| WR | 42.8% | **94.2%** | +51.3pp |
| Avg P&L | +0.51% | **+4.66%** | +4.15% |

## 根因

CLOSE入场时价格已从结构位(FVG.lower)上移。最近的结构支撑在0.1-0.5%下方 → 87.5%被击穿率(V500发现)。

## 方案

1. **入场价 = FVG.lower / OB.lower** (结构位本身)
2. **SL = 入场价下方最近的结构支撑** (多源: FVG/OB/swing_low/CHOCH/BOS/EQL/SSL)
3. **TP = 入场价上方最近的结构阻力** (多源: FVG_top/OB_top/swing_high/CHOCH/BOS/EQH/BSL)
4. **质量评分过滤**: SL距离 + TP数量 + 信号强度 → score≥3.0

## 全量4800结果 (V17 + ENTRY_AT_ZONE)

- 42,123 trades | WR 97.0% | Avg P&L +6.11%
- TP hit: 91.0% | SL hit: 3.0% | Trailing: 5.9%
- SL来源: FVG=44% CHOCH=18% BOS=13% OB=12% EQL=8% SSL=6%

## 文件

- `structure_zones_v17.py` — 多源TP/SL结构扫描器
- `v17_backtest_engine.py` — ENTRY_AT_ZONE完整回测
- `v18_dashboard.py` — 仪表板可视化
- `smc_opt_v17/v17_backtest_4800.json` — 全量结果
