# V44 前端适配与止损根因审计经验

## 触发场景
当全量回测输出已经生成，但前端指标缺失/不一致、页面进程被 kill、或用户继续追问“止损多到底是信号、入场、组合还是未到点位”时，先做数据契约与根因归因，不要直接调 SL/TP。

## 前端数据契约修复
V44 `v44_full.json` 是 dict 包装结构，前端必须读取 `all_trades`，并补齐以下字段后再进入统一缓存：

- `symbol`
- `entry_date` / `exit_date` / `signal_date`
- `entry_mode`
- `pnl_pct` / `won`
- `exit_method` / `exit_reason`
- `engine` / `definition_version`
- `zone_type` / `conf_type` / `source_event`
- `market_state`
- `ctx_seq` / `seq` / `detail`

`is_winner()` 与 `normalize_v27_trades()` 要把 V44 纳入 `pnl_pct > 0` 口径，否则前端胜率会错。

## V44 大文件前端 OOM 坑
V44 全量文件可超过 200MB、交易数超过 23 万。以下操作容易导致前端进程被系统 kill：

1. 对完整 `trades` 做 `sorted()`，会额外复制大列表。
2. `_TRADES_LITE_CACHE` 如果仍保留全部字段，会与 `_TRADES_CACHE` 双份占内存。
3. `/backtest` 页面同时排序、去重、生成曲线时最容易触发 OOM。

修复模式：

- V44 下如果生成文件已按日期/股票顺序稳定输出，`build_backtest()` 可直接使用原始 `trades` 做采样曲线，避免 `sorted()`。
- V44 的 `_TRADES_LITE_CACHE` 只保留前端实际字段：`symbol, entry_date, exit_date, signal_date, entry_price, exit_price, pnl_pct, won, rr, hold_bars, sl, sl_pct, signal_type, zone_type, direction, entry_mode, conf_type, exit_method, exit_reason, market_state, phase, ctx_seq, seq, detail, entry_idx, sig_idx, confirmed_at, exit_idx, source_event`。
- `/api/picks` 使用单独轻量 `v44_picks.json`，不要从 200MB 全量文件现场派生。

## 必做验证
修复后至少请求并验证：

- `/api/summary`
- `/api/picks`
- `/`
- `/backtest`
- `/monitor`
- `/kline?s=<top_pick_symbol>`

并用本地 JSON 重算对齐：

- `total_trades`
- `win_rate`
- `avg_pnl`
- `stocks`

注意前端可能使用 3 年窗口过滤，因此 `v44_full.json` 全量交易数与 `/api/summary` 交易数可以略有差异；必须按同一 cutoff 重算后对齐。

## 止损根因审计结论模板
V44 类“止损多”不要直接归咎 SL。按分层归因：

1. `DIRECT_SIGNAL_CLOSE` / chase：信号出现即收盘入场，未等 raw zone retest，通常是最大失败源。
2. bull 信号在 bearish/ranging 弱环境中裸开：市场相位错配。
3. IFVG_Bull 单独触发：数量大但失败率高，应重审定义或要求绑定 sweep/CHOCH/raw retouch。
4. 真正 raw retouch：如 `CONFIRM_WICK_RETOUCH_RAW_HIGH`，通常显著优于 chase，应该保留为正式入场核心。
5. SL 过窄或被 cap：只有在排除前四类后才作为主要问题。

本次可复用的归因口径：

- `ENTRY_NOT_RAW_ZONE_RETEST_DIRECT_CHASE`
- `ENTRY_NOT_RAW_ZONE_RETEST_CONTINUATION`
- `IFVG_DEFINITION_OR_COMBO_WEAK`
- `MARKET_PHASE_MISMATCH_BULL_IN_WEAK_CONTEXT`
- `SL_TOO_TIGHT_OR_ENTRY_TOO_LATE`
- `IMMEDIATE_FAILURE_SIGNAL_OR_ENTRY`

## 下一版设计原则
V45/V44 后续优化应优先修入场与组合，不是调 SL：

- 删除或降级 `DIRECT_SIGNAL_CLOSE`。
- 正式交易只允许 raw zone retouch 类确认：`CONFIRM_WICK_RETOUCH_RAW_HIGH`、`LIMIT_RETOUCH_RAW_HIGH`、高质量 `RETEST_ENGULF`。
- IFVG_Bull 不应单独触发，必须绑定 sweep/CHOCH/raw retouch。
- bull 信号在弱市场相位中必须有更强过滤。
- 每笔未入场也要输出原因：信号存在但未回 raw zone、回 zone 但无确认、确认存在但市场状态失败、入场后结构失效、SL 过窄/被 cap。
