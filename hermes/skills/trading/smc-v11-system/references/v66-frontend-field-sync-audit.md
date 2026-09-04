# V66 前端字段端到端同步验收教训

## 触发场景
用户要求修复选股页/实时页字段空值后，不能只验证目标页面显示；SMC 前端类修复必须做端到端字段合同闭环验收。

## 核心教训
- 选股页和实时页显示正常，不等于数据层/K线/回测/分析/复盘/文档全部同步。
- `smc_unified.py` 里常见运行时兜底会让页面看起来正常，但底层 JSON 可能仍然缺字段。
- `/api/live-prices` 可能只输出驼峰字段（如 `pickDate/costLine/volClass/zoneType`），页面可用，但其它脚本/API 复用需要同时检查蛇形字段合同。
- K线页 `/api/kline_full` 是独立数据链路，可能仍使用旧信号字段 `type/upper/lower`，没有同步 `zone_type/zone_low/zone_high/cost_line/volatility_pct`。
- `/backtest`、`/analysis`、`/autopsy`、`/docs` 不会自动继承 `/monitor` 和 `/live` 的字段修复，必须单独验收。

## 必做验收矩阵
1. 页面显示：`/monitor`、`/live` 目标列是否显示非空。
2. API 合同：`/api/picks`、`/api/live-prices` 是否输出页面字段和可复用字段。
3. K线同步：`/api/kline_full?symbol=...&ver=...` 的 `signals_list/trades` 是否带统一字段。
4. 数据物理文件：对应版本的 `*_picks.json`、`*_trades.json`、daily candidates、monitor positions、trade ledger 是否物理补齐字段。
5. 其它页面：`/backtest`、`/analysis`、`/autopsy` 是否能展示或消费同一字段合同。
6. 文档结构：`/docs` 或对应 reference 是否记录字段来源、运行时兜底、物理数据合同、页面/API 覆盖范围。

## 判定标准
- 只能说“目标页面修复完成”：当 `/monitor` 和 `/live` 显示正常，但数据/K线/其它页面/文档未同步。
- 只有同时通过页面、API、K线、物理 JSON、回测、分析、复盘、文档验收，才能说“端到端同步完成”。

## 常见遗漏字段
- 日期：`select_date`、`pick_date`、`join_date`、`entry_date`
- Zone：`zone_type`、`zone_low`、`zone_high`、`dz_low`、`dz_high`
- 成本线：`cost_line`、`smart_money_cost`、`v25_cost_line`
- 波动：`volatility_pct`、`v25_atr_pct`、`v25_vol_class`、`vol_class`
- 引擎/来源：`engine`、`definition_version`、`source`
