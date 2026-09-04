# V287 60min-first 同源 SMC 生成器审计

## 触发场景

V284 证明：用日线候选/日线 POI 再反查 60m sequence，不能救信号质量，`FULL_TAKEOVER` 只有约 42% WR。V286 又证明父级市场/行业历史 fit 选择器在 2026 失效。因此下一步验证同源多周期方向：先在 60m 内生成 sweep → reclaim → MSS 的 POI，再映射到日线 T+1 执行，而不是从日线 zone 倒推低级别确认。

## 审计范围

- 脚本：`/root/.hermes/scripts/v25/v287_60min_first_smc_generator.py`
- 摘要：`/root/.hermes/smc_audit/v287_60min_first_smc_generator_latest.json`
- 产物：`/root/.hermes/smc_audit/v287_60min_first_smc_generator_no_write_20260703_153902/`
- 输入：`/root/.hermes/kline_cache_60min` 与 `/root/.hermes/kline_cache` 中 60min 500 bars 缓存；日线 750 bars 用于 next-day T+1 replay。
- 覆盖：60m cache 近期为主，仅 2025/2026，不能代表完整 2023/2024。
- 生产/前端/watchlist 写入：全部 false。
- T+1：0 违规。

## 60m-first 语义

1. 在 60m 上寻找前 20 根低点下破 `sweep_depth >= 0.25%`。
2. 同一根 60m 收回前低之上，确认 reclaim。
3. 之后 0-4 根 60m 内收盘突破局部 8 根高点，确认 micro MSS。
4. POI/SL 直接来自这次 60m sweep wick，而不是日线 OB/FVG。
5. 信号日之后的下一日开盘入场，日线 T+1 出场 replay，TP=1.5R，max_hold=10。

## 全量结果

| 范围 | N | 股票数 | WR | Avg | 2025 WR | 2026 WR | SL | TP | T+1违规 |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| 60m-first 全部 | 5,001 | 2,955 | 47.93% | +0.82% | 48.74 | 47.63 | 40.81% | 36.61% | 0 |

## Family 结果

| Family | N | WR | Avg | 2025 | 2026 | 说明 |
|---|---:|---:|---:|---:|---:|---|
| 60M_FAST_TAKEOVER | 1,366 | 50.95% | +1.08% | 57.14 | 48.82 | 比日线反查 60m 明显稳定，但未达生产 |
| 60M_SAMEBAR_TAKEOVER | 259 | 48.26% | +1.15% | 53.03 | 46.63 | 样本少，SL 高 |
| 60M_SLOW_TAKEOVER | 3,376 | 46.68% | +0.69% | 45.29 | 47.22 | 质量普通 |

## 二级诊断口袋

| 口袋 | N | WR | Avg | 年度 WR | 说明 |
|---|---:|---:|---:|---|---|
| 60M_FAST_TAKEOVER + DAILY_LOW + RISK6_8 | 92 | 64.13% | +2.84% | 2025 68.00 / 2026 62.69 | 最稳定方向，但样本偏少 |
| 60M_FAST_TAKEOVER + DAILY_LOW + RISK4_6 | 211 | 54.98% | +1.63% | 2025 65.15 / 2026 50.34 | 样本稍大但 2026 边缘 |
| 60M_FAST_TAKEOVER + DAILY_LOW + sweep 0.5-1% | 245 | 55.92% | +1.37% | 2025 62.35 / 2026 52.50 | 可继续研究 |
| 60M_FAST_TAKEOVER + DAILY_LOW + gap -2~0% | 320 | 58.44% | +1.63% | 2025 71.54 / 2026 50.25 | 2026 不够 |

## 结论

1. 同源 60m-first 方向优于“日线 POI 反查 60m”：整体 2026 WR 从 V284 的 `FULL_TAKEOVER` 约 42% 提高到 V287 全部 47.63%，FAST 子族 48.82%。
2. 但它仍未达到生产预期；SL 仍约 40.8%，说明单个 60m sweep/reclaim/MSS 不是充分的资金接管确认。
3. 真正有希望的局部方向是 `60M_FAST_TAKEOVER + DAILY_LOW + 中等风险 6-8%`，2025/2026 都超过 62%，但样本只有 92，不能接生产。
4. 下一步应沿着这个局部方向继续：加入 second-leg HL hold / retest 成功、60m 成交量接管、前日市场/行业参与度、gap 执行质量，验证能否在保持 2026 稳定的同时把样本提高到生产级。

## 使用注意

- V287 受 60m 缓存限制，只能证明 2025/2026 方向，不是完整 3 年全市场结论。
- V287 是研究脚本，不得接生产。
- 后续若要生产化，必须先扩充 60m 历史缓存到至少 3 年，再做 walk-forward/月度稳定性验证。