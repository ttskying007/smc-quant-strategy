# SMC 每日生产选股数据源约束

- 每日生产选股不得使用 `v65_trades.json`、`v66_trades.json` 等历史交易文件作为候选源。
- 历史交易文件只用于回测、分析、复盘、门禁验证。
- 每日选股必须从全市场最新 K 线缓存重新扫描，输出当前行情日候选。
- `OB → PINBAR` / `Sweep → OB → PINBAR` 不得进入生产选股或实时监控；若扫描到，只能作为验证/拒绝候选保留。
- 前端选股页应显示当前生产候选的 `select_date/pick_date` 与监控加入日期 `join_date/created_at`，不能用历史交易日期伪装当前选股。
- 当前实现路径：`v25/daily_scan.py` 从 `/root/.hermes/kline_cache/*_daily_750.json` 全市场扫描；`v25/smc_daily_ops.py` 将 `full_market_kline_scan` 的 `ACTIVE_CANDIDATE` 合入 `/root/.hermes/smc_opt_v66/v66_picks.json`，历史 V66 picks 降为 `EXPIRED_REVIEW`。