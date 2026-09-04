# V66 字段合同与前端同步验收教训

## 适用场景

当 SMC 生产版本出现前端列为空、API 字段为空、K线信号表旧 schema、选股/实时/回测/分析/复盘/文档不同步时，按本流程处理。典型症状：选股页缺“选股日/加入日”，实时页“成本线/波动”为空，K线 API 只有 `type/upper/lower` 旧字段，或者物理 JSON 缺 `zone_type/cost_line/volatility_pct`。

## 核心做法

1. 先对要改的页面/API入口跑 GitNexus impact analysis；高风险入口先汇报 blast radius，低风险入口可继续手术式修改。
2. 不要在每个页面散落兜底逻辑；抽一个统一字段合同函数，例如 `_apply_smc_field_contract(row, default_engine)`。
3. 统一合同至少覆盖：
   - 日期：`select_date`, `pick_date`, `join_date`, `entry_date`, `signal_date`
   - Zone：`zone_type`, `zone_low`, `zone_high`, `dz_low`, `dz_high`
   - 成本线：`smart_money_cost`, `cost_line`, `v25_cost_line`
   - 波动：`volatility_pct`, `v25_vol_class`
   - 引擎/信号：`engine`, `signal_type`, `conf_type`
4. 接入面必须全覆盖：`_normalize_pick_scope`、`/api/live-prices`、`/api/kline_full`、`/monitor`、`/live`、`/backtest`、`/analysis`、`/autopsy`、`/docs`。
5. 前端显示修复不等于完成；生产物理 JSON 也要补齐落盘，并保留 `.bak_TIMESTAMP` 备份。
6. 重启 8890 后用 HTTP 脚本验收，不只看浏览器肉眼显示。

## 验收标准

- `/api/live-prices` 每条 pick 的 snake_case 字段 `select_date/pick_date/join_date/zone_type/zone_low/zone_high/cost_line/smart_money_cost/volatility_pct/engine` 均非空；数值字段不能为 0。
- `/api/kline_full?ver=生产版本` 的 signals 返回标准字段：`zone_type/zone_low/zone_high/cost_line/volatility_pct/signal_date/engine`。
- `/monitor /live /backtest /analysis /autopsy /docs /kline` 页面 HTML 均包含“选股日、加入日、Zone、成本线、波动”。
- 生产 JSON（如 `v66_trades.json`, `v66_picks.json`, `v66_daily_candidates.json`）上述合同字段 `missing=0`，关键数值 `zero=0`。
- `python3 -m py_compile smc_unified.py` 通过，8890 服务重启后 `/api/summary` 可访问。

## 常见坑

- 只补驼峰字段（如 `costLine`）会让页面能显示，但外部脚本和验收脚本读取 snake_case 时仍判空。
- 只改 `/api/live-prices` 不够；K线页面可能来自 `_api_kline_full` 的独立旧 schema。
- 只改前端表头不够；`rows += ...` 的单元格数量必须与表头同步。
- 只改内存兜底不够；生产 JSON 下次被别的脚本读取时仍会缺字段。
- GitNexus `detect-changes` 可能要求 git 仓库；如果目标目录不是 git 仓库，记录该限制，但仍要完成逐符号 impact analysis 与 HTTP/JSON 验收。

## Monitor Position 叠加到 K线 API 的字段传播

`_api_kline_full` 在叠加 durable_monitor_position 持仓时（约 line 4940），必须从 position data 显式提取以下字段并传入 `trades.append({...})`，否则 K线交易表显示为空：

- `zone_low`: pos or raw 的 zone_low / raw_zone_low / dz_low
- `zone_high`: pos or raw 的 zone_high / raw_zone_high / dz_high
- `cost_line`: pos or raw 的 cost_line / smart_money_cost，或 (zone_low+zone_high)/2 计算
- `volatility_pct`: pos or raw 的 volatility_pct / risk_pct
- `pick_date`, `select_date`, `join_date`: 从 raw_pick / pos 提取或 fallback 到 buy_date

**典型症状**: K线交易表显示 Zone="-", 成本线="-", 波动="-"，但实时页面和选股页面正常。

## 信号级别 volatility_pct 始终为 0 的 fallback

`/api/kline_full` 返回的 `signals_list` 中，信号级别数据（BOS/FVG/CHOCH 等）的 `volatility_pct` 始终为 0，因为波动率是交易级别指标，不是信号级别指标。前端 JS 的波动列必须使用 fallback 链：

```javascript
var volPct = Number(s.volatility_pct || 0);
var volStr = volPct ? (volPct.toFixed(1) + '%') : (s.v25_vol_class || s.market_state || '-');
```

**典型症状**: K线信号表"波动"列全部显示"-"。

## Zone 列单点信号显示规则

信号级别 Zone 数据中，BOS/CHOCH/Swing 等单点信号的 `zone_low === zone_high`，此时显示 `zl.toFixed(2) + '~' + zh.toFixed(2)` 毫无意义。前端 JS 必须区分：

```javascript
var zone = (zl && zh && zl !== zh) ? (zl.toFixed(2) + '~' + zh.toFixed(2)) : ((zl && zh) ? zl.toFixed(2) : '-');
```

**典型症状**: K线信号表 Zone 列显示 "21.56~21.56" 这样的无意义范围。