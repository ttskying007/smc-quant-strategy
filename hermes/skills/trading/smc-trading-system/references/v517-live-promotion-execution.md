# V517 日线量价吸收：从研究到当前生产执行

适用：一个已完成 outcome-blind seed、独立 raw-bar oracle、冻结严格 T+1 回放、独立指标审计的低频日线信号，需要接入当前选股、模拟仓位、实时监控与前端。

## 不可混淆的三层

1. **历史 replay**：只用于回测与图表审计，绝不补写成今日候选或仓位。
2. **当前 scanner**：只扫描最新 committed 日线 epoch；response 当日仅产生 `PENDING_NEXT_OPEN`。
3. **生产执行**：仅允许该 pending 的下一交易日开盘验证；开盘严格落在预先可见的结构 SL/TP 之间才可创建仓位。

## 因果链与执行合同

```text
confirmed 3L/3R swing low
→ >=0.3% SSL 下扫且收回
→ 成交量位列此前 20 根完成日线前 20%
→ 下一根完成日线收盘突破 sweep high
→ PENDING_NEXT_OPEN
→ 下一交易日开盘：open > stop 且 open < target
→ BUY_VALID / 建立模拟仓位
```

- `stop = sweep_low × 0.99`
- `target = sweep 前已可见的最近确认 swing high`
- 入场和 target/stop 必须在开盘前已知；不得用后续 K 线计算。
- A 股出场强制 T+1：买入日不得触发卖出，即便同日碰到 SL/TP。

## 生产接入检查清单

1. 生产 registry 只能指向当前 raw scanner 的策略；`buy_enabled=true` 不得使旧回测/旧 watchlist 可买。
2. 后收盘任务先刷新并提交完整日线 epoch，再持久化当天的 pending snapshot；不要只保留会被次日 scanner 覆盖的 latest 文件。
3. 开盘任务只消费该 durable pending，读取带交易日时间戳的行情开盘价；行情日期不等于执行日时 fail closed。
4. 已错过精确下一交易日开盘的 pending 必须 `EXPIRED_MISSED_EXACT_NEXT_OPEN`，禁止迟到补单。
5. 建仓后仅把同一生产策略的 positions 传给实时 SL/TP 检查；旧引擎持仓必须隔离，不能混入当前生产页或触发出场。
6. 前端 `/`、`/monitor`、`/api/picks`、`/api/live-prices` 必须全都读取当前 registry strategy，不可因静态 `ACTIVE_VERSION` 回退到 V66/V88/V185。

## 验收

- 新 scanner 无行：生产页面显示 0 pending / 0 仓位，且没有历史回填。
- 人工 fixture：符合下一开盘价格约束的 row 只创建一次 BUY；不满足则拒绝。
- 迟到 fixture：不建仓，状态为 missed-exact-open。
- 同日 SL/TP fixture：状态可提示，但 position 与 ledger 均不产生 SELL。
- 所有旧仓位在晋级切换时被归档/隔离；实时 API 不显示它们。

## 注意

这里的“买入”是系统的模拟仓位/交易台账动作；若未接入券商接口，不得宣称已经向真实券商下单。
