# V44 raw-zone 信号修复与止损分诊执行经验

## 触发场景
当用户指出“止损触发较多”并怀疑是 SMC 信号不准确、OB/FVG/结构点/组合方式/未到入场点位导致时，不要先调 WR/RR 或放宽过滤；先做信号同构与执行边界审计。

## 本次新增的耐用流程
1. **先写可执行任务书 + 验收标准 + 预期提升**，再开始修复。用户要的是自主全量执行，不是让用户选择方案。
2. **raw zone / display zone 强制拆分**：
   - 交易层只能使用 `raw_zone_low/raw_zone_high`。
   - 归一化/视觉 zone 只能用于前端展示。
   - 每笔 setup/trade 必须同时记录 raw 与 display 字段，并写 `trade_boundary: RAW_ZONE_ONLY`。
3. **新增 schema/归因模块优先于改策略参数**：
   - `smc_signal_schema.py`：统一 raw/display 字段与校验。
   - `smc_sl_attribution.py`：每笔止损归因。
4. **OB 修复要对齐 LuxAlgo 结构锚定法**：
   - OB 由 structure/pivot anchor 回溯切片产生，不是每根 candle forward 扫。
   - 保留 raw candle high/low 作为交易边界。
   - `displacement` 可做质量评分，不宜硬过滤最近端真实 OB。
   - high-volatility parsedHigh/parsedLow 修正用于选择 OB 候选，但交易边界仍保留 raw candle。
5. **FVG 保留原始 gap 边界**：
   - 记录 `raw_zone_low/high`、`gap_low/high`、`mitigation_type`。
   - 禁止用 normalized zone 反推交易边界。
6. **入场修复原则**：
   - 删除 FVG continuation chase 这类“未回到 raw zone 仍追入”的 fallback。
   - 如果确认 candle 已 wick 触及 raw zone 且收在 zone 上方，执行价应按 raw zone high 记录，而不是 chase close。
   - `next open` 只能在 raw zone 内或近 raw low 容忍内，不能伪装成真实 retest。
7. **止损修复原则**：
   - SL 以 raw zone 与 sweep/结构失效点派生。
   - 如果结构 SL 被最大风险 cap 截断，要记录 `sl_was_capped_to_max_risk` 与 `structural_sl_before_cap`，归因到 `STRUCTURAL_SL_TOO_WIDE_CAPPED`，不能把它误判为信号有效失败。
8. **全量验证不能只报 WR**：必须同时输出：
   - setup/trade 数量
   - `schema_checks.raw_display_split`
   - `schema_checks.raw_zone_present`
   - `exit_counts`
   - `sl_attribution.by_cause`
   - 按 zone/event 分层指标
   - 漏单漏斗：structure → sweep → zone → retrace → confirm → quality → entry → market/width gate → trade

## 验收标准
- 代码语法检查通过。
- 全量 4800+ 标的跑完，不抽样。
- 所有正式 trade 都有 raw/display 双字段。
- `raw_zone_low/high == zone_low/high`，display 字段不参与交易。
- `entry_price` 不高于 raw zone high（除非明确记录为不可用于正式交易的实验模式）。
- SL 归因中不再出现“只知道止损，不知道原因”。
- 如果交易量大幅下降但 SL 消失，要明确说明：这是机制正确性提升但覆盖率过低，下一步应做“正确性保持下的召回率修复”，不能直接宣称策略完成。

## 关键坑
- 只看 `n_trades`/WR 会误判：raw-zone 严格后可能只剩极少交易，WR 很好但覆盖不足。
- `TRAILING_STOP` 可能是盈利保护，不应算作普通 SL；归因应标为 `TRAILING_PROFIT_STOP`。
- `sl_count` 与 `sl_attribution.sl_trades` 的口径可能不同，最终报告要解释口径。
- `entry_from_limit_retouch()` 里任何 continuation fallback 都容易把“未到入场点位”伪装成有效入场。

## 文件锚点
- `/root/.hermes/scripts/v25/smc_signal_schema.py`
- `/root/.hermes/scripts/v25/smc_sl_attribution.py`
- `/root/.hermes/scripts/v25/smc_core_luxalgo_v34.py`
- `/root/.hermes/scripts/v25/smc_core_pine_like.py`
- `/root/.hermes/scripts/v25/v41_final_engine.py`
