# SMC 系统故障诊断报告：为什么选不出股票、迭代与回测效果差

> 诊断日期：2026-08-17 | 数据源：本地完整镜像 + 运行中的 8890 仪表盘 API 实测
> 结论先行：**"没有股票选出来"当前是正确结果（经济门槛失败），但系统存在 3 个必须修复的工程缺陷（artifact 错位/漏斗 bug/前端硬编码），且迭代治理长期失效导致反复重测同一信息族。** 下面逐层给出证据。

---

## 一、前端实际状态审查（API 实测，非推断）

本地运行中的 8890 仪表盘实测（与远程同源）：

| 项目 | 实测值 | 说明 |
|---|---|---|
| `/api/summary` | `frontend_version=EMPTY_BOOK`，`production_state=FAIL_CLOSED_REPLAY_GATE_FAILED`，`production_blocker=V519_FROZEN_REPLAY_FAIL__CLOSE_ONTOLOGY__NO_VARIANTS`，`buy_enabled=false`，`active_buy_valid_count=0` | 前端诚实显示空仓 |
| `/api/picks` | `[]`（空） | 无任何选股 |
| `/api/live-prices` | `picks=[]`；`scanner_state=CURRENT_SCANNER_RAN_NO_PRODUCTION_ADMISSION`；漏斗：4889 股票 → SSL_BREACH 108 → SWEEP_RECLAIM **20** → HIGH_VOLUME_SWEEP_RECLAIM **20** → RESPONSE_BREAK 2 → FULL_SETUP 2 | 有 2 个候选但 `scanner_buy_valid_count=0` |
| 页面 | 导航 `SMC EMPTY_BOOK`，K 线链接固定 `ver=V517`，仪表盘"可交易候选 0 只" | 见下方"前端 V517 机制" |

### 前端"使用 V517"的机制（代码级）
- `lockEmptyBookKline()`（smc_unified.py）：brand 含 EMPTY_BOOK 且 URL 无 ver 参数时，**强制 K 线版本 = V517**
- 导航链接硬编码 `/kline?ver=V517`、持仓/扫描结果链接固定 `ver=V517`
- **结论：前端显示 V517 是 EMPTY_BOOK 下的"研究展示默认值"，不是生产选股版本。** 但 V517 是"量价吸收"本体，与当前 V697"纯价格"研究不是一回事 —— 用户看到 V517 容易误以为生产在用 V517。

---

## 二、选股链路断点（为什么一直没有股票：三重阻断）

### 阻断 1：经济门槛失败（正确阻断，根本原因）
两条最新研究链的冻结回放全部经济失败：

| 链 | seed | oracle | 冻结回放 | 失败点 |
|---|---|---|---|---|
| V517-V522（量价吸收） | ✅ PASS | ✅ PASS | ❌ **V519 FAIL** | V519：WR 59.8%/PF 1.50 但**月度门槛失败**（2023 多个月 0 交易）→ V520 阻断（`V520_BLOCKED__V519_FROZEN_GATE_FAILED`）→ V522 许可封锁 |
| V697-V699（纯价格 SSL-reclaim） | ✅ PASS（18,318） | ✅ PASS（18,318/18,318 一致） | ❌ **V699 FAIL** | V699：n=17,600、WR 53.3%（<55%）、**2023 avg -1.09%、2026 avg -1.72%、2023 WR 40.3%** → `CLOSE_ONTOLOGY__NO_VARIANTS` |

**按系统自己的规则（fail-closed），无 BUY_VALID 是正确状态** —— 这两条链的失败是"真失败"，不是 bug。

### 阻断 2：v700 scanner artifact 错位（工程缺陷，掩盖真实原因）
`v700_pure_smc_ssl_reclaim_current_scanner.py` **L16**：
```python
V697 = AUD/'v517_daily_effort_result_absorption_seed_gate_latest.json'   # 变量叫 V697，指向 v517！
V698 = AUD/'v520_daily_effort_result_absorption_independent_metric_audit_latest.json'  # 变量叫 V698，指向 v520！
```
**L121** admission 判定：
```python
admission_eligible = g.get('support_gate_pass') and a.get('audit_pass') and COMMITTED
```
实测：`g`（v517）support_gate_pass=true，`a`（v520）audit_pass=**false**（v519 失败）→ **admission_eligible=false** → 2 个候选（600873.SH vol_rank 0.25 / 601857.SH vol_rank 0.10）被标记 `RESEARCH_BLOCKED_NOT_EXECUTABLE`，`scanner_buy_valid_count=0`。

**危害**：
- `release_blocker` 报 `V698_INDEPENDENT_METRIC_AUDIT_FAILED` —— 而真正的 v698 是 `ORACLE_PASS`（oracle_pass=true）。**系统把"新链已通过"误报为"新链失败"**
- 当前恰好 V699 也失败了，所以最终结果（不买入）碰巧正确；**但一旦未来某个 replay 通过，这个错位会基于 v520 的旧状态误判准入，属于潜在误授权路径**

### 阻断 3：漏斗阶段 bug（展示错误）
v700 L138-142：`SWEEP_RECLAIM` 阶段名**从未被发出**（只发 CONFIRMED_SWING_LOW / SSL_BREACH / HIGH_VOLUME_SWEEP_RECLAIM / RESPONSE_BREAK / FULL_CURRENT_SETUP）→ `funnel['sweep_reclaim']` 与 `funnel['high_volume_sweep_reclaim']` **恒等**（实测都是 20）。而 v697 代码明确"量能仅诊断，不设门槛"（v697 L109），**漏斗标签"量能前20日Top20%"（smc_unified L2383）与实际逻辑不符**。

### 链图小结
```
V697 seed PASS ──> V698 oracle PASS ──> V699 replay FAIL（WR53.3%/年度负）→ 本体关闭 ✅正确
                                         └─> v700 scanner 找到 2 候选
                                                └─> admission 读 v520.audit_pass=false ❌错位
                                                      └─> RESEARCH_BLOCKED，0 BUY_VALID
```

---

## 三、迭代问题审查（为什么"迭代效果不好"）

### 3.1 反复重测同一信息族（最核心的迭代失效）
- **v519（量价吸收）与 v699（纯价格）失败模式同构**：2025 强、2023/2026 负、月频尾部失败 —— 两者本质都在测"日线 SSL sweep→reclaim"这一信息族
- v633 蓝图（7-26）已把"本地日线纯结构"列为**已关闭**（§1.1），v672（8-05）`STOP_STRATEGY_ITERATION__KEEP_EMPTY_BOOK`，v692（8-11）`PRICE_ONLY_FRONTIER_CLOSED`，v696（8-13）"仅允许新 PIT 维度重开" —— **但 v697 纯价格变体 8-14 仍被完整执行**
- 且 v697 的 support 门槛（300/40）**低于 v633 蓝图规定的 1000/300/500**

### 3.2 本体漂移（v517 → v697 不是小改动）
- v517 有量能门（`rank>=0.80`，L112），v697 删除（L109"diagnostic-only"）→ 输入集合变化约 5.34 倍（3,431 → 18,318 seeds）—— **这是本体变更，不是参数微调**
- 但 v697 的 `frozen_contract` 文本仍写"sweep volume in top quintile"、`causal_trace` 仍写 `high_volume_SSL`、`distinctness` 整段照抄 v517 —— **合同文本与代码不一致**

### 3.3 治理无代码级强制
- "[0] Frontier Registry 拒绝已关闭本体变体"只存在于文档，**无代码拦截** —— 每次"STOP"后靠新版本号即可绕过
- 结果：hermes 以最高纪律跑完每一轮（oracle 精确、T+1=0），却系统性重复验证同一个已证伪的信息族

---

## 四、回测问题审查（为什么"回测效果不好"）

### 4.1 早期回测（v11/V44 时代）指标不可信 —— 已实证的缺陷
- **TP 前视偏差**：v44_engine L899-957 用 entry 之后 120 根内的 CHOCH/摆动点做 TP（实盘不可预知）
- **T+1 后补**：V6 同根 K 线触发 SL/TP；V476 仍有同日 exit，靠 V477 补丁修复
- **无成本模型**：PF=135/RR>9/WR>90% 类结果未计佣金/滑点/涨跌停
- **无样本外**：auto_optimizer 200 迭代在同一批数据上搜索

### 4.2 后期冻结回放（纪律正确但经济失败）
- 冻结回放已消除未来函数（独立 oracle 零差异、T+1=0、费用 0.20%）
- **但真实经济性不达标**：所有大样本本体 WR 53-58%（门槛 55%），且 **2023/2026 年度系统性负收益**（V699 2023 avg -1.09%、2026 avg -1.72%）
- **核心结论：这不是回测 bug，而是"日线价格/量价族的真实 edge 不足以跨年度稳定盈利"这一市场事实** —— 系统反复验证了这一点（v519、v699 同构失败）

---

## 五、根因归类与修复路径

### A. 必须立即修复的工程缺陷（明确、可执行）
| # | 缺陷 | 修复 |
|---|---|---|
| 1 | v700 admission 读错 artifact（V697→v517、V698→v520） | v700 L16 改指 v697/v698/v699 的 latest；L121/L145/L151 改用 `oracle_pass` + `promotion_gate_pass` |
| 2 | 漏斗 `SWEEP_RECLAIM` 阶段缺失 + 量能标签造假 | v700 L100 补发 SWEEP_RECLAIM 阶段或删除该漏斗层；smc_unified L2383/L2450 文本对齐"量能仅诊断" |
| 3 | `reload_metrics` 优先读 V185（被否决版本）指标 | 改为只读 ACTIVE_VERSION 自己的 report |
| 4 | 前端硬编码 V517（nav 链接、_empty_book_page 数字） | EMPTY_BOOK 下显示"无生产版本"，K 线版本改为用户可选（不再锁死 V517） |
| 5 | contract 文本与代码漂移（v697 量能条款） | 用 v700/v697 的 `frozen_contract` 与代码条件做自动一致性校验 |

### B. 需要治理决策（中长期）
| # | 问题 | 建议 |
|---|---|---|
| 6 | 反复重测已关闭信息族 | 实现代码级 Frontier Registry：新本体必须声明与已关闭谱系的"不同因果维度"，否则拒绝创建任务 |
| 7 | 门槛低于蓝图（300/40 vs 1000/300/500） | 把 v633 门槛固化为检查脚本的硬约束 |
| 8 | 无 git 基线 | 立即 `git init` + 首次提交，后续每个版本可 diff/回滚 |

### C. 必须面对的根本事实
- **本地可得的日线/60min/15min 价格数据，在严格因果验证下不支撑跨年度稳定盈利的 SMC 本体**（V88 之后 70+ 版本零晋级是证据）
- 要突破，只有两条路：① 引入**新的因果信息维度**（V633 蓝图 Lane A-D：公告数值预测/公司条款/订单流/行业资金 —— 需补数据源）；② 接受"空仓是常态"，把系统收敛为"监控 + 极低频机会"工具
- **继续在同一数据族上换阈值/窗口/本体名迭代，已被本系统自己 10+ 次审计证明无效** —— 停止重复，转向新维度或工程收敛

---

## 附：修复记录（2026-08-17 已执行并验证）

### 修复 1：v700 scanner 指向真实 artifact ✅
文件：`E:\test\smc_project\hermes\scripts\v25\v700_pure_smc_ssl_reclaim_current_scanner.py`
- L16 改为指向 `v697_pure_smc_ssl_reclaim_seed_gate_latest.json` / `v698_pure_smc_ssl_reclaim_oracle_latest.json` / 新增 `v699_pure_smc_ssl_reclaim_replay_latest.json`
- admission 判定改用真实字段：`v697.support_gate_pass AND v698.oracle_pass AND v699.promotion_gate_pass AND epoch COMMITTED`
- `blocked_by` / `release_blocker` 改为准确报因（现显示 `V699_FROZEN_REPLAY_PROMOTION_GATE_FAILED`，此前误报不存在的 `V698_INDEPENDENT_METRIC_AUDIT_FAILED`）
- 验证：运行后 `blocked_by={v697:True, v698:True, v699:False, epoch:True}`，2 候选 0 BUY_VALID（正确）

### 修复 2：reload_metrics 停止读被否决版本 ✅
文件：`E:\test\smc_project\hermes\scripts\smc_unified.py`
- 删除 V88 下优先读 V185/V175/V172/V167/V102/V101/V100/V99 报告的 8 个分支
- 现在只读 ACTIVE_VERSION 自己的 report
- 验证：`reload_metrics()` 返回 `V88_PRODUCTION_CONTRACT`（不再含 V185）

### 修复 3：前端解除 V517 锁死 ✅
文件：`E:\test\smc_project\hermes\scripts\smc_unified.py`
- `build_nav()`：EMPTY_BOOK 下 K 线链接 `/kline?ver=V517` → `/kline`（用户自由选版本）
- `lockEmptyBookKline()`：改为 no-op（不再强制 ver=V517）
- `_empty_book_page`：去掉硬编码"（387笔）"数字
- 验证：页面 nav 无锁死、JS 无强制赋值、无 387笔

> 注：以上修复均在本地接管镜像完成并验证；远程 10.0.1.203 尚未同步（hermes 正在运行，直接覆盖有被其重写风险，需在冻结远程后同步）。

## 附：证据文件清单
- `E:\test\smc_project\hermes\scripts\v25\v700_pure_smc_ssl_reclaim_current_scanner.py`（L16/L121/L145-L151 错位，已修复）
- `E:\test\smc_project\hermes\smc_audit\v700_..._latest.json`（admission_eligible=false、漏斗计数、修复后 blocked_by）
- `E:\test\smc_project\hermes\smc_audit\v520_..._latest.json`（audit_pass=false、V520_BLOCKED）
- `E:\test\smc_project\hermes\smc_audit\v698_..._latest.json`（oracle_pass=true —— 与 v700 报错矛盾）
- `E:\test\smc_project\hermes\smc_audit\v699_..._latest.json`（2023 WR 40.3%/avg -1.09%）
- `E:\test\smc_project\hermes\scripts\smc_unified.py`（lockEmptyBookKline、reload_metrics、L2383/L2450，均已修复）
- 本地 API 实测：`/api/summary`、`/api/picks`、`/api/live-prices`（http://127.0.0.1:8890）
- `E:\test\smc_project\hermes\scripts\v25\v700_pure_smc_ssl_reclaim_current_scanner.py`（L16/L121/L145-L151 错位）
- `E:\test\smc_project\hermes\smc_audit\v700_..._latest.json`（admission_eligible=false、漏斗计数）
- `E:\test\smc_project\hermes\smc_audit\v520_..._latest.json`（audit_pass=false、V520_BLOCKED）
- `E:\test\smc_project\hermes\smc_audit\v698_..._latest.json`（oracle_pass=true —— 与 v700 报错矛盾）
- `E:\test\smc_project\hermes\smc_audit\v699_..._latest.json`（2023 WR 40.3%/avg -1.09%）
- `E:\test\smc_project\hermes\scripts\smc_unified.py`（lockEmptyBookKline、reload_metrics、L2383/L2450）
- 本地 API 实测：`/api/summary`、`/api/picks`、`/api/live-prices`（http://127.0.0.1:8890）
