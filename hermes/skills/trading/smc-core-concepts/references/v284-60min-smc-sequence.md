# V284 60min SMC 子结构序列审计教训

## 触发场景

V283 使用前一交易日 60min 的粗特征（收益、收盘位置、简化 MSS）后，最优大样本仍只有约 56%WR，说明不能用“60min 收强”替代 SMC 接管语义。V284 进一步检测 60min 内部时间顺序：`zone/SSL touch -> reclaim -> micro MSS/BOS -> HL hold/retest`。

## 审计范围

- 脚本：`/root/.hermes/scripts/v25/v284_60min_smc_sequence_audit.py`
- 最新摘要：`/root/.hermes/smc_audit/v284_60min_smc_sequence_latest.json`
- 输入：V280 全量 82,400 个日线分层语法事件。
- 可覆盖 60min 前日窗口：17,294 个事件（4553 个 60min 缓存文件，主要覆盖 2025/2026）。
- 防未来函数：只使用 `entry_date` 前一交易日的 60min K线；不使用买入日盘中/收盘数据。
- 生产/前端/watchlist 写入：全部 false。

## 60min 序列定义

在买入日前一交易日的 60min 内检测：

1. `NO_ZONE_TOUCH`：未触碰日线 demand zone。
2. `TOUCH_NO_RECLAIM`：触碰/跌破 zone 后未收回 `zone_low`。
3. `RECLAIM_NO_MSS`：收回 zone，但未突破触碰前高点形成 micro MSS/BOS。
4. `MSS_THEN_FAIL`：MSS 后又收盘跌回 zone_low 下方。
5. `MSS_HOLD_NO_RETEST`：MSS 后不破，但没有足够 retest/强收盘。
6. `FULL_TAKEOVER`：touch/reclaim/MSS 后维持不破，并出现 retest hold 或强收盘。

## 核心结果

| 60min 序列 | n | WR | Avg | SL% | 年份 | 结论 |
|---|---:|---:|---:|---:|---|---|
| `FULL_TAKEOVER` | 4,786 | 42.00% | +0.017% | 49.64% | 2025/2026 | 低质量，不是生产确认 |
| `NO_ZONE_TOUCH` | 9,139 | 42.83% | +0.039% | 44.11% | 2025/2026 | 未触碰并不更差，说明日线 zone 与前日60m错位 |
| `RECLAIM_NO_MSS` | 3,094 | 40.27% | -0.016% | 53.30% | 2025/2026 | 单纯 reclaim 无效 |
| `TOUCH_NO_RECLAIM` | 159 | 30.19% | -1.579% | 67.92% | 2026 | 明确坏信号 |
| `MSS_THEN_FAIL` | 18 | 11.11% | -3.984% | 83.33% | 2026 | 明确坏信号但样本小 |

最优大样本组合：`REV_SSL_CHOCH_OB|RANGE|NO_ZONE_TOUCH|RISK4_6`，n=101，WR=52.48%，Avg=+0.921%，仍远低生产标准。

## 结论

1. **真正 60min touch→reclaim→MSS 序列没有提升质量**：`FULL_TAKEOVER` 只有 42%WR，说明当前日线候选的 zone 并不是可交易的 60min 接管区域。
2. **低级别确认不是缺失的唯一环节**：即使补上前日 60min 子结构，仍不能把日线时间语法变成高胜率系统。
3. **失败根因指向“日线候选/POI锚点语义错配”**：当前 V280 的日线 zone 可能是事件标签或回测区域，但不是 lower timeframe 上的真实 smart-money 接管 POI。
4. **可用负面门禁**：`TOUCH_NO_RECLAIM` 和 `MSS_THEN_FAIL` 明显坏，适合做研究诊断/剔除，但样本覆盖小，不能单独作为生产系统。
5. **下一步不应继续叠加粗特征**：需要重建候选生成器，使日线 POI 与 60min 子结构同源生成；或者补齐历史 60min 后从 60min 直接生成事件，再聚合到日线，而不是拿日线 zone 去套前日 60min。

## 使用注意

- V284 是 no-write 研究审计，不得接生产。
- 60min 缓存只有近端约 500 根，不能代表 2023/2024。
- 如果后续做 V285，应改为 **同源多周期生成**：先在 60min 识别 sweep/reclaim/MSS/HL，再映射到日线 POI/趋势，而不是从日线事件反查 60min。
