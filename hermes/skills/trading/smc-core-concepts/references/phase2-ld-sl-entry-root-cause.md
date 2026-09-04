# Phase2 L→D SL/入场根因审计模式

适用场景：SMC Phase2 / L→D 系统出现“胜率低、SL 多、是否信号/入场/止盈止损问题”的追问时。不要只调 RR 或扩大 SL，必须把问题拆成 **信号质量、入场成交、SL 锚点、TP 目标** 四层逐项审计。

## 关键结论模式

一次全市场严格 L→D 审计显示：低胜率/高 SL 往往不是单一 SL 公式问题，而是：

1. **入场价格偏贵**：用 reclaim bar close 入场，常常已经离 demand zone 太远；SL 仍锚在 zone_low 下方，实际 risk 增大，正常回踩也容易打 SL。
2. **信号分层不足**：FVG_Demand 通常明显优于 OB_Demand；OB 若只是“位移前最后一根阴线”，会拖累整体。
3. **TP/RR 是放大器，不是根因**：RR 越高 SL 率越高，但如果入场仍偏贵，调 RR 只是被动折中。
4. **SL 与 entry 锚点不匹配**：只放宽 SL 会牺牲风险；应先让 entry 回到 zone 内，再重设结构 SL。

## 必做审计表

### 1. 信号质量审计

按 zone/signature 分桶：

| 分桶 | 要看什么 |
|---|---|
| FVG_Demand | WR、SL率、avg_pnl、样本数 |
| OB_Demand | 是否为负期望；若负期望，降级为观察标签 |
| OB_FVG_Demand | 样本是否足够；不要因小样本 100% WR 升级 |
| signal sequence | SSL→Displacement→POI→Entry 是否严格时间顺序 |

判断规则：

```text
若 FVG_Demand 正期望而 OB_Demand 负期望：
  生产只保留 FVG_Demand；OB_Demand 降级 WATCH/辅助上下文。
```

### 2. 入场模型审计

不能只测 reclaim close。必须对比真实可成交 entry：

| Entry | 语义 | 必须验证 |
|---|---|---|
| reclaim_close | 当前确认K收盘入场 | 是否追高 |
| next_open | T+1 下一开盘入场 | 跳空影响 |
| zone_high_limit | 触达 zone 上沿成交 | low<=limit<=high |
| zone_mid_limit | 触达 zone 中轴成交 | low<=limit<=high |

**严禁假设限价成交**：必须用 K 线验证 `low <= limit_price <= high`。若未触达，不算交易。

### 3. SL 设计审计

至少比较：

| SL | 说明 |
|---|---|
| current_zone_buffer | `min(zone_low*0.985, zone_low-ATR*0.25)` |
| tighter_zone_buffer | 较小 buffer，测试噪音敏感性 |
| wider_zone_buffer | 较大 buffer，测试是否只是止损过紧 |
| structure_low | sweep_low / recent swing low + ATR buffer |

判断规则：

```text
若 zone_mid/zone_high 入场大幅降低 SL，而 reclaim_close 仍高 SL：
  根因优先归为入场价格偏贵，不是 SL 单独问题。
```

### 4. TP/RR 审计

不要只固定 RR。至少对比：

| TP | 说明 |
|---|---|
| RR0.8 / RR1.0 / RR1.2 / RR1.5 | 固定对照 |
| nearest_BSL | 最近 buy-side liquidity / 前摆动高点 |
| min(BSL, RR1.2) | 防目标过远 |
| partial_exit | TP1 部分止盈 + trailing |

判断规则：

```text
RR 调整只说明盈亏分布，不足以证明策略修复。
若 entry 未修，TP 优化通常只是掩盖入场问题。
```

## 推荐 V68 候选路线

当严格 L→D 已证明 FVG 有正边际但 SL 多时，下一候选版本应是：

```text
FVG_Demand only
+ validated zone limit entry
+ structure SL
+ BSL/RR hybrid TP
+ T+1 hard enforcement
```

执行顺序：

1. 从 L→D 生成器拆出唯一 setup，不要一笔重复生成多个 RR 当成独立样本。
2. 生产只保留 FVG_Demand；OB_Demand 降级观察。
3. 对比 reclaim_close / zone_high_limit / zone_mid_limit，且验证真实成交。
4. 对比 current SL / sweep_low SL / swing_low SL。
5. 对比 RR0.8 / RR1.0 / BSL target / hybrid TP。
6. 全市场跑完后再决定是否升级；几十笔或 300 只只能作探索。
7. 输出表必须包含：zone_type、entry_model、sl_model、tp_model、WR、SL率、avg_pnl、样本数、risk_bin、retrace_bin、hold_bars。

## 报告方式

用户追问“为什么这么多 SL”时，必须明确归因比例，不要只给笼统解释：

```text
主要问题：入场价格/成交模型
次要问题：信号分层（FVG vs OB）
第三问题：TP/RR 与 SL 锚点匹配
不是：单纯 SL 太紧 / 单纯 RR 太高
```

并给出下一步可执行版本，而不是停在分析：

```text
下一步：V68 全市场候选 = FVG_Demand only + zone limit entry + structure SL + BSL/RR hybrid TP。
```
