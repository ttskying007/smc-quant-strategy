# V42/V43 SMC 止损与漏单排查工作流教训

## 触发场景
用户反馈“止损触发较多”“信号不准”“入场点问题”“未到入场点位”“继续但不要偏离主目标”时使用。

## 主目标约束
不要把任务变成单纯 WR/RR 优化，也不要粗暴扩张交易数。目标必须保持为：

1. 区分止损来源：信号定义错、入场点错、组合方式错、未到入场点位、出场/止损设置错。
2. 对每类失败给出代码路径级证据，而不是只报聚合指标。
3. 只修复被证据证明的高 MFE 漏单/错误入场路径。
4. 候选必须全量回测并通过门槛后才能晋级正式版本。

## 推荐排查顺序

### 1. 冻结当前正式版本基线
记录当前正式版本的交易数、WR、SL率、AvgPnL、TotalPnL、PnL/holding-days、亏损样本明细。不要在未冻结基线前改代码。

### 2. 止损样本归因
逐笔亏损输出：
- symbol / entry_date / exit_date
- zone_type / source_event / conf_type / entry_mode
- entry_index / signal_index / zone_idx / sweep_idx
- entry_price / zone_low / zone_high / sl / risk_pct
- 是否 entry outside zone
- 是否 zone invalidated before entry
- 是否未真正回踩 zone
- 是否 FVG/OB 选择错误

### 3. 漏单机会归因
对 missed opportunities 不能只看 `future_mfe_30` 聚合值，必须按代码路径分桶：
- `FVG_SETUP_PASSED_NOT_TRADED`
- `SETUP_PASSED_NOT_TRADED`
- `NO_RETRACE+FVG_NO_RETRACE`
- `NO_PREV_SWEEP`
- `ENTRY_OUTSIDE_ZONE_LIMIT`
- `ENTRY_LIMIT_RETOUCH_FAILED`
- `ZONE_TOO_WIDE`
- `MARKET_STATE_FAIL`
- `FVG_NOT_RANGE`
- `CONFIRM_TOO_LATE`
- `QUALITY_FAIL_ON_REPLAY`

每桶报告：count、avg_mfe30、high_mfe30_pct。优先修复 high_mfe30_pct 高且代码路径明确的桶。

### 4. FVG setup passed 但未交易
这是最像“路径漏接”的类别，应优先检查：
- 是否 `entry_from_limit_retouch` 只允许 zone limit retouch，导致强 FVG displacement 后不回踩而整段漏掉。
- 是否 `make_setup` 的 `entry <= zone_high * 1.012` 把 near-zone continuation 全部杀掉。
- 是否 `zone_width_pct > 3.0` 对 FVG 过严。
- 是否 `market_state != RANGE` 把 trend-up FVG 全部杀掉。
- 是否 dedupe 用同一 `entry_index` 让 OB 覆盖 FVG。

修复时不要全局放宽；优先做 FVG 专属 continuation fallback，并保留 zone invalidation 保护。

### 5. NO_RETRACE 高 MFE
不要直接追价。必须建立二级过滤：
- displacement 强度
- break 后 3 bar 是否站稳
- 是否出现浅回踩且不跌回 zone
- 是否仍在合理 entry distance 内
- 是否趋势/相对强度支持

未通过二级过滤的 NO_RETRACE 仍然不能交易。

### 6. NO_PREV_SWEEP 高 MFE
不要直接取消 sweep 要求。应测试替代流动性来源：
- local low sweep/reclaim
- EQL/EQH pool
- internal liquidity sweep
- displacement-only MSS
- compression breakout

替代 sweep 必须单独标记 `sweep_type`，不得伪装成 SSL。

## 验收门槛
候选版本必须至少同时满足：
- 交易数高于基线
- WR 不显著低于基线设定门槛
- SL率不高于门槛
- AvgPnL 不低于基线改善目标
- TotalPnL 高于基线
- 资金效率不低于基线

任何候选只增加交易数但 SL/WR 崩，都应拒绝，不同步前端。

## 工作流纪律
- 用户说“继续”时，不要只总结；继续执行下一步验证。
- 用户提醒“主要任务目标不要发生偏离”时，回复和工具动作必须重新锚定主目标：止损/漏单/入场/信号定义/组合方式根因。
- 不要在候选未通过验收时切换 `ACTIVE_VERSION` 或同步前端。
- 修改核心函数前先做影响分析；修改后立即编译/全量回测/前端验证。

## 已验证的有用诊断脚本模式
建立 `v43_phase1_setup_passed_autopsy.py` 这类脚本，对 missed rows 重放：
1. 重新检测 signals。
2. 定位原始 event / sweep / zone。
3. 依次执行 retrace、confirm、quality、entry、make_setup、dedupe、backtest。
4. 记录首次失败节点为 `diag`。

该模式比直接猜参数更可靠，适合未来 SMC 入场路径/止损归因任务复用。
