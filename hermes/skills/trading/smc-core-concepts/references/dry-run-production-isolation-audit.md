# Dry-run 生产隔离审计模式

适用场景：SMC 新版本只生成 UI/API preview、shadow payload、display-only dry-run，用户要求确认没有污染生产选股、实时监控、watchlist、summary 或推送。

## 核心原则

- dry-run 的验收目标不是证明策略可交易，而是证明字段合同完整、无结果泄漏、无 BUY 行为、未进入生产链路。
- 生产隔离必须同时看 API、物理 JSON、summary/version、active watchlist；只看 dry-run 文件本身不够。
- 结论必须明确边界：`display-only / shadow-only / NO_BUY`，不得声称已晋级、已实盘、已接生产前端。

## 必查项

1. Dry-run payload 合同：
   - 必填 UI/API 字段缺失数为 0。
   - outcome / pnl / win 等未来结果泄漏为 0。
   - `NO_BUY` 行不得含 buy/entry/open/pending 等 BUY-like action。
2. 生产 API 快照：
   - `/api/picks`：检查行数、Vxx marker 数、BUY-like 行数。
   - `/api/live-prices`：检查行数、Vxx marker 数、BUY-like 行数。
   - `/api/summary`：确认生产 engine/version 仍是当前正式版本。
3. 生产物理文件：
   - 在审计目录外扫描生产相关 JSON，不应出现 dry-run version marker。
   - active watchlist / morning push / ledger 不应包含 dry-run 标记。
4. 输出：
   - 写 `*_production_isolation_snapshot.json` 保存机器可读证据。
   - 写 `*_PRODUCTION_ISOLATION_ADDENDUM.md` 保存人读结论和边界。

## 报告模板

```markdown
## 结论

PASS/FAIL：Vxx dry-run 是否污染生产接口或 active watchlist。

- `/api/picks`：N 行，Vxx 标记 M，BUY-like 行 B
- `/api/live-prices`：N 行，Vxx 标记 M，BUY-like 行 B
- `/api/summary`：engine=`...`, version=`...`
- 审计目录外生产相关 JSON：未发现/发现 dry-run marker

## 当前状态边界

Vxx 当前只完成：
1. 可展示 dry-run payload：字段齐全、无结果泄漏、全部 NO_BUY。
2. 生产隔离验证：未进入 `/api/picks`、`/api/live-prices`、watchlist 或 production summary。

未完成/不得声称完成：
1. 未接生产前端页面。
2. 未启用真实买入。
3. 未晋级生产版本。
4. 未证明 Vxx 是可交易策略。
```

## Pitfalls

- 不要把历史交易文件或 dry-run preview 当作 active picks。
- 不要因为 `/api/picks` 有行就认为新版本已接生产；必须检查 version marker 和 action 语义。
- 不要只报告目录存在；必须读回 snapshot/addendum 关键字段，确认 JSON 与 Markdown 一致。
- 网络/流式中断后，继续从最后成功的只读验证点恢复，补齐产物清单即可；不要重跑会产生副作用的生产写入。