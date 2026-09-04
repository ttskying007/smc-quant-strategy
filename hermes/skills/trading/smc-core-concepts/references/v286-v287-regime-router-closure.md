# V286/V287 父级状态与同源 60min 生成器审计教训

## 触发场景

用户要求沿“按时间顺序发生 + 参数/周期/大小级别/股票 DNA 自适应”方向继续深入闭环。V285 已证明：每股历史 DNA 选择 V280 日线语法族不能稳定外推，2026 明显失效。因此本轮做两条新验证：

1. **V286**：用 entry 前一交易日市场/行业状态作为父级 router，walk-forward 选择 V280 日线时间顺序语法。
2. **V287**：不再拿日线 POI 反查 60min，而是从 60min 本身生成 sweep/reclaim/MSS/HL 结构，再映射到次日 T+1 交易，验证“同源低级别生成器”是否解决接管问题。

## 审计范围

- V286 脚本：`/root/.hermes/scripts/v25/v286_parent_regime_walkforward_selector.py`
- V286 摘要：`/root/.hermes/smc_audit/v286_parent_regime_walkforward_latest.json`
- V287 脚本：`/root/.hermes/scripts/v25/v287_same_source_60m_generator_audit.py`
- V287 摘要：`/root/.hermes/smc_audit/v287_same_source_60m_generator_latest.json`
- 输入：V280 全量 82,400 个日线分层时间顺序候选；60min 缓存覆盖 2025/2026 近端窗口。
- 市场/行业状态：只使用 `entry_date` 前一交易日的全市场/行业涨跌参与度；无同日收盘广度生产泄漏。
- 生产/前端/watchlist 写入：全部 false。
- focused ad-hoc verification：PASS；V286 selected rows、V287 generated events 均 T+1 违规 0；V287 无同日买卖退出。

## V286：年度 walk-forward 父级 regime router

测试：用过去年份训练 `市场/行业状态 → family/regime/risk/liq/range/vol/delay` 规则，再应用到未来年份。

基线测试期 2024-2026：

| n | WR | Avg | 2024 WR | 2025 WR | 2026 WR | SL% |
|---:|---:|---:|---:|---:|---:|---:|
| 70,556 | 47.33% | +0.68% | 46.00 | 51.31 | 40.17 | 40.47 |

V286 walk-forward：

| Selector | Grid | n | WR | Avg | 2024 | 2025 | 2026 | SL% | 结论 |
|---|---|---:|---:|---:|---:|---:|---:|---:|---|
| global_rule_set | strict_n150_wr58_avg15 | 7,562 | 52.76% | +1.45% | 56.85 | 53.71 | 47.20 | 28.19 | 最优综合；改善但不达生产 |
| parent_best_child | strict_n150_wr58_avg15 | 2,256 | 54.39% | +2.15% | 56.87 | 54.32 | 45.66 | - | 更精选，但 2026 仍弱 |
| global_rule_set | balanced_n100_wr56_avg10 | 11,594 | 52.52% | +1.38% | 57.33 | 53.87 | 44.47 | - | 覆盖更大但 2026 更差 |
| parent_best_child | loose_n50_wr54_avg05 | 5,337 | 58.65% | +3.06% | 64.93 | 51.60 | 42.98 | - | 高 WR 来自 2024，2026 失效 |

**结论**：市场/行业父级状态确实有效，能把基线 47.33%WR / 40.47%SL 改善到约 52.76%WR / 28.19%SL；但年度 walk-forward 仍无法解决 2026，不能生产。

### V286 诊断性非 walk-forward 口袋

这些只能说明方向，不可直接接生产：

| 条件 | n | WR | Avg | 年度 WR |
|---|---:|---:|---:|---|
| `RANGE + 市场上涨占比>=65 + 行业上涨占比>=65 + RANGE_LOW_SWEEP + LOW_VOL + RISK>=8` | 109 | 71.56% | +4.25% | 75.00 / 66.67 / 70.83 |
| `DOWN + MRET>=1 + IRET>=1 + UP_CONT_BOS_OB + RISK>=8` | 115 | 71.30% | +3.50% | 70.79 / 81.82 / 66.67 |
| `DOWN + MUP>=65 + IUP>=65 + UP_CONT_BOS_OB + LIQ>20 + RISK>=8` | 147 | 68.71% | +3.06% | 67.83 / 73.91 / 66.67 |
| `DOWN + MRET>=1 + IRET>=1 + REL -10~0 + ABSORB + RNG>=25 + RISK>=8` | 583 | 68.44% | +5.85% | 69.32 / 62.00 / 61.11 |

关键含义：**强市场 + 强行业 + 不过度领先/相对中性** 是有效父级状态；但年度学习仍会被 2026 regime shift 压制。

## V287：同源 60min 生成器

测试：不用 V280 日线 zone；直接从 60min 生成结构：

`前 5 个 60min 交易日低点 → 当日 SSL sweep → reclaim → micro MSS/BOS → hold/close strength → 次日开盘入场 → A股 T+1 日线 replay`

60min 数据限制：当前缓存主要覆盖 2025/2026，所以 V287 只能作为近端验证，不能代表 2023/2024 全周期结论。

### V287 全量结果

| n | 股票数 | WR | Avg | 2025 WR | 2026 WR | SL% | 结论 |
|---:|---:|---:|---:|---:|---:|---:|---|
| 88,095 | 4,235 | 38.26% | +0.13% | 39.36 | 37.76 | 60.22 | 原始 60min sweep 事件噪声极大 |

### V287 相对可用口袋

| 条件 | n | WR | Avg | 2025 | 2026 | SL% | 结论 |
|---|---:|---:|---:|---:|---:|---:|---|
| `TOUCH_NO_RECLAIM + STATE_DOWN + RISK2_4 + VOL1.2_2` | 1,711 | 62.36% | +2.32% | 64.29 | 62.09 | 36.88 | 近端最稳，但语义更像“下跌趋势恐慌探底反弹”，不是传统 reclaim takeover |
| `TOUCH_NO_RECLAIM + STATE_DOWN + RISK2_4` | 4,223 | 54.39% | +1.57% | 57.49 | 53.82 | 43.95 | 覆盖较大，质量中等 |
| `RECLAIM_NO_MSS + STATE_DOWN + RISK4_6 + VOL1.2_2` | 100 | 55.00% | +2.33% | 52.94 | 55.42 | 37.00 | 小样本弱可用 |
| `FULL_TAKEOVER + STATE_DOWN + RISK>=8 + VOL0.8_1.2` | 44 | 56.82% | +3.64% | 50.00 | 57.89 | - | 传统 takeover 并不突出 |

**关键反常发现**：传统预期中 `FULL_TAKEOVER` 应该最强，但 V287 里最稳的是 `TOUCH_NO_RECLAIM + STATE_DOWN + 中等风险 + 放量`。这说明 A股 60min 的有效模式可能不是“完美 reclaim/MSS 后追入”，而是**下跌状态中的流动性刺穿未收回，但次日资金反包/均值回归**。这更像恐慌释放后的 T+1 反弹，而不是标准 ICT takeover。

## 根因闭环

到 V287 为止，已排除/确认：

1. **机会不足已排除**：V280 日线 82,400 个机会，V287 60min 同源生成 88,095 个事件，机会都不少。
2. **固定时间窗口/顺序组合不足**：V278/V279/V280 大样本只能约 45%-49%。
3. **每股 DNA 不足**：V274/V285 walk-forward 均证明历史股票性格不稳定外推。
4. **市场/行业父级状态有效但不充分**：V286 最优 walk-forward 52.76%WR，2026 47.20%，仍不达标。
5. **同源 60min 传统 takeover 不是直接答案**：V287 全量 38.26%WR，`FULL_TAKEOVER` 不突出。
6. **新方向**：A股 T+1 下，低级别“恐慌释放/未收回 + 次日反包”可能比标准 ICT reclaim/MSS 更有效；但必须做更严格的 gap、次日开盘质量、市场/行业父级过滤和滚动验证。

## 下一步方向

不要继续扩大日线组合网格，也不要继续做 per-stock WR 白名单。下一步应做：

`V288 = V287 same-source 60min panic-release pocket + V286 market/industry parent state + gap/open execution quality + rolling walk-forward`

重点验证：

1. `TOUCH_NO_RECLAIM + STATE_DOWN + RISK2_4 + VOL1.2_2` 是否在 rolling/event-time 下仍稳定。
2. 是否必须叠加 `前日/信号日市场行业参与度` 才能过滤 SL。
3. 次日开盘 gap 是否决定成败：高开过大拒绝、低开承接、平开反包三类分桶。
4. 是否可以把 SL 从 36.88%-43.95% 继续降到可生产区间。

## 使用注意

- V286/V287 均为 no-write 研究，不得接生产。
- V286 非 walk-forward 高胜率口袋不可直接使用，只能作为方向。
- V287 60min 数据只有 2025/2026 近端覆盖，不可声称三年全市场生产结论。
- V287 的 `TOUCH_NO_RECLAIM` 语义与传统 ICT takeover 相反；后续必须逐笔复盘，确认不是 replay/SL/TP 口径造成的假阳性。
