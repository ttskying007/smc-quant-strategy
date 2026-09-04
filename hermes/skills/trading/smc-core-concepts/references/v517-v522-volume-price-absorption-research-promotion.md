# V517–V522 日线量价吸收本体：从价格结构闭环重启的正确方式

## 为什么 V516 不能阻止本方向

V415–V516 实际关闭的是**仅由价格/时间结构构成**的本体族：摆动、流动性、BOS/CHOCH、OB、FVG、Breaker、跨周期和跨证券上下文。尽管输入 K 线带有 volume 字段，V516 的已关闭语义没有把“成交量与价格结果之间的关系”作为独立因果条件。

因此，若一个方向引入预先存在的 volume 信息，并以量价关系定义机制，而非修改已有价格结构的周期、阈值、入场、止损、目标或持仓期，它是允许重启研究的**新因果 ontology**。

## 已冻结的量价吸收定义

`DAILY_EFFORT_RESULT_ABSORPTION`：

1. 3-left/3-right 已确认摆动低点，且在 sweep 前已可见；
2. 后续 K 线向下 wick breach 至少 0.3%，但收盘重新回到摆动低点上方；
3. sweep 当日成交量处于此前 20 个已完成交易日的前 20%；
4. 下一根完成日线的收盘突破 sweep K 线高点，确认“高卖压 effort 被吸收后价格有上行 result”；
5. 再下一交易日开盘才有资格执行，保证严格 A 股 T+1。

该定义的关键不是“放量”单独作为过滤器，而是 **异常卖出 effort（高成交量向下扫低）与随后的反向价格 result（收盘收回且下一日突破 sweep high）** 的关系。

## 正确闭环顺序

1. **V517 support gate**：禁止读取结果字段；全市场 seed 至少 `n>=300`，且每年 `n>=40`。
2. **V518 independent raw-bar Oracle**：独立重算摆动、成交量分位、sweep、收回、response 与 entry-eligible 时序；逐笔零差异才可继续。
3. **V519 one-shot frozen replay**：执行规则只能在看结果前冻结。此轮为：eligible-day open；stop=`sweep_low*0.99`；target=扫低前已可见的最近确认 swing high；退出从下一交易日开始；同日 TP/SL 碰撞按 SL；20 bar time exit；0.20% round-trip fee；单股串行持仓。
4. **V520 independent metric audit**：独立实现重建逐笔交易集合、overall/yearly 指标、T+1、目标可见性、重复与重叠。任何差异阻止晋级。
5. **V521 scanner-time dry run**：只使用最新已提交 epoch 生成 `PENDING_NEXT_OPEN`。禁止由历史回测交易或历史 seed 充当当前候选。
6. **V522 release audit**：研究晋级不等于生产写入。只有扫描器在下一交易日开盘验证 `open > stop` 且 `open < pre-known target` 后，才可转为 `BUY_VALID`；否则拒绝且不能回退历史候选。

## 已验证结果（仅研究晋级，不等于已生产部署）

- V517：404 outcome-blind seeds；2023/2024/2025/2026 = 80/147/133/44；支持门禁通过。
- V518：404/404 independent Oracle，零差异。
- V519：387 closed trades，Gross WR 63.5659%，AvgNet +0.9588%，PF 1.4146，payoff 0.8108，T+1=0。
- 年度 AvgNet：2023 +0.5529%，2024 +0.6952%，2025 +1.4535%，2026 +1.0559%；年度样本 72/146/129/40。
- V520：逐笔集合、指标、T+1 与目标可见性独立复算完全一致。
- V522：研究晋级通过，但 production/frontend/watchlist 均保持 false。

## 生产边界与用户偏好

- 用户要求信号因果正确性、逐机制审计、严格 T+1 和全链路时间语义优先于表面 WR/RR。
- 当用户说“继续”，应先检查是否存在已通过支持与 replay 门禁、但尚未完成 Oracle、独立复算、scanner-time 或 next-open 验证的具体链路；不能把“尚未 production write”误报为研究已闭环。
- 任何生产接入都必须从当前全市场扫描器的新 epoch 输出候选；历史 replay trades 仅能作研究/审计依据。
- 不得把这一个本体成功后再做 volume percentile、sweep 阈值、SL/TP、持仓期、年份或 regime 的结果导向变体；若要新研究，必须再次提出非同族的新因果本体并从 outcome-blind support gate 开始。

## 产物

- `/root/.hermes/smc_audit/v517_daily_effort_result_absorption_seed_gate_latest.json`
- `/root/.hermes/smc_audit/v518_daily_effort_result_absorption_independent_oracle_latest.json`
- `/root/.hermes/smc_audit/v519_daily_effort_result_absorption_frozen_t1_replay_latest.json`
- `/root/.hermes/smc_audit/v520_daily_effort_result_absorption_independent_metric_audit_latest.json`
- `/root/.hermes/smc_audit/v521_daily_effort_result_absorption_scanner_time_dry_run_latest.json`
- `/root/.hermes/smc_audit/v522_effort_result_release_audit_latest.json`
