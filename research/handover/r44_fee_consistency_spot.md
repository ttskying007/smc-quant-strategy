# R44: 现货费用语义抽查 (轻量 spot-check)

- 代码位置: research/paper_sim.py LL1616-1619 (TP1 部分) / LL1578-1585 (清仓)
- 模式: TP1 时 FEE×0.3, 清仓时 FEE×0.7, 合计恰好一次双边 FEE — 不双扣
- 卖出价: (1−SLIPPAGE) 一致
- 检查项: tp1_fee_x03 ✓ | fullclose_fee_rem ✓ | tp1_hit 轨道 ✓ | sell_slippage ✓ | single_fee_semantics ✓

**判定**: 通过 — 无需修改; 已记入要求成本单源化 (R42) 的补充证据
