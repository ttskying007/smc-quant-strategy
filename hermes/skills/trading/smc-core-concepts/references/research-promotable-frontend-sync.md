# 研究晋级策略的前端同步与生产隔离

## 适用条件

当一个 SMC 新本体已经通过 outcome-blind 支持门禁、独立 raw-bar Oracle、单次冻结严格 T+1 回放、独立指标审计、逐年门禁，且 scanner-time 合同已建立，但尚未获得独立生产放行时使用。

## 核心原则

“研究晋级”与“生产可买”是两个状态。前端必须完整展示研究证据，但不能因为展示完整而把历史回测行或 shadow 行写入生产选股、watchlist、仓位、实时买入或旧 `/api/picks`。

## 建议的数据面

建立独立只读 adapter，从冻结审计工件读取：

```text
seed gate -> oracle -> frozen replay trades -> metric audit
-> current scanner epoch -> release audit -> exact-next-open shadow
-> read-only frontend adapter
```

保持以下硬字段：

| 字段 | 约束 |
|---|---|
| `production_write` / `watchlist_write` | 始终 `false`，直到独立 production release 完成 |
| `buy_enabled` | 始终 `false`，即使是 `SHADOW_BUY_VALID` |
| 回测交易 | 标记 `REPLAY_ONLY`，不可作为当前候选 |
| scanner 行 | 只显示当前 committed epoch 生成的 `PENDING_NEXT_OPEN` |
| shadow 行 | 必须使用冻结 scanner snapshot，并仅在精确 next-open committed epoch 验证 |
| 空候选 | `0 pending / 0 BUY_VALID` 是合法结果，显示 `NO_BUY`，不可回填历史行 |

## 必须同步的前端面

1. **仪表盘**：研究晋级状态、实时 shadow 状态、指标、年份分布和全部门禁。
2. **K线**：用同源回放交易画出因果节点：结构锚点、sweep/reclaim、response、严格 T+1 entry、SL、结构 target 与实际 exit。
3. **回测/逐笔复盘**：展示完整冻结交易集；每行可跳转 K线。
4. **当前选股**：只展示 scanner/shadow 当前状态，清晰标记 `NO_BUY`。
5. **分析**：按 exit reason、逐年、T+1、重复/重叠等审计字段归因。
6. **共振**：若本体是同周期因果链，应把结构、量价、价格结果、执行时序列为共振层；不得把未验证 MTF 条件冒充为已验证共振。
7. **架构文档**：列出工件、路由、字段合同、禁止历史回填与独立生产放行条件。

## 最小 API / UI 验收

```text
py_compile adapter + server
GET research bundle: research_result=RESEARCH_PROMOTABLE
assert production_write=false, watchlist_write=false, buy_enabled=false
assert replay trade count matches frozen replay artifact
assert current picks come only from current scanner/shadow snapshot
GET sample kline with strategy version: causal signal count and trade count match adapter
browser-smoke dashboard and kline version selection
```

## 常见失败模式

- **直接复用 `/api/picks`**：会把研究或历史行混入生产生命周期。
- **将回测 CSV 视作实时候选**：属于历史回填，违反 scanner-time 合同。
- **只同步 summary，不同步 K线/逐笔因果节点**：无法验证信号与交易是否同源。
- **把 `SHADOW_BUY_VALID` 写成 BUY**：它只证明 shadow next-open 合同成立，仍需独立生产 release。
- **空候选时隐藏模块或退回旧 active 文件**：应明确显示 `NO_BUY`。
