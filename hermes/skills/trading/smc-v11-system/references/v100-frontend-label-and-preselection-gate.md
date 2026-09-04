# V100 前端壳层与选股前置门禁验收补充

## 触发场景

当 V100 已成为生产数据源，但 `smc_unified.py` 仍保留 `ACTIVE_VERSION='V88'` 作为历史路由外壳时，前端页面、summary/docs/analysis/backtest 可能继续显示旧版本标识，容易让用户误判生产口径。

## 关键结论

- V100 的 `<0.8% 小盈利污染` 修复必须是**选股阶段前置门禁**，不是回测结束后删除结果。
- 核心证据应同时检查代码与报告：
  - `v100_structural_net_gate.py` 顶部 contract：`Filter by structural RR/quality BEFORE a row enters the active selection pool`。
  - `v100_tier()`：先判断 `V98_A + TP2_R>=5 + TP3_R>=8 + expected_tp2_net>=0.8% + weak_environment`，再返回 `A_PRODUCTION_CORE`。
  - `normalize_row()`：只有 `tier == 'A_PRODUCTION_CORE'` 才设置 `is_active_pick=True` / `pick_scope='ACTIVE_CANDIDATE'`。
  - `v100_report.json.selection_contract` 必须包含 `pre-selection gate, not post-backtest deletion`。
- 前端版本标识修复不要贸然把 `ACTIVE_VERSION` 改成 `V100`；旧代码中很多数据路由仍依赖 `version == 'V88'` 来优先读取 V100 trades/picks/report。
- 安全模式：新增显示层变量，例如 `FRONTEND_VERSION = 'V100' if v100_report exists else ACTIVE_VERSION`，所有页面标题/nav/docs/analysis/backtest/monitor/live 使用 `FRONTEND_VERSION`；内部 `ACTIVE_VERSION` 继续作为数据路由外壳。

## 最小修复步骤

1. 在修改 `smc_unified.py` 前，做 GitNexus impact/detect-changes；若 CLI 索引无法识别脚本函数，仍需记录结果并继续做最小变更。
2. 保留 `ACTIVE_VERSION='V88'` 链路；新增 `FRONTEND_VERSION` 显示变量。
3. 替换可见页面文本：`SMC {ACTIVE_VERSION}`、dashboard/backtest/monitor/analysis/docs 标题改为 `SMC {FRONTEND_VERSION}`。
4. 不替换 API 错误消息和内部执行分支中的 `ACTIVE_VERSION`，这些仍用于路由与兼容。
5. 重启 8890 服务后验证：
   - `/api/summary`: `engine=V100_STRUCTURAL_NET_5R_GATE`, `version=V100`, `total_trades=59`（或当前报告值）。
   - `/api/picks` 与 `/api/live-prices`: `pick_date/join_date/zone_type/zone/cost_line/volatility_pct` 缺失数为 0。
   - `/`, `/monitor`, `/live`, `/docs`, `/analysis`, `/backtest`: 页面含 `SMC V100`，不含 `SMC V88`。
   - `py_compile smc_unified.py v25/v100_structural_net_gate.py` 通过。

## 给用户的回答口径

用户问“这是选的时候剃除，还是回测结束后剔除？”时，直接答：

> 是选股阶段前置门禁剔除，不是回测后删除结果。V100 在 `v100_tier()` 中计算结构 TP/SL、TP2/TP3 RR、TP2 预期净收益，并在进入 active production picks 之前过滤；报告中的 `selection_contract` 也写明 `pre-selection gate, not post-backtest deletion`。

用表格列出验证结果，避免长篇解释。