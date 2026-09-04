# 前端选股/实时监控日期与 NEXT_DAY_PENDING 同步教训

适用场景：修复 SMC 前端 8890 的选股页、实时页、早盘推送中“选股日期/加入日期/买入日/zone/成本线/波动/NEXT_DAY_PENDING”字段不一致或为空的问题。

## 核心原则

1. **买入日不能用 pick_date 兜底**
   - `pick_date/select_date` 是信号/选股发生日。
   - `created_at/buy_date/filled_at` 才是真实加入/买入时间。
   - 持仓表的“买入日”必须固定取真实 `buy_date || created_at || filled_at`，不能为了有值而回退到 `pick_date`；否则会把 6/3 选股、6/4 买入显示成 6/3 买入。

2. **NEXT_DAY_PENDING 是实时监控的一等状态**
   - 选股日当天生成的候选应进入 `NEXT_DAY_PENDING`，不能算作 BUY/OPEN。
   - 选股页统计要同时显示 `OPEN` 与 `NEXT_DAY_PENDING`，否则会出现“汇入今日自动选股 0 条，但日志显示有选股”的误解。
   - `/api/live-prices` 应合并 `OPEN + NEXT_DAY_PENDING`，pending 行状态显示为 `NEXT_DAY_PENDING`，但不触发盈亏/止损/止盈逻辑。

3. **每日选股页面只显示最新有效候选，不混历史候选**
   - `/api/picks` 应用 monitor state 交叉引用：如果 active pick 已经在 positions 中，补 `join_date` 与 `monitor_status`。
   - 对历史候选必须按日期分组：最新交易日选股 / 历史候选 / 已持仓 / NEXT_DAY_PENDING。
   - 不要把历史 ACTIVE_CANDIDATE 混进“今日选股”。

4. **成本线/波动字段必须有后端兜底**
   - 实时页字段：`costLine` 优先 `smart_money_cost`，再回退到 `entry_price/price`。
   - 波动字段：`volClass` 优先 `volatility_class`，再回退到 `market_state/regime/quality_tier/risk_pct/zone_type`。
   - zone 为空时从 `zone_type/signal_type/trade_role/entry_type` 逐层回填，避免前端空列。

5. **ingest 返回值要区分新增与已存在 pending**
   - `added=0` 不代表没有选股；可能是已经存在于 `NEXT_DAY_PENDING`。
   - 返回并展示 `existing_pending_count`，按钮文案用：`新增 / 买入 / 新待次日 / 已在待次日 / active`。

## 推荐验证脚本片段

```python
import json, urllib.request
base='http://127.0.0.1:8890'
def get(path):
    return json.loads(urllib.request.urlopen(base+path, timeout=15).read().decode())

mon=get('/api/monitor/state')
print(mon['summary'])
print([p for p in mon['positions'] if p.get('status')=='NEXT_DAY_PENDING'])

picks=get('/api/picks')
print([{k:p.get(k) for k in ['symbol','pick_date','join_date','monitor_status']} for p in picks])

live=get('/api/live-prices')
print(live.get('total'), [
    {k:p.get(k) for k in ['symbol','status','pickDate','entryDate','joinDate','costLine','volClass']}
    for p in live.get('picks', []) if p.get('status')=='NEXT_DAY_PENDING'
])
```

通过标准：
- `/api/monitor/state.summary.pending` 与 positions 中 `NEXT_DAY_PENDING` 数量一致。
- `/api/picks` 最新选股含 `pick_date`、`join_date`、`monitor_status`。
- `/api/live-prices.total == OPEN + NEXT_DAY_PENDING`。
- pending 行有 `costLine` 与 `volClass`，状态为 `NEXT_DAY_PENDING`。
- 早盘推送中持仓买入日显示真实买入/加入日，不显示为选股日。
