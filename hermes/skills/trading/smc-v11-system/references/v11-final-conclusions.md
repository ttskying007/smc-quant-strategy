# SMC V11 全量研究最终结论 (2026-05-14)

## 数据覆盖
- 日线: 4905只 (腾讯ifzq公开API)
- 周线: 4830只 (Hubble+腾讯双源)
- 60min: 4551只 (腾讯ifzq)
- 数据源: 腾讯ifzq (公开) > Hubble (需Key:123456) > 东方财富 (SSL问题)

## 全量迭代路径

| 版本 | 核心改动 | WR | 结论 |
|------|---------|----|------|
| V7.0 | 13种序列模式全量 | 80.3% | LIQ→ZONE最优 |
| V8.0 | Per-stock自适应 | 80.3% | +0.2% vs Global |
| V9.0 | 动态SL+60min共振 | 75.3% | 紧SL最优 |
| V10.0 | 失败+滚动窗口 | - | FVG SL 56% vs OB 18% |
| V11.1 | OB-only过滤 | 94.2% | **最大突破** |
| V11.2 | 拆解分析 | - | OB唯一主导 |

## 最优策略
OB_Bull→T+1开盘买→SL=OB.lower×0.995→TP=+3%→5bar超时
WR=94.2% PnL=+2.59% 覆盖94%股票

## 关键文件
- signals_v20.py: V20信号引擎
- stock_dna_v11.json: 4832只DNA
- ob_only_v111.json: OB对比
- decompose_v112.json: 8维度拆解
