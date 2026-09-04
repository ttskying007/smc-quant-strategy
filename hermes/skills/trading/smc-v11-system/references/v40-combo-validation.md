# V4.0 全量信号组合验证 (2026-05-14)

脚本: `combo_validation_v40.py`
数据: 4767只 × 204组合 × 3窗口(full/mid/recent) × 2周期(daily/60min)
输出: `smc_opt_v21/combo_validation_v40.json`

## 全局最佳组合 (跨所有股票聚合)

| 组合 | WR | N | 股票数 |
|------|-----|-----|--------|
| BOS_Bull+CHOCH_Bull+MSS_Bull | 97.5% | 396 | 109 |
| BOS_Bull+CHOCH_Bull | 97.4% | 576 | 152 |
| BOS_Bull+EQL | 97.1% | 243 | 66 |
| OB_Bull+BOS_Bear | 96.2% | 555 | 157 |
| BOS_Bull+OB_Bull | 96.0% | 1024 | 269 |
| CHOCH_Bull+Sweep_BSL | 94.9% | 831 | 223 |
| BOS_Bull+MSS_Bull | 94.3% | 3445 | 823 ← 最大覆盖 |

## 个股最佳组合 (4252只各有最佳)

84%股票的最佳是单信号上下文:
- FVG_Bear: 961只 (GlobalWR=90.7%)
- BPR: 734只 (GlobalWR=89.9%)
- Sweep_SSL: 477只 (GlobalWR=90.5%)
- BOS_Bear: 400只 (GlobalWR=91.9%)

仅16%股票需要多信号组合。

## 核心结论

1. 不同股票需要不同信号组合 — 单一信号不适用所有
2. 选股用S→D序列(95%三窗口一致), 入场确认用上下文组合
3. 全局聚合多信号WR更高, 但个股层面单信号覆盖更广
4. 日线>>60min (99% vs 86%)
