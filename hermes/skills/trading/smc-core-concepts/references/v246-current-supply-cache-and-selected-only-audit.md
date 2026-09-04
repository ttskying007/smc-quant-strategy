# V246/V236 当前供给闭环审计教训：缓存、selected-only 与全宇宙验证

适用场景：SMC 生产/影子候选出现“历史高质量但当前无供给”、或某条历史路线看似可晋级但当前扫描为 0 行时。

## 核心教训

1. **先验证当前供给链路的基础缓存是否新鲜**
   - `v185_market_breadth_cache.csv` 曾停在 `20260624`，导致 V236/V246 当前规则里的 `br_above_ma20` 使用旧值，当前候选被误杀。
   - 不能只看规则输出 0 行就判定“路线无当前供给”；必须检查 breadth/market/industry 等前置特征缓存的最后日期是否覆盖最新 K 线日期。

2. **历史 selected 集合上的高胜率不能直接晋级**
   - V246 selected 历史集合可达到约 `573 / WR 94.4% / avg 7.6%`，但这是已筛选集合。
   - V330 在 selected 集合内找到 `bull_count_3 >= 3` 等高质量切片；但 V331 放到全 V164 dry-run 宇宙后降到约 `WR 89.9% / avg 5.1%`，不满足生产门槛。
   - 任何规则如果只在 already-selected historical rows 上验证，只能作为 shadow 方向，不能当生产晋级证据。

3. **当前候选必须做 T+1 executable replay，而不是只看 actionable 行数**
   - V326 找到当前候选后，V327 逐笔回放区分 `OPEN_UNEXPIRED`、`CLOSED_BY_EXECUTABLE_REPLAY`、TP/SL/TIME。
   - 有些“当前候选”在 T+1 回放后已经 TP/SL/TIME，不应继续映射到实时候选端点。

4. **状态字段要按语义判断**
   - V327 的 closed 状态值是 `CLOSED_BY_EXECUTABLE_REPLAY`，不是单纯 `CLOSED`。
   - 后续统计 closed/open 时必须用 `status contains CLOSED`，否则会把已闭合行误算为 open。

## 推荐审计顺序

1. 重跑/刷新当前扫描源，确认 latest market date。
2. 审计基础特征缓存：
   - breadth cache 最后日期；
   - industry feature 前一交易日日期；
   - all-market strong1 前一交易日日期。
3. 按谱系拆分当前供给：V161/V164、V175、V211、旧 strict parent 等，不要用单一过时 parent rule 代表 V246。
4. 对 <=10 bar 非历史候选做 T+1 executable replay，剔除已闭合候选。
5. 对候选切片做两层验证：
   - selected historical population：只用于发现方向；
   - full dry-run universe：生产晋级必须通过这一层。
6. 若 full universe 不过门槛，即使 selected 集合和当前小样本好看，也只能 shadow，不可生产。

## 可复用门槛

生产候选至少检查：

- `n >= 570`
- `min_year_n >= 70`
- `WR >= 93%`
- `avg >= 7.6%`
- `all_year_wr_min >= 91%`
- `micro_profit_pct <= 1%`
- `T+1 same-day exit violations == 0`

当前候选至少检查：

- 非历史 overlap；
- `bars_since_entry <= 10`；
- T+1 replay 未同日卖出；
- 状态不是已 TP/SL/TIME 的伪活跃；
- 来源字段无 `pnl/exit/won/mae/mfe/hold_bars` 等结果泄漏字段。

## 关键文件模式

- breadth cache：`/root/.hermes/smc_audit/v185_market_breadth_cache.csv`
- V164 dry-run：`/root/.hermes/smc_audit/v164_corrected_scanner_dry_run_*/v164_dryrun_rows.json`
- current lineage supply：`v326_v246_lineage_current_supply_*`
- executable replay：`v327_v326_current_candidate_executable_replay_*`
- selected-only slice audit：`v330_v327_current_open_quality_slice_*`
- full-universe validation：`v331_v330_slice_full_universe_validation_*`
- breadth refresh audit：`v332_breadth_cache_refresh_*`
