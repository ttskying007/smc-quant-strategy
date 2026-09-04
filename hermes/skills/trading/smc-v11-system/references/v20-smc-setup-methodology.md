# V20.2 SMC Setup — 流动性→结构→POI 完整方法论

## 问题诊断

全量4800回测发现, 所有基于"信号窗口内集合"的组合过滤方法都劣于Baseline:
- 固定序列模式(Sweep→CHOCH→FVG→OB): WR降0.6pp, 交易减95%
- 自由组合上下文: WR降0.6-3pp, 无一超越Baseline
- 看跌上下文+OB_Bull: WR降3pp

根因: **信号组合未尊重时间顺序, 且缺少流动性扫描和POI概念**。

## SMC标准的做多入场流程

ICT/SMC 理论中的完整做多Setup:

```
1. Demand Zone形成: 价格在一个支撑区域内(OB_Bull或FVG_Bull) — 这是机构建仓区
2. SSL Sweep: 价格下穿Demand Zone → 扫掉多头止损 → 机构吸收流动性
3. CHOCH_Bull: 价格反转上穿LH → 结构转换 → 确认趋势改变
4. POI入场: 价格回测Demand Zone → 进入"兴趣点" → 入场
```

关键: **Demand Zone必须在Sweep之前形成**, 这样Sweep才是"扫过建仓区"而非随机穿刺。

## 检测算法实现

```python
def detect_smc_setups(signals, ohlcv):
    # Long: Demand Zone → SSL Sweep → CHOCH_Bull → POI
    # Short: Supply Zone → BSL Sweep → CHOCH_Bear → POI
    
    for sw in sweeps_ssl:
        # 1. Find CHOCH_Bull within 30 bars after sweep
        # 2. Find Demand Zone (OB_Bull/FVG_Bull) formed BEFORE sweep (within 20 bars)
        # 3. Verify zone price is near swept level (ATR*1.5)
        # 4. Entry at demand zone bar (zone IS the POI)
```

代码: `/root/.hermes/scripts/v11/signals_v20.py` — `detect_smc_setups()`

## 全量4800结果

| 指标 | Baseline | SMC Setup |
|------|----------|-----------|
| WR | 72.7% | **87.1%** |
| PnL/笔 | +2.11% | **+3.52%** |
| TP率 | 72% | **87%** |
| Setup数 | — | 2,697 (1313多+1384空) |
| 交易数 | 14,196 | 1,732 |

## 为什么SMC Setup有效

1. **时间顺序至关重要**: Demand Zone先形成 → 然后被穿刺 → 然后结构转换 → 这个顺序确保交易在真正的"机构猎杀"之后入场
2. **流动性扫描是必要条件**: 没有Sweep的入场 = 没有流动性事件 = 机构未参与
3. **POI入场 = 最优价格**: 入场在Demand Zone本身, 而非随机FVG/OB
4. **结构转换确认趋势**: CHOCH确保不是死猫反弹

## 已知限制

1. Setup稀疏: 仅25%股票有Setup, 平均3.4个/只有Setup的股票
2. CHOCH仍为瓶颈: 每只2.7个CHOCH, 限制了Sweep→CHOCH配对
3. 做空Setup同样有效但验证较少

## 相关文件

- `/root/.hermes/scripts/v11/signals_v20.py` — detect_smc_setups()
- `/root/.hermes/scripts/v11/smc_setup_backtest.py` — SMC Setup回测
- `/root/.hermes/scripts/v11/free_combo_mining.py` — 自由组合挖掘(对比分析)
- `/root/.hermes/scripts/v11/per_stock_mining.py` — 个股差异分析
- `/root/.hermes/scripts/v11/combo_filter_backtest.py` — 组合过滤回测
