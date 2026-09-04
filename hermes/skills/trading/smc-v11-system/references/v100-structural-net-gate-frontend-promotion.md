# V100 结构净收益门禁与前端生产晋级闭环

## 触发场景

用户要求继续执行 SMC 前端/选股/实时页修复，尤其是：
- 选股页增加或修复 `选股日期`、`加入日期`
- 选股页 `engine` / `zone` 为空
- 实时页 `成本线` / `波动` / `zone` 为空
- 已有候选版本需要晋级为当前前端生产源

## 核心教训

不要只修页面模板或单个 API 字段。字段为空通常是 **生产源路由 + JSON 字段合同 + 缓存读取优先级** 三层不一致。

V100 晋级的稳定做法是：

1. **先生成物理 JSON 输出**
   - `/root/.hermes/smc_opt_v100_structural_net_gate/v100_trades.json`
   - `/root/.hermes/smc_opt_v100_structural_net_gate/v100_active_picks.json`
   - `/root/.hermes/smc_opt_v100_structural_net_gate/v100_watch_picks.json`
   - `/root/.hermes/smc_opt_v100_structural_net_gate/v100_report.json`

2. **在生成脚本里补齐字段合同，而不是靠前端猜**
   - 日期：`pick_date`, `join_date`, `pickDate`, `joinDate`, `selectDate`, `entryDate`, `选股日期`, `加入日期`
   - Zone：`zone`, `zone_type`, `zone_low`, `zone_high`, `zoneType`, `zoneLow`, `zoneHigh`
   - 成本：`cost_line`, `smart_money_cost`, `costLine`
   - 波动：`volatility_pct`, `volatility`, `volatilityPct`, `v25_vol_class`, `volClass`
   - 交易：`tp1`, `tp2`, `tp3`, `sl`, `rr`, `engine`

3. **前端仍可保留 V88 外壳，但数据源必须优先读 V100**
   在 `smc_unified.py` 中新增 `V100_DIR`，并在这些入口优先 V100：
   - `_active_pick_mtime()`
   - `_v88_latest_market_date()`
   - `_merge_v90_daily_picks()`：V100 存在时不要混入 V90
   - `_merge_v91_shadow_picks()`：优先合并/返回 V100 active picks
   - `_cache_valid()` / `_refresh_cache()`：优先 `v100_trades.json`
   - `get_version_trades('V88')`：V100 存在时返回 V100 trades
   - `reload_metrics()`：优先 `v100_report.json`
   - 扫描日期/文档说明中将 V100 report 放在 V99/V98 前面

4. **每日任务链路必须同时升级**
   `smc_daily_ops.py` 的 `run_shadow_selector()` 应连续执行：
   `v98_reachable_5r_probability_gate.py → v99_high_wr_production_gate.py → v100_structural_net_gate.py`

   同时：
   - `build_log()` 优先读取 V100 active picks
   - `files` 元数据加入 V100 active/report
   - daily ingest 候选池加入 V100 active picks

5. **验收必须同时覆盖 API 和浏览器页面**

   必跑：
   - `python3 -m py_compile smc_unified.py smc_daily_ops.py v100_structural_net_gate.py`
   - 重跑 `v100_structural_net_gate.py`
   - 重跑 `smc_daily_ops.py`
   - 重启 8890 或确保新进程加载代码
   - `POST/GET /api/reload`
   - `/api/picks`
   - `/api/live-prices`
   - `/monitor`
   - `/live`
   - `/backtest`
   - `/analysis`
   - `/autopsy`
   - `/docs`
   - 至少一个 `/kline?symbol=...&tf=daily&ver=V88`

## 字段缺失验收脚本片段

```python
import json, urllib.request
base = 'http://127.0.0.1:8890'
picks = json.load(urllib.request.urlopen(base + '/api/picks', timeout=60))
live = json.load(urllib.request.urlopen(base + '/api/live-prices', timeout=60)).get('picks', [])
keys = [
    'pick_date','join_date','选股日期','加入日期',
    'zone','zone_type','cost_line','smart_money_cost',
    'volatility_pct','volatility','engine','tp1','tp2','tp3','sl','rr'
]
for name, rows in [('picks', picks), ('live', live)]:
    miss = {k: sum(1 for r in rows if r.get(k) in (None, '', 0)) for k in keys}
    print(name, len(rows), miss, sorted({r.get('engine') for r in rows}))
```

通过标准：
- `/api/picks` 与 `/api/live-prices.picks` 上述字段缺失全为 0
- 页面实际显示 `选股日期/加入日期/Zone/成本线/波动`
- engine 显示新生产引擎，例如 `V100_STRUCTURAL_NET_5R_GATE`
- T+1 违规为 0

## 重要坑

- `/api/live-prices` 返回的是 dict，实时行在 `payload['picks']`，不是 `payload['data']`。
- 页面 HTML 中出现字符串 `undefined` 可能来自 JS 防御判断源码，不等于运行时字段为空；要结合浏览器快照或 API 字段缺失统计验证。
- 8890 端口重启时可能残留旧进程；必须用端口占用确认新代码已加载。

## V101 多周期/DNA/多组合候选白名单闭环

当用户要求处理“多周期字段缺失 / 每股 DNA 缺失 / BOS_CONTINUATION 未设计 / 不同信号不同入场出场 / 当前生产仍是单组合”时，采用 V101 合同层做最小变更：

1. **生产池与候选池严格分离**
   - `PRODUCTION_COMBO_WHITELIST` 只保留已验证生产组合，例如 `REVERSAL_SSL_CHOCH_DEMAND_OB_STRUCTURAL_5R`。
   - `CANDIDATE_COMBO_WHITELIST` 放新组合，例如 `CONTINUATION_BOS_PULLBACK_STRUCTURAL`。
   - 不要把 BOS_CONTINUATION 直接加入 production whitelist；它必须先作为独立候选池统计。

2. **BOS_CONTINUATION 候选门禁示例**
   - `combo_contract_key == CONTINUATION_BOS_PULLBACK_STRUCTURAL`
   - `mtf_trend_permission == MTF_LONG_ALLOWED`
   - `tp2_rr >= 5.0`
   - `tp3_rr >= 8.0`
   - `expected_tp2_net_pct >= 0.8`
   - `0 < risk_pct <= 1.2`
   - 满足后标记：
     - `combo_candidate_whitelist_v101 = true`
     - `combo_candidate_eligible_v101 = true`
     - `production_grade_v101 = BOS_CONTINUATION_CANDIDATE`
   - 但仍保持 `production_eligible_v101 = false`。

3. **必须输出独立文件和报告字段**
   - `/root/.hermes/smc_opt_v101_mtf_dna_combo_contract/v101_bos_continuation_candidates.json`
   - `bos_continuation_candidate_total`
   - `bos_continuation_candidate_stats`
   - `combo_counts_candidate_whitelist`
   - `candidate_combo_whitelist`

4. **日报链路也要同步**
   `smc_daily_ops.py -> v101_contract_summary` 必须包含：
   - `bos_continuation_candidate_total`
   - `bos_continuation_candidate_stats`
   - `combo_counts_candidate_whitelist`
   - `candidate_combo_whitelist`

5. **验收标准**
   - `production_total` 不因候选池新增而变化。
   - `combo_counts_production` 仍只包含生产白名单组合。
   - `prod_has_bos == 0`。
   - BOS 候选字段缺失为 0：`trend_tf/signal_tf/entry_tf/weekly_state/daily_state/m60_state/mtf_stage/mtf_trend_permission/smc_dna/combo_contract_key/combo_family/combo_contract/zone/cost_line/volatility_pct`。
   - `/api/picks`、`/api/live-prices` 字段缺失仍为 0。
   - 浏览器 `/monitor`、`/live` 不出现 `undefined/null`，且不会显示未晋级生产的 BOS 候选。
