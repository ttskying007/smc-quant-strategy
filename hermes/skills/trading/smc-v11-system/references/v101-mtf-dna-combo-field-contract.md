# V101 MTF/DNA/多组合字段合同与前端验收

## 适用场景
当 SMC 生产层升级到 V101 或后续“多周期字段 + 每股 DNA + 多组合候选/生产白名单”架构时，必须用本页作为字段合同和验收清单，避免只看聚合胜率而遗漏前端/API空值。

## 关键合同

### 1. 生产池与候选池必须分离
- `PRODUCTION_COMBO_WHITELIST` 只允许已验证生产组合，例如 `REVERSAL_SSL_CHOCH_DEMAND_OB_STRUCTURAL_5R`。
- `CANDIDATE_COMBO_WHITELIST` 用于新组合候选，例如 `CONTINUATION_BOS_PULLBACK_STRUCTURAL`。
- `production_eligible_v101` 只能由生产白名单 + 生产门禁决定；候选门禁只写 `combo_candidate_eligible_v101`，不得污染生产池。

### 2. V101 每行必须具备的核心字段
多周期字段：
- `trend_tf`, `signal_tf`, `entry_tf`
- `weekly_state`, `daily_state`, `m60_state`
- `mtf_stage`, `mtf_trend_permission`, `mtf_conflict_state`

DNA字段：
- `smc_dna`
- `dna_preferred_behavior`
- `dna_effective_entry_mode`
- `dna_effective_combo`

组合合同字段：
- `combo_contract_key`, `combo_family`, `combo_contract`
- `production_whitelist_v101`, `production_eligible_v101`, `production_grade_v101`
- `combo_candidate_whitelist_v101`, `combo_candidate_eligible_v101`

前端/API字段：
- `pick_date`, `join_date`
- `zone`, `zone_type`
- `cost_line`, `smart_money_cost`
- `volatility_pct`

注意：`combo_candidate_gate_reason_v101` 可以作为审计说明字段，但如果非候选行本来为空，不应把它放进 active-pick 必填缺失统计，否则会产生伪缺失。

## 验收步骤
1. 修改合同层后先编译：`python3 -m py_compile v101_mtf_dna_combo_contract.py smc_daily_ops.py`。
2. 重跑 V101 合同层，检查：
   - 生产池数量与组合分布不被候选组合污染。
   - BOS_CONTINUATION 等候选池单独输出并统计。
   - 核心字段缺失总数为 0。
   - T+1 违规为 0。
3. 检查日报摘要字典不要有重复 key。Python 字典会后值覆盖前值，不报错，但会掩盖脏代码。可用 AST 扫描 literal duplicate keys。
4. API 验证必须覆盖 `/api/picks` 和 `/api/live-prices`：
   - `pick_date` / `join_date` 0 缺失。
   - `zone` / `zone_type` 0 缺失。
   - `cost_line` / `smart_money_cost` / `volatility_pct` 0 缺失。
5. 浏览器验收必须看两个页面：
   - `/monitor`：选股表显示“选股日期”“加入日期”，且 Zone、成本线、波动有值。
   - `/live`：实时表显示“选股日期”“加入日期”“成本线”“Zone”“波动”，不得出现空值/null/undefined。

## 已验证口径示例
- V101 生产池：59 笔，`REVERSAL_SSL_CHOCH_DEMAND_OB_STRUCTURAL_5R`，net WR 89.83%。
- V101 BOS_CONTINUATION 候选池：1528 笔，独立候选白名单，不进入生产池。
- `/api/picks` 与 `/api/live-prices` 字段缺失均为 0。
- `/monitor` 显示 `选股日期=05-27`、`加入日期=06-04`、`Zone=DEMAND_OB [9.17~9.23]`、`成本线=9.20`、`波动=0.65%`。
- `/live` 显示 `成本线=9.20`、`Zone=DEMAND_OB [9.17~9.23]`、`波动=0.65%`。

## Pitfalls
- 不要把候选组合直接加进生产白名单；先作为独立候选池统计。
- 不要只验证 `/api/summary`；本次问题出在选股页/实时页字段空值，必须验证 `/api/picks`、`/api/live-prices` 和浏览器渲染。
- 不要把“条件性审计说明字段”放进所有 active rows 的必填统计。
- `smc_daily_ops.py` 运行可能被旧版本全量子流程拖慢；若验证目标是 V101 字段合同，可以先独立验证 V101 产物、API、前端，再单独处理调度性能。