# SMC 系统防再犯规则清单（踩坑记录 → 强制纪律）

> 用途：后续一切代码修改/回测/报告/前端工作必须遵守。违反任一条即视为缺陷。
> 更新：2026-08-17（汇总自运营文档 + 代码审计 + 故障诊断）

---

## 一、回测与执行纪律（血泪教训）

| # | 坑（历史事实） | 防再犯规则 |
|---|---|---|
| R1 | **V88 入场价不可成交**：532 笔中 73 笔（13.7%）zone_limit 价不在 entry_date 当日 [low,high] 内 | **回测入场价必须可成交**：入场价必须在入场日 [low,high] 区间内，否则改用 next-open 并重算 SL/TP/PnL；落地为断言 `entry_price ∈ [low,high]`，violation=0 才算通过 |
| R2 | **TP 前视偏差**（v11/v44）：TP 用 entry 后 120 根内 CHOCH/摆动点 | **目标必须入场前可见**：TP/SL 锚点只用 entry 前已确认的摆动点/结构点；禁止扫描未来 |
| R3 | **T+1 后补**（V6 同日触发 SL/TP、V476 同日 exit） | **严格 T+1**：入场当日禁止出场；出场合集从 entry 后第一根可交易 bar 开始；落地断言 same_day_exit_violation=0 |
| R4 | **无成本模型**（早期 PF=135 未计费） | **费用必须计入**：双边 0.20% 往返 + GAP_SL 跳空处理；SL 优先碰撞 |
| R5 | **同数据调参过拟合**（auto_optimizer 200 迭代同一批数据） | **冻结回放一次成型**：预注册参数，回放失败即 CLOSED_NO_VARIANTS，禁止结果后调参 |
| R6 | **样本-WR 幻觉**（小样本 WR 90%+） | **经济门槛硬约束**：n≥1000、每年 n≥300、WR≥55%、AvgNet≥+0.5%、PF≥1.15、payoff≥0.70、每年 AvgNet>0、每月 n>4、T+1=0；支持不足不得放宽 |
| R7 | **月度样本门槛失败**（V519 2023 多月 0 交易） | 逐月 n>4 是独立门槛，中间零交易月视为失败，不得省略 |
| R8 | **单标的重叠/串行违规** | 每标的串行单仓，重叠 identity 去重（symbol+日期身份） |

## 二、本体与谱系纪律（防"换皮重测"）

| # | 坑 | 防再犯规则 |
|---|---|---|
| R9 | **v697 本体漂移**：删了量能门槛但 frozen_contract/causal_trace/distinctness 仍写 high_volume | **契约文本与代码必须一致**：任何过滤条件删除/新增，必须同步改 contract 文本、causal_trace、注释、常量；落地为契约哈希校验 |
| R10 | **v700 读旧链 artifact**：变量名 V697 指 v517 文件、V698 指 v520 文件 | **artifact 路径必须与变量名/字段名一致**：变量名、路径、报告字段三方对齐；release_blocker 用真实字段（oracle_pass 而非 audit_pass） |
| R11 | **重复重测已关闭信息族**（v519 与 v699 同构失败仍重跑） | **新本体必须声明不同因果维度**：与已关闭谱系的差异须写进 distinctness，代码级 Frontier Registry 拦截 |
| R12 | **报告命名错位**：v697 写 v517_report.json、v700 写 v521_report.json | **输出文件名必须与本体版本号一致**：v697 链写 v697_*，禁止复制残留 |
| R13 | **seed 读结果字段**（历史高 WR 因 outcome 泄漏） | **outcome-blind 硬性**：seed 层禁止读 pnl/exit/mfe/mae/entry_price；落地字段断言 |
| R14 | **oracle 自证**（用 seed 代码重算） | **独立 oracle**：不 import seed 代码，从原始 K 线独立重算，identity 集合零差异 |
| R15 | **身份用 bar index**（缓存更新后失效） | **身份用日期**：symbol+交易日 绑定，不用缓存 index |

## 三、生产与前端纪律

| # | 坑 | 防再犯规则 |
|---|---|---|
| R16 | **文件存在性推断生产版本**（V88 靠 report 存在当选） | **生产状态唯一来源是 registry**：production_strategy 由 registry 决定，代码禁止按文件存在性推断 |
| R17 | **reload_metrics 优先读被否决版本**（V185 指标冒充 V88） | **指标只读 ACTIVE_VERSION 自己的报告**：禁止跨版本路由 metrics |
| R18 | **picks 污染**（历史回测行当当前选股，曾显示 884 只） | **历史 trades/picks 不得进入当前选股面**：当前候选只能来自 committed epoch 的 raw scanner；历史只做只读展示 |
| R19 | **stale 候选当当前**（旧日期 pick） | 超过 3 个交易日的候选必须 WATCH_ONLY |
| R20 | **前端锁死版本**（EMPTY_BOOK 强制 V517） | **前端版本由用户选择**，EMPTY_BOOK 只限制写入不限制查看 |
| R21 | **硬编码数字**（"387笔"会过期） | **前端数字动态读取**，禁止写死 |
| R22 | **变量名覆盖**（v700 main 里 r 被 candidate 返回值覆盖） | 函数作用域内避免用单字母变量名保存关键对象；代码评审检查 |

## 四、工程纪律

| # | 坑 | 防再犯规则 |
|---|---|---|
| R23 | 无 git，不可追溯 | **所有改动入 git**，版本化 |
| R24 | 硬编码 /root/.hermes | 路径集中配置（本地用 junction 缓解，重构为配置化） |
| R25 | 明文 API key | 密钥不入库 |
| R26 | 报告文件命名/路径硬编码 | 输出路径参数化 |

---

## 五、V88 重验执行检查单（本次任务强制）

- [ ] R1：入场价 ∈ 当日 [low,high]（violation=0）
- [ ] R2：TP/SL 锚点入场前可见
- [ ] R3：T+1 严格（same_day_exit_violation=0）
- [ ] R4：费用 0.20% + GAP_SL + SL 优先
- [ ] R5：预注册参数，一次回放
- [ ] R6/R7：经济门槛（年/月）
- [ ] R9：contract 文本与代码一致
- [ ] R10：artifact 路径三方对齐
- [ ] R13：seed outcome-blind
- [ ] R14：独立 oracle
- [ ] R15：身份用日期
- [ ] R16：不推断生产，只评估
