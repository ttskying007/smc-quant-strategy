# V102 选股/实时/K线字段合同同步教训

## 触发场景
用户要求在选股页增加 `选股日期`、`加入日期`，并修复下方引擎 `zone` 空值、实时页 `成本线` 和 `波动` 空值。

## 核心教训
- 前端字段修复不能只改页面 HTML 表头或局部渲染；必须同时验证 API 数据合同、页面动态 JS 渲染和浏览器实际 DOM。
- `/monitor` 与 `/live` 字段正常后，还要检查 `/api/kline_full` 的 `trade_list.append()` 白名单构造；K线页 trade 标识会在这里丢失 DNA/组合合同/MTF 等字段。
- K线页标题/版本 badge 若从 Python f-string 中嵌 JS 字符串，警惕 `{FRONTEND_VERSION}` 被双花括号或普通字符串污染成字面量；优先从 API 返回 `frontend_version`，JS 用 `d.frontend_version || d.version || ver`。
- 静态 HTML 包含关键词不代表动态页面正确；必须用浏览器读取实际表格行/合同块，确认不是脚本源码里的字符串。

## 最小修复路径
1. 统一用 `_apply_smc_field_contract()` 回填 `pick_date`、`join_date`、`zone_low/high`、`cost_line`、`volatility_pct`、`zone`、`engine`。
2. 在选股页/实时页渲染层显示：`选股日期`、`加入日期`、`Zone`、`成本线`、`波动`、`DNA`、`组合合同`。
3. 在 `_api_kline_full()` 的 `trade_list.append()` 里透传：`dna_preferred_behavior`、`symbol_dna_mode`、`combo_contract_key`、`combo_role`、`combo_mtf_permission`、`mtf_permission`、`daily_structure_state`、`production_eligible_v102`、`v102_balanced_volume_gate`。
4. `/api/kline_full` 响应增加 `frontend_version`，K线 JS badge 使用 API 值，避免硬编码。
5. 重启 8890 后验证 API 和 DOM：
   - `/api/picks`、`/api/live-prices` 目标字段缺失计数必须全部为 0。
   - `/api/kline_full?symbol=...` 的第一笔 trade 必须含日期、zone、cost、volatility、DNA、combo。
   - 浏览器实际访问 `/monitor`、`/live`、`/kline?s=...`，确认表格行非空且无 `{FRONTEND_VERSION}` 字面量。

## 验收样例
- 选股页：`选股日期=20260527`、`加入日期=20260604`、`Zone=DEMAND_OB [9.17~9.23]`、`成本线=9.20`、`波动=0.65%`。
- 实时页：`成本线=9.20`、`Zone=DEMAND_OB [9.17~9.23]`、`波动=0.65%`。
- K线页：标题显示 `V102`，合同块显示 `REVERSAL_SPECIALIST` 与 `REVERSAL_SSL_CHOCH_DEMAND_OB_STRUCTURAL_5R`。
