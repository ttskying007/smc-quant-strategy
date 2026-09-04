# SMC V5 系统 — 市场状态驱动

## 架构

市场状态 → 策略管理 → SignalScore → 仓位分配 → 风险控制

## SMC信号正解 (2026-05-14 验证)

### 信号角色
| 信号类型 | 角色 | 说明 |
|----------|------|------|
| LIQ (Sweep_SSL, EQL) | **唯一起点** | 事件触发，一次性发生，改变订单状态 |
| STRUCT (BOS, CHOCH, MSS) | **仅确认** | displacement的结果，不能反向触发组合 |
| ZONE (OB_Bull, FVG_Bull) | **入场目标** | displacement的产物，等待价格回访 |

### 关键规则
1. **STRUCT永远不是起点** — 它是displacement的结果，用STRUCT作起点反转了时间因果
2. **OB_Bull是完整事件产物** — 自带机构逻辑，独立使用，不参与序列匹配
3. **OB与LIQ同bar** — 两者同时出现在摆动低点，OB天然不能序列化
4. **FVG_Bull需要LIQ前序** — 孤立FVG WR=64.5%，有LIQ前序 WR=74.5% (+10pp)
5. **FVG回补率是市场状态指标** — >60%=MeanReversion, <40%=Expansion

### 正确流程
```
LIQ(事件) → 可选STRUCT(确认) → ZONE生成 → 等待回访 → T+1入场
```

## V5 策略分层

### L1: OB_Bull (永开)
- 全量回测: 6090笔 WR=95.3% avgPnL=+4.09%
- 不依赖市场状态，任何市场都可用
- SL: V19 find_sls (结构止损)
- TP: V19 find_tps (cap 5%)
- RR filter: tp_dist/sl_dist >= 1.0

### L2: LIQ→FVG (仅MeanReversion)
- 全量回测: 292笔 WR=59.2% avgPnL=+0.96%
- 仅在FVG回补率>60%时启用
- 近30天A股: 4% WR（五一前后特殊行情）
- gap ≤ 10bar，取最小gap

## 市场状态检测

### FVG回补率
```
fill_rate = 最近20个FVG_Bull中被回补的比例
回补定义: FVG bar之后，价格low ≤ FVG.upper
```

### 状态分类
| 状态 | 条件 | L1策略 | L2策略 |
|------|------|--------|--------|
| Expansion | fill_rate < 40% | 开 | 关 |
| Transition | 40% ≤ fill_rate ≤ 60% | 开 | 关 |
| Mean Reversion | fill_rate > 60% | 开 | 开 |

## SignalScore 计算

```
Score = 0.0
+ HTF同方向(bullish)      +0.2
+ Fresh OB                +0.2 (OB_Bull专属)
+ LIQ后≤5bar             +0.2 (LIQ→FVG专属)
+ 市场状态匹配            +0.4 (OB全分 / FVG在MR全分 else 0 in Transition)
= min(1.0, score)
```

## 仓位分配

```
PositionSize = BaseRisk × StrategyWeight × SignalScore × RiskScaler
  BaseRisk = 1.0
  L1_Weight = 0.60
  L2_Weight = 0.20
```

## 风险控制

```
RiskScaler:
  WR > 70%           → ×1.2
  50% ≤ WR ≤ 70%     → ×1.0
  WR < 50%           → ×0.5
  连续亏损 ≥ 3        → ×0.5 (覆盖上述)
```

## TP/SL 方法

- 使用 V19 `find_tps` / `find_sls` (非固定cap)
- TP cap: 入场价 × 1.05
- RR filter: tp_dist / sl_dist >= 1.0
- 监控: 逐bar遍历(非仅查最后bar)

## 关键数据

- L1 OB_Bull: 6090笔 WR=95.3% PnL=+4.09%
- L2 LIQ→FVG: 292笔 WR=59.2% PnL=+0.96%
- 组合: 6382笔 WR=93.6% PnL=+3.94%
- 市场状态: A股无Expansion, 73% Transition, 27% MR
- 文件: backtest_v5_full.json, LD_picks_v5.json
