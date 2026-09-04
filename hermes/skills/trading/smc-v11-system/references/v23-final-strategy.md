# SMC V23 最终策略参考

## 策略配置

```yaml
方向: Bull-only
信号: Scout-only (FVG/OB单信号)
SL策略: 
  摆动点封顶0.5% (距入场≤20K线)
  无摆动: 跳过(不交易)
TP策略:
  摆动点自然阻力 | 固定3.0%保底

阶段自适应参数:
  breakout:      {sl: 0.3, tp: 3.0, min_res: 0.65}
  volatile:      {sl: 0.5, tp: 5.0, min_res: 0.70}
  ranging:       {sl: 0.7, tp: 3.0, min_res: 0.75}
  trending_up:   {sl: 0.3, tp: 5.0, min_res: 0.60}
  trending_down: {sl: 0.5, tp: 5.0, min_res: 0.70}

周期SL乘数:
  ALL-UP: 1.0     # 三周期全↑ = 正常SL
  NEUTRAL: 1.2    # 无方向 = 加宽20%SL

过滤:
  OB: 仅当有摆动SL时接受
  周线: 趋势向下时跳过
  信号密度: ≥8个信号
  成交量: ≥0.8×30日均量
  FVG: 收阳(c>o)且gap≥0.3%
  冷却: 出清后跳过15根K线
```

## 预期性能

| 场景 | WR | RR | PF |
|------|-----|-----|-----|
| 基准(200只) | 87.5% | 11.9x | 102 |
| 突破期(breakout) | 91% | 13.9x | — |
| 震荡期(ranging) | 82% | 9.8x | — |

## 运行命令

```bash
# 回测(200只快速测试)
cd ~/.hermes/scripts && python3 v11/rolling_backtest_v23.py

# 全量扫描(4800只, ~15min)
cd ~/.hermes/scripts && python3 v11/scan_full_market_v23_v2.py

# 股票质量筛选
cd ~/.hermes/scripts && python3 v11/stock_screener_v23.py

# 实时信号监控
cd ~/.hermes/scripts && python3 v11/live_monitor_v21.py --quick

# Dashboard
curl http://localhost:8900
```

## 关键文件

```
~/.hermes/scripts/v11/
  rolling_backtest_v23.py     # V23回测引擎
  scan_full_market_v23_v2.py  # V23全量扫描(带checkpoint)
  stock_screener_v23.py       # 股票质量评分系统
  live_monitor_v21.py         # 实时信号监控
  v16_dashboard.py            # Dashboard (port 8900)

~/.hermes/smc_opt_v23/
  backtest_v23.json           # 200只测试结果
  v23_full_merged.json        # 全量扫描结果(待生成)

~/.hermes/smc_signals/
  stock_quality_ratings.json  # 4792只股票质量评分
  latest_signals.json         # 最新实时信号
```
