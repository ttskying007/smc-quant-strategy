# V502–V516 本地纯结构研究前沿闭环

适用于用户要求在不依赖外部数据的前提下，继续寻找 A 股 SMC 新方向并回测胜率、收益与盈亏比时。目标不是无限枚举变体，而是区分“新本体机制”与“旧机制调参”，并在证据充分时正式停止。

## 固定研究纪律

1. 仅使用本地可复现 OHLCV/K线；不把无法获得的外部分钟、Tick、盘口、资金流作为后续前提。
2. 每个方向必须先冻结本体语义并生成 outcome-blind seeds，字段中不得含 PnL、exit、MFE、MAE 等结果信息。
3. 独立 raw-bar oracle 必须逐笔重导 swing、BOS/CHOCH、POI、touch、reclaim、hold 与 entry 时序。
4. 通过支持门槛后只允许一次固定执行回放：次日开盘、严格 T+1、串行单股持仓、预先冻结 SL/TP/time/fee。
5. 生产准入至少要求：`n>=300`、每年 `n>=40`、总体和逐年期望均为正、PF/盈亏比过线、T+1=0。
6. 支持不足时不得放宽窗口或阈值凑样本；经济失败后不得改 SL、TP、年份、市场状态或窗口重新包装为“新方向”。

## 已完成的新本体方向

| 本体 | n | Gross WR | AvgNet | Payoff | PF | 关闭原因 |
|---|---:|---:|---:|---:|---:|---|
| SSL-created Bear IFVG | 50,401 | 60.7270% | +0.5034% | 0.7863 | 1.2158 | 2023 AvgNet/PF 为负 |
| Weekly SSL Rejection Block Transfer | 37,514 | 56.8055% | +0.5351% | 0.9479 | 1.1932 | 2023、2026负收益 |
| Internal Inducement Sweep | 6,066 | 74.3983% | +0.0744% | 0.4436 | 1.0414 | 2023、2024负收益；小赢大亏 |
| Double SSL Absorption | 23,531 | 74.0767% | +0.2180% | 0.4677 | 1.1078 | 2023负收益；payoff<0.5 |
| Daily Two-sided Purge | 9,719 | 57.4648% | +0.1969% | 0.8166 | 1.0758 | 2023、2026负收益 |
| Weekly BOS Demand Transfer | 57,038 | 66.8905% | +0.3769% | 0.5925 | 1.1233 | 2023、2024负收益 |
| Weekly Breaker Transfer | 50,605 | 68.1889% | +0.3668% | 0.5641 | 1.1224 | 2023、2026负收益 |
| Weekly IFVG Support | 27,827 | 58.9607% | +0.1387% | 0.7601 | 1.0433 | 2023、2026负收益 |
| Weekly BOS Context → Daily SSL | 7,387 | 64.1262% | +0.1247% | 0.6237 | 1.0407 | 2023、2024、2026负收益 |

最后的独立方向 `Weekly BSL→SSL two-sided purge → Daily CHOCH/OB` 全市场 4,897 股只得到 51 个完整信号（2023/2024/2025/2026 分别 6/10/19/16），未达到总数300、每年40的支持门槛，因此不打开收益结果、不放宽条件，直接关闭。

## 结构性诊断

当前瓶颈不是信号数量或因果时序，而是稳定的“小赢大亏”分布：不少方向表面 WR 达 68%–74%，但平均亏损约 -8% 至 -10%，平均盈利约 +3% 至 +6%，导致 payoff 仅 0.44–0.59；同时至少一个年份为负期望。用年份、行情状态、窗口、SL或TP过滤这些失败会重新进入结果驱动筛选，不是新 SMC 信息。

## 可复现闭环与缺失产物修复

关闭结论必须由当前环境可重跑的 registry audit 证明，不能只引用旧报告。若汇总脚本因独立 metric artifact 缺失而失败：

1. 从对应 frozen replay 的逐笔 CSV 重新计算 overall、yearly、exit reasons。
2. 检查 chronology、duplicate symbol-entry、serial overlap、T+1、search_count。
3. 要求重算指标与 frozen report 完全一致。
4. 重建缺失的 `*_independent_metric_audit_latest.json` 后，再运行总 registry closure。
5. 只有 registry 全部为 true 才可宣布研究完成。

V501 就是此模式：从 V500 的 50,605 笔 closed rows 独立重算，overall/yearly/exit reasons 全部 exact match，chronology/duplicate/overlap/T+1 均为0，然后 V516 registry 才重新通过。

## 停止条件

当 daily、weekly、cross-security、liquidity、breaker、IFVG、inducement、absorption、two-sided purge 等已定义本体全部满足以下条件时，正式停止：

- 每个已回放方向均经济失败或逐年稳定性失败；
- 最后未回放方向在 outcome-blind 阶段即支持不足；
- registry 中未关闭方向数为0；
- 没有一个新的、非 timeframe/context/threshold/entry/exit 变体的因果本体。

正式状态（仅对价格/结构/时间框架/上下文纯结构空间）：`CURRENT_LOCAL_OHLCV_PURE_STRUCTURE_RESEARCH_COMPLETE__ZERO_ALL_YEAR_PROMOTION_PASS__STOP_STRATEGY_ITERATION`。

**后续证据更新（2026-07-16）**：成交量—价格 effort/result absorption 是与上述空间不同的日线OHLCV信息维度，不是该关闭结论禁止的 threshold/timeframe/context/entry/exit 变体。V517–V520 已以 outcome-blind→Oracle→单次冻结T+1→独立指标回放验证通过（387笔，WR 63.5659%，AvgNet +0.9588%，PF 1.4146，四年度正、T+1=0）；V522为 research-promotable，V523只在生产外做精确次日开盘 shadow。生产BUY仍未准入：post-close日线不能事后把D1开盘补填成真实成交，需独立实时开盘链路后才可讨论生产放行。

此时后续工作不能回到已关闭的价格结构变体；允许继续的是这个新成交量—价格本体的严格前瞻shadow运行与执行链路因果验证。