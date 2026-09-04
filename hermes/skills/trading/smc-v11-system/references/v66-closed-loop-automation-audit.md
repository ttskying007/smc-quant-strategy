# V66 闭环自动化与日志审计经验

## 触发场景
用户要求验证 SMC 系统是否已经形成完整自动闭环：每日选股、实时监控、SL/TP 触发、买卖账本、复盘归因、分析与前端日志全部自动运行，而不是只修单页字段或手工生成文件。

## 关键结论
- 不能把“选股文件已生成”当作闭环完成。生产闭环必须覆盖：selector → 今日候选筛选/拒绝原因 → 自动汇入 monitor state → 实时行情轮询 → SL/TP 关闭 → trade ledger → closed reviews → ops logs → 前端页面/API。
- 旧 cron 指向过期版本脚本时，页面可能仍有历史 picks，但每日自动更新实际已经断链。排查必须同时看 cron、cron.log、生产版本、文件 mtime、ops log 和前端 API。
- V66 是当前生产版本时，`/v45`、`v45_4 原生事件驱动 SMC` 一类页面只能作为历史/事件实验入口，不能让导航或默认 API 暗示它是生产主链路。

## 推荐闭环结构
生产闭环脚本建议集中为一个模式化 runner，例如：

```text
smc_closed_loop_ops.py daily       # selector + audit + 今日 picks ingest
smc_closed_loop_ops.py live        # 交易时段轮询实时价格，触发 SL/TP、账本、复盘
smc_closed_loop_ops.py postmarket  # 收盘快照：live + daily audit refresh
smc_closed_loop_ops.py selftest    # 端到端检查 API 与页面
```

cron 需要覆盖：

```cron
# 09:05 trading days: selector + pick ingest + daily audit log
5 9 * * 1-5 root cd /root/.hermes/scripts && /usr/bin/python3 v25/smc_closed_loop_ops.py daily >> /root/.hermes/smc_monitor/cron.log 2>&1
# intraday: poll live prices so SL/TP, ledger and closed reviews are persisted
*/5 9-11 * * 1-5 root cd /root/.hermes/scripts && /usr/bin/python3 v25/smc_closed_loop_ops.py live >> /root/.hermes/smc_monitor/cron.log 2>&1
*/5 13-15 * * 1-5 root cd /root/.hermes/scripts && /usr/bin/python3 v25/smc_closed_loop_ops.py live >> /root/.hermes/smc_monitor/cron.log 2>&1
# postmarket snapshot
20 15 * * 1-5 root cd /root/.hermes/scripts && /usr/bin/python3 v25/smc_closed_loop_ops.py postmarket >> /root/.hermes/smc_monitor/cron.log 2>&1
```

## 日志/审计页必须展示
`/logs` 或等价页面至少包含：

- 当前生产版本与 selector return code。
- 今日选股数、45 日候选、Active 候选、最新候选日期。
- 今日自动汇入数与原因：例如 `NO_TODAY_PICKS`。
- 选股漏斗：`pick_scope` 分布。
- 拒绝原因：如 `REENTRY_EXACT_HIGH_EXTENDED_RANGE`、`REENTRY_BQ_LT_60`。
- 候选样本：symbol、选股/入场日期、zone、confirm、setup family、match score、scope。
- 实时摘要：open/closed positions、ledger count、today ledger count。
- SL/TP 复盘：symbol、closed_at、PnL、bucket、diagnosis、repair_plan。
- 文件 mtime：picks/trades/report/positions/reviews/ledger/cron log，防止 stale 数据伪装成实时。

## 验证清单
完成闭环改动后不要只打开页面，必须实际跑：

```bash
python3 -m py_compile smc_unified.py v25/smc_daily_ops.py v25/smc_closed_loop_ops.py
python3 v25/smc_closed_loop_ops.py daily
python3 v25/smc_closed_loop_ops.py live --force
python3 v25/smc_closed_loop_ops.py selftest
```

并核对：

- `/api/summary` 的 `active_default` 是当前生产版本。
- `/api/logs` 包含 `daily_ingest`、`pick_diagnostics`、`review_summary`。
- `/api/monitor/state` 包含 `positions`、`ledger`、`reviews`。
- `/api/live-prices` 返回 `monitor_update` 与 `tradeLedger`。
- `/monitor`、`/live`、`/logs`、`/analysis`、`/autopsy` 页面全部 HTTP OK。
- 交易休市时 `live --force` 只能验证链路，不代表已验证真实行情价格；需要明确标注。

## 版本错配陷阱
如果用户质疑“为什么还显示 v45_4 原生事件驱动 SMC”：

1. 先查 `ACTIVE_VERSION` 和 `/api/summary.active_default`，确认生产版本。
2. 搜索硬编码的 `v45_4`、`V45.4`、`原生事件驱动`。
3. 将导航与默认 API 从历史实验版本改为当前实验最新值，或标注为“事件实验”，避免误导生产状态。
4. K 线页 JS 默认版本必须与生产版本保持一致，例如 V66 时不要保留 `currentVersion = 'V45.4'`。

## 用户验收口径
对 Lei 这类 SMC 闭环任务，最终报告必须明确：

- “之前是否已经闭环”要诚实回答，不能因为局部功能能跑就说完成。
- 区分：生产主链路、历史实验页、休市状态下的链路验证。
- 给出表格化测试结果：daily/live/selftest、positions、ledger、reviews、pages、today_count、daily_ingest。
- 如果今日无票，要给出最新候选日期和拒绝原因，而不是只说“无选股”。
