# V46.1 P0：回测-选股-前端同步修复验收

适用场景：SMC 分层引擎或前端集成出现 `errors_count`、变量未定义、K线标识与回测不一致、选股列表来自历史交易伪装当前候选等问题。

## 必做顺序

1. **先修运行时与验收错误**
   - 搜索目标版本脚本中的未定义变量、验收字段和输出字段。
   - 对类似 `zq` 的分类变量，不要临时填默认值；必须从 zone 宽度、raw zone、zone high/low 推导真实分层值。
   - 验收必须至少包含：`errors_count == 0`、watchlist 错误数为 0、当前选股不是历史交易。

2. **增加可重建缓存开关**
   - 对依赖 base/cache 的全量脚本增加 `--rebuild-base` 或同等参数。
   - 参数触发时先删除/失效化相关 cache，再重新构建，避免前端继续读取旧 base。

3. **K线信号源必须与回测一致**
   - 如果回测使用复合信号源（例如 Pine-like FVG/BPR/EQL/OTE/LV + LuxAlgo V34 structure/sweep/OB），前端 `/api/kline` 必须使用同一组合。
   - K线高亮应优先按 `source_event_idx -> zone_idx -> retrace_index -> conf_index` 定位；没有 active candidate 时才 fallback 到 watch-only。

4. **当前选股必须 watchlist-first**
   - 当前 picks/API 不得从 historical backtest trades 伪装生成。
   - 输出记录需显式标注 `pick_scope`：`ACTIVE_CANDIDATE`、`WATCH_ONLY`、必要时才有 `HISTORICAL_BEST`，前端默认排除 `HISTORICAL_BACKTEST_TRADE`。
   - `pick_date` fallback 应覆盖 `entry_date/date/pick_date/conf_date/retrace_date/signal_date`。

5. **同步验收覆盖所有展示入口**
   - 编译检查目标脚本和 `smc_unified.py`。
   - 小样本跑通后再跑全量。
   - 验证输出 JSON：trades、watchlist、validation_summary、report。
   - 验证前端/API：active version、active pick file、picks contract、kline signals/highlights、示例 symbol 的高亮链路。

## 验收口径

- 不只看 WR/RR；必须证明信号标识、入场/确认日期、选股来源、前端K线标识和回测输出来自同一套数据。
- 最终报告列出：修改文件、关键字段、验证命令、全量指标、API同步检查结果、仍未解决的信号质量债务。
