# V251/V252 研究方向闭环：停止局部过滤，转向新供给/新执行机制

## 触发场景
当 V185 生产基线之后出现类似 V246/V248 这种“历史指标很强，但当前 scanner 无新供给、局部弱月仍存在”的候选版本时，使用本参考进行下一步研究判断。

## 已验证结论
- V246/V248 历史候选强：573 笔，WR=94.4154%，AvgPnL=7.6022%，min_year_n=71，all_year_WR_min=92.22%，micro=0.349%，T+1=0。
- 但 V247 current smoke 显示当前 parent raw_rule_rows=0 / V246 current rows=0，因此不能生产晋级、不能写 watchlist/frontend。
- 弱月仍为：202312（12笔/WR66.67%/4亏）、202511（11笔/WR81.82%/2亏）、202601（12笔/WR83.33%/2亏）。
- V249 归因：亏损主要集中在 DEMAND_OB_TRUE_TAKEOVER_RECLAIM / BEAR_RISK，以及小部分 BOS_CONTINUATION。
- V250/V251 证明继续做 path/regime/局部过滤不可晋级：
  - 日期/月度特化规则虽然能修数字，但属于日历过拟合，禁止生产。
  - 全局 breadth/risk 过滤会破坏年度覆盖或 avg。
  - DEMAND_RECLAIM + BEAR_RISK 条件过滤不能消除弱月。
- V252 post-entry progress gate 只边际修 202601/BOS，不能解决 202312/202511 的 DEMAND/BEAR_RISK 核心弱点；且 post-entry 字段不能作为 pre-entry 生产 selector。

## 后续执行结果（V253/V254）
- V253 replay exit probe 已执行：针对 `DEMAND_OB_TRUE_TAKEOVER + BEAR_RISK/V185_CHILD` 做真实 K 线执行出场（zone fail / cost fail3 / no-progress3 / profit guard / max5 / combo）。结论：全部不可生产；最佳 `zone_fail` 仍为 N=573、WR=94.0663%、Avg=7.2797%、all_year_WR_min=90.14%、弱月仍 3 个，且伤害 104 笔原盈利。不要继续做局部出场规则主线。
- V254 current supply recon 已执行并在重跑 V90 scanner 后复核：最新行情 `v128_parallel_shadow_candidates` recent10 有 50 行、non-overlap V246 有 42 行，但全部属于 `SSL_SWEEP_CHOCH_REVERSAL + BEAR_RISK` 三类 POI；用历史 V230 同族字段（chase/risk/zone_width/reclaim_pos）回测无任何 frontier 通过历史门槛。结论：有当前供给，但不是已验证可用供给，不能写 watchlist/frontend。
- V90 scanner 实测 2026-07-01：scanned_symbols=4655，all_contract_candidates=906，recent_active_candidates=16，active_entry_window_candidates=0，watch_only_expired_entry_window=16；v128 recent45=1827，v125_contract_pass_recent45=0。

## 后续执行结果（V255）
- V255 current-compatible historical bridge 已执行：以最新 V128 current non-overlap recent10 的 42 行为约束，只使用当前 scanner 已具备的前置字段（`poi_source/market_state/risk_pct/zone_width/reclaim_pos/reclaim_above/touch_to_reclaim/entry_chase/bars_since_entry`），回到历史 V230 非 V246 样本做历史桥接规则搜索。
- 当前 42 行构成：`BEAR_RISK+DEMAND_OB=38`、`BEAR_RISK+FVG_Demand=3`、`BEAR_RISK+OB+FVG=1`。
- 历史同族非 V246 样本质量很差：`BEAR_RISK+DEMAND_OB` 1983 笔 WR=64.55%/Avg=2.78%，`FVG_Demand` 405 笔 WR=58.27%/Avg=2.22%，`OB+FVG` 179 笔 WR=62.01%/Avg=2.87%。
- V255 测试 57 个 current-compatible 前置规则，production/research frontier 均为 0。结论：不能把当前 `SSL_SWEEP_CHOCH_REVERSAL + BEAR_RISK` 供给通过现有 scanner 字段桥接到生产；必须拒绝，直到新增真正 source layer。

## 后续执行结果（V256/V257）
- V256 pre-entry weekly/daily structure source-layer 已执行（no-write）：从本地 `daily_750` 只用 entry 前数据构造 5/10/20/40/60 日位置、波动区间、量比和 5 日聚合“周线”结构特征；560/573 历史行覆盖。80 个单因子门禁 0 production / 0 research frontier。最佳 `v256_range10>=5.84918` 仅 N=504、WR94.25、Avg7.87、minYear67、弱月仍3；`v256_pos20<=86.5033` 虽 WR95.24/yearWRmin94.2，但 N=504/minYear62/弱月4，不可用。结论：周线/日线位置结构层不能修复 V246 弱月。
- V257 weak-month loss root-cause 已执行（no-write）：202312亏损为 DEMAND_OB_TRUE_TAKEOVER/V185_CHILD 混合（TIME+SL），202511/202601亏损为 BOS_CONTINUATION；亏损行的共同特征是入场前个股处于更高 20/40/60 日位置、周线 close_pos4 更高，同时部分市场/行业参与偏弱。但 oracle 单因子最多移除5个弱月亏损时会破坏 N/minYear/弱月覆盖；不能转生产 selector。结论：弱月低胜率是“高位 continuation + 局部弱广度/行业参与 + 小样本月份”叠加，不是可用的单一前置字段问题。

## 后续执行结果（V258/V259/V260/V261）
- V258 current-compatible rich source mining 已执行（no-write）：基于 V230 非 V246 历史池 + 最新 current recent45 non-overlap 204 行，测试 3280 个当前兼容字段规则；production_pass=0、research_pass=0。结论：当前 SSL/BOS 的 MIXED/BEAR/ACCUMULATION 供给无法用现有 scalar/source 字段桥接到生产。
- V259 source-safe BOS_CONTINUATION rebuild 已执行（no-write）：新增 raw K 线前置特征（event break/body/prev10/prev20 range/pre-entry pullback/gap，未使用 entry-day high/low/close），3177 规则中 1 个历史 production pass：`BOS_CONTINUATION AND raw_prev20_range_pct>=39.8518 AND raw_event_body_pct>=75`，combined N=614、WR=94.1368%、Avg=7.6485%、minYear=72、allYearWRmin=92.22%、micro=0.6515%、T+1=0；但 current_recent45_hits=0。
- V260 independent audit/current smoke 已执行（no-write）：V259 最优规则 selector 独立复算匹配，selector_leak_fields=[]，entry_day_high_low_close_used=false；历史 production_gate_pass=true，但 current_actionable_rows=0，因此 KEEP_SHADOW_NO_WRITE。
- V261 current supply mismatch closure 已执行（no-write）：最新 current 204 行 raw feature 覆盖 204；event=BOS 107/SSL 97，market=MIXED 99/BEAR_RISK 73/ACCUM 32，完全没有 BULL_CONTINUATION。V259 生产 selector 当前失败原因：97 行非 BOS、104 行 BOS 但 prev20 range<39.8518、3 行 range ok 但 body<75、最终 selector_match=0。要求 current_hits>=5 时，V259 frontier production/research pass 全为 0；>=1/2 仅少量 research shadow，不可生产。结论：V259 是历史强但当前无供给；当前有供给但质量结构错误，不允许写 watchlist/frontend。

## 后续执行结果（V262/V263/V264）
- V262 fresh BOS retest generator 已执行（no-write）：raw daily 生成 26,454 行、current recent45 938 行；raw child WR=43.47%/Avg=0.081%，169 个 current-compatible 规则 0 production / 0 research frontier。结论：新 BOS retest 供给本身噪音过大，不能生产。
- V263 60m pre-entry confirmation 已执行（no-write）：V262 child 60m 覆盖 5,770/26,408=21.85%，covered child WR=40.92%/Avg=-0.10%；298 个 60m 前置确认规则 0 production / 0 research frontier。结论：60m 前置确认不能拯救 V262，且本地 60m cache 多数不到 202607，不能 current 路由。
- V264 raw daily SSL sweep reclaim source probe 已执行（no-write）：全市场生成 95,149 行、current recent45=6,803 行、non-overlap=6,799；raw child WR=42.06%/Avg=0.351%、weak_month_count=37。单因子/双因子 source-safe 规则在最低 child WR/Avg 剪枝后没有可用候选，0 production / 0 research frontier。结论：流动性 sweep reclaim 有当前供给但质量结构错误，禁止写 watchlist/frontend。

## 后续执行结果（V265/V266）
- V265 breakout-retest reclaimed-support source-layer 已执行（no-write）：全市场生成 51,373 行、current recent45=2,463；raw child WR=43.13%/Avg=0.244%、weak_month_count=36；source-safe 单/双因子无候选通过最小 child WR/Avg 剪枝，0 production / 0 research frontier。结论：突破后回踩“支撑互换”有当前供给但质量结构错误，禁止写 watchlist/frontend。
- V266 limit-up pinch reclaim source-layer 已执行（no-write）：全市场生成 8,028 行、current recent45=510；raw child WR=43.81%/Avg=0.424%、weak_month_count=35；0 production / 0 research frontier。结论：A股涨停/强势脉冲后缩量回踩再确认，日线级别仍无法形成可用 frontier。
- 连续 V262/V264/V265/V266 证明：daily-only 新信号家族虽然都有当前供给，但裸信号质量稳定在 WR≈42–44%、Avg≈0.08–0.42%，单/双因子无法桥接到 V248 级生产门槛。下一步不应继续 daily-only raw source probes，除非引入真正新数据层（盘中/竞价/盘口/行业资金流）。

## 后续执行结果（V267/V268/V269）
- V267 industry rotation + stock retest source-layer 已执行（no-write）：使用证监会行业分类构造行业 breadth/momentum/turnover proxy，再生成突破回踩候选。全市场 all=22,493、non-overlap=22,491、current_recent45=898；裸 child WR=41.17%/Avg=0.45%，规则前置剪枝后 0 production / 0 research frontier。结论：粗行业轮动供给充足但质量结构错误。
- V268 Eastmoney thematic board rotation + stock retest source-layer 已执行（no-write）：使用东财 496 个概念/行业板块会员构造更细主题轮动。all=12,677、non-overlap=12,676、current_recent45=261；裸 child WR=41.75%/Avg=0.536%。最佳小样本规则 `board_rank_ret5<=5 AND board_rank_turnover<=20 AND board_ret5>=2.0` 仅 child N=20/WR65.0/Avg4.27，combined N=593/WR93.42/Avg7.49/yearWRmin91.21/weak_month=7，未过 production/research。结论：日线派生的主题板块轮动 proxy 仍不可生产。
- V269 corrected-cache 60m confirmation retest 已执行（no-write）：发现 V263 记录的 `m60_dir=/root/.hermes/kline_cache_60min` 与当前实际 60m cache 位置不一致，使用 `/root/.hermes/kline_cache` 重跑 V262 60m 前置确认。覆盖 2,436/26,408=9.22%，covered child WR=36.12%/Avg=-0.683%；149 个规则 0 production / 0 research frontier。结论：修正 cache 后 60m 更差，不能拯救 V262，且 60m 覆盖不足以 current 路由。
- 连续 V267/V268 证明：仅用日线派生的行业/板块轮动 proxy 不能形成 V248 级别新供给；连续 V263/V269 证明：现有 60m cache 不足且确认层不能拯救噪音日线 source。

## 下一步研究规则
1. 不要继续在 V246/V248 上叠加局部过滤作为主线。
2. 不要继续把 BEAR_RISK demand reclaim 的局部 replay exit 当主线；V253 已证明会伤害大量盈利且不能修弱月。
3. 不要继续尝试用当前 V128 已有字段（risk/zone/reclaim/touch/chase）桥接 `SSL_SWEEP_CHOCH_REVERSAL + BEAR_RISK` 当前供给；V255 已证明历史同族基线过差且无可用 frontier。
4. 不要继续用单股日线/周线位置、波动、量比这类 pre-entry 标量修 V246 弱月；V256/V257 已证明无 frontier。
5. 当前供给方向必须新增 source layer / 信号家族，而不是把 V128 当前 SSL BEAR rows 直接接入生产。可继续的方向仅限 shadow/no-write：
   - 非 V246/V248/V128 同源的新信号家族；
   - 新增可在 current scanner 复现的 source layer，例如真实 intraday 结构确认、盘口/成交额质量、行业/板块资金流，而不是已有 breadth/周线标量；
   - 重新生成 current non-overlap supply，并用历史独立审计证明同族有效。
6. 每个候选必须先过：历史独立审计 + current scanner smoke，再考虑前端/watchlist。

## 预定义可用/不可用标准
|级别|硬门槛|
|---|---|
|生产可用|date-independent、无泄漏、current scanner 最新行情有 rows、N>=570、min_year_n>=70、WR>=94%、Avg>=7.6%、all_year_WR_min>=92%、micro<=1%、T+1=0、弱月<=1、独立审计匹配、前端/watchlist smoke 通过|
|研究可用|能解释或修复 2/3 弱月，或产生新的 non-overlap 当前供给，同时不破坏 V246/V248 历史基线|
|不可用|月份/日历特化、结果字段/未来字段泄漏、post-entry 字段作为 pre-entry selector、年度覆盖被砍、current rows=0 却声称可生产|

## 报告格式偏好
给 Lei 汇报此类研究时必须表格化：基线表、已完成/未完成表、候选规则对比表、最终判定表。不要用长段落替代表格。