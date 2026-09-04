# V102 前端字段合同重执行与动态渲染验收

## 触发场景
- 用户报告选股页字段未完成：缺 `选股日期`、`加入日期`。
- 选股页/实时页字段为空：`engine`、`zone`、`成本线`、`波动`。
- K线页或实时页是 JS 动态渲染，源码/API 看起来已修但页面仍显示旧内容。

## 最小修复路径
1. 先确认字段合同入口：统一经 `_apply_smc_field_contract()` 回填 `pick_date`、`join_date`、`zone`/`zone_low`/`zone_high`、`cost_line`/`smart_money_cost`、`volatility_pct`、`dna_preferred_behavior`、`combo_contract_key`。
2. 选股页 `/monitor`：表格列和合同摘要都必须显示 `选股日期`、`加入日期`、`Zone`、`成本线`、`波动`、`DNA`、`组合合同`。
3. 实时页 `/live`：API `/api/live-prices` 和前端行渲染都要检查；不要只验证 HTML 模板静态文本。
4. K线页 `/kline`：标题版本必须来自 `/api/kline_full` 返回的 `frontend_version`，避免把 `{FRONTEND_VERSION}` 当 JS 字面量输出。
5. K线 API `/api/kline_full` 的 `trade_list` 必须透传合同字段：`pick_date`、`join_date`、`zone_type`、`zone_low`、`zone_high`、`cost_line`、`volatility_pct`、`dna_preferred_behavior`、`combo_contract_key`、`engine`。

## 验收脚本要点
- API 检查：`/api/summary` version/engine；`/api/picks` 和 `/api/live-prices` 统计关键字段空值；`/api/kline_full?symbol=<当前选股>&tf=daily&ver=V88` 检查首条 trade 的合同字段。
- 浏览器检查：实际打开 `/monitor`、`/live`、`/kline?s=<当前选股>`，确认动态表格单元格可见，而不是只看源码字符串。
- 若源码已修但浏览器仍旧：优先怀疑 8890 旧进程未重启。编译通过后杀旧进程，用 Hermes 受管后台进程启动，再做健康检查。

## 经验教训
- 对前端字段问题，不能只说“已补字段”；必须 API + 浏览器动态渲染双验收。
- K线页最容易漏：它依赖 `/api/kline_full` 的异步 JSON，不是只改 `build_kline()` HTML。
- 运行服务不要用 shell 级 `nohup ... &`；在 Hermes 中用受管 background process 启动，再单独跑 readiness/API 验证。
