# V101 多组合合同闭环复盘

## 何时使用
当 SMC 系统出现“前端能显示，但合同不完整、API 丢字段、候选/生产混淆、DNA 覆盖不足、或日报与页面口径不一致”时使用。

## 这次沉淀的关键教训
1. **嵌套状态不等于合同完成**
   - `weekly_state` / `daily_state` / `m60_state` 只是中间结构。
   - 如果要做机器审计，必须再导出扁平字段：
     - `weekly_trend_state`, `daily_trend_state`, `m60_trend_state`
     - `weekly_phase`, `daily_phase`, `m60_phase`
     - `weekly_permission`, `daily_permission`, `m60_permission`
     - `weekly_conflict`, `daily_conflict`, `m60_conflict`
     - `weekly_structure_state`, `daily_structure_state`, `m60_structure_state`

2. **DNA 不能只覆盖有交易样本的股票**
   - 如果只按 `trades` 聚合，DNA 覆盖会少于全市场缓存数。
   - 正确做法：用交易样本生成行为画像；对无样本股票，再用 K 线缓存补出一个 `WATCH_ONLY` / `NO_VALIDATED_SAMPLE` DNA 占位。
   - 覆盖率验收要对齐缓存股票总数，而不是交易数。

3. **BOS 延续必须独立成候选组合**
   - `CONTINUATION_BOS_PULLBACK_STRUCTURAL` 必须单独统计。
   - 不能混进反转生产池，也不能靠前端隐藏来“假装不存在”。

4. **组合合同要同时下发到数据和 API**
   - 交易行应带：`combo_entry_rule` / `combo_wait_rule` / `combo_sl_rule` / `combo_tp_rule` / `combo_production_gate`
   - 实时接口也必须透传这些字段，否则前端验收会通过但 API 审计仍然缺口。

5. **验证顺序固定**
   - 先跑脚本产物，确认 `field_missing_* == 0`
   - 再查 `/api/picks` 与 `/api/live-prices`
   - 最后看浏览器表格与控制台，确认没有 `undefined` / `null` / `NaN`

## 推荐检查清单
- 产物报告中 production / candidate / BOS 候选彼此隔离
- `v101_symbol_dna.json` 数量与缓存股票数一致
- active rows 与 candidate rows 的 field contract 都为 0 缺失
- `/api/live-prices` 不仅有价格字段，也有合同字段
- 前端页面只显示来自最新产物的字段，不靠旧缓存凑值
