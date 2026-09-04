# SMC 序列检测正解 — V5 市场状态驱动

## 信号分类与角色 (2026-05-14 校正)

| 信号类型 | SMC角色 | 序列检测用途 | 说明 |
|----------|---------|-------------|------|
| **LIQ** (Sweep_SSL, EQL) | 🟢 **事件起点** | 序列唯一起点 | 一次性发生，改变订单状态，机构动机核心 |
| **STRUCT** (CHOCH/BOS/MSS) | 🟡 **确认过滤** | 仅作确认，不起点 | displacement的结果，不能反向触发组合 |
| **ZONE** (OB_Bull, FVG_Bull, Pinbar_Bull) | 🔵 **入场位置** | 由displacement生成 | 本身不触发事件，等待价格回访 |
| **OB_Bull** | 🥇 完整事件产物 | **独立使用** | 自带机构逻辑，与LIQ同bar时不能序列化 |
| **FVG_Bull** | 🥈 需前序验证 | **需LIQ前序** | 孤立FVG WR=64.5%，有LIQ前序WR=59.2%(V5全量) |

## V5 市场状态驱动架构

```
RULE 1: Always detect Market State before trading.
RULE 2: OB strategy always enabled.
RULE 3: LIQ→FVG enabled only in Mean Reversion market.
RULE 4: Position size determined by signal score.
RULE 5: Risk dynamically scaled by recent performance.
RULE 6: System trades portfolio, not individual signals.
```

### 市场状态检测 (FVG回补率)

```
Expansion (<40% fill):   LIQ→FVG关闭，仅OB
Transition (40-60%):     全部减仓50%
Mean Reversion (>60%):   OB + LIQ→FVG全开
```

A股市场特征: 全量历史中0% Expansion, 73% Transition, 27% Mean Reversion。
FVG在A股中几乎总是被回补(中位数>60%)。

### SignalScore (仓位分配)

```
HTF同方向      +0.2
Fresh OB       +0.2 (OB专属)
LIQ后≤5bar     +0.2 (LIQ→FVG专属)
市场状态匹配   +0.4

Position Size = BaseRisk × StrategyWeight × SignalScore × RiskScaler
```

### 风险控制

```
近期20笔 WR>70% → RiskScaler ×1.2
          50-70% → 正常
          <50%   → ×0.5
连续亏损≥3 → 全部减半
```

## 正确的时间序列

```
事件 → 确认 → 位置 → 入场
 LIQ  → STRUCT → ZONE → T+1
(起点)  (过滤)   (目标)  (执行)
```

**错误模式** (已修正):
- ❌ STRUCT 作为起点 → 时间因果被反转
- ❌ OB 参与序列匹配 → 与LIQ同bar，永远匹配不到
- ❌ 固定百分比SL/TP → 不如结构止损
- ❌ 无市场状态判断 → 在不适合的市场用错策略

**正确实现** (V5):
- ✅ LIQ 唯一起点
- ✅ OB_Bull 独立策略 (L1, 永开)
- ✅ LIQ → FVG_Bull 组合 (L2, 仅MeanReversion)
- ✅ STRUCT 仅用于确认过滤
- ✅ V19 find_tps/find_sls + RR≥1
- ✅ 市场状态驱动策略开关

## V5 全量回测 (3,369只股票, 6,382笔交易)

| Tier | 策略 | 笔数 | WR | avgPnL | 适用市场 |
|------|------|------|-----|--------|---------|
| L1 | OB_Bull | 6,090 | 95.3% | +4.09% | 全市场 |
| L2 | LIQ→FVG | 292 | 59.2% | +0.96% | 仅MR |
| 组合 | V5 | 6,382 | **93.6%** | **+3.94%** | — |

V4→V5提升: 交易量+27%, WR+16.3pp, PnL+48%

### 市场状态分层

| 状态 | L1笔数 | L1 WR | L2笔数 | L2 WR |
|------|--------|-------|--------|-------|
| Expansion | 0 | — | 0 | — |
| Transition | 5,316 | 95.3% | 0 | — |
| Mean Reversion | 774 | 95.1% | 292 | 59.2% |

## 关键教训

1. **OB_Bull 是主力引擎** — 95.3% WR, 95%交易量
2. **LIQ→FVG仅MR时正收益** — 59.2% WR (全量), 避免Transition误用
3. **V19结构SL/TP优于固定cap** — TP=结构目标(swing high), SL=结构支撑(zone_low/swing_low)
4. **RR≥1过滤器必要** — 排除风险回报比不利的组合
5. **市场状态是策略选择的基础** — 先看市场，再选策略
6. **近30天LIQ→FVG为异常值(4%WR)** — 五一+季报特殊行情，不代表策略失效
7. **监控系统只查最后一根bar的bug** — 已修复为逐bar遍历 (见 references/monitor-bar-walk-fix.md)

## 相关文件

- 扫描器: `/root/.hermes/scripts/v11/scan_LD_v6.py`
- 回测: `/root/.hermes/scripts/v11/ob_ctx_backtest_v6.py`
- 监控: `/root/.hermes/scripts/v11/monitor_check.py`
- 前端: `http://localhost:8890/monitor`
- V6信号库: `/root/.hermes/smc_opt_v21/LD_picks_v6.json`
- V6回测: `/root/.hermes/smc_opt_v21/ob_ctx_backtest_v6.json`

## V6 更新 (2026-05-14)

### ⚡ 回调入场理论 (V6.2 重大发现)

OB/FVG/Pinbar 对价格回调到zone的反应截然不同，根源于各自的市场微观结构：

| ZONE | 回调效果 | WR变化 | 原理 |
|------|---------|--------|------|
| **OB_Bull** | ✅ 改善 | +3.2pp | OB=机构订单块支撑。价格回调=测试支撑→牛旗确认 |
| **Pinbar_Bull** | ✅ 改善 | +5.5pp | Pinbar低点=买入支撑。回调=二次确认 |
| **FVG_Bull** | ❌ 恶化 | -37pp | FVG=公允价值缺口。价格回补=缺口填充→看跌信号 |

**入场规则**:
- OB/Pinbar: 等价格回调到zone_low → 买入 (等待≤7bar, SL=zone_low×0.96)
- FVG: 下一根开盘立即买入 (不要等回调！缺口填充=利空)

**最优参数** (40组网格搜索):
MW=7, SL=0.96, zone=lower → WR=97.9% avg+4.61%

### Pinbar_Bull POI
新增Pinbar_Bull作为ZONE类型。检测: 长下影(影>实体×2, 影>幅度50%) + 小上影(<20%) + 收阳。
L2组合新增: Sweep_SSL→Pinbar_Bull(103), EQL→Pinbar_Bull(32), BOS_Bull→Pinbar_Bull(24)等。

### OB上下文矩阵
CTX类型 × POI类型 全矩阵。OB_Bull为L1独立信号(12438个)，15%有前序上下文标签。
L2非OB组合(448个)包含10种CTX→POI类型，在MR市场中启用。
OB组合不产生独立L2交易(与L1 entry冲突)，作为上下文标签增强SignalScore。

### 架构锁定
前后端固定: scan_LD_vX.py + monitor_check.py (后端) + smc_unified.py + monitor_page.py (前端), 端口8890。
只在此架构上调整，不重建。数据文件改名时前后端必须同步更新路径。

## V409–V410 自动组合状态机（2026-07-13）

用户纠正研究方向后，恢复以**信号自动化组合**为主，而不是继续寻找外部数据源。第一阶段只物化时序组合和生命周期，绝不使用结果字段：

| 组合 | 因果链 |
|---|---|
| R1 | SSL Sweep → Bull CHOCH（1–20 bar）→ CHOCH锚定、向后定位的Demand OB → 触碰→收复→持有确认 |
| R2 | SSL Sweep → Bull CHOCH（1–20 bar）→ CHOCH后0–3 bar生成Bull FVG → 触碰→收复→持有确认 |
| C1 | Bull BOS → BOS锚定、向后定位的Demand OB → 触碰→收复→持有确认 |

实现：`/root/.hermes/scripts/v25/v409_causal_signal_combination_state_machine.py`。全市场4655只日线，所有候选均 `tradable=false`、无 entry/exit/PnL。C1必须按 `(symbol, poi_idx)` 去重；连续BOS不能让同一个OB重复成为新setup。

第二阶段使用**唯一冻结**的评估合同，而不是调参：`TAKEOVER_CONFIRMED → 下一交易日开盘`，仅报告5/10/20日close mark、MAE、收盘跌破zone比例；不搜索TP、SL、阈值。实现：`v410_frozen_combo_t1_mark_replay.py`。这能将“组合语义正确”与“组合在所有市场状态都具备经济性”严格分离。

V410首轮显示R1/R2/C1均不能直接晋级；尤其2023三种组合均显著负、zone invalidation高。正确的下一步不是按收益剔除年份或加标量阈值，而是先做 POI 生命周期完整性审计。

### V415–V417：先修语义，再冻结重评（2026-07-13）

V415 发现 V409 的生命周期标签不能直接用于结果判断：

- 回溯锚定的 OB 在结构确认前已经 wick touch（`PRE_EVENT_MITIGATED`）或 close 跌破区间（`PRE_EVENT_INVALIDATED`），不得被称为确认后的首次回踩；
- FVG 在第三根 K 线收盘后才存在。`event_idx < poi_idx` 不是信号无效，而是生命周期必须从 `max(event_idx, poi_idx)+1` 才可开始；不可把 FVG 创建 K 线当回踩。

严格生成器合同：`全部前置条件已知 → 新鲜 post-prerequisite touch → reclaim → hold`。只有已被提前触碰/失效的 OB 被排除；FVG 保留但延后到创建后启动生命周期。

V416 重建后，严格 `TAKEOVER_CONFIRMED` 数量为：R1=173、R2=655、C1=20,224。V417 使用与 V410 **完全相同**、预先冻结的合同（`TAKEOVER_CONFIRMED → 下一交易日开盘 → 5/10/20 日 mark`，无 TP/SL/阈值/退出搜索）重评 21,042 笔，T+1=0，且输入不含结果字段。

结果：所有 3 个组合的 5D/10D 年度稳定性门禁均为 **0/6 通过**。R1 5D/10D 均负（-0.5516%/-0.2563%）；R2 更弱（-0.7734%/-1.0315%）；C1 虽总体 5D/10D 为 +0.1452%/+0.4850%，但正收益率仅 44.45%/45.36%，且 2023–2024 负、10D zone invalidation=34.79%。

**结论：** V411 对旧标签的结论不可单独视为语义证明；但 V417 已在修复后的严格定义下复核，三条日线组合仍然不能生产晋级。禁止再对 R1/R2/C1 作阈值、窗口、TP/SL 或按年份过滤的再挖掘。下一步若继续纯 SMC，必须提出新的、事前定义的因果机制，而不是修改这三条已否决组合。
