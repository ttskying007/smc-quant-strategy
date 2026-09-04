# V99/V100 经济性复盘与前端同步验收教训

## 触发场景

当 SMC 版本通过“浮盈保护 / trailing / 小锁盈”把胜率显著抬高时，不能只报告 `pnl_pct > 0` 的 gross WR。A 股 T+1 + 手续费 + 滑点环境下，0.1%~0.8% 的小盈利通常没有交易意义，会污染胜率判断。

## 本次可复用结论

### 1. 胜率必须同时报告 gross 与 net

最低合同：

| 指标 | 必报 |
|---|---|
| gross WR | `pnl_pct > 0` |
| net WR | `pnl_pct >= fee_slippage_threshold_pct`，默认 0.8% |
| small-win count | `0 < pnl_pct < 0.8` |
| payoff | `avg_win / abs(avg_loss)` |
| profit factor | `sum(wins) / abs(sum(losses))` |
| exit_reason 分桶 | 特别检查小盈利是否集中在同一出场原因 |

如果 gross WR 很高但 net WR 很低，版本不能晋级生产。

### 2. 小锁盈陷阱

V99 的 `MFE>=2R -> lock +0.25R` 把表面胜率推到 95%+，但 345/869 笔是 0~0.8% 小盈利，全部来自 `V99_PROFIT_PROTECT_STOP`。

根因不是主要信号错误，而是 TP/SL 出场合同错误：

- 当 `risk_pct≈0.5%~1.1%` 时，`0.25R` 只等于约 `0.13%~0.27%`。
- 这类盈利不足以覆盖手续费/滑点。
- 不能把这种交易计作有效成功。

### 3. 修复方向

优先生成一个高 RR 候选版本，而不是继续堆胜率：

- 保留信号/入场不变。
- 保留高胜率门禁。
- 移除 sub-cost 小锁盈。
- 回到结构 TP2 / 结构 SL 或至少锁定 `>=1R` 且收益必须超过成本阈值。
- 所有版本报告增加 `net_wr_ge_0_8` 和 `small_win_pct`。

本次 V100 候选方向：V99 门禁 + V98 结构出场，ABC 结果从 V99 的 gross WR 95%+ / net WR 约56% / payoff 约2.2R，恢复到高payoff、无小盈利污染，但真实net WR只有约74%~80%，不能晋级生产。

### 4. V100 实测结论（2026-07-06复跑）

脚本：`/root/.hermes/scripts/v25/v100_economic_net_wr_gate.py`
输出：`/root/.hermes/smc_opt_v100_economic_net_wr_gate/v100_report.json`

规则：保留 V98 信号/入场 + V99 语义分层，移除 `0.25R` 小锁盈，改为 `MFE>=4R→锁2R`、`MFE>=6R→锁3R`。

结果：

| 池 | n | gross WR | net WR>=0.8% | small-win | avgPnL | PF | 决策 |
|---|---:|---:|---:|---:|---:|---:|---|
| A+B | 113 | 79.65% | 79.65% | 0 | +2.5855% | 17.36 | 不晋级 |
| ABC | 855 | 74.50% | 74.50% | 0 | +2.7393% | 12.44 | watch-only |

关键教训：移除小锁盈后胜率大幅回落，说明 V99 的 95%+ 胜率主要来自出场合同，不是信号层真正达到90%净胜率。V100是经济性复盘产物，不能作为生产版本。

## 前端同步验收规则

用户问“前端是否全部同步”时，不要只验证 `/api/picks`。必须表格化检查：

| 面 | 必查 |
|---|---|
| 选股 | `/api/picks` 字段缺失：pick_date/join_date/zone/cost_line/volatility/TP/SL/RR |
| 实时 | `/api/live-prices` 同字段缺失；特别检查 tp2/tp3 是否也传出 |
| K线 | `/api/kline_full?symbol=...&ver=...` 是否有 trades/highlight/signals |
| 回测 | `/backtest` 是否读到当前版本 trades |
| 分析/复盘 | `/analysis`、`/autopsy` 是否使用当前 trade cache |
| 文档 | `/docs` 是否更新版本结论与已知未闭环项 |
| 壳层标识 | nav/title/summary/equity_curve 是否仍显示旧 ACTIVE_VERSION；若仍旧，必须明确“数据面已同步，壳层未完全晋级” |

## 完成标准

只有当以下都满足时，才可说“全部同步完成”：

1. 当前版本的 trades/picks 被所有核心页面读取。
2. 选股/实时/K线字段缺失为 0。
3. TP1/TP2/TP3/SL/RR 在选股和实时 API 都非空。
4. `/docs` 明确写入当前版本、经济性结论和未闭环项。
5. 静态标题、summary、equity_curve 不再显示旧版本；否则只能说“核心数据同步完成，前端壳层仍未完全同步”。
