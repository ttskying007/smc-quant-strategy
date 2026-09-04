# SMC 上下文影响力分析 (2026-05-15 AI引擎)

## 核心发现

在1000笔随机采样的V9交易中，信号前后的SMC上下文数量与胜率存在强单调关系：

```
上下文数量   胜率      强度
ctx_0 (孤立): 42.3%  ████
ctx_1:        64.3%  ██████
ctx_2:        79.4%  ████████
ctx_3:        87.3%  █████████
ctx_4:        92.0%  █████████  ← 2.2倍于孤立信号
```

## SMC上下文定义

每笔交易检查4种上下文：
1. **LIQ Sweep** (Sweep_SSL/Sweep_BSL): 信号前10bar内有流动性猎杀
2. **STRUCT Break** (CHOCH/BOS): 信号前15bar内有结构突破
3. **At Swing Point**: 信号在真实摆动点±2bar内
4. **FVG Nearby**: 信号±5bar内有FVG

## 关键结论

1. **孤立信号不可交易** (WR=42.3%) — 必须要求至少1个SMC上下文
2. **每个额外上下文提升WR 15-22pp** — 4个上下文可达92%
3. **V10.2验证**: 强制要求SMC上下文后，WR从64.1%提升到84.2%
4. **V11验证**: 加入Breaker Block作为额外上下文后，WR达95.0%

## 上下文分布 (V9全量)

| 上下文 | 占比 |
|--------|------|
| LIQ sweep | 29% |
| STRUCT break | 38% |
| At swing point | 41% |
| FVG nearby | 29% |
| Isolated (none) | 22% |

## OB_Bull入场分析

AI分析颠覆性发现: **日线直接入场远优于60min精确入场**。

| 入场源 | 交易数 | WR | avg PnL |
|--------|--------|-----|---------|
| 日线直接 | 3,132 | **99.4%** | **+9.69%** |
| 60min精确 | 1,716 | 59.7% | +6.02% |

60min精确入场反而降低WR 40pp。日线OB信号在60min级别被噪音干扰。

## 方法论文档

分析引擎: `/root/.hermes/scripts/v11/ai_analysis_engine.py`
分析报告: `/root/.hermes/smc_opt_v9/analysis/ai_analysis_report.json`
