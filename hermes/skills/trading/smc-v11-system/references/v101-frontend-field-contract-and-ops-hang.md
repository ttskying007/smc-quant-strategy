# V101 前端字段合同与日报卡住处理

## 适用场景

SMC 前端 `/monitor`、`/live` 或 ops 日报出现字段空值、字段缺失统计异常，尤其是：

- 选股页缺少 `选股日期` / `加入日期`
- 引擎下方 `Zone` 为空
- 实时页 `成本线` / `波动` 为空
- 报告 `field_missing_active` 对可选说明字段误报缺失
- `smc_daily_ops.py` 全量链路长时间无输出、无 CPU、卡在 poll/wait

## 字段合同规则

1. 前端必需字段要按页面实际渲染验证，不只看 API 聚合：
   - `/monitor`: `pick_date` / `join_date` / `zone` / `zone_type` / `cost_line` / `smart_money_cost` / `volatility_pct`
   - `/live`: `pickDate` / `joinDate` / `costLine` / `zone` / `volatilityPct`
2. 可选解释字段不能作为生产 active 必填字段：
   - 例如 `combo_candidate_gate_reason_v101` 只在候选行有意义。
   - 生产 active 行为空是正常状态，不能计入 `field_missing_active`。
3. 必填字段应是稳定合同字段：布尔 eligibility、whitelist 标记、日期、zone、成本、波动。
4. 验收必须检查 DOM 文本中无 `undefined` / `null` / `NaN`。

## 日报卡住处理

当 `smc_daily_ops.py` 前台或后台执行超过常规耗时：

1. 先检查父/子进程状态，不要盲目重复启动：
   - `ps -o pid,ppid,etime,pcpu,pmem,rss,stat,wchan:24,cmd -p <pid>,<child>`
   - `pgrep -P <pid> -a`
   - `tail -120 /tmp/<ops-log>.log`
2. 如果子进程长期 `0% CPU`、日志为空、wchan 显示 poll/wait，且输出文件未更新，可判定为轮询卡住。
3. 终止卡住任务后，使用已落盘的核心报告和线上 API/页面做最终验收；不要把“日报卡住”误判为核心 V101 生成失败。
4. 如果需要补日报摘要，优先做局部字段报告验证；全量日报链路可能会因 V98/V101 子流程耗时较长。

## 最小验收清单

- `python3 -m py_compile v101_mtf_dna_combo_contract.py smc_daily_ops.py`
- 重跑 V101 核心报告并确认：
  - `production_total` 不被候选池污染
  - `bos_continuation_candidate_total` 独立统计
  - `field_missing_active_total == 0`
  - `t1_violations == 0`
- API 验收：`/api/summary`、`/api/picks`、`/api/live-prices`
- 浏览器验收：`/monitor`、`/live` 表格字段显示正常，DOM 无 `undefined/null/NaN`
