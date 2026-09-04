# V46.2 Lux structure核准、出场审计与reversal/continuation分层

## 触发场景
用户指出 SMC 信号不准确、K线标识与回测/选股不同步、盈亏比或出场价格口径异常，尤其要求“全面review/全量核准/继续下一步/增加goal”时使用。

## 已验证的 durable workflow

### 1. 结构核心核准必须做逐bar不变量，不只看WR
对全市场日线缓存逐股票检查：
- `pivot_rule == luxalgo_leg_currentLevel`
- Bull structure: `pivot_price == pivot_bar.high` 且 `prev_close <= currentLevel < close`
- Bear structure: `pivot_price == pivot_bar.low` 且 `prev_close >= currentLevel > close`
- 结构线只表示 `pivot_bar_index -> break_bar_index`，不能向右延伸成支撑/压力线
- OB 必须是 currentLevel break 前、pivot→break 区间内最近一根反向K线
- MSS 必须为 internal 独立结构，并有同方向 recent sweep 上下文
- kept trade 的 `source_event_idx` 必须能回链到当前 Lux structure 信号，不能回链旧引擎

### 2. 出场审计不能再用单一 exit_price 反推分批收益
若回测包含 TP1/TP2/TP3/trailing 分批退出，单一 `exit_price` 容易代表“最后一腿价格”，而 `pnl_pct` 是加权综合收益。必须新增或核准：
- `exit_legs`: 每腿 `date/index/price/weight/pnl_pct/reason`
- `exit_weight_sum == 1.0`
- `realized_pnl_pct == sum(weight * leg.pnl_pct)`
- `exit_price_effective == entry_price * (1 + realized_pnl_pct/100)`
- `exit_price_final` 单独保留最后一腿价格
- 前端/复盘默认用 effective exit price 做收益反推，final exit price 只作明细展示

### 3. continuation 与 reversal 必须分开核准，不能让 BOS continuation 掩盖 reversal 问题
主 V46.1 kept 交易可能主要来自：
`BOS continuation -> OB/FVG -> retest -> confirmation`。
这不等于 reversal SMC 已经正确。新增/核准 reversal goal 时必须单独生成：
`LIQ -> CHOCH/MSS -> OB/FVG -> retest -> legal confirmation`。
并分别输出：
- continuation kept 指标
- reversal all 指标
- reversal strict/no-pinbar 指标
- reversal displacement-only 指标
- 分桶：`zone_type × source_event × conf_type`

经验结论：宽松 reversal 全样本通常质量低于 continuation kept；高质量 reversal 只出现在 displacement 或少数严格 two-bar 子桶。不要把全量 reversal 直接并入主选股。

### 4. 选股页默认不能展示系统自己 REJECT 的 active candidate
若 watchlist-first 产生 active candidates，默认 `/api/picks` 必须只返回真正可交易候选：
- layer in `A/B/PASS` 或 `position_size > 0`
- REJECT 候选必须移到单独审计接口，例如 `/api/picks/rejects`
- 如需全量观察候选，用 `/api/picks?include_reject=1`
- `/api/picks/contract` 应明确给出 `tradable_active_pick_count` 与 `rejected_active_pick_count`

否则用户会把“被系统自己拒绝的观察项”误认为真实选股，造成前端同步误判。

### 5. 前端同步验收入口
每次修复后必须重启 8890 并用 HTTP 验证：
- `/api/kline_full?symbol=600519.SH&tf=daily&ver=V46_1`：K线信号与结构线
- `/api/summary?ver=V46_1`：指标同步
- `/api/picks`：默认可交易选股
- `/api/picks?include_reject=1`：全部候选
- `/api/picks/rejects`：拒绝项审计
- `/api/picks/contract`：契约统计

## Pitfalls
- 不要用聚合 WR/RR 证明信号正确；必须做 source_event、pivot、break、zone、entry、exit 的逐笔/逐bar审计。
- 不要把 Pine/Lux “画出来像”当作对齐；必须核准 currentLevel crossover/crossunder 与 pivot->break。
- 不要把 `exit_price_final` 当成综合收益反推价。
- 不要把 continuation 高胜率误报成 reversal 修复成功。
- 不要让 REJECT active candidate 出现在默认选股页。
