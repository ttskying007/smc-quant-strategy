# V49 90日闭环复盘与交易质量门禁

## 适用场景
当用户要求检查 SMC 回测/选股/实时监控/复盘是否形成闭环，或指出“盈利太小、盈亏比太低、卖早/跑早、止盈止损不合理”时，必须使用本流程，而不是只汇报聚合 WR/RR。

## 用户硬约束
- 持仓不得超过 90 个日线 bar。
- 盈利交易低于 2% 视为手续费/滑点不够的无效小盈利。
- 亏损在 -1% 内视为噪音退出，不应当作为有效风控结果自我安慰。
- 盈利交易 realized R 不得低于 2R；低于 2R 要计入质量问题，即使 PnL 为正。
- 单笔 `risk_pct` 不应小于 1%，否则容易被手续费/滑点吞噬。
- 统计口径必须按 `entry_date` 窗口过滤，排序按 `entry_date -> exit_date -> symbol`。

## 必做闭环
1. 选股：active/watchlist 必须来自真实 picks，不得用历史 trades 伪装当前候选。
2. 实时监控：实时页读取 picks，输出当前价、PnL、SL/TP 状态、接近止盈/止损状态。
3. 退出触发：记录 `exit_date`、`exit_reason`、`exit_legs`、`exit_price_final`、`pnl_pct`、`realized_r`。
4. 退出后继续追踪：即使已经止盈/止损，也要继续读取后续 90 日 K 线，计算 MFE/MAE、post-exit MFE、capture rate。
5. 逐笔归因：每笔交易必须判断是信号错误、入场偏高、卖早、卖晚、保护线过早、结构破坏退出、还是 runner 捕获不足。
6. 前端同步：复盘页应展示 90 日闭环摘要、问题计数、最差交易列表；API 应暴露完整 JSON 供检查。

## 问题标签
逐笔复盘建议至少输出这些 issues：

- `HOLD_OVER_90`
- `WIN_BELOW_2PCT_FEE_INEFFICIENT`
- `LOSS_BELOW_1PCT_NOISE_EXIT`
- `WIN_RR_BELOW_2R`
- `RISK_BELOW_1PCT_FEE_NOISE`
- `SOLD_EARLY_NEXT_90D`
- `BAD_EXIT_LOST_BUT_90D_RECOVERED`
- `LOW_90D_MFE_CAPTURE`

## 关键诊断口径
- 聚合胜率高不代表系统合格；必须看逐笔是否满足 2R、2% 最低盈利、90日 MFE 捕获。
- 如果胜率高但 `WIN_RR_BELOW_2R` 很多，问题通常在出场保护线过早或 runner 结构不够。
- 如果 `SOLD_EARLY_NEXT_90D` 很多，不能简单加大 max_hold；应检查结构化 runner 是否在 swing low / demand zone 破坏前过早退出。
- 如果 `LOW_90D_MFE_CAPTURE` 很多，说明信号方向可能对，但趋势利润捕获失败。

## V49 经验教训
一次有效修复把：
- `max_hold` 从 240 改到 90；
- 早期保本 buffer 从 0.1% 改到至少 2.5%；
- TP2 后保护从 1.5R 提高到 2R；
- trailing 锁定从 2R 提高到 4R；
- 新增退出后 90 日持续复盘。

修复后能消灭超 90 日持仓、小于 2% 盈利、-1% 内噪音亏损，但仍可能留下大量 `WIN_RR_BELOW_2R` 与 `SOLD_EARLY_NEXT_90D`。这时下一步不是继续美化 WR，而是把出场改成结构化 runner：早期只在结构破坏时退出，TP2 后跟随 swing low / demand zone，而不是固定小幅锁利。

## 前端/API同步检查
完成修复后必须验证：
- `/api/picks` 确实读取 active picks/watchlist。
- `/live` 或实时监控页股票来源来自 picks。
- `/autopsy` 或复盘页展示闭环卡片。
- `/api/autopsy/closed-loop` 返回完整 JSON。
- 页面无 Traceback，统计窗口按 `entry_date` 生效。
