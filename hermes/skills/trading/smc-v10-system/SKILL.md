---
name: smc-v10-system
description: SMC V10 多维共振交易系统 — 摆动点+信号序列+多周期共振+每股票参数优化
category: trading
---

# 🗄️ SMC V10 — Multi-Resonance Trading System (ARCHIVED)

> **注意**: V10 已由 V11 完全取代。V11 继承了 V10 的共振框架和序列理念，
> 但增加了: 时间窗口约束、自适应参数(代替全局参数)、API限流器(防429)、
> 真实多周期数据、增强信号检测。
> 新开发请使用 `smc-v11-system`。
> 代码仍在磁盘上供参考: `~/.hermes/scripts/v10/`

## 核心创新 (历史贡献)

V10 在 V9 基础上新增四大维度:

| 维度 | 模块 | 功能 |
|------|------|------|
| 摆动点 | `swing_points.py` | 4层级(micro/meso/macro/mega) pivot检测, 结构树, 阶段识别 |
| 信号序列 | `signal_sequencer.py` | Gold/Silver/Bronze序列匹配, 顺序决定信号质量 |
| 共振引擎 | `resonance_engine.py` | TF共振+指标共振+摆动共振+序列共振, 四维综合评分 |
| 每股票优化 | `per_stock_opt.py` | 每股票独立参数爬山搜索, 150次迭代/股 |

## 架构

```
v10/
├── __init__.py           # version + constants + weights
├── swing_points.py       # 多周期摆动点检测
├── signal_sequencer.py   # 信号发生顺序分析
├── resonance_engine.py   # 多维度共振评分
├── per_stock_opt.py      # 每股票参数优化器
├── smc_backtest_v10.py   # 整合回测引擎
├── smc_webui_v10.py      # 交互式WebUI (port 8891)
├── verify_v10.py         # 端到端验证脚本
└── run_per_stock_opt.py  # 每股票优化启动器

v10_5/                    # V10.5 增强信号模块
└── signals.py            # 增强版FVG/Sweep/OB/CHOCH + LiquidityVoid + RejectionBlock
```

## 关键概念

### 摆动点 (Swing Points)
- 4层级: micro(3,3) / meso(8,5) / macro(20,8) / mega(50,15)
- 跨层验证: 高层级摆动点确认低层级
- 结构树: all_aligned + direction + strength
- 市场阶段: trending_up/down/ranging/volatile/breakout

### 信号序列 (Signal Sequence)
- Gold: Sweep → CHOCH → FVG Retest → OB (4/4 = WR 80%)
- Silver: 缺Sweep或缺OB (WR 70%)
- Bronze: Sweep + FVG only (WR 62%)
- 顺序乘以: Gold 1.5x, Silver 1.25x, Bronze 1.1x

### 共振评分 (Resonance)
- TF共振 (30%): 多时间框架方向对齐
- 指标共振 (30%): FVG+Sweep+OB+CHOCH同时出现
- 摆动共振 (25%): Micro+Meso+Macro对齐
- 序列共振 (15%): Gold/Silver/Bronze序列匹配
- 评级: S(全共振>0.75) / A(>0.60) / B(>0.45) / C(>0.30) / D(跳过)

### 阶段感知参数
- trending: SL×0.8 TP×1.2, more trades
- ranging: SL×1.3 TP×0.7, fewer trades, higher quality
- volatile: SL×1.5 TP×0.6, very strict
- breakout: SL×0.7 TP×1.5, momentum play

## 启动方式

```bash
# WebUI (port 8891 — separate from V9's 8881)
cd ~/.hermes/scripts && python3 v10/smc_webui_v10.py --port 8891

# 程序化使用
from v10.swing_points import find_swing_points, analyze_swings
from v10.signal_sequencer import analyze_signal_sequence, quick_sequence_check
from v10.resonance_engine import evaluate_full_resonance, get_resonance_grade
from v10.smc_backtest_v10 import evaluate_trades_v10, compare_v9_v10

# 端到端验证
python3 v10/verify_v10.py
```

## API端点 (WebUI :8891)

| 端点 | 说明 |
|------|------|
| GET /api/analyze?symbol=X | 完整分析: 摆动+序列+共振+回测 |
| GET /api/compare?symbol=X | V9 vs V10 对比 |
| GET /api/resonance_report?symbol=X | 文本共振报告 |
| GET /api/per_stock_params | 每股票优化参数 |

## 与V9的关系
- V9: 信号检测 + 基础回测 + WebUI(:8881)
- V10: 在V9信号基础上叠加共振/序列/摆动分析
- V10依赖V9的信号检测(hubble/signals)和基本回测框架
- V10使用独立端口8891避免冲突
