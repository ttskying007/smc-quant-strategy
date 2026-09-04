# V415–V516 本地纯结构研究边界闭环（2026-07-15）

触发：用户要求在不依赖外部数据的前提下，继续寻找能提升 SMC 胜率、收益和盈亏比的新方向。

## 固定规则

- 仅使用本地日线/周线 OHLCV；不依赖外部数据。
- 每个新 ontology 必须先冻结语义、通过独立 Oracle，再只运行一次严格 T+1 回放。
- 禁止事后阈值、SL、TP、持仓期、年份或市场状态挖掘。
- 晋级至少要求：n>=300、每年 n>=40、所有年度 AvgNet>0、总体 PF>1（各分支可有更严格预声明门禁）。

## V517–V523：闭环后的新信息维度例外（2026-07-16）

V516 关闭的是**价格/结构/时间框架/上下文**纯结构本体，不包含已存在的日线成交量这一独立信息维度。随后唯一允许打开的非变体方向是 `DAILY_EFFORT_RESULT_ABSORPTION`：已确认 3L/3R swing low → 0.3% wick sweep 且收回 → sweep 日成交量位于前20日top quintile → 次日收盘突破 sweep high → 后一日开盘入场。

结果已按 outcome-blind 支持门禁、独立 raw-bar oracle、一次冻结严格T+1回放、独立 raw-bar metric replay 依次闭环：seed=404（2023/24/25/26=80/147/133/44），closed n=387，Gross WR=63.5659%，AvgNet=+0.9588%，Payoff=0.8108，PF=1.4146；四个年度均为正（n=72/146/129/40；AvgNet=+0.5529%/+0.6952%/+1.4535%/+1.0559%），T+1=0。证据：`v517`–`v520` latest JSON，发布审计：`/root/.hermes/smc_audit/v522_effort_result_release_audit_latest.json`。

当前只允许 **shadow**：V523 已对 601929.SH 的冻结D0候选完成精确D1开盘验证（2026-07-16 open=2.21，stop=2.0691，target=2.39，SHADOW_BUY_VALID），没有生产/前端/watchlist/持仓写入。每日18:10的 `v523_post_close_shadow_observer.py` 先验证上一冻结快照，再仅用当前commit epoch重建下一日 pending snapshot；无当日候选时状态必须是 `SHADOW_READY_NO_CURRENT_SIGNAL`，不得回退历史交易。由于 post-close daily K线不能在次日09:30执行真实开盘成交，任何生产BUY仍必须先实现并验证独立的实时开盘执行链路；不得把收盘后看到的开盘价补填为真实生产买入。

## 结论

最终审计：`/root/.hermes/smc_audit/v516_local_structure_frontier_closure_latest.json`

V415–V516 覆盖：structure-flip POI、post-reclaim expansion、EQL/spring、failed-breakdown/breaker、range/PO3、supply-failure breaker、target-first DOL、protected-swing transfer、internal-liquidity/IFVG/BPR、Turtle Soup、市场/行业 SMT、周线 rejection block、internal inducement、double SSL absorption、two-sided purge、BSL acceptance retest、周线 BOS/FVG/breaker/IFVG 与日线 transfer/context。

经济前沿中最高 headline WR 为 internal inducement sweep：n=6066、gross WR=74.3983%、AvgNet=+0.0744%、payoff=0.4436、PF=1.0414，但 2023/2024 AvgNet 为负。最高 AvgNet/payoff 为 weekly SSL rejection block transfer：n=37514、gross WR=56.8055%、AvgNet=+0.5351%、payoff=0.9479、PF=1.1932，但 2023/2026 AvgNet 为负。

最终 distinct weekly two-sided purge→daily transfer 只有 51 个完整 seed（2023/24/25/26=6/10/19/16），未达到预结果支持门禁，因此没有打开 outcomes，禁止放宽语义凑样本。

V516 registry audit 通过，decision=`CURRENT_LOCAL_OHLCV_PURE_STRUCTURE_RESEARCH_COMPLETE__ZERO_ALL_YEAR_PROMOTION_PASS__STOP_STRATEGY_ITERATION`。当前本地 OHLCV 纯结构研究边界已闭环；不要继续做 timeframe/context/threshold/entry/exit 变体。仅当出现真正新的因果 ontology，且在看 outcomes 前满足全量与逐年支持门禁，才可重启策略研究。生产、前端、watchlist 均未写入。
