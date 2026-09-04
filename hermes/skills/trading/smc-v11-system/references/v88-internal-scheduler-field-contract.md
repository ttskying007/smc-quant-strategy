# V88 内置调度与前端字段合同修复经验

适用场景：SMC 前端/生产系统要求“程序启动后自己执行每日选股、复盘、分析、数据更新”，并且 `/monitor`、`/live` 页面出现选股日期、加入日期、engine、zone、成本线、波动等字段为空。

## 程序内置调度优先级

用户明确纠正过：这类每日任务不要依赖系统 crontab 或 Hermes Gateway；只要 `smc_unified.py` 运行起来，就应该由程序内部调度自己执行。

推荐实现形态：

1. 在 `smc_unified.py` 启动入口 `server.serve_forever()` 前启动 daemon scheduler thread。
2. 调度线程每 60 秒检查一次工作日与任务时间。
3. 状态持久化到 `/root/.hermes/smc_monitor/internal_scheduler_state.json`，按 `last_success_date` 避免同日重复执行。
4. 日志写入 `/root/.hermes/logs/smc_internal_scheduler.log`。
5. 暴露 `/api/scheduler/status`，返回 enabled、jobs_config、每个 job 的 last_run/rc/stdout_tail/stderr_tail。
6. 暴露 `/api/scheduler/manual-run?job=morning_push|closed_loop&force=1`，用于前端或人工显式触发；默认后台线程执行，避免阻塞 HTTP 请求。
7. 移除系统 crontab 中的 SMC 每日任务，并保留 crontab 备份。

标准 job：

| job | time | script | purpose |
|---|---:|---|---|
| morning_push | 08:30 | `python3 smc_morning_push.py` | 数据更新 + V90/V91 选股 + 早盘推送 |
| closed_loop | 17:15 | `python3 smc_daily_closed_loop.py` | 数据更新 + 选股 + V88 回测 + 分析 + 复盘 smoke |

## 前端字段合同验收

字段修复不能只看页面肉眼，要做 API + HTML 双验收：

| 页面/API | 必须零空值字段 |
|---|---|
| `/api/picks` | `select_date`, `pick_date`, `join_date`, `joined_at`, `engine`, `zone_type` |
| `/api/live-prices` | `cost_line`, `volatility_pct`, `zone_type`, `engine` |
| `/monitor` HTML | 表头必须含选股日期、加入日期，且行内有实际值 |
| `/live` HTML | 成本线、Zone、波动列必须渲染数值 |

注意：`/api/live-prices` 可能返回 dict 包装结构，不一定直接是 list。审计脚本应兼容 `rows/picks/items/data`。

## 入场可执行性回归坑

V88 `zone_limit` 修复时，不能只检查策略价 `entry_price` 是否在 entry day 的 high/low 范围内；如果回退到 `entry_price_original_v86`，也必须再次验证原始价是否可执行。

正确 fallback：

1. 如果 `zone_limit entry` 不在入场日 high/low：标记 `execution_repair='ZONE_LIMIT_NOT_TOUCHED_USE_NEXT_OPEN'`。
2. 先尝试 `entry_price_original_v86`。
3. 如果原始价仍不在入场日 high/low，则回退到入场日 `open`（若 open 在 high/low 内），否则回退到 close。
4. 重新按新 entry 缩放 SL、重算 TP1/TP2/TP3、模拟退出腿、更新 PnL/RR。
5. 记录 `entry_price_fallback_source`，例如 `original_v86` 或 `entry_day_open`。

## 发布前最小回归清单

必须全部通过后才可回复完成：

```bash
python3 -m py_compile smc_unified.py v25/v88_apply_production_contract.py test_internal_scheduler_contract.py
python3 test_internal_scheduler_contract.py
python3 v25/test_frontend_field_contract_mpkfagiawk77km.py
python3 v25/test_v88_current_picks_contract.py
python3 v25/test_v88_executable_entry_contract.py
python3 test_monitor_entry_execution_contract.py
python3 v25/smc_daily_closed_loop.py
```

同时检查：

```bash
crontab -l | grep -E 'smc_daily_closed_loop.py|smc_morning_push.py|precompute_smc_indicators.py'
curl -fsS http://127.0.0.1:8890/api/scheduler/status
curl -fsS http://127.0.0.1:8890/api/picks
curl -fsS http://127.0.0.1:8890/api/live-prices
```

合格标准：

| 项 | 标准 |
|---|---|
| scheduler | `internal_scheduler=true` |
| SMC daily system cron | 0 残留 |
| picks/live rows | 数量一致且关键字段 0 空值 |
| V88 executable entry audit | PASS |
| T+1 | 0 violation |
