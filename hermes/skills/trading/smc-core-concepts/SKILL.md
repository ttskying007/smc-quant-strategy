---
name: smc-core-concepts
version: 2.0.0
description: >-
  ICT / Smart Money Concepts (SMC) 核心知识库。
  涵盖：FVG、Order Block、OB上下文矩阵(CTX→POI)、市场结构、流动性、OTE、Killzone、PD Array、Pinbar。
  V6: POI=OB/FVG/Pinbar, CTX=LIQ/STRUCT, 15种组合矩阵。
  生产晋级/前端闭环参考：references/v152-production-promotion-closure.md（promotable backtest → trades/report；live picks 保持 daily scanner 来源）。交易量不足或大量0.5%左右/BE_SL微利退出时，先看 references/production-volume-micro-pnl-gate.md。V153/V164晋级前置门禁：历史gate通过仍不可直接写生产；必须补loss rows、excluded bucket、scanner-time exact selector；scanner dry-run缺少历史selector字段如`v143_lifecycle_status`时只保留诊断候选，见 references/v153-pre-promotion-scanner-contract.md。V152→V161 晋级审计（前端已路由≠生产有效；synthetic BE/micro-pnl 污染、scanner-time c
  Scanner 规则完整性门禁参考：references/scanner-rule-integrity-gate.md（历史回测子集可能已预过滤，真实 scanner 推广前必须显式验证 TRUE_TAKEOVER_2/3 前置条件、无 outcome 泄漏、无非 takeover BUY）。
  V152→V161 晋级审计（前端已路由≠生产有效；synthetic BE/micro-pnl 污染、scanner-time contract、月度稳定性分开判断）见 references/v152-v161-production-promotion-audit.md。
  当用户询问"SMC"、"ICT"、"聪明钱"、"FVG"、"Order Block"、"OB"、"Pinbar"、"CTX"等概念时触发。
user-invocable: true
metadata:
  category: trading
  emoji: 🧠
  tags: [ict, smc, trading, fvg, order-block, liquidity, market-structure, killzone, ote, ifvg, eql, po3, mss, breaker-block, pinbar, ctx-poi-matrix, v6]
---

# ICT / Smart Money Concepts 核心知识库

## 最新研究闭环指针

- **日线量价 / Wyckoff 本体库存闭环（V517–V537）**：V517 日线努力—结果吸收的支持与独立 Oracle 均通过，但 rolling-cache 的最终 latest 冻结严格 T+1 replay 为381笔，2026已平仓39笔，低于预注册每年>=40门槛，故策略许可已撤销（`FAIL_CLOSED_REPLAY_GATE_FAILED`）。V525 高RR子集支持不足；V527 Spring/Test/SOS、V530 SOS/Backup、V533 Selling Climax/AR/ST/SOS 均因冻结回放的经济性或跨年稳定性失败而关闭；V537 严格 No-Supply 三日缩量缩幅→需求扩张只有102个结果盲种子（年5/48/37/12），支持不足，未打开结果即关闭。不能对这些关闭路径改窗口、阈值、SL/TP、持有期、年份或状态桶。权威谱系、数据资格、预注册门槛与生产空仓边界见 `/root/.hermes/smc_audit/v538_v517_lineage_reconciliation_and_frontier_closure_20260721.md`。

- **多周期 raw 缓存、多源观测与保留合同（V536）**：在进入15m/60m/日线/周线联动的价格结构、量价吸收、Spring/Test、SOS/Backup或Selling Climax本体前，先冻结同源、同价格口径的完整OHLCV缓存。先对代表证券实测完整目标区间；若返回完整历史，优先全区间 raw 15m 请求而非沿用旧季度/年度分块假设，并以逐交易日精确验收作为静默截断门禁：15m=16 bar，60m=4 bar。raw 60m 可由四根同源15m精确聚合；weekly 只能由独立 raw daily 聚合（不得假定日线和分钟聚合完全相同）。历史 raw writer 与多源健康 witness 必须分离：允许监测和交叉审计，不允许按 bar 静默混源补洞。若用户要求随机节奏，只能随机化锁保护的批次大小与批次间等待；单证券所需的完整历史范围不得随机缩短。磁盘保留策略只清理明确过期的重复 reports/logs、系统 journal 与可再生包缓存；当前 raw cache、生产状态、sessions、snapshots 与冻结审计不得删。构建/加速前先以实测单证券耗时计算期限容量，禁止以移除覆盖门禁或未验证并发来伪造速度。详见 `references/v536-multitimeframe-raw-cache-source-health-and-retention.md`。

- **冻结回放事件身份与量价新本体门禁**：滚动K线缓存的 bar index 不是稳定身份；冻结 seed 必须以 `symbol + trading dates` 重绑定，cache/source更新后必须从 outcome-blind generator → 独立 Oracle → 一次严格T+1 replay → 独立指标审计全链路重跑。对新增量价本体，先预声明支持和质量门槛；一次冻结回放失败即关闭，禁止再搜窗口、量比、SL/TP、持有期或状态变体。V517/V527 实证、复现步骤和生产空仓边界见 `references/frozen-replay-date-identity-and-volume-ontology.md`。

- **研究证据谱系对账（先纠正分类、再决定研究是否重开）**：当不同审计报告对同一信息源给出“覆盖不足”与“已完整回放”等冲突结论时，必须从上游 `latest` 工件一路追到映射、特征物化和冻结 replay，并核查脚本是否硬编码读取过期的带日期路径。严格区分 `CLOSED_UNAVAILABLE`（PIT/覆盖/原始对齐不合格，未做经济结论）与 `CLOSED_ECONOMIC`（数据已合格、固定 schema 的冻结 replay 失败）。纠正旧诊断不得成为重开阈值、窗口、组合、出场或子集挖掘的理由；全程 no-write。详见 `references/research-lineage-reconciliation.md`。

- **前端三层分离与逐笔合同**：当生产为 EMPTY_BOOK 或研究仍 Shadow 时，当前候选、冻结研究 replay、旧系统历史 artifact 必须分别只读展示；K线同时显示 SMC视觉上下文、因果节点、BUY/SELL/SL/TP 与逐笔 RR，严禁历史回填为当前选股。EMPTY_BOOK 锁定的是写入，不应删除图表版本/周期/信号开关或历史审计入口；可视SMC上下文必须标记为 display-only，不能扩张冻结交易集合。详见 `references/frontend-research-production-audit-separation.md` 与 `references/empty-book-visual-audit-and-rr-feasibility.md`。

- **结构目标RR可行性先验门禁（V525）**：结构SL/TP即便均为入场前可见锚点，也必须逐笔计算 planned RR，不能把“结构目标”自动当作可生产。V517 的预入场 `RR>=1.5` 审计将404个源seed缩至79个（逐年16/35/19/9），支持门槛失败且严格回放 WR30.38%、AvgNet+0.401%；禁止以稀疏高RR子集替代全市场生产策略。完整合同与验收见 `references/empty-book-visual-audit-and-rr-feasibility.md`。

- **生产许可不等于当前买入，且不可把“无候选”误写成“未许可”**：当冻结 replay、独立 Oracle/指标、逐年稳定性与 current-scanner 完整性均通过，且用户明确要求生产化时，应授予策略级 `production buy license`，而不是继续把它停在 shadow。策略级许可与逐笔 `BUY_VALID` 必须分离：无当前 raw scanner 行时 registry 为 `LIVE_READY_NO_CURRENT_SIGNAL`、`buy_enabled=true`、仓位为零；不得因无候选撤销许可，也不得历史回填。每笔买入仍只能经过 `committed epoch → PENDING_NEXT_OPEN → exact-next-open (open > stop && open < target) → BUY_VALID`。生产 controller 必须只消费此链路，旧谱系 cron 若还能写候选/持仓/推送必须暂停。完整的 V517 许可、registry、pending、cron 和验证合同见 `references/v517-v523-effort-result-absorption-closure.md`。

- **V517–V523 日线量价吸收本体（月度样本量门禁）**：生产样本量不再按年度或在途年比例计算，而是从第一笔到最后一笔已平仓入场之间，逐个自然月要求 `n>4`；中间零交易月视为失败，禁止通过省略月度行掩盖。当前 V519 379笔/WR60.9499%/AvgNet+1.0304%/PF1.3933/T+1=0，但月度门禁失败（202402、202403、202412、202501、202503、202505、202511、202602），故 V520 阻断、V522 许可撤销、生产 `FAIL_CLOSED_REPLAY_GATE_FAILED`。不得对量比、窗口、SL/TP、hold 或月份作结果导向变体。完整谱系与合同见 `references/v517-v523-effort-result-absorption-closure.md`。
- **V502–V516 本地 OHLCV 纯结构前沿总闭环**：所有新本体必须依次通过 outcome-blind seeds、独立 raw-bar Oracle、单次冻结严格 T+1 回放、逐年稳定性；支持不足不得放宽，经济失败不得改窗口/SL/TP/年份伪装新方向。当前日线、周线、跨证券、流动性、Breaker、IFVG、诱导、吸收、双边清扫方向均无全年份晋级者；高 WR 普遍由小赢大亏构成。若 registry 依赖的独立审计产物缺失，必须从 frozen replay 逐笔 CSV 重建指标/时序/T+1 审计后再宣布闭环。详见 `references/v502-v516-local-structure-frontier-closure.md`。
- **V415–V516 会话级停止纪律补充**：当用户继续要求“整体胜率太少，继续寻找其它方向并回测”时，先检查最终审计。如果最新审计为 `CURRENT_LOCAL_OHLCV_PURE_STRUCTURE_RESEARCH_COMPLETE__ZERO_ALL_YEAR_PROMOTION_PASS__STOP_STRATEGY_ITERATION`，必须明确回答目标已完成并停止；不要为显得主动而开启 V517 或继续做 timeframe/context/threshold/entry/exit/SL/TP/hold/year/regime 变体。合法重启只允许真正新的因果 ontology，且在查看 outcomes 前满足支持门禁（至少 n>=300、每年 n>=40，或更严格预声明门槛）。详见 `references/v415-v516-local-structure-frontier-closure.md`。
- **V498–V501 周线 Breaker→日线迁移闭环**：冻结 `确认周线摆动低点→周线向下BOS→向前6周最近阳线定义Bearish OB→后续周收盘突破OB高激活Breaker→日线touch→reclaim→hold→次日开盘`。全市场67,684种子，独立raw-bar Oracle 67,684/67,684零差异；串行严格T+1回放50,605笔，毛WR68.19%/AvgNet+0.3668%/payoff0.5641/PF1.1224，但2023 AvgNet-1.7481%、2026 -0.5616%。高胜率仍是小赢大亏且跨年失稳，关闭本体，禁止BOS阈值/OB回看/激活窗口/SL/TP/hold/年份/regime变体。详见 `references/v498-v501-weekly-breaker-transfer-closure.md`。
- **V481–V484 双边流动性清洗反转闭环**：冻结 `确认区间高低→先扫BSL收回→2..10bar后扫SSL收回→3bar内突破SSL raid high→次日开盘`。全市场12,311种子，独立raw-bar Oracle 12,311/12,311零差异；严格T+1回放9,719笔，毛WR57.46%/AvgNet+0.1969%/payoff0.8166/PF1.0758，但2023 AvgNet-0.6576%、2026 -0.6060%。另有2,347个setup次日开盘时目标已被消费，说明T+1经常错过区间回归空间。关闭本体，禁止raid间距/阈值/SL/TP/hold/年份/regime变体。详见 `references/v481-v484-two-sided-liquidity-purge-closure.md`。
- **V477–V480 双重SSL扫损吸收反转闭环**：冻结 `确认SSL→首次扫损收回但未突破raid高→2..10bar后二次扫同一SSL且更高低点→3bar内突破两次raid高→次日开盘`。全市场24,236种子，独立raw-bar Oracle 24,236/24,236零差异；严格T+1回放23,531笔，毛WR74.08%/AvgNet+0.2180%/payoff0.4677/PF1.1078，但2023 AvgNet-0.4266%/PF0.8275。相比单次Turtle Soup毛WR+3.41pp，但AvgNet仅+0.0203pp且payoff更差，关闭本体，禁止raid间距/深度/SL/TP/hold/年份/市场状态变体。详见 `references/v477-v480-double-ssl-absorption-closure.md`。
- **V473–V476 内部诱导流动性扫损延续闭环**：冻结 `外部保护低点→确认高点→bull BOS→更高内部低点→仅扫内部诱导低点且外部低点保持→3bar内突破raid高→次日开盘`。全市场6,223种子，独立raw-bar Oracle 6,223/6,223零差异；严格T+1回放6,066笔，毛WR74.40%但AvgNet仅+0.0744%、payoff0.4436、PF1.0414，2023/2024均负。高胜率由小赢大亏构成，关闭本体，禁止raid深度/risk/SL/TP/hold/年份/周线或行业叠加变体。详见 `references/v473-v476-inducement-sweep-closure.md`。
- **V469–V472 行业领先→个股滞后 SSL 传导闭环**：区别于同日 SMT 背离，冻结 `排除个股后的行业SSL扫损收回→3日内行业突破raid高→行业守住SSL时个股10日内滞后扫损→个股反转确认→次日开盘`。全市场32,559种子，独立 raw-bar Oracle 32,559/32,559零差异；严格T+1一次回放31,830笔，整体毛WR71.35%/AvgNet+0.7101%/payoff0.6446/PF1.364，但2023 AvgNet-0.6668%/PF0.7068，年度门禁失败，禁止lag窗口/SL/TP/hold变体。跨证券时序必须用日期，不能比较不同序列的bar idx；SL统计必须显式枚举原因，不能让`BSL`被子串误判为`SL`。详见 `references/v469-v472-industry-lead-lag-closure.md`。
- **V457–V460 周线 SSL 拒绝块迁移闭环**：从同源日线聚合周线，冻结 `周线SSL扫损收回 → 周线拒绝影线POI → 下一周日线touch→reclaim→hold → 次日开盘`。V457全市场38,787个种子，V458独立Oracle 38,787/38,787零差异；V459严格T+1一次性回放37,514笔，整体WR56.81%/AvgNet+0.5351%/payoff0.9479/PF1.1932，但2023与2026期望为负、PF<1，2025主导表面优势，因此不晋级且禁止阈值/SL/TP/持有期/周期变体。详见 `references/v457-v460-weekly-rejection-block-closure.md`。
- **历史优势转 current scanner / 数据 fail-closed**：历史 trades/picks 不能作为当前候选供给；必须按 `provider fetch → 响应合同 → 原子缓存 → freshness gate → raw scanner → BUY_VALID` 重建。刷新失败禁止 selector/scanner/ingest，不能用系统当天伪造数据日期；0 `BUY_VALID` 是合法空仓。V365 apparent survivor 已确认属于“确认后特征倒灌到确认前 entry”，只能作为 quarantine 回归样本，不能作为 shadow challenger。完整架构、BUY_VALID 时序门禁、单一 challenger 治理及三个不同本体的准入定义见 `references/current-scanner-fail-closed-productionization.md`。当 registry 进入 `EMPTY_BOOK` 时，手工回测、重选、实时 scanner metadata、日志和内置调度也必须同步 fail-closed；旧 V88/V90/V185 artifact 不可回填当前页面。最小 API/页面/任务验收矩阵与 ISSUE→SPEC PR→IMPL PR 产物范式见 `references/empty-book-frontend-and-automation-contract.md`。
- **因果生产重建与合法空仓闭环**：路线图必须服从最新因果证据；若历史 baseline/challenger 的入场早于所需确认或 provenance 不完整，应取消生产化任务而不是强行保留版本标签。生产链路采用事务化行情 epoch、唯一 registry、显式 `BUY_VALID`，新本体严格执行 outcome-free generator → independent Oracle → one frozen T+1 replay；失败即 `CLOSED_NO_VARIANTS`。无晋级策略时，经过 API/前端/执行验证的 `EMPTY_BOOK` 是完整成功状态。详见 `references/causal-production-rebuild-empty-book-closure.md`。
- **纯结构新本体准入与冻结回放**：先做结果前支持门禁，再做独立 raw-bar Oracle 与单次严格 T+1 replay；高毛胜率若同时存在低 payoff、低 PF 或负收益年份，不得晋级。统计 SL 时禁止用 `'SL_' in exit_reason`，否则会把 `BSL_` 目标误计为止损。完整流程、ICT Unicorn/Turtle Soup 证据与修复模式见 `references/pure-structure-ontology-frozen-replay.md`。
- **V431 本地日线纯结构前沿关闭**：完成 R1/R2/C1/R3/R4/R5 的独立语义、生命周期、冻结 T+1 回放对账后，所有本地日线纯结构本体均未通过逐年固定质量门槛。历史高 WR（如 V246/V333）若无法从当前 raw scanner 同源重建且最新候选为零，不得冒充当前生产选股。停止对已关闭本体做窗口/阈值/SL/TP/持有期变体；仅当出现不同因果本体或通过 PIT/全历史准入的新信息维度时重启。详见 `references/v431-local-daily-structure-frontier-closure.md`。执行准入门槛、R1–R5 的冻结结果和“经济失败后停止而非调参”的通用研究流程见 `references/local-daily-pure-structure-frontier-closure.md`。
- V308 daily industry leadership proxy：在 V307 后测试全历史日线 proxy 能否复现 first120 行业领涨传导。输入 V280 82,400行，日线开盘proxy覆盖81,686行/4,603股/T+1=0；严格移除同日 high/low/close 派生字段（`stock_open_hold`/drawdown/push 等）避免日开盘执行泄漏。Baseline WR45.55/Avg0.48；市场/行业开盘广度可抬到中高50%（如 `mkt_gap_up>=75` 10,896笔/WR57.68，`ind_gap_up>=75` 14,395笔/WR56.03），安全组合最好大样本 `RANGE_LOW_SWEEP_RECLAIM + ind_gap_up>=75 + ind_gap_ge1<45 + mkt_gap_up>=75` 1,747笔/WR57.18/Avg1.41/年WR 53.80/65.75/56.45/55.66。结论：日线开盘广度是弱状态层，不能复现V307 first120真实接管；下一步应做 scanner-time intraday continuation module（开盘广度→first15/30/60/120行业持续→候选同源POI生命周期），不要继续调日线gap桶。详见 `references/v308-daily-industry-leadership-proxy.md`。
- V307 industry leadership transmission：在 V306 后测试真实行业领涨传导（entry-day first120 15m 行业ret/up/amount排名 + 候选个股参与）。输入 V306 87,499覆盖行/4,154股/T+1=0，扫描4,653个15m文件，构造223,005个stock-date和3,330个industry-date特征。Baseline仍弱 WR39.62/Avg-0.69/SL51.71；但 `LEADER_TOP20 + INDUSTRY_GAP_LED + m120_iup>=65` 407笔/WR73.96/Avg6.08/SL19.41，`industry ret rank TOP20 + INDUSTRY_GAP_LED + candidate PARTICIPATE` 639笔/WR73.40/Avg5.66。结论：真正有效的不是单股DNA/first60参数，而是“行业领涨开盘缺口→行业first120 top20持续→候选股参与”的资金传导；但强口袋仍集中202605/202606，因15m近端覆盖限制不可生产。下一步需扩展15m历史、shadow live行业leader模块，或寻找能复现first120行业leader的日线proxy。详见 `references/v307-industry-leadership-transmission.md`。
- V306 opening gap source：在 V305 后测试 entry-day 开盘缺口来源（市场/行业/个股独立）+ 上午15m持续性。输入 V305 88,351 行/4,197股/T+1=0，扫描4,905个日K文件构造65个entry-date的市场/行业gap上下文。Baseline仍弱 WR39.56/Avg-0.70/SL51.75；但 `INDUSTRY_GAP_LED` 达 1,462笔/WR63.27/Avg3.84/SL29.96，`INDUSTRY_GAP_LED + i_gap_up>=65 + m120_iup>=65` 458笔/WR71.83/Avg5.76，`INDUSTRY_GAP_LED + ACC_VWIDE>=5 + SWEEP<0.6` 90笔/WR77.78/Avg9.73。结论：最强状态层是“行业领涨开盘缺口 + 同日上午行业扩散”，不是单股DNA或继续调first60/first120；但高质量口袋只覆盖202605/202606，不能生产。下一步应做真实 Industry Leadership Transmission（开盘行业leader→候选所属行业/行业内排名→first60/120持续），或扩展15m历史。详见 `references/v306-opening-gap-source.md`。
- V305 morning 15m persistence：在 V304 后测试更长的可执行上午窗口（first60/first120）+ 同窗口市场/行业/个股成交额扩散。输入 V302 67,559 行，生成 88,351 个可执行候选/4,197股/T+1=0。整体仍弱：WR39.56/Avg-0.70/SL51.75；first120 好于 first60 但仍只有 WR41.02/Avg-0.56。最佳诊断口袋 `MORNING120_NO_FADE|RISK>=8|MUP45_55|IUP55_65` 810笔/WR56.42/Avg2.36/月度53.90/50.00/60.69；小口袋 `MORNING120_NO_FADE|GAP0_1|RISK>=8|IUP55_65|SVR1.2_2` 80笔/WR76.25/Avg6.74。结论：等待完整上午能减少 GAP_SL 并提升局部质量，但仍只是状态层，不能单独生产；停止继续调 first60/first120 桶，下一步应测试真实板块领涨传导、竞价/开盘缺口来源、盘口/订单流 proxy 或更长历史15m。详见 `references/v305-morning15-persistence.md`。
- V304 entry-session 15m market/industry diffusion：在 V303 后测试买入时第一/第二根15m的全市场+行业同步扩散与个股成交额持续性。输入 V303 168,940 行，entry-time diffusion 覆盖101,384行/T+1=0，明确禁止 `DAY_OPEN_BASE` 使用 first/second 15m 特征。结果：可用行基线 WR38.59/Avg-0.795；最佳小口袋 `FIRST15_ACC_HOLD|ACC_MID1.5_3|SWEEP0.6_1.2|IUP55_65|REL0_1` 129笔/WR57.36/Avg0.80/月度最低54.10；较大口袋 678笔/WR51.92/月度最低51.06。结论：同窗口行业扩散有信息量，但只是状态层，不能把 naive 15m lifecycle 变成生产级；停止继续调简单 m_up/i_up/volume 桶，下一步只能测试竞价/开盘缺口来源、真实领涨板块传导、上午成交额持续性或盘口/订单流 proxy。详见 `references/v304-entry15-market-industry-diffusion.md`。
- V303 executable 15m entry timing：在 V302 之后测试买入日可执行 first/second 15m 确认。输入 V302 67,559 笔，生成 168,940 个入场模式/4,591只/T+1=0。按买入时点修正了初版 `DAY_OPEN_BASE` 使用 first2 push/dd 的未来特征风险，并验证无泄漏。结果：`FIRST15_ACC_HOLD` 30,192笔/WR38.80/Avg-0.774，`FIRST15_TAKEOVER` 22,943笔/WR40.45/Avg-0.689，`SECOND15_CONT` 19,561笔/WR38.86/Avg-0.733；最佳无泄漏口袋约432笔/WR52.08/月度最低49.51，远低生产。结论：更细周期+可执行首/次15m确认不能救 V302，问题不是买点晚一两根K，而是 lifecycle 未识别真实资金接管；停止继续调 first/second 15m 阈值，下一步只能引入竞价/开盘缺口来源、真实板块同步扩散、成交额持续性或盘口/订单流 proxy。详见 `references/v303-executable-15m-entry-timing.md`。
- V302 15m same-source lifecycle audit：按 V301 后续方向补全 15m 全市场最近窗口审计。Tencent m15 覆盖 4,653/4,655 只、每只800根，生成 67,559 笔 2026 近端候选/4,591只/T+1=0，但 base WR39.38/Avg-0.645/SL44.32/GAP_SL15.05；最优大口袋 `ACC_VWIDE>=5 + SWEEP<0.6 + RISK>=8` 1,142笔/WR52.54/Avg1.44/月度最低36.86，仍远低生产。结论：15m粒度本身不解决问题，naive ACC→MAN→DIS 到次日开盘会产生大量无法活到T+1执行的假接管；下一步必须测可执行买入窗口(first/second 15m hold、竞价/开盘缺口质量、市场/行业15m同步扩散)，不要继续调15m ACC/MAN/DIS阈值。详见 `references/v302-15m-same-source-lifecycle.md`。
- V301 previous-day board leadership overlay：在 V300 后测试前一交易日市场/行业涨停触板、强势板块、行业排名是否能作为父级router。未加跨年守门的热板块口袋 6,541笔/WR73.72/Avg5.36，但仅覆盖2026；两年守门后最佳仍是 V300 base 本身 3,935笔/WR53.04/2025 58.50/2026 51.36/月度最低37.28/T+1=0，说明前日涨停/强板块只提供近端诊断信息，不能解决弱月稳定性。停止继续调 daily board/limit-up 阈值；下一步只能引入更因果的15m/竞价/盘口/真实板块资金或更长分钟数据。详见 `references/v301-prevday-board-leadership.md`。
- V300 entry-session 60m volume diffusion：在 V299 严格生命周期后，测试买入日前1/2/3根60m的市场/行业/个股成交量扩散。自动高WR口袋 `k1_mup50_iup50_muv35_iuv20_svol1.3` 1,628笔/WR72.11/Avg4.07但仅覆盖2026，不可生产；两年稳定守门后最佳 `k2_mup65_iup65_muv20_iuv20_svol1.0` 3,935笔/WR53.04/2025 58.50/2026 51.36/月度最低37.28/T+1=0。结论：60m量能扩散有信息量但仍救不了弱月，是状态层不是生产信号；下一步必须引入15m/竞价/盘口/真实板块资金或停止60m阈值分支。详见 `references/v300-entry60-volume-diffusion.md`。
- V299 strict 60m lifecycle gate：在 V297/V298 之后继续测试更严格 60m 内部生命周期：`ACC压缩/缩量 → MAN放量刺破 → RECLAIM → DIS放量扩散 → 1/2/3 bar站稳`。raw 65,387笔/WR50.69/Avg0.73/2026 WR48.50/月度最低30.63/T+1=0；高WR口袋如 `man_vol>=1.6 & risk<=6 & close_ext>=1.0` 1,090笔/WR54.31/2026 WR51.15/月度最低36.84；按月度稳定排序的最稳规则反而只有639笔/WR44.91。结论：继续调现有60m K线内部acc/sweep/man_vol/dis_vol/hold阈值无法救弱月，必须引入15m、分笔/盘口、竞价、成交额持续性或真实板块资金扩散。详见 `references/v299-strict-60m-lifecycle-gate.md`。
- V297-V298 60m 同源 ACC→MAN→DIS 生成器闭环：V297 直接从4552只本地60m扫描 `ACC蓄势→MAN下扫→reclaim→DIS突破→次日T+1入场`，raw 26048笔/WR50.47/Avg0.68/2026 WR48.15/月度最低30.56/T+1=0；非泄漏最佳规则仍仅 906笔/WR55.52/2026 WR47.20。V298 再加 entry-session 60m 市场/行业/个股 persistence，best `k2_mup65_iup50_raw` 3589笔/WR55.28/Avg1.44/2026 WR52.30/月度最低33.51/T+1=0。结论：同源60m生命周期供给充足但定义仍过粗，不能生产；下一步应补 15m/分笔/竞价/成交额持续性，或构造更严格的 `ACC压缩→MAN放量刺破→RECLAIM缩量不破→DIS连续放量扩散` 并做弱月复盘。详见 `references/v297-v298-intraday-lifecycle-generator.md`。
- V296 second60 anti-chase + lifecycle gate：在 V293 659行上重模拟 k2/k3 persistence 并加入 V295 得出的 entry-time 生命周期门禁。最佳 `post_hold_min_pct<=4 & exclude_midwide_shallow_nonstrong`（排除 `中/宽蓄势 + 浅扫 + 非强impulse`）得到122笔/WR72.95/Avg3.14/2025 WR69.70/2026 WR76.79/月度最低58.33/T+1=0；弱月 202602/03/04 从 V294 的45/45/50 提升到58.33/63.64/66.67。结论：弱月根因确为假接管生命周期，不是market/industry阈值；但样本小且历史仅近端，仍不可生产，下一步必须用更长60m/15m或同源ACC→MAN→DIS生成器验证，而不是继续调mup/iup/k。详见 `references/v296-second60-antichase-lifecycle-gate.md`。
- V295 V294弱月根因审计：针对 V294 best `k=2, market_up>=65, industry_up>=50` 的 202602-202604 弱月做 no-write root-cause。V294强月134笔/WR79.85/Avg3.91/SL11.19；弱月47笔/WR46.81/Avg-0.19/SL51.06，根因不是微利/T+1/行业阈值，而是 `浅扫 + 宽蓄势 + 弱/中等impulse + 放量但接管不稳` 的假接管。弱月亏损集中在 `SWP_SHALLOW<1`、`ACC_WIDE|SWP_SHALLOW|IMP_WEAK`、C26/C39。entry-time候选 `open_to_confirm_pct<=1.5 & stock60_pos>=50` 可到81笔/WR80.25/2026 WR78.38/弱月60+，但样本仍小且后验过滤，只作为 V296 在 V293/V294 659行上重模拟 `second60 persistence + anti-chase + lifecycle gate` 的方向，不可生产。详见 `references/v295-v294-weak-month-root-cause.md`。
- V294 entry-session 60m persistence：在 V293 first60 同步扩散基础上，验证第2/第3根60m是否持续扩散并模拟可执行延迟入场。最佳 `k=2, market_up>=65, industry_up>=50, stock hold zone` 181笔/WR71.27/Avg2.85/2025 74.44/2026 68.13/SL21.55/GAP_SL1.66/T+1=0，较 V293 best WR70.35/Avg2.62/GAP_SL2.33/月度最低33.33继续改善到月度最低45.00；第三根60m不如第二根，说明等待过久会追价。仍未达生产稳定性，下一步应针对 202602-202604 弱月做 regime/loss root-cause（行业退潮、second60追价、risk_after_persist、SL锚点）。详见 `references/v294-entry60-persistence.md`。
- V293 entry-session 60m participation + lifecycle：在 V292 best `first60_bull_hold_zone` 659笔/WR56.60/Avg1.09/2026 53.85 基础上，加入买点前已知的 entry day 第一根60m全市场/行业同步扩散和pre-entry lifecycle。最佳大样本 `entry60 M_UP>=65 & I_UP>=65` 172笔/WR70.35/Avg2.62/2025 77.11/2026 64.04/SL24.42/GAP_SL2.33/T+1=0，显著优于V292但月度最低仍33.33、样本偏少，不接生产。机制结论：真正有效的是“个股first60 hold + 同小时市场/行业同步扩散”，下一步V294应验证 second/third 60m 扩散持续性，判断月度低谷是否来自开盘脉冲后行业退潮。详见 `references/v293-entry60-participation-lifecycle.md`。
- V291-V292 可执行 60m 入场闭环：在 V288 same-source 60m-first 基线上，V291 测试次日预挂 POI limit（zone_high/618/mid/382/low）全部失败，最好仍是原 daily open 1434笔/WR52.86/Avg0.51；zone_high first2 仅462笔/WR40.48/Avg-0.57，说明次日打回 60m POI 不是便宜买点而是接管失败。V292 改为次日 first60 hold/continuation 确认，best `first60_bull_hold_zone` 659笔/WR56.60/Avg1.09/2025 62.21/2026 53.85/GAP_SL 2.73/T+1=0，较 V288 降低GAP_SL并提升Avg但月度最低仍38.36，未达生产。结论：方向应从“回踩更低价”转为“接管持续性确认”；下一步需要 15m/盘口/竞价/成交额持续性或行业扩散，而不是继续调 POI limit/RR/hold。详见 `references/v291-v292-executable-60m-entry-closure.md`。
- V287-V290 时间顺序/父级状态/同源60m/操盘生命周期闭环：继续按“时间顺序、参数自适应、股票DNA、大小周期”方向反复迭代。V287 父级 market/industry regime 后验有强口袋但 rolling next-month 失败（best rolling 1313笔/WR48.97/2026 42.72）；V288 改为 same-source 60m-first `SSL sweep→reclaim→micro MSS→60m POI→next daily open`，best 1434笔/WR52.86/2025 52.63/2026 52.95/T+1=0；V289 加 participation overlay，最好大样本 rel_ret=REL_-10_0 455笔/WR57.14/2025 60.00/2026 55.94/月度最低35.94；V290 operator lifecycle overlay 局部口袋 124笔/WR65.32/2025 75.00/2026 61.96，但样本小且月度最低45.45。结论：父级状态、分段DNA、同源60m、生命周期proxy都有信息但均未达生产；不能继续同类窗口/历史最优规则调参，下一步只能引入更原生 lifecycle 数据（更长历史60m/15m、盘口/竞价/成交额持续性、板块领涨扩散）重建 `Market/Industry Regime → Stock Operator Lifecycle(ACC/MAN/DIS) → Active POI family → Rhythm shift → Same-source 60m/15m takeover → Daily execution`。详见 `references/v287-v289-temporal-regime-60m-closure.md`。
- V286 滚动时间段股票DNA审计：当用户指出“庄家/大资金只会一段时间操纵个股且可能换资金，所以DNA应按时间段自动适应”时，不要用后验WR白名单；必须做 next-month rolling 验证。V286 用 V280 82,400条时序事件，测试90/180/360日滚动训练→下月选择。结果：90d stock DNA 3064笔/WR46.61/2026 39.76；180d 4063笔/WR48.29/2026 41.43；360d 4441笔/WR49.40/2026 43.01；rolling global 360d 488笔/WR56.56但2026 47.46且月度不稳。结论：分段DNA方向成立但当前DNA只是历史规则表现+简单桶，无法识别操盘生命周期；下一步必须建 `Market/Industry Regime → Stock Operator Lifecycle → SMC Story Family → Adaptive Rhythm → Same-source 60m POI/Takeover → Daily Execution`，不要继续只调窗口或按股票历史最优组合生产。详见 `references/v286-rolling-period-stock-dna-audit.md`。
- V285 每股DNA时间顺序选择器审计：当“交易量偏少”时，先证明原始机会密度。V280原始时序机会并不少：82,400笔/4,643股/每股17.75次，测试期2024-2026仍70,556笔/每股15.20次；交易少来自质量门禁过滤而非SMC原子机会不足。V285 walk-forward 证明单股历史DNA不能稳定外推：loose selector 6,681笔/WR47.31/2026 WR39.87，balanced 4,674笔/WR47.00/2026 WR40.17。大流量family在2026同步退化，说明瓶颈是父级市场/行业regime，而不是继续按单股历史最优组合生产。下一步架构应为 `Market/Industry Regime → SMC Story Family → Stock DNA/Parameter Pocket → Entry/Exit Contract`。详见 `references/v285-stock-dna-temporal-selector.md`。
- V279 自适应时间顺序语法审计：按用户方向测试“参数不固定/按股票DNA自适应/按时间顺序发生”。全市场4655只、2023-2026、no-write；在线语法为`个股DNA环境→已确认SSL Sweep→突破已确认Swing High→自适应displacement→真OB→FVG/OB重叠→回踩reclaim→次日入场`，只用事件前 swing/range/body/vol。结果：base 7243笔/WR43.77/Avg0.16/年最低WR32.54/SL44.55%；单维最好 LOW_VOL 713笔/WR51.05/年最低35.51；多维最好 react<=1+risk<=8+ssl_age<=20 115笔/WR59.13/Avg1.67/年最低58.49，仍远低生产。结论：自适应窗口和在线股票DNA只能弱增强，不能把日线`SSL→BOS→OB回踩`变成生产级；下一步应做“market/板块regime→个股DNA选择语法族→日线候选→60m/参与度确认”，不是继续调BOS/SSL/wait参数。Artifacts: `/root/.hermes/smc_audit/v279_adaptive_temporal_grammar_latest.json`，详见 `references/v279-adaptive-temporal-grammar-audit.md`。
- V270-V278 时间顺序组合/交易量/DNA闭环：V270在V262 fresh BOS retest上补prior SSL顺序事件，质量仅小幅改善（prior_SSL20 WR约48%，仍失败）；V272全市场4655只、240组BOS→Demand→Retest参数面证明“放宽时间顺序”可给足交易量（最高94,221笔，约6.75笔/股/年），但质量塌陷（最佳WR仅44.79%，0生产/研究通过），说明低交易量不是原始机会不足，而是高质量门禁筛掉大量低质通用BOS回踩。V273按股票DNA分桶：strict最佳变体4633只有机会、1944只n≥8，432只股票WR≥60且avg>0，DNA过滤后4297笔/WR68.12；max-volume变体4598只n≥8，294只股票过WR60，5966笔/WR64.47。V274 walk-forward验证股票DNA不可稳定外推：base_n4_wr60_avgpos 下一年16260笔/WR45.47/Avg0.33，strict_n6_wr65 10672笔/WR45.48/Avg0.32；V278固定时间顺序参数面证明原始事件充足但最佳参数仍仅约49%WR。结论：不应继续简单放宽sequence window/reclaim参数，也不能把股票DNA in-sample白名单接生产；真正瓶颈是入场前市场/板块状态与当年regime过滤，而不是每股机会数。Artifacts: `/root/.hermes/smc_audit/v272_time_order_parameter_surface_fast_latest.json`, `/root/.hermes/smc_audit/v273_sequence_stock_dna_latest.json`, `/root/.hermes/smc_audit/v274_walkforward_stock_dna_sequence_latest.json`, `/root/.hermes/smc_audit/v278_sequence_combo_attrition_ultrafast_latest.json`。
- V261-V263 post-V260 current-supply闭环：V259/V260历史通过但当前0行，V261证明204条current V128/V230供给与V259 selector完全错配（BOS_CONTINUATION 107条中104条prev20 range不足、3条body不足、0 match），带当前命中的旧标量规则≥5 hits时0 production/research pass；V262新写raw daily BOS→Demand retest生成器（4655只K线，严格break prior20 high，no-write）能生成938条recent45当前行，但历史质量极差：child 26,408笔/WR43.47/Avg0.08；V263再加entry前60m确认仍失败：60m覆盖5,770笔，child WR40.92/Avg-0.10，0 pass，且本地60m缓存大量停在20260515附近，不能支撑202607当前路由。结论：不要把raw daily BOS retest或60m pre-entry filter接生产；下一步只能做真正更强的BULL_CONTINUATION环境/事件源或刷新并重建分钟级候选生成，不再对V128/V230/current rows做标量剪枝。Artifacts: `/root/.hermes/smc_audit/v261_current_supply_mismatch_closure_latest.json`, `/root/.hermes/smc_audit/v262_fresh_bos_retest_generator_latest.json`, `/root/.hermes/smc_audit/v263_v262_60m_confirmation_probe_latest.json`。
- V259-V260 source-safe BOS_CONTINUATION重构：按V258结论转向“新事件定义”，只用事件bar与入场日前K线（明确不使用entry-day high/low/close），发现BOS_CONTINUATION子供给规则 `raw_prev20_range_pct>=39.8518000725375 AND raw_event_body_pct>=75`。V260独立审计通过：child 41笔/WR90.24/Avg8.30，combined 614笔/WR94.14/Avg7.65/yearMin72/yearWRmin92.22/micro0.65/T+1=0，production gate pass；但current_recent45_hits=0，当前不可路由生产，只能shadow/no-write等待当前供给。Artifacts: `/root/.hermes/smc_audit/v259_bos_continuation_source_safe_rebuild_latest.json`, `/root/.hermes/smc_audit/v260_v259_independent_audit_current_smoke_latest.json`。
- V251-V258 V246/V185后续研究治理：V246/V248历史强基线(573笔/WR94.42/Avg7.60/yearMin71/T+1=0)仍有弱月与当前供给断层；V251定义生产/研究/不可用门槛并关闭局部过滤，V252 post-entry进度门禁、V253 BEAR_RISK Demand replay exit、V254/V255当前供给历史桥接、V256周/日线pre-entry结构层、V257弱月loss root-cause、V258当前兼容rich source mining均未产生可晋级规则。V258验证204条recent45非重叠当前供给、554个source-side predicate、3280条单/双规则，0 production/research pass；当前SSL/Demand供给历史质量约60-70%WR，不能接V246。下一步必须引入真正新数据/新事件定义（例如候选生成时的60m/板块资金/竞价订单流/重构BOS_CONTINUATION语义），不要继续对V246/V230做标量剪枝。Artifacts: `/root/.hermes/smc_audit/v258_current_compatible_rich_source_mining_latest.json`。
- V249/V250 V246 local stability diagnosis：V248/V246历史门禁通过但存在3个局部弱月(202312 WR66.7、202511 WR81.8、202601 WR83.3)。弱月损失分两类：202312前日广度/行业参与明显弱，202511/202601主要是BOS_CONTINUATION在ACCUMULATION/BULL_CONTINUATION路径失败；简单source-side阈值/行业删除最多把弱月从3降到2且样本跌破或未达更高门槛；V250条件path/regime过滤最多压到1个弱月但n/minYear/Avg不满足后续晋级门槛，无可晋级修复。下一步不能再做简单标量/path剪枝，必须引入新的前置信息层或重建BOS_CONTINUATION路径语义。Artifacts: `/root/.hermes/smc_audit/v249_v248_local_stability_diagnosis_no_write_20260701_173900/v249_summary.json`, `/root/.hermes/smc_audit/v250_v249_path_regime_conditional_probe_no_write_20260701_174600/v250_summary.json`。
- V225-V227 participation layer continuation：Baostock行业参与度覆盖V185 334/334，但行业单规则无生产/研究门禁通过；V226 peer+industry pair出现2个research-pass规则（最好300笔/WR88.33/Avg6.80/yearMin85/micro1.00/T+1=0），V227独立审计0泄漏/0时间序错误/当前6个active全通过，但minYear<40所以生产失败、no-write。详见 `references/v225-v227-participation-layer-continuation.md`。
- V222-V224 peer participation proxy：用本地日K构造前一交易日全市场/板块/prefix同群参与度，V223规则（保留全部V185_CHILD；V175仅保留prefix-3前日上涨占比<=92.9594）研究门禁通过但生产门禁失败(minYear=38<40)：312笔/WR88.46/Avg6.844/yearMin84.48/micro0.96/T+1=0；当前6个V185 active全部通过该规则。关闭本地prefix代理标量过滤，若继续板块方向需真实行业/板块映射。详见 `references/v222-v224-peer-participation-proxy-closure.md`。
- V221 V185入场前60m特征闭环：Baostock 60m严格只用entry_date前数据，334/334覆盖；确认低WR行有“前日60m高位收盘/放量/追价/risk高”特征，但所有过滤只得到小样本口袋（如 n=206/WR92.23/Avg7.75/minYear17），0个过生产/研究门禁。关闭V185/V175 60m标量过滤，下一步只能做真正的新候选生成器/板块参与层或生产稳定化。详见 `references/v221-v185-preentry-60m-source-feature-closure.md`。
- V220 Baostock 60m micro-resolution 闭环：V175 247/247 60m覆盖，测试264个RR/hold/lock变体，0个过生产门禁；高WR/Avg/year变体卡在micro(如 rr2.2_h20_lock2p0_trig1p0: WR88.26/Avg6.306/yearMin85.11/micro1.62)，micro-safe变体卡在2026/year稳定(如 rr2.2_h20_lock1p5_trig1p2: WR85.43/Avg6.572/yearMin78.95/micro0.81)。关闭通用60m exit-grid调参，下一步必须用入场前信息层。详见 `references/v220-60m-micro-resolution-closure.md`。
- V217-V219 V185当前活跃候选审计：/api/live-prices?version=V185 返回 rows 在 `picks` 不是 `data`；当前6个active全为 WATCH_ONLY；V218发现60min本地缓存5/6滞后到20260513，V219仅刷新6个active symbol到202606261500并重放60m：5个TP、1个SL，但这只是active-symbol审计，不是全历史60m生产验证。详见 `references/v217-v218-v185-current-live-guard-60m-cache.md`。
- V211-V214 V185+V211 质变候选：从 V164 corrected BUY 中找到非重叠 TRUE_TAKEOVER_2 + bull_count_3>=3 + post_pullback_depth<=3 子供给，去重后 V185+V211 combined=504笔/WR89.29/Avg6.825/yearMin86.75/micro0.79/T+1=0；当前仅 shadow/no-write，需重建最新 scanner dry-run 后才能做 active/API 路由。详见 `references/v211-v214-v185-plus-true-takeover2-persistence.md`。
- V208-V210 V185亏损根因闭环：V185低胜率来源主要是V175组件的高risk/高reclaim close位/追价行；非泄漏标量过滤、source-aware剪枝、等待更深POI回踩均未过新生产门槛，继续研究必须改供给层/新增入场前信息层。详见 `references/v208-v210-v185-loss-root-cause-closure.md`。
- V183-V186 shadow breakthrough：本轮新验证发现 V183 原始range-spring生成器失败，但 V185/V186 从 V167非重叠子集 + source-side risk/body + 可执行p50 runner 得到首个 combined gate pass（n=334/WR=86.23/Avg=6.56/yearMin=82.81/micro=0.90/T+1=0）；仅为 shadow combined production candidate，未写前端/watchlist。详见 `references/v183-v186-shadow-candidate-breakthrough.md`。
- V183-V185 旧池闭环：V175/V167/V85/V128 继续过滤、调 exit、等 bar survival 都不能产生质变；高 RR continuation 只提高 Avg 但 WR/year 不稳，POI close-break 仍是根因。下一步必须做 V186 新候选生成器。详见 `references/v183-v185-old-pool-closure-v186-direction.md`。

## 概述

- 严格日线因果组合的生命周期重建、独立 T+1 审计、供应量门槛及禁止事后放宽参数的闭环见：`references/strict-daily-causal-combination-closure.md`。
- V175/V176语义拆分与执行层收益释放教训：`references/v175-v176-semantic-split-execution-frontier.md`。
# ICT / Smart Money Concepts 核心知识库

## 最新研究闭环指针

- V183-V185 旧池闭环：V175/V167/V85/V128 继续过滤、调 exit、等 bar survival 都不能产生质变；高 RR continuation 只提高 Avg 但 WR/year 不稳，POI close-break 仍是根因。下一步必须做 V186 新候选生成器。详见 `references/v183-v185-old-pool-closure-v186-direction.md`。

## 概述

> 最新生产研究教训：V107C `TRADEABLE_REGIME` 市场状态层重推导见 `references/v107-tradeable-regime-rederive.md`。继续 SMC 策略本体时，若要做市场状态/信号语义研究，必须用 `*_daily_750.json` 做多年份全市场 breadth；不要用 TP/SL 微调替代 BULL_EXPANSION 内部语义拆解。

ICT（Inner Circle Trader）交易方法论由 Michael Huddleston 提出，核心思想是：**市场由"聪明钱"（Smart Money / 机构/做市商）主导，散户的亏损是机构的利润来源**。SMC（Smart Money Concepts）是对 ICT 核心思想的系统化提炼。

**核心哲学**：价格在流动性之间摆动。机构通过制造虚假的突破来猎杀散户的止损，然后在对手方积累头寸。

## 1. 市场结构 (Market Structure)

### 核心概念

价格走势由**高点和低点**定义，而不是任意指标。

#### 结构定义

| 趋势方向 | 结构特征 | 标记 |
|----------|----------|------|
| 上升趋势 (Uptrend / Bullish) | HH (Higher High) + HL (Higher Low) | 连续上升 |
| 下降趋势 (Downtrend / Bearish) | LH (Lower High) + LL (Lower Low) | 连续下降 |
| 横盘 (Ranging / Sideways) | EQH (Equal Highs) + EQL (Equal Lows) | 横向区间 |

#### BOS (Break of Structure) / MSB (Market Structure Break)

- **Bullish BOS**: 价格突破前一个 HH → 确认上升趋势延续
- **Bearish BOS**: 价格跌破前一个 LL → 确认下降趋势延续
- **特点**: BOS 发生在趋势**延续**中

#### CHOCH (Change of Character) / 结构转换

- **Bullish CHOCH**: 在下降趋势中，价格突破最后一个 LH → 趋势从下降转为上升
- **Bearish CHOCH**: 在上升趋势中，价格跌破最后一个 HL → 趋势从上升转为下降
- **特点**: CHOCH 发生在趋势**反转**中，是重要的入场信号前兆

#### 实战判断步骤

```
1. 找最近 5-10 根 K线，标记 HH/HL/LH/LL
2. 判断当前趋势
3. 确定关键结构点（最近的 HH 或 LL）
4. 等待价格突破这些关键点
5. BOS = 趋势延续，CHOCH = 趋势反转
```

## 2. 流动性 (Liquidity)

### 核心理念

流动性 = 止损单和挂单聚集的地方。机构需要流动性来建仓/平仓。

#### 流动性类型

| 类型 | 位置 | 含义 |
|------|------|------|
| **BSL (Buy-side Liquidity)** | 价格上方 | 空头止损 + 追多挂单 → 前高附近 |
| **SSL (Sell-side Liquidity)** | 价格下方 | 多头止损 + 追空挂单 → 前低附近 |
| **EQH (Equal Highs)** | 双顶 | 大量空头止损累积处 |
| **EQL (Equal Lows)** | 双底 | 大量多头止损累积处 |
| **Trendline Pool** | 趋势线突破处 | 趋势交易者的止损 |
| **Moving Average Pool** | MA 附近 | 均线交易者的止损 |

#### Liquidity Sweep (流动性猎杀 / Stop Hunt)

机构先向一个方向推动价格，**触发散户止损**，然后反向建立真实头寸。

**过程**：
1. 价格接近前高/前低（流动性池）
2. 小幅突破该水平 → 触发止损单
3. 大量止损被吃掉后，价格立即反转
4. 留下一个**长长的影线（Wick）**

**识别特征**：
- K线突破关键水平后迅速收回
- 留下长上影线（BSL Sweep）或长下影线（SSL Sweep）
- 伴随放量
- 之后价格反向运行

#### V37 Liquidity Zone Detection (流动性区域检测)

改进: 从单点摆动检测 → 流动性区域(池)检测

传统SMC只检测单个摆动点的突破。V37方法聚类附近的多个摆动点形成流动性池:

| 类型 | 构成 | 意义 |
|------|------|------|
| BSL池 | 3-5个相邻的摆动高点 | 空头止损集中区 |
| SSL池 | 3-5个相邻的摆动低点 | 多头止损集中区 |

检测逻辑:
1. 三级摆动点: micro(3根) / meso(8根) / macro(20根)
2. 聚类: 相邻摆动点在15根K线和0.5%价格误差内合并
3. 密度评分: 摆动点越密集, 流动性越大
4. 猎杀追踪: 价格刺穿区域后1-3根K线内是否反转

关键发现 (A股日线, 2026-05-09验证):
- 池检测: 8.1次猎杀/股票 (vs V11单点Sweep的4次/股票)
- 猎杀→FVG比率: 仅27%的猎杀在5根K线内产生FVG
- 有/无猎杀交易的WR无显著差异
- 结论: A股日线gap特性使流动性猎杀在日线层面无法有效利用
- 真正的ICT猎杀→反转模式需要intraday数据(60min/15min)

### 流动性吸筹流程 (Liquidity Grab → 反转)

```
看涨反转流程 (Buy-side Setup):
1. 确认下降趋势 (LH/LL)
2. 价格向下突破前低 → SSL Sweep (猎杀多头止损)
3. 价格立即反弹 → 显示这是一个"假突破"
4. 价格突破前一个 LH → CHOCH (结构转换)
5. 价格回踩 FVG/OB 区域 → 入场点

看跌反转流程 (Sell-side Setup):
1. 确认上升趋势 (HH/HL)
2. 价格向上突破前高 → BSL Sweep (猎杀空头止损)
3. 价格立即下跌 → 显示这是"假突破"
4. 价格跌破前一个 HL → CHOCH (结构转换)
5. 价格回抽 FVG/OB 区域 → 入场点
```

## 3. FVG (Fair Value Gap) — 公允价值缺口

### 定义

FVG 是三根连续 K线之间的**价格缺口**，代表机构订单未完全填充的区域（不效率价格区域）。

### 计算公式

```
Bullish FVG (看涨缺口, 出现在上涨中):
  FVG 上沿 = min(前一根K线的高点, 后一根K线的高点) 
  FVG 下沿 = max(前一根K线的低点, 后一根K线的低点)
  条件: 上沿 > 下沿 (即存在缺口)

Bearish FVG (看跌缺口, 出现在下跌中):
  FVG 上沿 = max(前一根K线的高点, 后一根K线的高点)
  FVG 下沿 = min(前一根K线的低点, 后一根K线的低点)
  条件: 上沿 > 下沿 (即存在缺口)
```

### K线结构

```
Bullish FVG:
K线1: 阴线（低开高走或实体较小）
K线2: 大阳线（突破性）
K线3: 阳线或小阴线（但未覆盖K线2的实体）
      结果: K线1的低 < K线3的低 → 中间形成缺口区域

Bearish FVG:
K线1: 阳线
K线2: 大阴线（突破性）
K线3: 阴线或小阳线（但未覆盖K线2的实体）
      结果: K线1的高 > K线3的高 → 中间形成缺口区域
```

### FVG 类型

| 类型 | 说明 | 交易价值 |
|------|------|----------|
| **普通 FVG** | 标准的三K线缺口 | 中 |
| **3色连续 FVG** | 连续3根同色K线形成的FVG (3bear/3bull)，缺口方向与颜色一致 | **高** (confidence+0.15, grade≥3) |
| **混合 FVG** | 三根K线颜色不一致的FVG | 中 |
| **Implied FVG (IFVG)** | 影线中点隐含缺口 — 无可见gap但影线暴露价格失衡 | 中低（1.5%阈值） |
| **Mitigated FVG** | 价格已经回到缺口区域（被填充/被测试过） | 低（已消耗） |
| **Unmitigated FVG** | 价格尚未回到缺口区域 | 高（待测试） |

### Implied FVG (IFVG) — 影线中点隐含缺口

ICT定义: 当K线实体重叠但影线暴露了价格失衡区域时, 用影线中点检测。

**检测逻辑** (`detect_ifvg_v11`):
1. 仅当无可见gap时检测 (IFVG ≠ FVG)
2. 用两侧K线(high+low)/2作为隐含价格中点
3. 隐含Bullish FVG: c1中点 < c3中点 × 0.985 (1.5%隐含缺口)
4. 隐含Bearish FVG: c1中点 > c3中点 × 1.015

### Mitigated FVG — 被填充FVG的反向区域 (原Inversion FVG改名)

当一个FVG被完全填充（价格回到缺口区域内）后：
- Bull FVG被填充 → 原lower边界变成空头阻力（FVG_Mitigated_Bear）
- Bear FVG被填充 → 原upper边界变成多头支撑（FVG_Mitigated_Bull）

**检测逻辑** (`detect_mitigated_fvg_v11`):
1. 追踪每个FVG的mitigated状态
2. 在mitigated_at位置生成反向FVG_Mitigated信号
3. 区间 = 原FVG的lower-upper区域
4. 方向 = 与原FVG相反

### FVG 交易规则

#### 入场条件（多头示例）：
1. ✔ 下降趋势中出现 Bullish CHOCH
2. ✔ 价格回撤到 Bullish FVG 区域内
3. ✔ 在 FVG 内部出现看涨吞没/针形/确认K线
4. ✔ FVG 在折扣区（Discount Zone, 0.618-0.79 斐波那契范围内）
5. ✔ 该 FVG 是 Unmitigated 的（之前未被填充过）

#### 止损放置：
- FVG 中位止损（保守）：止损在 FVG 中线上方/下方
- FVG 下方止损（激进）：止损在 FVG 下沿下方（多头）
- FVG 上方止损（激进）：止损在 FVG 上沿上方（空头）

#### 止盈目标：
- TP1: 前一个 HH/LL 或相等的流动性池
- TP2: 下一个 FVG 方向
- TP3: 1:2 或 1:3 盈亏比

## 4. Order Block (OB) — 订单块

### 定义

Order Block 是**机构建仓前最后一根 K线**（在反转前的那个方向），代表机构在此区域大量买入或卖出。价格通常会回到 OB 区域进行"重新测试"。

### 识别规则

```
Bullish OB (看涨订单块):
  - 价格从下跌转为上涨的最后一次下跌中的K线
  - 通常是孕线、针形或高成交量K线
  - 规则: 在 Bullish CHOCH 之前，最后一个明显的下行K线
  - 特征: 该K线的收盘价 ≈ 下一轮反弹的起点

Bearish OB (看跌订单块):
  - 价格从上涨转为下跌的最后一次上涨中的K线
  - 规则: 在 Bearish CHOCH 之前，最后一个明显的上行K线
  - 特征: 该K线的收盘价 ≈ 下一轮下跌的起点
```

### OB 未来函数陷阱 (2026-05-15 发现)

⚠️ `detect_ob_smc2026()` 存在严重未来函数：从全部swing(含未来)向后扫描确认OB。
99.95%的OB信号由未来swing确认(中位数24bar后)，导致WR虚高(97.2%→真实100%但n=10)。
回测必须过滤 `confirmed_at > entry_bar + margin`。FVG/Pinbar不存此问题。
详见: `references/ob-future-function.md`

1. **Unmitigated OB**（未测试过的）> Mitigated OB（已被测试过的）
2. **高时间框架 OB > 低时间框架 OB**
3. OB + FVG 重叠区域 → 最强支撑/阻力
4. OB 的实体部分 > 影线部分

> ⚠️ **未来函数陷阱 (2026-05-15 发现)**:
> `detect_ob_smc2026()` 从全部swing(包括未来swing)向后扫描找OB，导致99.95%的OB信号由未来swing确认(中位数24bar)，回测结果虚高。
> **回测必须过滤 `confirmed_at > entry_bar + 5` 的OB信号。**
> FVG/Pinbar无此问题(检测不依赖swing确认)。LuxAlgo OB在CHOCH/BOS时检测，更安全。
> 详见: `references/ob-future-function.md`

### Breaker Block (破坏块)

当CHOCH发生后，原来的最后一个OB被"破坏"，变成反向的Breaker Block。

**转换机制**:
- Bull CHOCH发生 → 前一个Bear OB被破坏 → 变成支撑(BreakerBlock_Bull)
- Bear CHOCH发生 → 前一个Bull OB被破坏 → 变成阻力(BreakerBlock_Bear)

**检测逻辑** (`detect_breaker_block_v11`):
1. 从最近的CHOCH信号往前找同方向的最后一个OB
2. 该OB被"破坏"后变成Breaker Block
3. 区间 = 原OB的lower-upper区域
4. 方向 = 与CHOCH相同

**Breaker Block vs OB**:
| 特征 | OB | Breaker Block |
|------|-----|--------------|
| 位置 | 行情反转前的最后一根K线 | CHOCH后原来OB被破坏 |
| 有效性 | 被测试前有效 | 被破坏后立即有效 |
| 方向 | 与反转前趋势一致 | 与反转后趋势一致 |

### 入场策略（多头示例）：
- 等待价格回踩到 Bullish OB 区域
- OB 区域内有 FVG → 强确认
- OB 正好在 Discount Zone (0.618-0.79) → 非常强
- 价格在 OB 区域内出现企稳/反转K线 → 入场

### 入场精度原则 (V22 SMC正解, 2026-05-18)

**Zone回撤必须用wick(影线)判断，不是close(收盘价)**:
- ❌ `closes[j]` 在zone内 → 收盘回到zone上方会漏掉完美入场
- ✅ `lows[j] < dz_low * 0.995` → 影线刺入zone即算回撤

**确认方式优先级**:
1. IDM_BOUNCE (诱导确认): 价格穿透zone后收回 → 最强
2. PB_BOUNCE (Pinbar确认): 长下影+收阳 → 强
3. ~~REV_BOUNCE~~: 任何阳线 → 太弱，V22已删除

**入场价跳空保护**:
- `entry_price ≤ dz_low × 1.03` → 次日开盘距zone超过3%拒绝入场

**双Zone入场**: OB和FVG都作为有效需求区

**结构SL选择 — 仅用入场前结构** ⚠️:
- ✅ Swing低点(入场前) / OB下沿(入场前) / FVG下沿(入场前)
- ❌ 入场后形成的新低 → 循环论证(价格跌下来→形成低点→用它做SL→"SL撑住了")
- 最小SL距离: 2% (太近不靠谱)
- 最大SL距离: 8% (太远无意义)

## 5. OTE (Optimal Trade Entry) — 最优交易入场

### 原理

基于斐波那契回撤，**最佳入场点**在 61.8% 到 79%（有时到 88.6%）的回撤区域。这个区域被称为**折扣区（Discount Zone）**。

### Premium / Discount 定价模型

| 区域 | 斐波那契范围 | 含义 |
|------|-------------|------|
| **Premium Zone (溢价区)** | 0 - 0.382 | 价格偏高 → 适合做空/卖出 |
| **Fair / Equilibrium** | 0.382 - 0.618 | 均衡区域 |
| **Discount Zone (折扣区)** | 0.618 - 0.79 | 价格偏低 → 适合做多/买入 |
| **Deep Discount** | 0.79 - 1.0 | 深度折扣 → 但可能已跌破结构 |

### OTE 计算

```
取一段明显的趋势波动:
  低点 = L, 高点 = H

折扣区计算:
  Entry Long  = L + (H - L) * 0.618  (上沿)
  Entry Deep  = L + (H - L) * 0.79   (下沿)

溢价区计算:
  Entry Short = H - (H - L) * 0.382  (下沿)
  Entry Deep  = H - (H - L) * 0.618  (上沿)
```

### OTE 入场 Checklist

1. ✔ 确认趋势方向
2. ✔ 计算该趋势波动的斐波那契 0.618-0.79
3. ✔ 等待价格回撤到折扣区
4. ✔ 折扣区内有 FVG 或 OB → ✅ 强信号
5. ✔ 价格在折扣区形成反转K线形态 → 🚀 入场

## 6. Killzone (交易时间段)

### 时间窗口（美东时间 ET）

| Killzone | 美东时间 | 最佳交易对象 | 特点 |
|----------|----------|-------------|------|
| **Asian Killzone** | 8PM - 12AM ET | 外汇/加密货币 | 波动小，通常是区间震荡 |
| **London Open** | 2AM - 5AM ET | 外汇、欧洲市场 | 第一个大波动 |
| **NY AM Open** | 7AM - 10AM ET | 美股、外汇 | 最大波动时段 |
| **NY Lunch** | 10AM - 12PM ET | — | 波动减小，应避免 |
| **Silver Bullet** | 10AM - 11AM ET | 美股 | ICT 特定策略：1小时高概率交易 |
| **Afternoon / NY Close** | 1PM - 3PM ET | 美股 | 收盘前流动性 |

### 加密货币特殊时间

- **北京时间 8AM-10AM** (美东 8PM-10PM 夏令时) → 亚洲开盘/美股收盘对冲
- **北京时间 2PM-4PM** (美东 2AM-4AM) → 伦敦开盘
- **北京时间 8PM-10PM** (美东 8AM-10AM) → 美股开盘，最大波动
- **北京时间 2AM-4AM** (美东 2PM-4PM) → 美股收盘

### Killzone 与信号的关系

| Killzone | 最佳信号类型 |
|----------|-------------|
| Asian Killzone | 建立区间 → 等突破 |
| London Open | 亚洲区间突破 + FVG |
| NY AM Open | 流动性猎杀 + CHOCH + FVG |
| Silver Bullet | 精确 FVG + OB 叠加 |
| NY Close | OB 重新测试 + 收盘价突破 |

## 7. PD Array (Premium/Discount Array)

PD Array 是 ICT 的**入场区域"雷达"**，包含所有可能的价格反应点：

| 元件 | 优先级 | 说明 |
|------|--------|------|
| OB (Order Block) | 1 | 最强的价格反应区域 |
| FVG (Fair Value Gap) | 2 | 缺口 → 价格倾向于回补, 但回调入场反效(缺口填=看跌) |
| Pinbar (V6.2) | 3 | 锤子线 → 回调到低点测支撑 |
| Fibo OTE (0.618-0.79) | 4 | 折扣区域 |
| **Order Flow Gap** | 4 | 订单流缺口 |
| **Weekly / Daily OB** | 5 | 更高时间框架的OB |
| **Unmitigated FVG** | 6 | 尚未被填充的 FVG |
| **均衡点 (EQ)** | 7 | 斐波那契 0.5 回撤 |
| **FVG 中位线** | 8 | FVG 的中线 |

**优先级递进规则**：
先看最高时间框架 → 找 OB → 找 FVG → 找 OTE → 叠加越多越强

## 8. 多时间框架分析

### 框架对齐

```
高时间框架 (Higher TF): Weekly / Daily → 确定大方向
中时间框架 (Medium TF): 4H / 1H → 确定结构点
低时间框架 (Lower TF): 15min / 5min → 精确入场
```

### 对齐流程

```
1. Weekly: 确定大趋势（做多还是做空）
2. Daily:  找关键 OB / FVG / 流动性池
3. 4H:     找当前波动的结构 + 最近的 FVG
4. 1H:     找 PD Array 入场区域 + 信号确认
5. 15min:  找精确入场点 + 止损位置
```

### 时间框架权重

| 时间框架 | 趋势权重 | 信号权重 |
|----------|----------|----------|
| Weekly | 80% | 10% |
| Daily | 70% | 20% |
| 4H | 50% | 40% |
| 1H | 30% | 60% |
| 15min | 10% | 70% |
| 5min | 5% | 80% |

#### MSS (Market Structure Shift) — 微观结构转换

与CHOCH类似但更微观：打破最近5根K线形成的局部结构。

**与CHOCH的区别**:
| 特征 | CHOCH | MSS |
|------|-------|-----|
| 时间框架 | 中(15根K线摆动) | 微(5-10根K线) |
| 确认要求 | 2-3根K线持续在外 | 1-2根K线 |
| 强度 | 强(结构级反转) | 弱(局部反转) |
| 触发频率 | 低 | 高 |

**检测逻辑** (`detect_mss_v11`):
1. 找最近5根K线的最高点和最低点
2. 价格突破这5根K线的范围
3. 确认K线维持在突破方向
4. 最小突破幅度0.3%

#### PO3 (Power of 3) — 蓄势·操纵·分配

ICT的Power of 3: 市场经历三个阶段的完整周期。

**三阶段**:
| 阶段 | 代码 | 价格行为 | 成交量 | 颜色标记 |
|------|------|----------|--------|----------|
| **Accumulation (蓄势)** | ACC | 窄幅震荡(2-3%范围)，方向不定 | 低(80%×均量) | 灰色 |
| **Manipulation (操纵)** | MAN | 突然突破ACC区间(假突破)，扫荡流动性 | 放量 | 橙色 |
| **Distribution (分配)** | DIS | 向反方向运行，开启新趋势 | 持续放量 | 绿色 |

**完整的PO3周期**:
```
ACC: 价格在窄区间内来回8-15根K线 → 机构悄悄建仓
MAN: 价格突然扫过ACC的高/低点 → 猎杀散户止损
DIS: 价格反向运动 → 机构分配头寸
```

**检测逻辑** (`detect_po3_v11`):
1. ACC: 3-8根窄幅K线(范围<3%)且量<80%×均量
2. MAN: 紧接ACC突破ACC范围
3. DIS: 1-7根K线内价格反转

## 信号组合（完整交易系统）

> ⚠️ **序列检测正解 (2026-05-14 V5校正)**: LIQ唯一起点，STRUCT仅确认，OB独立策略，FVG需LIQ前序。
> V5新增: 市场状态(FVG回补率)驱动策略开关，SignalScore仓位分配，RR≥1过滤。
> 详见: `references/smc-v5-system.md`
> 监控修复: `references/monitor-bar-walk-fix.md` (TP/SL逐bar遍历修复)

### Pinbar (锤子线) — 入场确认工具，非独立信号 ⚠️ (V7.5校正)

**SMC正解角色**: Pinbar是**入场确认(Entry Confirmation)**，在已有PD Array(OB/FVG/BreakerBlock)处使用，不是独立POI。

**检测标准** (V7.5严格版):
- 长下影线: 下影 > 实体 × 2.5
- 下影占主导: 下影 > 振幅 × 0.6
- 小上影: 上影 < 振幅 × 0.15
- 收在上半部: close > (open + low) / 2

**常见错误**:
- ❌ 把吞没/孕线/刺透当独立zone类型 → 这些是入场确认形态，应在OB/FVG处使用
- ❌ Pinbar检测过于宽松 → 导致大量假信号(WR<70%)
- ✅ Pinbar_Bull作为POI可用但需严格过滤，配合OB/FVG使用效果最佳

**回调入场**(类比OB): 等价格回调到pinbar低点 → 测试支撑 → 确认入场

### Retrace Theory — 回调入场核心原理 (V6.2, 2026-05-14)

**OB_Bull回调入场: WR +3.2pp (93.5%→96.7%)**
- OB是订单块支撑位, 价格回调到zone_low是"测试支撑" → 牛旗确认
- 等价格触碰zone_low后入场, 从zone_low以下0.96×zone做SL
- MAX_WAIT=7bar最优(40参数网格搜索, n=2000)
- 约22%的OB信号会回调到zone, 78%不回调整(直接上涨)

**FVG_Bull回调入场: WR -37pp (66.1%→29.1%) — 坚决不用！**
- FVG是公允价值缺口, 价格回补缺口=缺口填充 → **看跌信号**
- 不是"回调买入", 而是"缺口已失效"
- FVG保持立即入场(next bar open): WR=66.1% avg+1.73%

**Pinbar_Bull**: 类比OB, 回调到pinbar低点=测试支撑, 用回调入场

### 入场模式对照表

| POI类型 | 入场模式 | 入场价 | 等bar | SL | 原因 |
|---------|---------|--------|-------|-----|------|
| OB_Bull | retrace | zone_low | 7 | ×0.96 | 测支撑=牛 |
| Pinbar_Bull | retrace | zone_low | 7 | ×0.96 | 同OB |
| FVG_Bull | immediate | next open | 0 | find_sls | 回调=填缺口=熊 |

### 10. OB上下文矩阵 (CTX→POI, V6)

**矩阵**: POI(OB/FVG/Pinbar) × CTX(LIQ/STRUCT), 共15种组合, 实际V6有10种
**核心**: OB_Bull是明星信号(WR=94.1%), 上下文增强非替代, CTX→OB作为标签非独立交易
**诊断**: 信号缺失排查→sbb统计→gap分布→dedup冲突→RR过滤→break bug→scoring权重
**关键发现**: ctx_count=3时WR=98.9%; gap=1-3最优; L2组合在MeanReversion最有效

### 11. 信号角色 (SMC正解 + V6验证 2026-05-14)

| 信号类型 | 角色 | V6表现 | 说明 |
|----------|------|--------|------|
| LIQ (Sweep_SSL, EQL) | 事件起点 | combo=62-76% | 流动性猎杀→POI |
| STRUCT (BOS, CHOCH, MSS) | 事件起点 | combo=50-72% | BOS→FVG最优(72.5%) |
| OB_Bull | 独立策略+上下文锚点 | WR=94.1% | 完整事件产物, 12438个 |
| FVG_Bull | 组合ZONE端 | combo=62-72% | 需前序事件确认 |
| Pinbar_Bull | 组合ZONE端(V6新增) | combo=44-76% | 2026年退化严重 |

**L2组合回测(gap1-10)**:
  EQL→Pinbar: 428笔 WR=72.4% avg+2.39% PF=4.7 (最佳L2)
  BOS→FVG: 365笔 WR=69.6% avg+2.16% PF=3.5
  CHOCH→FVG: 174笔 WR=69.5% avg+2.16% PF=3.7
  Sweep_SSL→Pinbar: 950笔 WR=46.0% avg+0.56% PF=1.4 (最差, 量最大)

### 高概率入场 Checklist

```
✅ 条件 1: 高时间框架趋势方向一致 (Daily/Weekly 顺向)
✅ 条件 2: 发生了流动性猎杀 (SSL/BSL Sweep)
✅ 条件 3: 出现了 CHOCH (结构转换)
✅ 条件 4: 存在 Unmitigated FVG 
✅ 条件 5: 存在 Order Block
✅ 条件 6: 价格在 Discount Zone (OTE 0.618-0.79)
✅ 条件 7: 当前时间是 Killzone
✅ 条件 8: 价格在 PD Array 区域内出现确认K线（针形/吞没/孕线）

满足 5/8 = 可以考虑入场
满足 6/8 = 高概率入场
满足 7/8 = 极大概率
满足 8/8 = 圣杯级（极罕见）
```

## 10. 各市场应用

| 市场 | 最佳时间框架 | 最佳 Killzone | 注意事项 |
|------|-------------|---------------|----------|
| **A 股** | Daily / 60min / 15min | 9:30-10:30 AM CST (A股开盘) | T+1, 无杠杆, 只用多单 |
| **港 股** | Daily / 60min / 15min | 9:30-10:30 AM HKT | T+0, 无杠杆 |
| **美 股** | Daily / 4H / 15min | NY Open 9:30-11:30 AM ET | T+0, 有杠杆 |
| **加密货币** | 4H / 1H / 15min | 24h 但 NY Open 最佳 | 7x24, 高杠杆, 波动大 |

## 11. 风险控制

### 每次交易
- 单笔风险 ≤ 总资金的 1-2%
- 盈亏比至少 1:2 (建议 1:3)
- 如果 FVG 被完全填充 → 退出交易（信号失效）
- 如果 OB 被突破并收在该侧 → 退出交易

### 仓位计算
```
仓位 = (账户资金 × 风险百分比) ÷ (入场价 - 止损价)
```

### 不适合交易的情况
1. 没有 Killzone（流动性低，点差大）
2. 没有 Unmitigated FVG
3. 价格不在折扣区
4. 重大新闻发布前后 30 分钟（非农、CPI、FOMC）
5. 高时间框架趋势与信号方向不一致

---

## 附：常用缩写速查

| 缩写 | 全称 | 含义 |
|------|------|------|
| HH | Higher High | 更高的高点 |
| HL | Higher Low | 更高的低点 |
| LH | Lower High | 更低的高点 |
| LL | Lower Low | 更低的低点 |
| BOS | Break of Structure | 结构突破（趋势延续） |
| MSB | Market Structure Break | 同 BOS |
| CHOCH | Change of Character | 结构转换（趋势反转） |
| BSL | Buy-side Liquidity | 上方流动性（空头止损） |
| SSL | Sell-side Liquidity | 下方流动性（多头止损） |
| FVG | Fair Value Gap | 公允价值缺口 |
| IFVG | Inverse FVG | 反向 FVG |
| OB | Order Block | 订单块 |
| OTE | Optimal Trade Entry | 最优交易入场 |
| PD Array | Premium/Discount Array | 溢折价阵列 |
| **PO3** | Power of 3 | 蓄势-操纵-分配三阶段 |
| EQH | Equal Highs | 相等的双顶 |
| EQL | Equal Lows | 相等的双底 |

---


## 跨表同步审计（V27）

当用户报告“信号不准确 / 回测和选股不一致 / 图表和复盘不一致”时，不能只在单点调参数。必须同时检查：
- 回测交易是否按同一信号语义生成
- 选股列表是否复用同一锚点和过滤逻辑
- K线图表的标记是否读取相同字段
- 分析/复盘是否使用同一胜负口径

**常见修复准则**
- 历史 trade 没有 `won` 字段时，统一用 `pnl_pct > 0` 回退
- zone 回撤默认按 wick touch 语义检查，不要用 close-only 代替
- 任何 UI 派生布尔值都必须与后端交易口径一致

详见：`references/v27-cross-surface-sync-audit.md`

1. 选取1-2只代表性股票（高波动+蓝筹）
2. 逐bar输出完整K线(OHLC) + 摆动点标记 + 每个bar上的所有信号及zone/penetration
3. 对照Pine标准逐信号验证：bar位置是否正确、是否重复、是否遗漏
4. 根因定位到代码行级别（如"OB搜索方向错误"），而非调ATR倍数

**关键已知缺陷**：
- OB: LuxAlgo必须从break bar **向后**搜索最近反向K线（非swing→break向前）
- CHOCH/BOS: 需要ATR×0.2穿透确认，同方向3bar去重
- Sweep: 必须3bar cooldown per direction，仅扫30bar内最深穿刺
- EQL/EQH: 类型名必须匹配SIG_STYLE的`EQL_High`/`EQL_Low`
- SMC2026 OB (confidence=0.65): 仅渲染，不交易。LuxAlgo OB (confidence=0.75): 用于交易

**⚠️ SMC纯结构原则**: 选股和交易决策**不得使用通用技术指标**（MA20、距N日高/低百分比、RSI等）。SMC选股仅基于市场结构：Demand Zone确认 → 价格反弹 → 流动性清扫 → CHOCH反转 → 回撤到Zone。评分基于SMC事件计数，非百分比阈值。

详细诊断方法论及V20→V22完整修复清单见: `references/signal-accuracy-diagnostic.md`
SMC信号同源/SignalRegistry/Pine对齐审计见: `references/signal-registry-pine-alignment-audit.md`
V66 语义硬门禁、OB亏损桶、多回踩rank、每日全市场覆盖审计教训见: `references/v66-semantic-gate-lessons.md`
V66 字段+语义闭环修复模式（物理JSON、轻量缓存、选股页、实时API、K线API一起验收；strict失败时只标记semantic_layer不声称信号正确）见: `../smc-v11-system/references/v66-field-semantic-closure.md`
V175/V128 溯源与 active picks 同步审计（V175按`original_event_type`回溯V128；当前V128刷新后若候选数不同，先判定物化滞后，不要误判历史回测失效；API污染口径区分active picks与live HOLDING）见: `references/v175-v128-provenance-active-picks-audit.md`
SMC前端字段契约修复模式（/monitor、/live、/api/picks、/api/live-prices 的选股日期/加入日期/Zone/成本线/波动统一回填；嵌套zone/production_gate/raw_pick合并；浏览器别名pickDate/costLine/volClass同步）见: `references/frontend-field-contract-repair.md`
V172 strict registry 晋级/回退教训（语义100%通过但效果失败仍必须回退）见: `references/v67-strict-registry-gate-lesson.md`
V173/V175 质量边界与语义拆分教训（V173只可研究叠加；V174证明古典SSL→CHOCH不是V172盈利主体；V175把生产语义改为DEMAND_OB_TRUE_TAKEOVER_RECLAIM并保留古典结构审计字段）见: `references/v173-v175-quality-frontier-semantic-split.md`
SMC纯结构选股及Score评分体系见: `references/smc-pure-scanning.md`
K线渲染架构(ECharts markArea/markLine/markPoint)见: `references/kline-rendering-architecture.md`
K线SMC信号坐标对齐(date优先于旧idx，分层排查候选高亮/通用信号/结构线/交易标记)见: `references/kline-smc-date-index-alignment.md`
波浪锚定OB与K线同步陷阱见: `references/wave-aligned-ob-and-kline-sync.md`
V66/Phase2 SL 根因审计模式（实盘多数 SL 时必须检查 active pick 合法性、SL公式回测/实盘一致性、回撤触碰 vs 收复确认、OB/FVG分流、ledger/review闭环）见: `references/v66-phase2-sl-root-cause-audit.md`
V286-V288 父级 Regime + 滚动窗口审计（每股 DNA 失效后，转向市场/行业滚动参与度；UP_CONT_DOWN + W10_RET_POS 达 N=626/WR=63.58%，risk8 子集 N=190/WR=80.53%，仍需 scanner-time 合约验证后才可接生产）见: `references/v286-v288-parent-regime-rolling-window.md`
V286/V287 父级状态与同源60min生成器闭环教训（市场/行业父级状态有效但不充分；同源60min传统takeover全量仍弱；A股T+1下“恐慌刺穿未收回+次日反包”成为新候选方向，下一步做V288 gap/open+父级过滤+rolling验证）见: `references/v286-v287-regime-router-closure.md`
V284 60min SMC子结构序列审计教训（前日60min touch→reclaim→MSS→HL hold 未能提升质量，说明当前日线zone与低级别真实接管POI错配；下一步应同源多周期生成而非日线zone反查60min）见: `references/v284-60min-smc-sequence.md`
SMC全架构/实盘SL/低RR闭环审计模式（先验证daily selector是否与前端生产版本一致、DIAGNOSTIC_ONLY污染、risk合同冲突、显式SL/TP/RR/exit_legs缺失，再归因POI早死/RECOVERY弱/低RR/未来target语义风险）见: `references/smc-full-architecture-live-sl-audit.md`
Phase2 严格 L→D 生成器重建模式（先隔离生成器，不碰前端/生产；审计信号同源、时间顺序污染、历史高胜率是否真回撤；全市场按 FVG/OB、RR、risk、retrace 分桶，候选如 FVG_Demand + RR0.8 + risk6-8）见: `references/phase2-strict-ld-generator.md`
Phase2 SMC语义根因审计（胜率仍低时不要调参；拆分FVG延续 vs OB回踩，验证FVG immediate是否强于reclaim，检查time decay、mitigation次数、OB是否只是last down candle、pinbar是否被错误用于FVG）见: `references/phase2-smc-semantic-root-cause.md`
Phase2 L→D SL/入场根因审计（用户追问“为什么这么多SL”时，必须四层拆解：信号质量FVG vs OB、入场成交reclaim close vs zone limit、SL锚点、TP/RR；优先验证 FVG_Demand only + 真实可成交zone limit entry + structure SL + BSL/RR hybrid TP）见: `references/phase2-ld-sl-entry-root-cause.md`
V70 zone-dead/reaction-confirmation 教训（当SL中`zone_dead`占比极高时，不要继续调SL/TP；必须逐笔审计zone是否收盘死亡、趋势是否错误、入场早晚、MFE/恢复情况；FVG Demand需要touch后reclaim/two-bar reaction再next-open入场，structure SL + micro TP可作为高精度子引擎候选）见: `references/v70-zone-dead-reaction-confirmation.md`
V70 90% WR 信号层门禁/晋级教训（当entry/SL/TP矩阵最高仍<90%时，必须证明SL是否`ZONE_DEAD`主导，再引入非泄漏的市场广度、个股状态、zone宽度、sweep pierce、risk band门禁；90%+但n<100或年份集中时只保留研究候选，不接生产）见: `references/v70-90wr-signal-gate-and-promotion.md`
V201-V202 post-V175 研究闭环（V85 target-room 扩展与 Baostock 60min micro-resolution 均未过门禁；V175仍为基线；下一步必须是全量历史60min候选生成/板块资金/竞价订单流等新预入场信息层）见: `references/v201-v202-target-room-and-60m-micro-closure.md`
V183-V186 post-V175 generator closure（V128 target geometry、fresh daily lifecycle OB/reclaim、strict 3-bar takeover、source-rule mining 全部未过门禁；下一步必须改事件定义为 swing/liquidity/wave anchored generator，而非继续调阈值）见: `references/v183-v186-post-v175-generator-closure.md`
V183-V185 post-V175 research closure（V175后续研究闭环：V183原始K线反转生命周期失败，V184原始K线延续HOLD失败，V185 V128增强源特征无frontier；下一步必须引入市场/板块广度上下文+预入场目标几何，而不是继续标量过滤/通用exit）见: `references/v183-v185-post-v175-research-closure.md`
V189-V191 post-V175 新特征源闭环（anchored VWAP/机构成本、涨停注意力、东财板块同行确认全部未通过；高WR多为micro-profit污染；停止继续切V128/V167/V175，除非引入真实新数据/语义层）见: `references/v189-v191-new-feature-source-closure.md`
V71 Context→Event→POI 状态机教训（FVG改OB或OB锚到sweep源头仍不能解决时，不要再调字段/T+1/TP/SL；必须先识别市场状态、事件类型、POI折价/OTE位置、touch+reclaim反应和POI/结构失效语义）见: `references/v71-context-event-poi-state-machine.md`
V78/V79 全量候选生命周期审计教训（趋势→事件→POI→入场→失效必须拆开验证；旧候选层筛选能提高总体质量但2023/2024覆盖失败时，下一步是重建候选生成器V80，而不是继续加门禁）见: `references/v78-v80-lifecycle-signal-layer.md`
V66 前端/实时/选股数据源一致性审计（字段不空但页面/报告不一致时，必须分离 current picks、positions历史仓位、live API、ledger/review；不要把历史OPEN/PENDING当今日有效选股）见: `smc-v11-system/references/v66-frontend-live-data-source-consistency.md`

Continuation 候选/生命周期全量闭环（必须物理OB去重、剔除BOS前已mitigate/invalidate的zone；语义行数/TAKEOVER数不可当候选或交易数）见: `references/v351-v357-canonical-continuation-lifecycle.md`。对同一未触及OB被多个后续BOS重复引用的 canonical identity、最早因果事件保留、右侧未观测 `WAIT_*` 分母处理，以及 no-write 生命周期边界，补见：`references/continuation-poi-lifecycle-canonicalization.md`。
V286 父级市场/行业 Regime 选择器 walk-forward 教训（每股DNA失败后，上移到父级状态选择语法；2024/25提升但2026仍崩，说明历史fit父级规则不能直接生产）见: `references/v286-parent-regime-selector-walkforward.md`
V287 60min-first 同源生成器教训（日线POI反查60m失败后，改为60m sweep→reclaim→MSS先生成POI；整体仍不足，但 FAST+DAILY_LOW+RISK6_8 是下一步候选方向）见: `references/v287-60min-first-same-source-generator.md`
V233/V234 post-V231亏损闭环（V231剩余亏损仍主要来自V175老行的reclaim追高/实体过热/risk偏高；`reclaim_close_pos<=0.9592`等只能算research overlay，minYear不足不可生产；V234 overlay+new supply无严格frontier，下一步应做V235 fresh generator而非继续旧行阈值微调）见: `references/v233-v234-v231-loss-frontier-closure.md`
V183/V184 供给层 payoff 与反应质量闭环（V85/V90/V128/V175 旧供给继续做源侧过滤只能得到高波动尾部收益，不能通过 WR/年份稳定门槛；下一步必须改候选生成器本身）见: `references/v183-v184-supply-payoff-reaction-closure.md`
V198-V200 Baostock历史60min研究闭环（V199 base_60m接近晋级但Avg<6.2且micro>1；V200 rr2.5_h15_lock03_1r为近前沿但micro=2.43仍不可用）。**数据因果门禁**：跨年60min单请求会静默截断至约1,500根，必须按自然年查询并逐日核对四个时段；生成器/成交只能使用`adjustflag=3`原始OHLCV，复权价不可作为历史执行输入。全市场严格覆盖审计通过前，不允许产出MTF策略收益结论。详见: `references/v198-v200-baostock-60min-research.md` 与 `references/v367-v371-intraday-data-and-causality-closure.md`。
V183-V186 post-V175研究闭环（V128/V167/V175继续过滤、V183 fresh/classical/target geometry、V184非泄漏前沿、V185市场宽度均关闭；唯一有价值种子是V85 HOLD_ABOVE_POI + target room>=10%，需重建供给而非过滤旧行）见: `references/v183-v186-post-v175-research-closure.md`
V195-V197 raw absorption/reclaim 生成器闭环（raw absorption、source-quality frontier、breadth overlay 均未通过；V197高Avg口袋年覆盖不足，不可降门槛推广；下一步只能引入新数据/语义层）见: `references/v195-v197-absorption-closure.md`
V81 context-first Smart Money generator lesson（单股POI层失效时，必须按 Environment→Trend→Event→POI→Entry→Semantic Exit 重建候选生成器；V81原型证明方向正确但质量门禁过宽，V82应聚焦真/假RECOVERY、MIXED阻断、POI反应强度和T+1构造式执行）见: `references/v81-context-first-smart-money-generator.md`
V183-V185 fresh-generator negative closure（V81 fresh supply、最佳动量+target pocket、执行矩阵、日/周MTF全部未过门禁；下一步必须重建供给层：displacement→新Demand POI→结构HL/reclaim，而非继续过滤旧V81/V128/V167）见: `references/v183-v185-fresh-generator-negative-closure.md`
V183-V185 raw generator closure（raw SSL lifecycle、reaction confirmation、raw BOS continuation全市场失败；不要继续调日线SSL/BOS通用生成器，下一步应重建V132 true-takeover源特征或补历史60min）见: `references/v183-v185-raw-generator-closure.md`
V183/V184 post-V175 supply closure（raw Pine-like strict SSL sweep→CHOCH→OB generator全市场失败；V85高WR短线供给runner无法升级为V175子引擎；下一步必须在入场前证明post-reclaim takeover，而不是继续过滤/runner覆盖）见: `references/v183-v184-supply-generator-closure.md`
V185-V190 env breadth + conservative runner frontier（V175后首个质量候选：source-side 市场广度 + takeover persistence + wide zone，V129小目标不可用；保守trail需只用前序bar高点，当前仅shadow/promotion candidate）见: `references/v185-v190-env-breadth-runner-quality-frontier.md`
V185 production promotion closure（V175 + 非重叠 true-takeover runner child，334笔/WR86.23/Avg6.56/minYear41/yearWRmin82.81/T+1=0；含生产候选物化、smc_unified路由补丁、API验收）见: `references/v185-production-promotion-closure.md`
V185继续研究V316-V319闭环（出场矩阵、动态出场、V167候选供给、60min覆盖均未过生产门槛；当前V185保持baseline，M60本地缓存不足以做2023-2026全量晋级）见: `references/v316-v319-v185-continuation-closure.md`
日线分支关闭后，60min历史数据源与延迟确认必须先过严格因果/完整性审计：按每股日线日期核对4个60min时段；takeover_2/3等后续确认不可倒灌到更早entry，见: `references/v367-v371-intraday-data-and-causality-closure.md`

全历史 intraday SMC 的四时段覆盖、局部 MSS 锚定、候选与可执行订单分离、T+1 串行持仓，以及“因果正确但经济无边际”时关闭整个语义分支的流程见: `references/full-history-intraday-causal-frontier.md`

同源60min重建 raw daily 后的逐股数据门禁、异常日分段隔离、独立语义差分、真正的日线POI→60min touch/reclaim/hold→next-open 串行T+1回放，以及经济门禁失败即停止 Oracle/shadow/UI 晋级的完整合同见：`references/raw-daily-true-mtf-data-gate.md`

V379–V385 raw-source PIT context frontier：在固定 MTF 执行合约后，先做 outcome-blind 数据门禁，再以预声明的市场参与度/行为同群状态做结果分桶；弱提升未过跨年发现门槛时必须关闭价格派生上下文分支，转向带原始发布时间的独立事件或资金数据。详见：`references/v379-v385-pit-context-frontier.md`

**历史分钟数据合同补充**：V371 级全市场 source audit 必须按自然年分块（防止 provider 约1,500 bar 静默截断）、逐日核对四个 60min 时段，并对会话失效重试同一请求后再判数据缺失。当前 qfq 日线不可混用 raw 60min；必须先做日线/分钟价格口径聚合对齐，随后再进行 raw-vs-qfq 结构差分和“确认后下一根开盘”因果重放。详见: `references/intraday-data-contract-and-causality.md`。

V320-V322 raw supply/regime closure（压缩突破回踩、SSL sweep reclaim、市场宽度overlay均未过生产门槛；raw daily事件供给多但precision低，下一步必须证明post-event absorption/takeover persistence）见: `references/v320-v322-raw-supply-regime-closure.md`
V320-V323 fresh supply/current scanner闭环（raw compression与raw SSL新供给均失败；V246历史强但current exact route不可重建；V323仅1条shadow行TP，不能生产晋级）见: `references/v320-v323-fresh-supply-current-scanner-closure.md`
V185 cron productionization gap（API/前端显示V185不等于定时任务全链路已切V185；必须分开审计smc_daily_closed_loop、smc_daily_ops、morning_push、ops_latest、旧V167审计cron）见: `references/v185-cron-productionization-gap.md`
V185-V205 post-V175 qualitative breakthrough（V175+V185 child combined passes shadow production gate: n=334/WR86.23/Avg6.56/minYear41/yearWRmin82.81/micro0.90/T+1=0；已完成V203独立校验、V204 shadow materialization、V205 endpoint mapping smoke；下一步是GitNexus impact后接V185_SHADOW路由，不再继续daily scalar search）见: `references/v185-v205-shadow-candidate-breakthrough.md`
SMC生产验证/版本化API smoke模式（验证“改造是否正常执行”时必须 py_compile→重跑确定性脚本→读artifact指标→smoke `/api/summary`/`/api/picks`/`/api/live-prices`；注意 `?version=` 可能不被代码读取、`?ver=` 缺分支会fallback到当前生产，需区分版本化查询兼容bug与生产污染）见: `references/smc-production-validation-and-versioned-api-smoke.md`
V188 post-V175 closure（V183 classical sweep、V184/V185 old pools/breadth、V186 micro confirmation、V187 accumulation、V188 impulse-demand retest均关闭；下一步必须引入新的入场前语义特征源或做最新V128 active-pick重物化）见: `references/v188-impulse-demand-retest-closure.md`
V192-V194 post-V175 continuation closure（limit-up demand retest、FVG微利runner、HTF结构门禁全部失败；V177-V194关闭旧候选过滤/退出/上下文路径，下一步必须从原始K线构建“吸收证据”新事件源）见: `references/v192-v194-post-v175-research-closure.md`
V109 RANGE_TRANSITION 确认语义重建教训（BULL_EXPANSION需拆 TREND_UP vs RANGE_TRANSITION；RANGE_TRANSITION 不得用 0-7 bar 无第二结构确认的过早入场；必须报告 unique(symbol,entry_date) 去重口径，避免 REVERSAL/CONTINUATION 双 family 重复放大样本；只作研究，不接生产）见: `references/v109-range-transition-confirmation.md`
V275 时间顺序组合/参数审计（BOS→Demand→Retest 可放大量但质量塌陷；SSL_BEFORE_ZONE/9-20bar有弱增益但远低生产门槛；股票DNA必须walk-forward；下一步应重建全事件语法漏斗而非继续调BOS/demand/wait参数）见: `references/v275-temporal-sequence-param-audit.md`
V282 真实行业参与度 + 分层时间语法审计（V280已证明日线机会并不少；前日全市场+行业强度可把 ABSORB_FAST 大样本抬到约55%WR，但跨年仍不稳；下一步必须做60m reaction/MSS接管确认）见: `references/v282-industry-participation-sequence.md`
V283 60min 前日反应覆盖审计（4553个60m缓存仅近端覆盖17,294候选；粗60m收益/收盘位置/MSS最优大样本仅56%WR，下一步需真正60m sweep→reclaim→micro-HL/MSS子结构确认器）见: `references/v283-60min-reaction-overlay.md`
生产闭环审计方法（历史污染物理隔离、daily full-market completeness、信号语义 vs 溯源边界、multi-retrace 审计）见: `references/smc-production-closure-audit.md`
V246 历史高质量候选晋级当前生产的阻断/闭环模式（历史通过不等于当前可执行供给；必须按 V161/V175/V211/V185_CHILD 分线重建、排除历史重叠、actual_bars<=10、再做T+1 SL/TP/max_hold执行重放；V327最新结论当前open=0，不路由endpoint）见: `references/v246-current-supply-promotion-closure.md`
V246/V236 当前供给闭环教训（历史 selected-only 高胜率不能晋级；必须全 V164 宇宙验证；current 候选需 T+1 executable replay；breadth/industry 等前置缓存必须先验新鲜度，避免 stale cache 误杀供给；`CLOSED_BY_EXECUTABLE_REPLAY` 等状态需按 contains CLOSED 统计）见: `references/v246-current-supply-cache-and-selected-only-audit.md`
V246/V334 当前供给与全宇宙闭环审计教训（selected-only 高质量不可直接晋级；必须 lineage current supply → T+1 replay → full-universe validation → numeric frontier 全链路通过；若高WR子集样本不足/无当前供给且大样本WR/avg不达标，应关闭该信号族晋级路线）见: `references/v246-v334-current-supply-full-universe-closure.md`
V335–V337 退出结构 vs 信号族上限审计（历史selected-only高胜率不能晋级；固定TP/SL与TP1+runner都无法同时满足WR/Avg时，不要继续调退出，必须做MFE/MAE诊断并重建扩张过滤/供给层）见: `references/v335-v337-exit-signal-ceiling-and-mfe-diagnosis.md`
V158–V160 non-leak lifecycle 稳定性教训（V158聚合达标但V159月度/rolling暴露弱期；V160未找到完全稳健纯SMC门禁；下一步必须做dry-run scanner contract与字段可用性审计，不得直接生产晋级）见: `references/v158-v160-lifecycle-stability.md`
V164 corrected scanner rule dry-run 教训（V160 scanner BUY 泄漏非 TRUE_TAKEOVER；真实 scanner 晋级前必须显式应用 `(TRUE_TAKEOVER_2 OR TRUE_TAKEOVER_3_STRICT) AND body<=87.1077`，并 dry-run 证明 0 outcome leak / 0 non-takeover BUY / 0 production write）见: `references/v164-corrected-scanner-rule-dry-run.md`
V90/V103A 生产源隔离与闭环审计（summary/picks/live 不同源、V103A历史完成交易伪装active、V91 shadow混入、WATCH_ONLY被算作tradable、daily completeness零active仍应通过等问题）见: `references/v90-v103a-production-source-isolation.md`
SMC cron / morning push 超时恢复（daily ops总耗时>15分钟、外层timeout需2400s、/api/picks是list、WATCH_ONLY不得冒充生产选股）见: `references/smc-cron-timeout-recovery.md`
生产闭环审计方法（历史污染物理隔离、daily full-market completeness、信号语义 vs 溯源边界、multi-retrace 审计）见: `references/smc-production-closure-audit.md`
V103A 生产链路/active/前端一致性审计（底层全量信号→生产池→active→/api/picks 压缩异常；区分代码级未来函数、时序语义污染、后验白名单；检查 summary/picks/live-prices 同源）见: `references/v103a-production-chain-audit.md`

## V105/V106/V107 结构-市场门禁教训

Strict reclaim 语义通过后，如果 WR/月度稳定性仍不足，不要用 `0.6R` 微止盈或人为收紧 SL 伪晋级。必须回到原始结构 TP/SL，分层验证 `retrace_pct`、`risk_pct`、市场宽度/环境门禁；若最佳结构出场仍低于晋级门槛，下一步是重建 `TRADEABLE_REGIME` 市场状态层，而不是继续调 TP/SL。详见: `references/v105-v106-structure-market-gate.md`

生产闭环审计方法（历史污染物理隔离、daily full-market completeness、信号语义 vs 溯源边界、multi-retrace 审计）见: `references/smc-production-closure-audit.md`
V81 context-first Smart Money generator lesson（单股POI层失效时，必须按 Environment→Trend→Event→POI→Entry→Semantic Exit 重建候选生成器；V81原型证明方向正确但质量门禁过宽，V82应聚焦真/假RECOVERY、MIXED阻断、POI反应强度和T+1构造式执行）见: `references/v81-context-first-smart-money-generator.md`
V172/V167高质量门禁（V167可用后用 zone_width>=2 + post3_pullback<=2 做质量升级；区分生产可用/质量升级/不可用边界，并要求 /api/picks 与 /api/live-prices 实时守门一致）见: `references/v172-v167-high-quality-gate.md`
生产闭环审计方法（历史污染物理隔离、daily full-market completeness、信号语义 vs 溯源边界、multi-retrace 审计）见: `references/smc-production-closure-audit.md`
V164→V167 scanner-contract到production-candidate晋级门槛（先经济可用性矩阵，再scanner-time精确规则，再endpoint隔离；V167候选规则为BEAR_RISK+DEMAND_OB+TRUE_TAKEOVER_3_STRICT+body<=65，TP=1.5R/10bar/SL zone_low-1%）见: `references/v164-v167-scanner-to-production-gate.md`
V144 UI/API dry-run 合同模式（把 late-known lifecycle/failure metadata 映射为可展示、不可交易 payload；强制 `shadow_only=true`、`production_write=false`、`trade_action=NO_BUY`、0 outcome leak、0 BUY contract violation，并读取生产快照证明未污染 watchlist/前端/生产配置）见: `references/v144-ui-api-dry-run-contract.md`
V144/V145 只读预览路由验收模式（新增 shadow/backtest 预览 API 时，必须验证 `/api/summary` 生产版本不变、`/api/picks` 与 `/api/live-prices` 无 shadow 版本污染、preview 全部 `shadow_only` + `NO_BUY` + 0 outcome leak）见: `references/v144-read-only-preview-route-verification.md`
生产闭环审计方法（历史污染物理隔离、daily full-market completeness、信号语义 vs 溯源边界、multi-retrace 审计）见: `references/smc-production-closure-audit.md`
生产闭环审计方法（历史污染物理隔离、daily full-market completeness、信号语义 vs 溯源边界、multi-retrace 审计）见: `references/smc-production-closure-audit.md`
V181–V183 供给层边界教训（V175后不要继续切 V167/V128 现有字段；强规则先审计 selector 字段是否 outcome leak；`exit_reason`/MFE/MAE/realized PnL/hit flags 禁止用于生产 selector；若强边只存在于结果字段，下一步是新候选生成器或 entry 前代理特征）见: `references/v181-v183-supply-layer-boundary.md`
V180-V182研究闭环/供给边界教训（V175后续研究方向判定：退出层、60min、V128过滤、V167剩余供给、延迟确认、固定runner均未过门槛；下一步必须重建真实新候选生成器而非继续过滤旧产物）见: `references/v180-v182-research-closure-and-supply-frontier.md`
V183-V187 post-V175续研闭环（严格SSL→CHOCH新生成器、压缩突破延续、breadth-only、V167 leftover+breadth均未单独过生产门槛；`v132_bull_count_3>=3`是下一代供给层首要机制；若已有V185-V205 shadow突破则停止daily scalar search，转入shadow路由集成）见: `references/v183-v187-post-v175-research-continuation.md`
V183-V206 V185 定性突破闭环（V185 combined 通过shadow production gate；child单独不可用；V203/V204/V205/V206B完成formal/current/shadow/API/live guard；下一步需GitNexus impact后才可路由前端）见: `references/v183-v206-v185-production-candidate-closure.md`
Post-V175研究方向治理（用户要求持续研究但不能无休止迭代时，先固定可用/不可用门槛，复核已完成artifact，关闭失败分支；V185 combined已成为新基线，后续研究必须击败V185而非只击败V175）见: `references/post-v175-research-direction-governance.md`
V183-V184 fresh generator负结果闭环（K线源BOS continuation与SSL sweep→CHOCH naive新生成器均不可用；下一步应重建true-takeover语义或补60min覆盖）见: `references/v183-v184-fresh-generator-negative-closure.md`
V183-V185 fresh generator负结果闭环（原始日K SSL→CHOCH→Demand OB、PO3、Demand OB true takeover 三条新供给层均失败；下一步先反向审计V128/V167稀疏构造能力，再写新生成器）见: `references/v183-v185-fresh-generator-negative-closure.md`
V186-V188 Baostock 60m闭环（V175 60m replay接近但micro不过关；延长/高RR会牺牲WR/年份稳定；V167 leftover即使60m也不过child gate；下一步必须做候选生成时的intraday语义，而不是退出层）见: `references/v186-v188-baostock-60m-closure.md`
V185-V187后续闭环（V128+市场宽度、post-reclaim微确认、raw accumulation breakout retest均未通过；下一步必须引入行业/板块同步或新的pre-entry takeover proxy）见: `references/v185-v187-post-v175-closure.md`
V183-V198 Post-V175 日线研究闭环（daily OHLCV + V128/V129/V167/V175 全部后续路径无新生产引擎；只剩历史分钟数据或全新entry前数据源才有质变空间）见: `references/v183-v198-post-v175-daily-research-closure.md`
V185 active 生命周期退出归档教训（active rows 不能只字段补齐；必须按 T+1 SL/TP/max_hold 合约机械回放，已触发退出的行从 active/picks 移除并归档到 reconciled_closed_active；空 active 合法）见: `references/v185-active-lifecycle-exit-reconciliation.md`

## V278 时间顺序组合/参数供给链审计（2026-07-02）

当用户指出“交易量偏少 / 每股机会应该很多 / 假定 SMC 原子指标无问题，重新研究组合指标与时间顺序参数”时，必须先做全市场供给链审计，不要直接继续收紧生产过滤器或只调 WR/RR。

固定流程：
1. 统计原始事件密度：SSL、BOS10/20/40、候选 Demand、retest。
2. 拆链路流失：BOS → demand20 → retest20 → executable entry。
3. 做时间顺序参数面：`BOS lookback × demand lookback × SSL window × reclaim mode × wait`。
4. 同时报供给量、每股机会密度、年度稳定性、SL/TP/Time 出口结构。
5. 若最优参数仍不达生产要求，明确停止调参，转向语义重建。

V278 关键结论：原始事件并不少（SSL 171,692；BOS10 219,455；BOS20 142,927；BOS40 91,090），宽松组合可达 180,802 个唯一机会/每股3年38.84次，但 WR 仅42.90%、SL 50.79%。最佳参数（如 BOS40 + demand5 + SSL20 + strict + wait3）也只有约49% WR。说明 `BOS → 最近阴线Demand → 回踩/收复` 实际退化为普通突破回踩；时间顺序参数只弱增强，不能把错误语义调成生产级。

下一步应重建组合语法：`Environment/Market State → Liquidity Event → Structure Shift → 真POI类型分离(OB/FVG/OB+FVG) → POI质量/mitigation/zone death → Reaction → Entry`。

生产闭环审计方法（历史污染物理隔离、daily full-market completeness、信号语义 vs 溯源边界、multi-retrace 审计）见: `references/smc-production-closure-audit.md`

**生命周期右边界、身份与当前前沿（V352–V355）**：30-bar 生命周期在K线缓存右边界不足30根时，必须输出 `WAIT_TOUCH_UNOBSERVED` / `WAIT_RECLAIM_UNOBSERVED` / `WAIT_HOLD_UNOBSERVED`，不得误标为 `EXPIRE_*`。统计/候选层不能把同一OB、相同触及-收复-接管路径的连续BOS当作多条独立setup；应保留事件来源列表，同时用OB+生命周期路径+状态建立setup身份。对于当前scanner视图，同一 `symbol + OB + exact zone` 的多个未决续发BOS路径必须保留为溯源，但只能物化一个canonical frontier状态：优先最新event，event相同时优先成熟状态（HOLD > RECLAIM > TOUCH）；zone不一致必须显式隔离为上游契约冲突，不能静默合并。当前shadow候选只允许未决WAIT状态且本地K线新鲜；这不是买入信号，历史60min覆盖未达门槛时不得进入60min回测或生产。

**独立语义差分门禁（V356）**：不能把“同一函数的自校验零失败”当作语义正确性。必须以独立实现逐个对照 `confirmed swing`、`structure`、`FVG`、`sweep`、`event-anchored OB` 的集合和因果锚点；结构对照时 MSS 是带sweep前序的 CHOCH subtype，应先归一为基础 break identity，另行审计 MSS 资格。V27 的首个可检测pivot为 index 6（left+right warmup），不是 index 3；必须显式写入合同。每日缓存推进后，旧seed集合不能与新缓存硬比，应先重跑语义源→差分→生命周期链。差分必须 `mismatch_total=0`、seed sets相等、结构swing/OB anchor均无未来因果，才允许刷新 shadow 生命周期；这仍不是生产晋级。

## ⚠️ V66 实现差距警告（2026-06-10 发现）

**当前 V66 生产系统不是真正的 SMC 回撤系统**，而是带 SMC 标签的突破交易系统。核心证据：`daily_scan.py:216` `entry_idx = c.bar + 1` — 确认后下一根开盘进场，100% 无回撤等待。

| SMC 理论要求 | V66 实际 | 证据 |
|-------------|---------|------|
| Sweep → CHOCH → 回撤到 POI → 确认 → 入场 | entry_idx = conf_bar+1 (下一开盘直接进) | 137/137 笔无回撤 |
| 流动性猎杀作为前序事件 | 不检查 sweep | 0/137 笔有 sweep 前序 |
| 市场状态(延续/反转/盘整) | market_state 全部为 "?" | 137/137 未计算 |
| POI 拒绝 K 线确认 | 无等待 | 137/137 立即入场 |
| SL = POI 下方 + ATR buffer | 45/137 笔 SL=zone_low | SL 在 zone_low 零缓冲 |
| 多信号合流(OB+FVG+CHOCH) | 仅单信号组合 | 0 笔三重合流 |

**差距分析全文见**：`smc-v11-system` 技能的 `references/v66-architecture-gap-analysis.md`

## V351–V359：语义生命周期不等于可交易优势（2026-07-11）

对日线 continuation 路径做研究回放时，必须分离 **语义成立**、**生命周期完成**、**可交易优势** 三件事：

1. 先用 `v354_lifecycle_setup_identity_audit.py` 按 `symbol + OB + touch/reclaim/takeover path + state` 去重；原始 BOS seed 不是独立 setup，直接回测会夸大样本。
2. V351 的语义种子仅为 `confirmed swing → bullish BOS → nearest bearish OB`；它没有把流动性 Sweep、CHOCH、未缓解 OB 作为生成器硬条件。V352/V353 的 `PERSISTENT_TAKEOVER` 仅证明 touch→reclaim→hold 与后续两根收盘在 zone_high 上方，不证明该 setup 有交易优势。
3. 执行研究必须从 takeover 后两根收盘确认，再于下一交易日开盘入场；退出从 entry+1 起检查，强制 T+1。止损跳空按开盘价，SL/TP 同 K 线按保守 SL，目标只能取入场前已确认的摆动高点。
4. V359 归因标签只能读取 BOS 收盘时可见的数据：OB 在 BOS 前是否已 wick-mitigated、15 bar 内是否有 Bull Sweep、30 bar 内是否有 Bull CHOCH。禁止用事件后的 K 线生成标签。
5. 若 identity-collapsed 全市场回放仍表现不稳定或 pre-mitigated OB 占压倒性多数，结论是 **生成器语义不合格**，不是修改 TP/SL 的理由；不得接入 production/watchlist/frontend。
6. V360–V362 稳定性门禁：任何从 V358/V359 结果上挖出的 pre-entry gate，必须再做 chronological stress（2024H1、2025Q1、2026Q1）和月度负收益检查；即使全年 2023–2026 均为正，只要压力窗口为负或负收益月份过多，就只能保留研究候选，不能晋级生产。严禁把 `exit_reason` 这类事后结果当作稳定门禁。

## V128→V131 Target-RR Shadow Gate（生产晋级前必查）

当 scanner/shadow 候选在语义退出或 time-stop 口径下看起来盈利时，晋级前必须用非泄漏目标重评估：入场前已知 BSL / prior high，若无则固定 1.5R；严格 T+1，退出从 entry 后一根 bar 开始。若重评估后出现“高胜率但 Avg 为负”，根因优先判定为目标/风险结构问题，而不是继续调 POI source 标签。

详见：`references/v128-v131-target-rr-shadow-gate.md`

## V152→V164 晋级/降级门禁补充

当后续审计证明当前 promoted 版本存在 synthetic BE、0.5% micro-profit 伪胜率、历史交易伪装当前选股、或 scanner-time 合同不完整时，必须先把该版本降级为历史诊断版本，再验证 `/api/summary`、`/api/picks`、`/api/live-prices` 和 `/`、`/monitor`、`/live` 浏览器 smoke 均不再路由污染版本。候选版本只有在 losing rows、excluded bucket、T+1、micro/synthetic、scanner-time dry-run、endpoint/browser 全部闭环后才能写前端；研究/字段合同不可直接晋级生产。

详见：`references/v152-v164-promotion-demotion-gate.md`

## 历史分钟数据与确认时序门禁（V366+）

当日线分支已关闭、研究转向历史 60min/15min 时，数据可得不等于允许回测。必须先完成全市场、逐年、逐日、逐时段覆盖审计；provider 对跨年请求可能静默截断，必须按自然年分块并检查实际首尾时间戳。日线与分钟数据先建立 raw/QFQ 价格口径合同：QFQ 只能用于与既有 QFQ 日线研究层对齐，raw 可成交价验证必须另做结构差分，二者不得混算 POI/SL/TP。

尤其禁止把 `takeover_2/3`、连续持有、未来 K 线 high/low/close 等确认特征倒灌给更早的 `entry_idx`。若独立重演发现 `entry_idx <= confirm_idx`，该结果族整体作废；表面 OOS、高 WR 或历史选择器不能修复未来污染。正确链路为 `event → fresh POI → touch → reclaim/hold confirm → 下一根可成交 bar open → T+1 replay`。全流程和最小证据包见：`references/historical-intraday-source-and-causality-gate.md`；确认索引逐笔审计、raw覆盖/qfq对齐双数据门禁与分支关闭规则见：`references/causal-replay-and-intraday-data-contract.md`。全市场 raw 覆盖→QFQ 对齐→因果 lifecycle 的执行顺序、以及 limited probe 不得替代完整 universe gate，见：`references/intraday-data-gate-and-future-confirmation.md`。

## 公告披露型新数据源 PIT 门禁

对前十大股东等“报告期快照”型新数据，必须先把 `symbol + report_end` 与公开公告记录绑定，再按公告日严格早于决策日的规则做全量覆盖审计；公告接口瞬时返回 HTML/非 JSON 时，只能记为待重试的请求失败，绝不能记为没有历史披露。详情、95%全体/逐年覆盖门槛和 no-write 证据表合同见：`references/pit-public-report-shareholder-source-gate.md`。