# V287-V289 时间顺序/父级状态/同源60m闭环审计

## 触发场景

当用户要求继续深入研究“按时间顺序发生、参数自适应、股票 DNA、大/小周期组合”的方向时，不能只继续调 `BOS lookback / SSL window / wait / risk`。需要按以下顺序关闭分支：

1. 父级市场/行业 regime 是否能选择 SMC story family；
2. rolling selector 是否能 walk-forward 到下月；
3. daily zone 反查 60m 失败后，是否同源 60m-first 生成能解决；
4. 若仍不达标，根因不是“机会少”，而是 operator lifecycle / 真实资金接管语义缺失。

## V287：父级 market/industry regime × rolling selector

脚本：`/root/.hermes/scripts/v25/v287_regime_conditioned_rolling_selector.py`

产物：`/root/.hermes/smc_audit/v287_regime_conditioned_rolling_latest.json`

设计：
- 输入 V280 82,400 条全市场 time-ordered candidates。
- 对每条候选补入场前一交易日 market/industry participation。
- 用 prior-window 训练，仅预测 next-month。
- no-write，不写 production/frontend/watchlist。

结果：

| Selector | N | WR | Avg | 2024 | 2025 | 2026 |
|---|---:|---:|---:|---:|---:|---:|
| parent_180d_n80_wr58_avg1_top20 | 4,076 | 46.22 | +0.40 | 39.64 | 49.73 | 40.62 |
| parent_360d_n120_wr56_avg1_top30 | 4,595 | 43.92 | +0.32 | 39.32 | 48.68 | 40.81 |
| parent_540d_n180_wr54_avg1_top40 | 5,803 | 46.82 | +0.50 | 46.65 | 51.53 | 38.94 |
| parent_360d_n80_wr60_avg2_top20 | 1,313 | 48.97 | +1.05 | 56.84 | 48.54 | 42.72 |

结论：父级 market/industry participation 能在**描述性后验 surface**中产生高质量口袋（例如 `MRET>=1|IRET>=1|UP_CONT_BOS_OB|DOWN|RISK>=8` 约 71% WR），但 rolling next-month 不能稳定外推。说明 regime 方向有信息，但现有 rolling 规则选择器仍是历史表现追随，不是状态识别器。

## V288：同源 60m-first 生成器

脚本：`/root/.hermes/scripts/v25/v288_same_source_60m_first_generator.py`

产物：`/root/.hermes/smc_audit/v288_same_source_60m_first_latest.json`

设计：
- 不再用 daily zone 反查 60m。
- 直接在 60m 上生成：`SSL sweep → reclaim → micro MSS → same-source 60m bearish-candle POI → next daily open entry`。
- 日线出场严格 T+1，从 entry 后下一日开始检查 TP/SL。
- 本地 60m cache 约 4553 只、500 bars，主要覆盖 2025/2026；因此不是完整 2023-2026 结论。

结果：

| Best variant | N | WR | Avg | 2025 | 2026 | T+1 |
|---|---:|---:|---:|---:|---:|---:|
| rr1.2_h20_risk6 | 1,434 | 52.86 | +0.51 | 52.63 | 52.95 | 0违规 |

说明：同源 60m-first 比 V284 daily-zone overlay 更一致，但仍远低生产要求。根因不是“daily/60m 不同源”这一项单独造成，而是 60m sweep/MSS/last bearish candle POI 仍过于通用，不能识别真正 operator takeover。

## V289：60m-first + market/industry participation overlay

脚本：`/root/.hermes/scripts/v25/v289_60m_first_participation_overlay.py`

产物：`/root/.hermes/smc_audit/v289_60m_first_participation_overlay_latest.json`

结果：

| Surface | N | WR | Avg | 2025 | 2026 | 月度最低 |
|---|---:|---:|---:|---:|---:|---:|
| rel_ret=REL_-10_0 | 455 | 57.14 | +0.87 | 60.00 | 55.94 | 35.94 |
| M_UP>=65 & I_UP50_65 | 41 | 65.85 | +1.43 | 66.67 | 65.71 | 样本太小 |
| VOL>=2 & M_RET>=1 & I_RET>=1 | 67 | 61.19 | +0.99 | 70.00 | 59.65 | 样本太小 |

结论：participation 能提高 60m-first 的稳定性，但月度低谷仍明显，且可用样本偏小。不能生产。

## V290：operator lifecycle overlay

脚本：`/root/.hermes/scripts/v25/v290_operator_lifecycle_overlay.py`

产物：`/root/.hermes/smc_audit/v290_operator_lifecycle_overlay_latest.json`

设计：
- 在 V288 same-source 60m-first rows 上补 pre-entry lifecycle 证据：
  - accumulation compression：sweep 前 20 根 60m range；
  - manipulation：sweep depth；
  - takeover：MSS impulse；
  - post-MSS hold：同日后续 60m 是否守住 POI。
- 仍然 no-write，只做研究分桶。

结果：

| Surface | N | WR | Avg | 2025 | 2026 | 月度最低 |
|---|---:|---:|---:|---:|---:|---:|
| ACC_WIDE>=7 + shallow sweep + weak impulse | 124 | 65.32 | +1.60 | 75.00 | 61.96 | 45.45 |
| MAN_TAKEOVER_NO_ACC + R4_6 | 105 | 56.19 | +1.14 | 57.14 | 55.84 | 42.86 |
| HOLD_STRONG>=1 | 1,155 | 53.68 | +0.66 | 54.68 | 53.26 | 42.19 |

结论：operator lifecycle 特征确实能把局部口袋抬到 65% WR，但最优口袋样本只有 124 且月度最低仍 45.45，不可生产。更重要的是，最优口袋并不是“标准 ACC→MAN→TAKEOVER”，而是 `宽波动 + 浅扫 + 弱突破`，说明当前 lifecycle proxy 仍在捕捉行情状态/波动形态，不是真正的操盘生命周期。下一轮若继续，必须用更原生的数据定义 lifecycle（更长历史 60m/15m、盘口/竞价/成交额持续性、板块内领涨扩散），而不是继续在 500 bars 60m cache 上切桶。

## 总闭环结论

V278-V290 已经连续验证：

1. **机会不少**：V280 有 82,400 条，交易量少是门禁筛掉低质机会，不是原子事件少。
2. **固定时间顺序参数无效**：V278/V279 最佳仍远低生产。
3. **股票 DNA 不能直接外推**：V274/V285/V286 均失败，rolling 也不够。
4. **父级 market/industry regime 有信息但不能靠历史规则追随生产**：V287 后验有强口袋，walk-forward 不稳。
5. **同源 60m-first 能提升一致性但不够**：V288/V289 最好大样本约 53-57% WR，仍离生产目标远。

因此下一步如果继续，不能再做同类参数/过滤/历史最优规则选择；必须重建“操盘生命周期”状态机：

`Market/Industry Regime → Stock Operator Lifecycle(Accumulation/Manipulation/Distribution) → Active POI family → Rhythm shift → Same-source 60m/15m takeover → Daily execution`

关键不是“选择哪个历史表现好的规则”，而是**在入场前识别这只股票当前是否处于被资金接管的生命周期阶段**。

## 验证

Focused ad-hoc verification PASS：
- import V287/V288/V289 scripts；
- no-write flags；
- V287 source rows/selectors；
- V288 best rows and T+1=0；
- V289 overlay consistency。

注意：这是专项验证，不是完整 canonical test suite green。
