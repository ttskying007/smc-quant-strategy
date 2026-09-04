# V2.0 多周期选股系统 — 最终结果

## 数据覆盖

- 日线: 4800只 (缓存在 /root/.hermes/kline_cache/*_daily_300.json)
- 60min: 4551只 (腾讯ifzq API下载, 15线程并行, /root/.hermes/kline_cache/*_60min_500.json)
- 周线: 东方财富API下载 (klt=102) + 日线合成fallback. 缓存于kline_cache/*_weekly_200.json (1125只真实+其余合成). 腾讯m120不是周线(120分钟).
- 有效序列: 1607只 (有周线SMC趋势 + 日线序列组合)

## 周线SMC趋势判断

从日线合成周线后, 用V20信号引擎检测:
- CHOCH_Bull/Bear + BOS_Bull/Bear 数量对比
- 最近一个CHOCH的方向
- 最新摆动结构标签 (HH/HL/LL/LH)

趋势分类: bullish (看涨趋势), bearish (看跌趋势), neutral (无明确方向)

## 日线序列组合

6种模式 (3 long + 3 short):
- L→D: 流动性扫荡 → 需求区入场
- S→D: 结构突破 → 需求区入场  
- L→S→D: 流动→结构确认→需求区入场
- 对应的short版本 (供给区)

检测: 信号三分类(LIQUIDITY/STRUCTURE/ZONE), 按时间顺序匹配, 去重

## 回测验证

目标: 序列出现后5bar内涨幅≥2%

| 趋势 | L→D | S→D | 总股票 |
|------|-----|-----|--------|
| bullish | 154 (48%) | 166 (52%) | 320 |
| bearish | 116 (89%) | 14 (11%) | 130 |
| neutral | 397 (65%) | 216 (35%) | 613 |

- bullish+L→D avg rate=91%, bullish+S→D avg rate=96%
- bearish+L→D avg rate=85%
- neutral patterns avg rate 89-94%

## 窗口稳定性

full→recent对比 (≥5样本的模式):
- stable: 36% (命中率波动<5pp)
- improved: 18%
- degraded: 45%

结论: 模式效果随时间变化大, 需定期重新评估 (建议每周/每月更新数据库)

## 60min集成

数据已下载但尚未在序列检测中使用。下一步: 当日线序列触发时, 在60min数据中寻找精确入场点。

## 文件清单

| 文件 | 说明 |
|------|------|
| /root/.hermes/scripts/v11/multi_tf_v2_final.py | 主分析引擎 |
| /root/.hermes/scripts/v11/stock_signal_matrix.py | 个股信号效能矩阵 |
| /root/.hermes/scripts/v11/smc_sequence_engine.py | 序列策略引擎 |
| /root/.hermes/smc_opt_v21/multi_tf_db_v2.json | 个股数据库 |
| /root/.hermes/smc_opt_v21/stock_signal_matrix.json | 信号效能矩阵 |
