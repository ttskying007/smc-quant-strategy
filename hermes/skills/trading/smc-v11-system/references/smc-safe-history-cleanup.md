# SMC 历史版本/归档文件安全清理流程

适用场景：用户要求清理 SMC 历史版本、过老文件、大文件，但不能影响当前生产前端、每日任务、实时监控。

## 原则

- 不直接删除疑似旧文件；先做依赖扫描，再隔离重命名/移动，再验证，最后删除。
- 当前生产链路优先保留：`smc_unified.py`、`scripts/v25/`、`smc_monitor/`、当前生产 `smc_opt_v66/`、每日扫描输出目录、release/audit 仍引用的大快照。
- 历史交易/归档文件即使不是生产源，也可能被复盘、audit、release gate 引用；必须先查引用。
- 清理目标优先选择已经是旧归档的目录，例如 `/root/.hermes/archive`；不要先动当前根目录下仍被代码引用的 `smc_opt_v*`。

## 推荐步骤

1. 盘点大小：统计 `/root/.hermes/archive`、`/root/.hermes/smc_opt_v*`、`/root/.hermes/scripts`、`/root/.hermes/smc_monitor` 的目录大小和文件数。
2. 查引用：搜索生产代码中是否引用候选目录/文件名，尤其是 `smc_unified.py`、`scripts/v25/*.py`、每日任务脚本、release gate/audit 脚本。
3. 基线验证：在清理前跑一次：
   - `python3 v25/smc_closed_loop_ops.py selftest`
   - API：`/api/summary`、`/api/picks`、`/api/live-prices`、`/api/logs`
4. 隔离而非删除：把候选目录移动到 `/root/.hermes/.cleanup_quarantine_<timestamp>/`，并写 manifest，记录原路径、文件数、大小。
5. 隔离后验证：再次运行 selftest、live 强制刷新、关键 API 和页面：`/monitor`、`/live`、`/logs`、`/analysis`、`/autopsy`、`/backtest`。
6. 只有验证通过才删除隔离内容；删除后创建空的原目录占位（如 `/root/.hermes/archive`），避免外部脚本假设目录存在。
7. 删除后再跑最终复测，并保留 manifest 到 `/root/.hermes/smc_cleanup_manifest_<timestamp>.json`。

## 验证指标

最低通过条件：

- selftest 返回 ok。
- `/monitor`、`/live`、`/logs`、`/analysis`、`/autopsy`、`/backtest` HTTP 200。
- `/api/picks` 可读；当前 full-market 生产候选仍存在。
- `PINBAR` 生产候选数量为 0。
- `join_date` 空值为 0。
- `/api/live-prices` 中实时成本线空/0 为 0，波动字段空值为 0。
- 日志 `data_date` 仍是当前数据日期。

## 本次沉淀案例

2026-06-03 清理 `/root/.hermes/archive`：

- 先隔离 `/root/.hermes/archive` 到 `/root/.hermes/.cleanup_quarantine_20260603_151855/archive`。
- 隔离后验证 selftest、live、API、页面均正常。
- 删除隔离归档，释放约 2989.6 MB / 8122 files。
- 保留 manifest：`/root/.hermes/smc_cleanup_manifest_20260603_151855.json`。
- 保留当前生产依赖目录：`smc_opt_v66`、`smc_opt_v65`、`smc_opt_v25`、`smc_opt_v50_signal`、`smc_monitor`、`scripts/v25`。
