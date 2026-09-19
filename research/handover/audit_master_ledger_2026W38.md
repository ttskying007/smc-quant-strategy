# SMC 审计全景总账 (R1-R42 合并索引)

**As of**: 2026-09-20 周日 06:44 · **基线**: n=1527 avg=+3.77% PF=3.63 (frozen 2026-09-16)
**审计套件**: 23 测试文件 / 228 断言 全绿 · **Git**: 9ef4b07

## 一、核心三层审计 (B 级, 此轮全部 CLEAN)

| 维度 | 工具/脚本 | 结论 | 状态 |
|---|---|---|---|
| 前视偏差 | R40 (entry vs buy) | T+1 验证: entry=公告+1真空, buy=entry, neg-gap=0 | ✅ CLEAN |
| 退出完整性 | R41 (sell/hold/pnl/reason) | 1527 全过; naive `pnl==单点算术` 是错断言(分批TP所致) | ✅ CLEAN |
| 成本模型 | R42 (core.cost_model) | 0.2% fee双边 + 0.1% slip单边 = 0.4%/笔; R41 3笔负TP腿被完整解释; 已单源化 | ✅ CLEAN |

## 二、结构分解结论

### rank 语义 (canonical 1527 腿, R31)
- 全体单调 ✓ (rank=5 是最优 +4.93%
- 逐年溢价仅 2/4 年份通过 — 2025 年 rank≤3 avg=+2.34 反超 rank≥4 的 +2.14
- 结论: 生产 gate=rank>=3 无更改必要 (gate 不是筛选器而是噪声滤波器)

### 板块分层 (R38)
| 板块 | n | avg | WR | PF |
|---|---:|---:|---:|---:|
| 创业板 (20%) | 470 | +4.84 | 71.5 | 4.94 |
| 深市主板 (10%) | 390 | +3.07 | 62.6 | 3.29 |
| 沪市主板 (10%) | 373 | +2.89 | 59.5 | 2.83 |
| 科创板 (20%) | 294 | +4.09 | 66.3 | 3.42 |
逐年一致: 20%板溢价 +1.31/+3.30/+0.45 — **SL 制度性自动宽松(20%) 是溢价部分成因**, R39 证实同板块内窄SL仍最弱

### risk_pct 分档 (R26 修正后, n=1527)
窄SL(0-4%) 档WR=40%, 但 E3(剔除<4%) frozen OOS **FAIL** — 解释力被市场时间结构吸收; risk_pct 门控家族已全部关闭。

## 三、退出/亏损原因解剖

### 退出通道 (R34)
| reason | n | sum_pnl | avg | WR | 持有时长 |
|---|---:|---:|---:|---:|---:|
| TIME_STOP | 793 | +5010.5 (+87.1%) | +6.32 | 79.6 | 12.0 d |
| TP2_RUNNER | 241 | +2135.7 (+37.1%) | +8.86 | 98.8 | 5.5 d |
| SL_HIT | 232 | -1179.5 (-20.5%) | -5.08 | 0 | 4.0 d |
| SL_GAP | 132 | -328.7 (-5.7%) | -2.49 | 15.2 | 3.0 d |
| BE | 129 | +113.7 (+2.0%) | +0.88 | 83.7 | 5.1 d |

### MFE 回吐 (R34b)
- TIME_STOP: MFE 均 +13.05%, 实收 6.32 → **回吐 6.7pp (n=456 回吐≥5pp)**
- TP 布局目前 TP1→TP2 两级; **TIME_STOP 腿部是最大利润泄漏源** — 登记待 PAPER30+解禁后的 trailing-TP 候选

## 四、生产 pipeline (周六状态)
- announce 拉取: 15.5s/天 (修前超时 >600s; R35 时间线闭合: 不是新 bug 是修复推进)
- daily_combo_run 自愈: announce DB 落后时自动调用 announce_gap_refill (timeout=1800, 已验证)
- sanity_check: 7/8 PASS (唯一 FAIL = funnel 历史仅 5 天; 周一交易日后第 6 天)
- 当前持仓: 仅 1 笔 FILLED (002801 hold=17d, pnl=-2.94%, SL余量 5.7%) — 预计下周 inner stop-out / TIME_STOP, **第一次落下 R13归因字段的试卷即将评分**

## 五、未决实验账本 (全部登记在案)
| 状态 | 条目 | 备注 |
|---|---|---|
| REJECTED | E3 min-risk>=4% frozen OOS | Δavg=+0.149pp < 0.4 阈值 |
| REJECTED | delay-1bar 延迟入场 | v2_sl_controlled 家族 |
| REJECTED | D5 三维自适应 | flip 57% > 50% |
| REJECTED | 弱市加权 k=2 | WFO 零样本 |
| FROZEN | TP/SL 组合实验 | 需 PAPER 30 closed (现 10) |
| FROZEN | INT70 单日 yoy 全景 impact | Δ样本, 缺 60min 数据 |

## 六、明日 (周一) 检查单
1. daily run 全绿 (announce rc=0)
2. 002801 是否被 time-stop / SL
3. funnel_monitor 添第 6 天
4. 如出现 PAPER 新单: 确认 loss_attribution 在 CLOSED 后正确填充
