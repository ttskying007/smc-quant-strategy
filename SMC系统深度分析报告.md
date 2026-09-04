# SMC 策略系统全量深度分析报告（最终版）

> 基于用户核心理念：**不同股票 × 不同 SMC 指标组合 × 按发生时间顺序 × 不同时间阶段/周期 × 自动组合 → 寻找聪明钱**
> 数据源：本地完整镜像 `E:\test\smc_project\hermes`（scripts 1339 文件/30.9 万行 + smc_opt 72 版本目录 + smc_audit 5495 项 + skills/trading 26 引擎资产）
> 分析方法：4 个并行子代理深度分析（核心引擎/v11 时代/v25 流水线/全版本指标）+ 主代理代码级验证 + 8 份治理文档精读
> 完成时间：2026-08-17

---

## 一、系统设计意图：如何"寻找聪明钱"

### 1.1 核心理念 → 系统实现映射

| 用户概念 | 系统实现 | 证据（文件+行） |
|---|---|---|
| 不同 SMC 指标 | FVG / IFVG / OB / CHOCH / MSS / Sweep(SSL/BSL) / Breaker / POI / 结构 / 流动性 / EQL / PO3 / Pinbar / OTE | sequencer_v11.py NORMALIZE_MAP:191-212；smc-core-concepts SKILL.md |
| 按发生时间顺序组合 | 信号序列模板（Platinum/Gold/Silver/Bronze/Scout 五级） | sequencer_v11.py SEQUENCE_DEFS:34-188 |
| 序列时间窗口 | Gold=Sweep→CHOCH→FVG→OB，窗口 3/4/3 K 线 | sequencer_v11.py:36-51 |
| 不同周期组合 | MTF 共振（周线趋势+日线结构+小时确认 3 层对齐） | smc_unified.py _api_resonance |
| 不同时间阶段 | 状态机阶段 W1→D1→D2→D3→D4→H1→H2→H3→H4→E | v676 章程:30-42 |
| 自动迭代 | hermes agent 每日生成大量版本脚本（峰值单日 65-81 个） | v25_timeline 数据 |
| 寻找聪明钱 | SMC 本体：流动性扫损(raid)→结构转换(CHOCH)→因果 POI→reclaim→takeover | v697-v701 SSL reclaim |

### 1.2 系统演化三阶段

**阶段一（2026-05-08 ~ 06-13）：信号序列自动组合 + 生产 gate 链**
- v11 体系（5-08~5-15 一周生成 306 脚本）：五级信号序列模板 + 自动优化
- 生产 gate 链：V65→V66→V67→V68→V70→V85→V86→V87→**V88**（6-13 生产契约）
- 早期指标虚高：V65 WR 88.81%（143 笔）、V70 WR 98.51%（67 笔）

**阶段二（2026-06-14 ~ 07-14）：gate 研究系列 + 因果性觉醒**
- V89-V185 研究 gate（72 目录），V167 production_write=true、V185 因果失败被拒
- 7-14 因果生产重建计划：确立五层单向架构 + fail-closed + EMPTY_BOOK

**阶段三（2026-07-14 ~ 08-14）：严格因果流水线（当前）**
- generator→independent_oracle→frozen_t1_replay→closure 四件套成熟（v432-v516）
- PIT 事件本体探索（v561-v625：margin/buyback/incentive/pledge/earnings）
- 三周期纯 SMC 状态机（v676 章程）→ v697-v701 SSL reclaim 落地
- 当前生产：FAIL_CLOSED_REPLAY_GATE_FAILED（正确空仓）

---

## 二、核心架构（已核实）

### 2.1 五层单向生产架构（7-14 计划文档）
```
[全市场原始行情] → [staging epoch] → [COMMITTED epoch manifest]
→ [outcome-free 本体生成器] → [独立语义 Oracle] → [单次冻结 T+1 回放]
→ [当前全市场 raw scanner] → [生产 registry] → BUY_VALID / EMPTY_BOOK
```

### 2.2 数据层（健康）
- kline_cache 19,192 文件（daily_750/300、60min_500/200、weekly_200、15min）
- epoch 机制：kline_epoch_current.json（8-14 COMMITTED，market_date 20260814，覆盖 99.98%）
- Sina 主源（Baostock 7-19 BLACKLISTED）；v536 sina 缓存 5,528 完成

### 2.3 生产控制面（8-13 快照）
- production_registry.json：`FAIL_CLOSED_REPLAY_GATE_FAILED` / strategy=null / buy_enabled=false
- positions.json：[]（空仓）；v526 pending：1 个（000009.SZ 7-21，已过期）
- 6-13 大隔离：935 个 V66 仓位被 quarantine

### 2.4 关键代码事实（铁证级）
1. **前端指标污染**：`reload_metrics()` 在 V88 下优先读 V185→V175→V172→V167→V102→V101→V100→V99 报告，V88 最后 —— 被否决版本仍在冒充生产指标
2. **v700 artifact 错位**：v700_scanner.py:16 变量名 V697 指向 v517 文件、V698 指向 v520 文件；且 v700 是 v521 复制残留（report 写到 v521_report.json L152、artifacts 键指 V697/V698 L151），仪表盘漏斗读 v700、V517 bundle 读 v521 —— 两个"同一"漏斗数据源不一致
3. **v697 本体漂移**：v697_seed.py:109 "volume is diagnostic-only" 但 docstring 假设 3 写 top-quintile、causal_trace 写 high_volume
4. **显示层与 scanner 脱节**：仪表盘"量能前20日Top20%"（smc_unified.py L2383）、"量能分位低于 0.80 不进入响应检测"（L2450），但 v700 scanner 从不按量能判定（L104-109 只记录 vol_rank、L70 拒绝条件不含量能）；且 stage 'SWEEP_RECLAIM' 从未被发出 → funnel['sweep_reclaim'] 与 ['high_volume_sweep_reclaim'] 恒等（v700 L138-140）
5. **V185 推广链与注册表冲突**：`_promoted_contract_dir`（L274-296）、`_promoted_trade_file`（L995-1013）、`reload_metrics`（L1744-1759）在存在 v185_report.json 时仍推广 V185，而 v432 审计已 REJECT_V185；`/api/kline_full?ver=V88` 在 EMPTY_BOOK 下仍能加载 V185 交易
6. **组合逻辑四种**（smc_unified 层）：① 漏斗门（v700 diagnostic_funnel 6 阶段：CONFIRMED_SWING_LOW→SSL_BREACH→SWEEP_RECLAIM→HIGH_VOLUME→RESPONSE_BREAK→FULL_SETUP）；② 跨版本组合（`_merge_v90_daily_picks` 按 V185>V175>V172>V167>V90 优先级；`_v100_production_rows` 白名单 V185/V175/V172/V167/V102/V101/V100 tier A）；③ 行级组合合同（`_apply_smc_field_contract` 按 event×zone 生成 REVERSAL_SSL_CHOCH_DEMAND_OB_STRUCTURAL_5R 等 4 类 key）；④ MTF/DNA（v101_mtf_dna_combo_contract）
7. **安全风险**：HUBBLE_BASE IP:3101 + X-API-Key "123456" **明文**（L5027-5028）；页面无鉴权
8. **死代码/不可达**：`if False` MSS 块（L6090）、`_api_history`/`_api_diagnostics` 硬编码 V31（L6951/6986）、`/tmp trading_sim`（L5836-5854）、engine_map 重跑分支因 registry 恒非 LIVE_READY 不可达（L6789）、`_empty_book_page` 硬编码"V517 冻结研究回测（387笔）"（L3346 会过期）、V44 summary 重复 JSON 键（L7107-7108）
9. **脏文件**：多处 `\n/root/.hermes/...py\n`（路径当文件名写入）

### 2.5 v11 时代组合与回测细节（子代理实测，行号级）

**信号体系**（signals_v11.py，2295 行实测）：**14 类信号** + 自适应阈值（ATR% 分 3 档波动率）：
- **FVG**（L182-308）：三根 K 线 gap 判定 + 颜色形态（全阳/全阴 continuation 增强）+ 分级（macro/meso/micro/nano）+ 堆叠/填充追踪
- **OB**（L698-834）：严格 ICT"反向末 K 线 + ≥2 根 impulse + 放量 >1.2×" + 摆动点距离加分
- **CHOCH**（L925-1100）：摆动点突破 + 位置约束（须在 20 根内 SSL sweep 之上，但无 sweep 时直接放行 —— 弱约束）
- **MSS**（L1865-1969）：3 根局部窗口破位（预警级）
- **PO3**（L1976-2156）：ACC→MAN→DIS 三阶段
- **Sweep**（L480-608）：BSL/SSL 影线破位 + 放量 + 次根反转确认
- **EQL / LiquidityVoid / RejectionBlock / BPR / IFVG / MitigatedFVG / BreakerBlock / OTE**（fib 0.5-0.618）
- 统一入口 `detect_all_signals_v11`（L2163-2295）sort by idx + 全局 seq —— "按时间顺序"的有序列表

**组合引擎**（v44_engine.py）三层漏斗：
1. **序列矩阵**（sequencer_v11.py）：16 个预定义序列（GOLD=Sweep→CHOCH→FVG→OB 窗口[3,4,3]、SILVER 三步、BRONZE 两步、SCOUT 单信号），时间分权重 **55%**（`temporal_score=exp(-avg_distance/4)`）—— 时间顺序是组合的第一权重
2. **四维共振**（resonance_v11.py）：tf×0.25 + indicator×0.30 + swing×0.15 + temporal×0.30
3. **入场决策 + 回踩确认**（V44 L1066-1214）：只收 FVG/OB/BreakerBlock + 量能 + 趋势过滤 + 共振门槛 + 质量分级 S/A/B/C/D（0.85/0.70/0.55/0.40）+ 回踩入场（15 根内回触区间）

**回测缺陷**（早期"高指标"不可信的根本原因）：
- **TP 前视偏差**：TP 用前方 120 根内 CHOCH/摆动点（实盘不可预知）
- **T+1 后补**：V6 同根 K 线触发 SL/TP；V476 仍有同日 exit，V477 补丁才强制（_patch_t1.py）；V44 入场用信号日收盘价
- **过拟合**：300 根日线单窗口、无年度分桶、无样本外；auto_optimizer 200 迭代**同一批数据**搜索（无 train/val 划分）
- **成本缺失**：PF=135/RR>9/WR>90% 类结果未计佣金/滑点/涨跌停
- **变体 bug**：v44_engine _a/_b/_c 的 bear pnl 符号错误；backup_v37 与 v11 的 BPR/IFVG 语义不同（混用即错）

**演进主线**（v11→v12→v14→v15→v17）：摆动点质量（对称确认/多 lookback 共识 [5,8,10,12,15,20]≥4 确认）→ OB 精度（位置扫描/位移 1.3-1.5x/趋势上下文）→ 结构状态机（HH/HL→CHOCH/BOS）→ 阈值 Pine 化（ATR 基准 5 档）—— 概念正确性持续提升，但回测纪律（T+1/前视/成本）直到 V477 才正面处理。

---

## 三、版本演进与回测结果（子代理 D 全量汇总：58 目录 83 报告 + 449 审计文档）

### 3.1 核心版本-指标表
| 版本 | 日期 | n | WR% | avg_pnl% | SL率 | avg_rr | 结论 |
|---|---|---|---|---|---|---|---|
| V66 | 6-12 | 137 | 90.51 | 20.65 | 8.8 | 5.02R | V88 前前端默认 |
| V67/V68 | 6-09/11 | 90,579/1,657 | 41.1/34.9 | 0.71/0.24 | 58.7/64.5 | 1.86/2.02R | **拒绝**（全市场扫描无期望） |
| V69 矩阵 | 6-11 | 1,693,559 | 62.47 | 2.22 | 37.0 | 1.21R | 研究矩阵（best combo n=30,380 WR 78.7） |
| V70 系列 | 6-12 | 51-7,479 | 58.7-98.5 | 0.48-3.95 | - | - | 全部 NO_PRODUCTION（n<100 或年度稀疏） |
| V81 | - | 47,612 | 53.27 | **-0.116** | - | - | **负期望** |
| **V85/V86** | 6-12/13 | 559/532 | 89.1/89.9 | 2.71/2.68 | 9.3/8.7 | - | 通过生产门禁（链上前驱） |
| **V88 生产** | **6-13** | **532** | **83.65** | **+2.87** | **12.97** | **2.44R** | **✅ 唯一正式生产契约**（n≥500、T+1=0、RR<1=0、年度 WR≥65%） |
| V91 | 6-13 | 523 | 90.25 | 2.69 | 9.75 | 2.11R | production_pass（研究判定，未写盘） |
| V97/V98 | 6-15/26 | 10,440/7,828 | 58.6/63.0 | 3.14/3.08 | 41.4/37.0 | - | 大样本 WR 不足 |
| V102 | 6-16 | 195 | 87.69 | 3.72 | 12.31 | 4.47x | 通过平衡门禁，受 V103a 拖累未上线 |
| V103a | 6-18 | 172 | 88.95 | 3.93 | 11.05 | 5.15R | **序列违规不晋级**（entry_before_reclaim） |
| **V104** | 6-19 | 487 | 54.62 | 0.42 | 42.92 | - | **❌ 经济失败**（2023/2024 WR 43-44%，语义过严崩塌） |
| V105 | 6-18 | 430 | 73.02 | 0.88 | 20.47 | - | **❌ 违反结构偏好**（唯一达标=0.6R 微止盈） |
| V152 | 6-22 | 127 | 92.91 | 2.94 | 7.09 | - | release_gate pass，无 live buy |
| V167 | 6-23 | 793 | 82.09 | 4.54 | 12.48 | - | PROMOTION_ARTIFACTS_PASS，未取代 V88 |
| V172/V175 | 6-23/7-17 | 247 | 83.81 | 6.05 | 8.91 | - | 晋级候选/仅语义标签 |
| **V185** | 6-26 | 334 | 86.23 | 6.56 | ~11.1 | - | **❌ REJECTED_CAUSALITY**（gate 全 true 但因果未证明） |
| V366 | 7-11 | - | - | - | - | - | **❌ 未来函数实证**（entry 先于确认 2-3 bar） |
| V443 | 7-14 | - | - | - | - | - | CAUSAL_REBUILD_COMPLETE__KEEP_EMPTY_BOOK |
| V517-V525 | 8-03/06 | 379-387 | 59.8-63.6 | +1.03-1.54 | - | 1.39-1.41 | FROZEN_REPLAY_FAIL（月度门槛失败） |
| **V699** | 8-14 | 17,600 | 53.30 | +1.18 | - | PF 1.38 | **❌ FROZEN_REPLAY_FAIL**（2023/2026 avg 负、月频不足） |
| V700/V701 | 8-14 | 2 pending | - | - | - | - | 空书运行，生产许可封锁 |

### 3.2 关键趋势（子代理 D）
1. **样本-WR 两难**：n>7,000 必然 WR 55-63%；80%+ WR 必须压到 60-800 笔 → 因果性/年度稳定性风险
2. **V88 后零晋级**：V236 后 10+ 条研究线（融券/质押/业绩披露/周线/WDH/SSL-reclaim）全部在冻结回放经济门槛失败（2023/2026 普遍为负收益）
3. **唯一生产**：V88（6-13 上线，2 个月后被判不可因果维持）→ EMPTY_BOOK
4. **教训版本**：V104（过度收紧崩塌）、V105（微止盈非结构解）、V185（指标达标≠因果成立）、V366（幸存者=未来函数）、V699（最新本体年/月维度失败）

---

## 四、迭代流水线方法论（v25 时代，子代理 C 行号级实测）

### 4.1 五层流水线实现（v25/，全部实际代码验证）
| 层 | 文件 | 输入→输出 | 验证 | 失败处理 |
|---|---|---|---|---|
| L0 epoch | refresh_daily_750.py | 全市场日线→staging→COMMITTED manifest（epoch_id/market_date/gate） | 请求覆盖、stale/future/回归检查 | 删 staging，旧 epoch 不变 |
| L1 seed | v517/v697 | kline_cache→outcome_blind_seeds + seed_gate_latest.json | no_outcome_fields、strict_chronology、年度支持≥300/40 | V517_SUPPORT_FAIL__CLOSE_WITHOUT_OUTCOMES |
| L2 oracle | v518/v698 | 独立重算 identity 集合（symbol+3 日期 key） | missing==0 and extra==0（v698 实测 18318/18318） | V518_ORACLE_FAIL__NO_REPLAY |
| L3 replay | v519/v699 | 冻结执行：次日开盘入场、SL=sweep_low×0.99、TP=入场前可见 swing high、time20、费 0.20%、串行单仓 | n≥300/年、每月>4、WR≥55%、AvgNet≥0.5%、PF≥1.15、payoff≥0.7、T+1=0 | CLOSED_NO_VARIANTS（v519 WR59.8%/PF1.5 但 2026 avg -2.32%；v699 WR53.3% 2023/2026 负） |
| L4 scanner+registry | v700/v701/v526 | 仅 committed date 最后 K 线产 PENDING_NEXT_OPEN | stop<open<target 才 BUY_VALID，否则 reject | registry 保持 FAIL_CLOSED_REPLAY_GATE_FAILED |

### 4.2 SSL reclaim 本体定义（v697/v700 纯价格版）
source event（3/3 确认 swing low）→ POI 锚点（最近未消耗 SSL）→ touch（0.3% 影线破位）→ reclaim（收盘>swing low）→ response（下一 bar 收盘>sweep high）→ eligible entry（再下一日开盘，T+1）→ invalidation（SL=sweep_low×0.99）→ TP（入场前可见 swing high）→ scanner 验收（stop<open<target）

### 4.3 漂移 4 类证据（子代理 C）
1. **量能过滤删除但契约文本保留**：v517:112 有 `rank>=VOL_TOP_QUINTILE` 门，v697:110 删除；但 v697:197 frozen_contract 仍写 top quintile、causal_trace 写 high_volume、volume_rank_prior 成死代码
2. **变量名/artifact 错位**：v700:16 变量 V697 指向 v517 文件、V698 指向 v520；release_blocker 标签写 V698 但读 v520 的 audit_pass（真正 v698 字段是 oracle_pass）
3. **产物命名错位**：v697 报告写 v517_report.json、v698 写 v518_report.json、v700 写 v521_report.json（复制残留）
4. **治理层面**：v633/v672/v692/v696 反复"STOP"，v697 纯价格变体 8-14 仍跑通全链，support 门槛 300/40 低于蓝图 1000/300/500

### 4.4 生产 registry 状态机（V1→V2）
- V1：EMPTY_BOOK | FAIL_CLOSED_CONTROL_EVIDENCE_INVALID
- V2（v526 promote）：FAIL_CLOSED_REPLAY_GATE_FAILED → ADMISSION_FROZEN_PENDING_EXECUTION → FAIL_CLOSED_MISSING_COMMITTED_SCANNER_EPOCH → LIVE_READY_NO_CURRENT_SIGNAL → LIVE_READY
- BUY_VALID 九条件（smc_monitor_state.py:269-289）+ pending SHA-256 完整性 + 开盘价∈(stop,target)

### 4.5 v25 目录统计
825 文件：audit 166、seed/generator 92、replay 85、gate 80、source/pit 76、oracle 55、scanner 14、state_machine 13；命名模板 `v{NNN}_{本体}_{角色}.py`，角色链 seed_gate→oracle→replay→metric_audit→scanner→observer

### 4.6 设计评价（子代理 C）
**亮点**：outcome-blind 纪律、独立实现互验、单次冻结回放、事务化 epoch、fail-closed 系统性
**缺陷**：复制粘贴漂移污染链完整性（潜在误授权路径）、契约文本与代码不一致、治理无代码级门禁（[0] frontier registry 只存在于文档）、死代码暴露机械编辑、反复重测同一信息族（v519 与 v699 结果同构：2025 强、2023/2026 负）

---

## 五、当前状态评估

### 5.1 系统状态（8-13/8-14 权威）
- 数据层：✅ COMMITTED epoch（8-14）
- 生产层：✅ fail-closed 空仓（无 BUY_VALID 是正确状态）
- 研究层：🔄 v697-v701 SSL reclaim 链完成，但 V699 经济失败（WR 53.3%<55%，2023/2026 负）、V700 谱系断裂（读错 artifact）、V697 本体漂移（量能门槛被删但文本保留）

### 5.2 核心瓶颈
1. **过拟合困境**：小样本高 WR 全是幻觉；大样本真实边缘 53-58%，达不到 55%+0.5% 门槛
2. **小赢大亏**：所有本体普遍"高 WR 低 payoff"（V603 WR 34.85%、V477 payoff 0.47、V473 payoff 0.44）
3. **谱系断裂**：迭代太快导致本体定义漂移（v517→v697）、artifact 错位（v700）、展示污染（reload_metrics）
4. **无版本控制**：不可追溯、不可回滚
5. **文档滞后**：SMC_PROJECT_GRAPH.md 停在 V88（5-23），实际 v701

### 5.3 系统优点（值得保留）
- 方法论成熟：outcome-blind、独立 Oracle、冻结回放、fail-closed 已是制度
- 数据工程完善：epoch 事务化、源隔离、覆盖审计
- 自我纠错文化：8-14 审计主动揭露谱系断裂
- 治理文档齐备：章程/蓝图/计划/closure 完整

---

## 六、结论：系统如何"寻找聪明钱"

系统完整实现了用户的理念框架，但**尚未找到可生产的"聪明钱"本体**：
1. 组合框架已成熟（指标×时间序列×周期×阶段）
2. 因果验证已严格（冻结回放消灭未来函数）
3. 但经济性始终不达标（真实胜率 53-58%，且小赢大亏）
4. 当前正确状态：EMPTY_BOOK（宁缺毋滥）

下一步方向（待用户决策）：Lane A-D 新信息维度（公告数值预测/公司条款/订单流/行业资金）或三周期状态机的继续打磨 —— 但必须遵守"新因果维度"原则，禁止对已关闭本体调参。

---

## 附录：补充打包
- skills/trading（26 个早期引擎资产，MD5 26EBF18E 校验通过）
- kline caches 5 目录（kline_cache 19,192 文件等，MD5 3A574EDB）
