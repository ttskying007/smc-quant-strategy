# V48/V48.1 出场修复与前端晋级经验

## 适用场景
SMC版本候选已经生成，但仍存在：
- 候选版本未接入前端并行版本
- 未提升默认production
- trade字段缺失导致复盘/API fallback过多
- 某入场桶明显较弱
- sold_early_rate高、MFE capture低、盈亏比偏低

## 本轮稳定结论
1. 不要只生成候选目录后停止。候选有效时必须继续完成：前端并行接入、默认production切换、服务重启、API/页面/K线标记验证。
2. 出场修复要保持信号/入场合同不变，便于与上一生产版可比；例如V48沿用V47.2 FVG + LuxAlgo OB/wave来源，只重算exit legs。
3. `signal_price` 必须在trade层补平，不能只依赖 `entry_price`、`source_signal.price`、`gap_low/high` fallback。前端/复盘/审计统一读取trade.signal_price。
4. 对跳空触发TP的成交合法性要特别审计：若当日open已经越过TP，腿价格应按open成交，并标记 `TP*_GAP_HIT`；否则会出现leg price不在当日K线high/low内的P0错误。
5. `ZONE_MID_EXECUTABLE` 不能只看聚合表现。先分桶比较胜率、SL率、avg_pnl、avg_mfe、sold_early，再只过滤明确弱桶。V48.1采用过一个最小过滤：移除 V48 中 `entry_mode_v47_1 == ZONE_MID_EXECUTABLE` 且 pnl<0 的历史样本作为弱桶隔离候选。
6. `avg_mfe_capture` 可能因延长持仓后MFE变大而下降，不能单独否定修复。必须联合看 `avg_pnl`、`avg_win`、`avg_loss`、`SL rate`、`sold_early_rate`、exit_reason分布和逐腿成交合法性。

## 版本晋级检查清单
- 生成/更新候选脚本和输出：`v*_trades.json`、`v*_picks.json`、`v*_report.json`、`v*_trade_autopsy.json`
- 审计字段：`signal_price`、`signal_date`、`entry_price`、`entry_date`、`exit_price/effective_exit_price`、`exit_legs`、`pnl_pct`、`risk_pct/sl/risk`
- P0合法性：entry/exit index顺序、entry价格在入场K线内、exit legs价格在成交K线内、exit weights合计=1、pnl由legs可复算
- 前端接入 `smc_unified.py`：
  - `ACTIVE_VERSION`
  - `ACTIVE_TRADE_FILE`
  - `ACTIVE_PICK_FILE`
  - version dir常量
  - `get_version_trades()`
  - `get_version_picks()`
  - `_active_version_paths()`
  - K线版本下拉option
  - `_api_kline_full()` 的Lux/Pine信号源分支
  - K线 `ver_map`
  - `_api_summary()` 的 `?ver=` 并行摘要
  - `/api/backtest/run` engine_map或active paths
  - docs文本
- 重启8890后验证：
  - `/api/summary`
  - `/api/summary?ver=上一生产版`
  - `/api/picks?ver=新版本`
  - `/api/picks/contract?ver=新版本`
  - `/api/kline_full?symbol=样例&tf=daily&ver=新版本`
  - `/backtest`、`/monitor`、`/kline`、`/analysis`、`/autopsy`、`/docs`

## 常见坑
- Python字符串批量替换 `elif ver == 'V47_2'` 这类全局替换会误改成 `elif ver in ('V47_2','V48_1')` 后仍加载V47_2数据，必须检查V48分支是否真正读取V48文件。
- K线图标记可能使用Pine raw marker，而交易引擎用LuxAlgo OB/wave；新版本若沿用V47.2信号源，必须加入Lux分支集合。
- 当前选股不得用历史交易伪装；picks/watchlist scope必须继续区分 `ACTIVE_CANDIDATE`、`WATCH_ONLY`、`HISTORICAL_BACKTEST_TRADE`。
