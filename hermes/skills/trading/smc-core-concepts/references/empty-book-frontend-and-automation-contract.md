# EMPTY_BOOK 前端与定时任务一致性合同

## 触发条件

生产 registry 已声明：

```json
{"state":"EMPTY_BOOK","production_strategy":null,"buy_enabled":false}
```

而页面仍出现遗留 V88/V90/V185 的“手动回测失败”、旧扫描日期、旧持仓统计或旧分析结果时。

## 规则

1. **Registry 优先于文件存在性与历史版本标签。** `v88_*`、`v90_*`、`v185_*` artifact 存在不能使其成为当前生产策略。
2. **手动入口先读取 registry。** `/api/backtest/run`、`/api/reselect` 在 EMPTY_BOOK 必须在选择任何 engine 前返回结构化 `EMPTY_BOOK_NO_PROMOTED_PRODUCTION_STRATEGY`；禁止运行旧引擎或重写历史 artifacts。
3. **scanner metadata 必须是当前生产 scanner 的 metadata。** EMPTY_BOOK 下应展示当前 committed 日线 epoch 的 `data_date`，同时显示 `scanner_state=NOT_RUN_EMPTY_BOOK`；不得拿旧 V90/V91 报告填 `last_scan_at` 或 `latest_scan_date`。
4. **0 候选不是错误。** 页面/日志必须清楚区分：行情刷新成功 + 生产扫描因无晋级策略被跳过，与刷新/扫描执行失败不同。
5. **历史分析与当前生产隔离。** EMPTY_BOOK 时，运行日志、实时持仓汇总、分析/复盘不得把历史 V185/V88 的 metrics 或 positions 呈现为当前生产结果；可保留为明确标注的只读历史研究入口。
6. **调度单一事实源。** 内部 scheduler 与 Hermes cron 都必须指向当前 fail-closed daily ops 合同；废弃“V88 closed loop”描述和命令。持久 state 中 `running=true` 超过一天而无运行进程时应恢复为 false，避免永远阻塞后续任务。

## 最小验收矩阵

| 表面 | 必须验证 |
|---|---|
| `/api/summary` | `production_state=EMPTY_BOOK`、当前 epoch 已提交、`buy_enabled=false` |
| `/api/picks` | 空数组；不得混入历史交易 |
| `/api/live-prices` | 当前行情日；`NOT_RUN_EMPTY_BOOK`；0 实时持仓 |
| `/backtest` | 无 V88 rerun 按钮/执行；明确禁用原因 |
| `/monitor` | 当前日期、0 候选、手动生产重选禁用；无旧 scanner 日期 |
| `/live` | 不将 dataDate 回填成 scanner 日期；scanner 未运行须显示 `-` |
| `/logs` | 任务为 `SKIPPED_EMPTY_BOOK`，历史分析/持仓明确隔离 |
| daily ops | 刷新成功、epoch COMMITTED、无 V88 artifacts mtime 变化、0 BUY_VALID |

## 实施产物范式

每次跨面修复必须先写：`ISSUE.md`（事实/根因/验收）、`SPEC_PR.md`（非目标/边界/验证）、`IMPL_PR.md`（变更和实测结果）。这不是将研究策略自动产品化的授权。
