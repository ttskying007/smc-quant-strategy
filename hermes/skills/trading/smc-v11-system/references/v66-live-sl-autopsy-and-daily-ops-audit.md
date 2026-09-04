# V66 实盘 SL 复盘与每日闭环审计

适用场景：用户要求检查某交易日 SMC 全流程是否执行完整，并追问“历史几笔交易基本全部 SL，是信号问题、入场问题还是什么问题”。

## 只读原则

如果用户明确说“先不调整 / 不做修改 / 只分析”，必须保持只读：

- 不改策略参数。
- 不改代码。
- 不改持仓状态。
- 不做补数据或清洗。
- 只读取 `ops_logs`、`daily`、`positions`、`trade_ledger`、`closed_reviews`、API 与前端页面结果。

## 每日闭环检查顺序

1. 读取 `/root/.hermes/smc_monitor/ops_logs/YYYYMMDD.json` 与 `ops_latest.json`。
2. 检查 K线刷新：`kline_refresh.returncode == 0`、`started_at/finished_at/duration_sec` 存在。
3. 检查 daily scan：`daily_scan.returncode == 0`，并从 `stdout_tail` 提取：
   - 最新行情日
   - 扫描股票数
   - latest-date candidates
   - active 数量
   - 当日 active symbol 列表
4. 检查 `/root/.hermes/smc_monitor/daily/YYYYMMDD_auto_daily.json`：
   - `added`
   - `buy_added`
   - `pending_count`
   - `validation_only`
   - `rejected_count`
   - 每只 position 的 `status/pending_reason/reject_reason`
5. 检查分析/回测摘要：`analysis_summary.metrics`、`analysis_summary.exit_counts`。
6. 检查复盘摘要：`review_summary.review_total/closed_today/review_reason_counts`。
7. 检查实时监控摘要：`live_summary.open_positions/closed_positions/ledger_total/ledger_today`。
8. 检查 cron/closed loop 日志对应时间点：
   - 09:20 前后出现 `MARKET_CLOSED` 是正常，因为未到 09:30。
   - 09:30 后应出现 `market_open: true`，且 `error == ""`。

## 06-08 / 09:20 这种场景的判断口径

当用户说“今天日 2026.06.08，当前 9:20”但系统时间或日志已经进入次日，需要分开解释：

- `data_date` 代表最新行情日，可仍为 `20260608`。
- 系统执行日可能为 `20260609`。
- 09:20 实时监控跳过并记录 `MARKET_CLOSED` 是正确行为，不是任务错误。
- 9:30 后才应进入 live monitor。

## SL 复盘必须先分层，不能直接归因信号错误

先把 closed review 分成至少五层：

| 层级 | 检查字段 | 解释 |
|---|---|---|
| 历史样本污染 | `pick_date` 到 `created_at` 的交易日年龄 | 过期 pick 被导入实时监控会制造假 SL |
| Zone 可执行性 | `zone_low/zone_high/dz_low/dz_high` | 缺 Zone 或入场远离 Zone，不能证明信号有效 |
| Provenance | `zone_idx/conf_index/source_event_idx` | 缺 provenance 时不能做精确信号回放 |
| 入场位置 | `entry_price` vs Zone | 入场低于/高于 Zone 过多，属于执行/生命周期问题 |
| 真实信号失败 | 入场在 Zone 内且 provenance/age 合格但仍 SL | 才归入信号/确认强度问题 |

## 关键判定规则

- 如果 closed review 中大量记录满足：
  - `pick_date` 比 `created_at` 早很多交易日；
  - `zone_low/zone_high == 0`；
  - `zone_idx/conf_index` 缺失；
  - raw 回测里原本是 `STRUCT_CONFIRM_BREAK` 或盈利，但实时监控成了 SL；

  则主因是 **历史候选污染 + 实时执行层误导入**，不是信号整体失效。

- 如果近期样本入场价已经低于 demand/FVG Zone 2% 以上，归因为 **Zone 生命周期失效 / 入场执行未复核**。

- 如果入场在 Zone 内，MFE 很低且随后 SL，才归为 **真实信号失败或确认强度不足**。

- 不要先说“止损太窄”。只有在干净样本中：入场有效、Zone有效、provenance完整、价格仅轻微扫过 SL 后快速 reclaim，才考虑止损设计问题。

## 必须输出的表格

### 全流程闭环

| 环节 | 时间/数量 | returncode | 结论 |
|---|---:|---:|---|
| K线刷新 | started→finished / duration | 0/非0 | 成功/失败 |
| daily scan | started→finished / duration | 0/非0 | 成功/失败 |
| 选股 | latest candidates / active | - | 成功/失败 |
| ingest | added/buy_added/pending | - | T+1是否合规 |
| 分析 | n_trades/wr/avg_pnl | - | 正常/异常 |
| 复盘 | review_total/SL/TP | - | 正常/异常 |
| live | open/closed/ledger | - | 正常/异常 |

### SL 归因

| 代码 | pick | buy | sell | PnL | Zone关系 | 归因 |
|---|---:|---:|---:|---:|---|---|

## 结论模板

- “全流程是否完整”：基于 ops/daily/log/API 的执行证据回答。
- “为什么基本全部 SL”：先说明是否是干净样本；若不是，明确不要用它推翻信号。
- “信号/入场/出场哪个问题”：按证据排序，不给未经验证的优化建议。

## 重要坑

- 不要只看前端 fallback 后的显示；要读原始 `closed_reviews.json`、`positions.json`、`trade_ledger.json`。
- 不要把回测层 WR/SL 和实时监控层 SL 混在一起。V66 回测 137 笔与实时 closed review 是两个样本池。
- 不要把 `MARKET_CLOSED` 当错误；09:20 属于盘前。
- 不要把历史手工导入 `manual_daily` 样本当作当前生产候选。