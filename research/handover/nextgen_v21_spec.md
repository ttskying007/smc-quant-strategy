# next-gen 重跑规格书 (gen_v21) — 冻结期只设计, 不执行

状态: 规格定稿 v1 (2026-09-20) · **执行需用户批准**(全市场重跑约 15-30 分钟, 产出新研究基线)
继承: gen_v20f2_wilder_h12.py 修改复制(house style: 改进不重写), 输出 `combo_v21_trades.csv`
不触碰: canonical `combo_v20f_trades.csv` 及其全部 139 个消费者

## 设计动机(三条登记线的交集)
1. R33: canonical 缺 sub_signals/rank_components → 组合级信号分解不可行
2. E4'': 结构特征入 rank 需在新数据上验证(1527 腿已切割 8 次, 禁再挖)
3. 用户 SMC 序列: 趋势→BOS/CHoCH→POI→距离→SL/TP 每环需要**显式落列**才能审计

## v21 新增列(全部 signal 日因果口径, 与回测 T+1 无前视)

### A. 结构上下文 (来自 r53b 检测器, PIVOT=3, 确认式)
| 列 | 语义 | 因果规则 |
|---|---|---|
| `board` | SH_MAIN/SZ_MAIN/CYB/KCB/BSE | 静态 |
| `trend_state` | up/down/none (信号日收盘时点) | 只计 event_bar<=i 的已确认事件 |
| `last_event_kind` | BOS↑/BOS↓/CHoCH↑/CHoCH↓ | 同上 |
| `last_event_date` | 事件确认bar日期 | 同上 |
| `last_event_level` | 被破摆动点价位 | 同上 |
| `event_gap_bars` | 信号日-事件bar | 同上 |
| `broken_low_level` | 最近跌破的摆动低(R55 口径) | 同上 |
| `sl_below_structure` | sl1 < broken_low_level (bool) | 对账列 |
| `supply_layers` | entry→tp1×1.05 内未补 bearish FVG 层数 | FVG 形成bar<=i |
| `nearest_supply_dist` | 最近头顶供给层距入场% | 同上 |
| `zone_90d` | premium/equilibrium/discount | 90日窗口至 i |

### B. 决策透明化 (R33)
| 列 | 语义 |
|---|---|
| `stage_span` / `adx_span` | 从 paper_sim 移植(已在生产账本, canonical 缺) |
| `sub_signals` | JSON: 阶段确认日/ADX确认日/披露日/入场日(+v21 结构事件链) |
| `rank_components` | JSON: rank_score 各分量(2/1/1/1/1/1/1)逐项值 — 使 R31 倒U可逐分量归因 |

### C. 保留
全部 v20f 列不动(含 mfe/mae/mfe_r/mae_r/rr_exit), 保证消费者兼容。

## 验收标准(执行后必查)
1. 行数一致性: 与 v20f 同窗口腿数偏差 0(同一事件集、同一过滤链)
2. 无前视: 抽 20 腿人工核对结构事件日期<=信号日; `no_lookahead` 3 用例续绿
3. 基线复现: net_pnl_pct 与 v20f 逐腿相等(引擎未动, 只加列)
4. 新列覆盖率: trend_state/supply_layers 非空率 >95%

## 执行后的首个实验(预注册占位, 到时另立文档)
- E4'' 影子: rank_score + 结构分量(如 zone_90d==discount 计 1) vs 原 rank 的 IS 对比
  → 通过后才谈 frozen OOS
- 用户序列可视化: 每腿输出"完整 SMC 叙事行"(趋势/事件/POI/距离/SL/TP 一行串)供前端渲染

## 明确不做
- 不改任何 gate/stage/ADX/rank 阈值(与 v20f 严格同引擎)
- 不在 v20f 冻结基线上验证任何新列的"预测力"(那属于过拟合矿, 等新数据)
