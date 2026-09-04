# V66 日扫生产门禁与任务时间显示

## 触发场景
用户发现最新选股/实时监控中只显示 `OB → PINBAR`，并质疑它是否绕过前面迭代形成的 V66 生产要求；随后要求日志、分析、复盘页面都能看到任务是哪天几点执行。

## 核心教训

### 1. V66 不能长期依赖 V65 历史源，但最新日扫描必须使用同一套回测机制
V65/V66 历史 overlay 源可能停在旧日期（例如 V65 最大 `20260521`），如果 daily ops 只跑 `v66_engine.py`，生产选股会一直没有最新行情日候选。

但不能把任意 `daily_scan.py` 新序列直接升级为 V66 生产入口。2026-06-03 已验证：`daily_scan.py` 扫出的 `OB → PINBAR` / `Sweep → OB → PINBAR` 在 `v66_trades.json` 与 `v65_trades.json` 中没有对应回测交易与 PnL 记录；将其标记为 `ACTIVE_ENTRY` 会造成选股/实时与回测/复盘/分析不是同一套机制。

正确原则：

```text
最新日全市场扫描器必须复用 V66 已回测生产机制；
若扫描结果的 sequence 不存在于 V66 回测交易，不得进入 /monitor 或 /live。
```

当前未验证 daily scan 序列必须标记为：

```text
pick_scope = VALIDATION_ONLY
is_active_pick = False
validation_status = NEEDS_SEQUENCE_BACKTEST
validation_reason = daily_scan sequence not present in V66 backtest trades
```

日志结果：

```text
daily_scan_merge.reason = DAILY_SCAN_SEQUENCE_NOT_IN_V66_BACKTEST
daily_ingest.reason = NO_LATEST_DATA_PICKS
```

关键实现教训：`daily_scan.py` 原循环 `range(scan_start, n - 5)` / `range(..., n - 2)` 会漏掉最后几根 K 线，可修复为允许最新 bar；但这个修复只解决“能扫描最新日”，不代表扫描出的新序列可以生产化。
### 2. 选股/实时监控必须区分生产候选与验证候选
生产页面只能展示已经过门禁或已被用户明确提升为生产扫描的 active picks/watchlist；未验证 daily scan 信号可以进入日志/审计，但不能伪装成正式选股或持仓监控。

实时导入时禁止沿用历史回测 `entry_price` 作为买入价。`to_position(source='auto_daily')` 必须用腾讯实时价（`qt.gtimg.cn`）重算：

```text
entry_price = tencent_last/tencent_open/current executable price
sl_price = entry_price × (1 - risk_pct/100)
tp1_price = entry_price × 原TP相对涨幅
execution_price_source = tencent_last / tencent_open / kline_YYYYMMDD
```

这样可以防止历史信号价“抢走”实时持仓成本，避免出现 5月买入却沿用1月/3月回测价格导致虚假 SL/TP 的问题。

推荐日志结果：

```text
daily_scan_merge.reason = DAILY_SCAN_QUARANTINED_UNTIL_SEQUENCE_BACKTEST
daily_ingest.reason = DAILY_SCAN_VALIDATION_ONLY_NOT_AUTO_INGESTED
```

如果曾误入实时监控，应清理 `positions.json` 与 `trade_ledger.json` 中对应候选，并先备份：

```text
positions.json.<timestamp>.quarantine.bak
trade_ledger.json.<timestamp>.quarantine.bak
```

### 3. 任务时间必须跨日志/分析/复盘页面显示
日志页、分析页、复盘页都要显示同一套任务执行时间，便于判断“哪天几点执行了什么任务”。不要只在 `/logs` 显示。

页面顶部建议统一显示：

| 字段 | 含义 |
| --- | --- |
| 任务日 | ops log 对应日期 |
| 日志生成 | ops_latest.json generated_at |
| V66选择器 | started_at → finished_at + duration_sec |
| 最新日扫 | started_at → finished_at + duration_sec |
| 日扫合并 | added / validation_only / reason |
| 监控汇入 | added / skipped / reason |

关键页面：

```text
/logs
/analysis
/autopsy
```

### 4. daily ops 函数要记录 started_at / finished_at / duration_sec
`run_selector()`、`run_kline_refresh()`、`run_daily_scan()` 等任务返回值中应包含：

```json
{
  "started_at": "ISO datetime",
  "finished_at": "ISO datetime",
  "duration_sec": 12.3,
  "returncode": 0
}
```

这样页面不需要猜测任务状态，可以直接从 `ops_latest.json` 判断执行窗口。

## 验收标准

- `/logs` 显示任务执行时间表；
- `/analysis` 显示任务执行时间表；
- `/autopsy` 显示任务执行时间表；
- `/api/logs` 返回 `kline_refresh`、`selector`、`daily_scan`、`daily_scan_merge`、`daily_ingest`；
- 未验证序列不会出现在 `/api/live-prices`；
- 未验证序列不会作为正式 active pick 出现在 `/api/picks`；
- 浏览器/HTTP 验证页面包含“任务执行时间、任务日、日志生成、V66选择器、最新日扫、监控汇入”。
