---
name: smc-engine-v5-high-winrate
version: 1.0
category: trading
description: SMC V5.5 高胜率共振信号引擎 (WR>88%, PF>9)。波动率自适应，三层参数独立优化。
trigger: SMC 信号分析, 股票扫描, 参数优化
---

# SMC Engine V5 — 高胜率共振信号引擎

## 架构

```
V5.5 Engine Architecture:
  Input (K线) → Volatility Classifier → 3-Layer Params → 
  FVG Detector + Sweep Detector + Trend Confirmation → 
  Signal Combiner → Backtest → Score
```

## 关键参数 (优化后)

### 高波动 (ATR≥3.0%)
- fvg_min_width: 0.32
- sweep_lookback: 14
- sweep_wick_ratio: 1.84
- sl_pct: 3.06
- tp_pct: 6.89

### 中波动 (1.5%≤ATR<3.0%)
- fvg_min_width: 0.20
- sweep_lookback: 14
- sweep_wick_ratio: 2.86
- sl_pct: 3.18
- tp_pct: 3.0

### 低波动 (ATR<1.5%)
- fvg_min_width: 0.16
- sweep_lookback: 14
- sweep_wick_ratio: 1.37
- sl_pct: 3.47
- tp_pct: 4.29

### 全局参数
- confirm_range: 2
- min_sources: 2
- max_trades: 4
- min_score: 2.32
- trail_activation: 0.35

## 评分函数

```
Score = WR*0.3 + min(40, PF*6)*0.3 + min(30, Ret)*0.2 + min(10, N)*0.1 + Bonus
Bonus: PF≥5→+5, PF≥8→+3, WR≥85%→+3, WR≥90%→+2
```

## 信号优先级
1. FVG + Sweep 共振 (最高分)
2. FVG + Trend Confirmation
3. FVG only (最低分)

## 文件路径
- 引擎: ~/.hermes/scripts/smc_v55.py
- 优化器: ~/.hermes/scripts/smc_opt_v55.py
- 结果: ~/.hermes/smc_opt_v55/final.json
- Status API: ~/.hermes/scripts/smc_api_lite.py (端口8879)
- WebUI: ~/.hermes/scripts/smc_webui_v54.py (端口8880)
- 代理监控: ~/.hermes/scripts/proxy_guardian.sh (crontab每分钟)

## 使用方式

```bash
# 快速测试
cd ~/.hermes/scripts && python3 smc_v55.py

# 优化运行 (注意: 会重置结果)
cd ~/.hermes/scripts && python3 smc_opt_v55.py -n 150

# 状态API (后台运行中)
curl http://127.0.0.1:8879/api/progress

# WebUI
curl http://127.0.0.1:8880/
```

## 优化结果
- WR: 88.9%
- PF: 9.21
- Score: 103.2
- N: 9笔 (高置信度)
- Ret: 25.3%

## Pitfalls
1. 优化器搜索到的极端参数 (fvg_min_width<0.1, sl_pct<1.5%) 是过拟合, 丢弃
2. 低波动股票 (<1.5% ATR) 信号质量差, 建议只交易中/高波动
3. 优化器每轮跑8只股票, 最终结果需要用全部10只验证
4. 不要在优化运行时重启status API (端口冲突)