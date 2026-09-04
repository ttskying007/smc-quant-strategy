# 可恢复的多周期原始缓存构建

适用：为全市场研究建立长历史 daily / weekly / 60m / 15m 原始 OHLCV 缓存，数据源单会话偶发阻塞，且缓存不得污染信号、交易、选股、前端或持仓。

## 成功标准

1. 每个已计为完成的标的均具备四个原子文件。
2. 15m 与 60m 分别通过逐交易日完整 slot 审计；weekly 由同源 daily 确定性聚合。
3. 控制器状态必须能区分 `BATCH_RUNNING`、正常批次结束、源端超时和缓存完成；禁止遗留无进程支撑的 `RUNNING`。
4. 任意中断后从实时缺口恢复；部分批次已完成的原子文件保留，未完成标的重试。

## 推荐执行模型

- **单会话、非并发**：先验证提供方对多 session 的行为；若会话会互相阻塞，禁止为了吞吐并发。
- **小批次 cron，不跑一个脆弱的长父进程**：每轮固定较小批量，下一轮按当前缓存缺口重新计算起点。
- **双层限时**：Builder 子进程使用独立 process group 和内部 timeout；cron wrapper 另有总时限。超时杀整个子进程组，保留之前的原子写入。
- **双锁**：外层调度锁防 cron 重叠，缓存写锁防其他构建器并发；两者用不同锁文件，避免同进程自锁。

## 控制器要求

在启动子进程前立即原子写状态：

```json
{
  "state": "BATCH_RUNNING",
  "active_batch_start": "<symbol>",
  "active_batch_size": 9,
  "production_write": false,
  "signal_or_trade_generation": false
}
```

子进程结束后记录 `returncode`、`timed_out`、请求数、完成数和剩余数。无论成功、超时或提前达到批次上限，均写终态（例如 `MAX_BATCHES_FINISHED`）；不要只依赖进程是否还存在推断状态。

## 验收顺序

1. 先运行 1 个标的，确认四个文件、bar 覆盖和 slot 审计。
2. 运行一个有硬超时的小批，核对缓存数的增量等于报告的 `completed`。
3. 安装周期调度后，验证至少 **两次独立自动触发**：日志中均有正常终态，且第二轮起点/remaining 由第一轮结果推进。
4. 运行中允许看到 `BATCH_RUNNING`；此时须同时存在 controller 与 builder PID，且文件数或 partial audit 正在变化。
5. 只有四周期数量一致、逐标的审计通过，才能将标的计入完成覆盖率。

## 常见陷阱

- `subprocess.run(timeout=...)` 的 `TimeoutExpired` 若未捕获，会让控制器退出并留下陈旧 `RUNNING` 状态。
- Builder 的 provider socket read 可能无限阻塞；只在 Python 内重试不足以保证恢复，必须有 OS 级子进程组超时。
- 长时间后台会话本身可能被宿主进程回收；用有界的系统 cron 增量轮次比单个多小时父进程更可审计。
- 不要以 m15 文件存在即认为全周期完成：必须验证 15m/60m slot 和同源派生关系。
- 数据构建只能写研究缓存与审计 manifest；不允许借历史交易文件生成“当前候选”。
