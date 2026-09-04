---
name: smc-v9-system
description: SMC V9 模块化交易系统 — 信号标识+全市场扫描+回测日志+交互式ECharts WebUI
category: trading
---

# SMC V9 — 模块化交易系统

## 架构总览

```
~/.hermes/scripts/v9/
├── __init__.py           # 模块路由 + 版本信息
├── smc_config.py         # YAML配置 + 环境变量覆盖 + 参数空间 + 股票列表
├── smc_hubble.py         # Hubble API客户端 (重试+缓存+错误处理)
├── smc_signals.py        # 6种SMC信号检测算法
├── smc_annotations.py    # [NEW] 信号标识引擎 — 趋势线/区域/结构/买卖点
├── smc_backtest.py       # [V2] 交易仿真 + 完整买卖日志 + 入场/出场原因
├── smc_watchlist.py      # [NEW] 全市场扫描(5400+A股/ETF/板块/指数) + 实时监测
├── smc_webui.py          # [V2] FastAPI + ECharts 交互式仪表盘(6标签页)
└── smc_optimizer.py      # [计划中] 多阶段优化器

~/.hermes/smc_opt_v9/    # V9统一输出目录 (含history.json, best_params.json, live_status.json)
```

## 模块说明

### smc_annotations — 信号标识引擎 [NEW]

生成ECharts可直接消费的K线标注数据结构。核心函数:

```python
generate_chart_data(ohlcv, signals, trades, params) → dict
```

输出数据结构:
| 层级 | 字段 | 可视化方式 | 说明 |
|------|------|-----------|------|
| 趋势线 | `trend_lines.BSL` | MarkLine线段(实线) | 买方流动性(多头支撑) |
| 趋势线 | `trend_lines.SSL` | MarkLine线段(实线) | 卖方流动性(空头压力) |
| 趋势线 | `trend_lines.EQL` | MarkLine线段(虚线) | 均衡线(近30根中枢) |
| 信号区域 | `zones.FVG` | MarkArea矩形(绿透明) | Fair Value Gap |
| 信号区域 | `zones.OB` | MarkArea矩形(蓝透明) | Order Block |
| 信号区域 | `zones.BPR` | MarkArea矩形(黄透明) | 平衡价格区间 |
| 信号区域 | `zones.MSB` | MarkArea矩形(灰透明) | 市场结构 |
| 信号区域 | `zones.Sweep` | MarkArea矩形(金透明) | 流动性扫荡 |
| 兴趣区 | `poi` | MarkArea矩形(紫边框) | Point of Interest |
| 供需区 | `supply_demand` | MarkArea矩形(绿/红) | Supply/Demand Zone |
| 结构点 | `structures` | MarkPoint箭头/图钉 | BOS/CHoCH(↑绿↓红) |
| 买卖点 | `entries` | MarkPoint图钉 | 入场方向+信号类型标注 |

颜色约定:
- FVG = `rgba(63,185,80,0.15)` — 绿色(价格未填充)
- OB = `rgba(143,188,255,0.12)` — 蓝色(机构订单块)
- POI = `rgba(188,140,255,0.25)` — 紫色边框
- Supply = `rgba(248,81,73,0.2)` — 红色(供应区)
- Demand = `rgba(63,185,80,0.2)` — 绿色(需求区)

### smc_config — 统一配置层

配置文件: `~/.hermes/config/v9_config.yaml`
- YAML格式，首次运行自动创建默认配置
- 支持环境变量覆盖 (SMC_V9_*)
- 参数空间定义：14维 (fvg_min_width, sweep_lookback, ob_strength_min, score_min等)
- 股票列表：沪深300 + 科创板 + 创业板 (40只默认)
- Hubble API配置：base_url, api_key

### smc_hubble — Hubble API客户端

- 请求重试 (3次, 指数退避)
- 多级缓存 (精确匹配 → glob回退 → 网络获取)
- V2 API端点: `/api/v2/cnstock/stocks`
- 自动检测数据顺序并转为正序 (oldest-first)
- 字段映射: time/open/high/low/close/volume
- ATR计算 (14日)
- 批量获取 + 格式化

Hubble API已知端点(参考 `references/hubble-api-endpoints.md`):
- `GET /api/v2/cnstock/symbols` — A股全量股票列表
- `GET /api/v2/cnstock/securities` — 实时证券行情
- `GET /api/v2/cnstock/batch-kline` — 批量K线
- `POST /api/v2/stock/cnstock/screener` — A股选股筛选
- `GET /api/v2/fund/etf-basic` — ETF列表
- `GET /api/v2/cnstock/index/basic` — 指数基本信息

### smc_signals — 信号检测模块

6种SMC信号:
- **FVG** (Fair Value Gap) — 价格未填充区域, 牛市/熊市
- **IFVG** — 反向FVG确认
- **Sweep** — 流动性扫荡 (SweepUp/SweepDown)
- **OB** (Order Block) — 机构订单块 (Bull/Bear)
- **BPR** (Balanced Price Range) — 平衡区突破 (Bull/Bear)
- **MSB** (Market Structure Break) — 市场结构突破 (Up/Down)

主要函数:
- `detect_all_signals(ohlcv, params)` → 所有信号列表
- `score_signal(signal, ohlcv, params)` → 信号评分 (1-5)
- `signal_summary(signals)` → 按类型统计计数

### smc_backtest — 回测引擎 [ENHANCED — V2]

V9新增:
- **完整交易日志**: 每笔交易附带中文入场/出场原因、质量评分
- **入场原因**: 流动性扫荡/机构订单块/FVG/结构突破 + 方向+强度
- **出场原因**: 触发止损/止盈/反转信号 + 盈亏金额
- **被拒绝信号**: 记录哪些信号被过滤掉及拒绝原因

核心函数:
- `evaluate_trades(ohlcv, params)` → 单股票回测，返回含 trade_logs
- `evaluate_params(params, stocks)` → 多股票批量评估
- `compute_score(fe)` → WR^2.0评分公式

trade_logs数据格式:
```
━━━ 交易 #38 ━━━
方向: 🟢 做多
信号: SweepDown (评分:4.0)
入场: 1344.98 | 出场: 1336.78
SL: 1336.78 | TP: 1369.57
收益率: -0.61% | R:R: 1.0
❌ 亏损
入场原因: 下方流动性扫荡 空头陷阱 多头入场 | 方向:做多 | 强度:中
出场原因: 触发止损(sl=1336.78) 亏损-0.61%
质量评分: 1
```

评分公式 (WR优先):
```python
score = (wr / 100) ** 2.0 * sqrt(min(n, 50)) * min(3, pf) * min(2.5, rr_avg)
if rr_avg < 1.2 and total_trades >= 3:  score *= 0.1
if total_trades < 8:                     score = 0
elif total_trades < 15:                  score *= max(0.3, total_trades / 15)
```

### smc_watchlist — 全市场扫描 [NEW]

覆盖:
- **A股**: 5400+只 (Hubble symbols端点)
- **ETF**: 全部列表 (etf-basic端点)
- **行业板块**: 所有申万行业
- **指数**: 主要指数

核心函数:
- `scan_and_build_watchlist(limit_stocks, limit_etfs, limit_indices, limit_sectors, min_score)` → watchlist
- `load_cnstock_list(limit)` → 股票列表
- `load_etf_list(limit)` → ETF列表
- `load_index_list(limit)` → 指数列表

返回的watchlist每项包含:
- name, symbol, market (A股/ETF/板块/指数)
- signal_type, signal_direction, signal_score, signal_price
- signal_date, signal_reason (入场理由)
- current_price, deviation_pct (价格偏离度)
- deviation_level (normal/moderate/high_risk)

### smc_webui — 交互式WebUI [ENHANCED — V2]

启动: `cd ~/.hermes/scripts && python3 v9/smc_webui.py --port 8881`
访问: `http://localhost:8881`

#### API端点

| 端点 | 参数 | 说明 |
|------|------|------|
| `GET /api/health` | — | 健康检查 |
| `GET /api/status` | — | 运行状态 + Hubble + Proxy |
| `GET /api/config` | — | 配置预览 |
| `GET /api/chart/data` | symbol,count,sl,tp,score,mt | **[核心]** K线+标注+回测+日志全量数据 |
| `GET /api/signals/scan` | symbol,period,count | 单股票信号扫描 |
| `GET /api/backtest/run` | symbol,sl,tp,score,mt | 单股票回测(含TradeLogs) |
| `GET /api/backtest/batch` | stock_count,sl,tp | 批量回测 |
| `GET /api/market/scan` | limit,min_score | 全市场扫描 + Watchlist |
| `GET /api/market/stocks` | limit | A股列表|
| `GET /api/market/etfs` | limit | ETF列表 |
| `GET /api/market/indices` | limit | 指数列表 |
| `GET /api/proxy` | — | Proxy Guardian状态 |
| `GET /api/history` | — | 优化历史 |
| `WS /ws` | — | 实时WebSocket推送 |
| `GET /` | — | **[完整ECharts前端]** |

#### 前端6标签页

1. **K线** — ECharts candlestick + 趋势线(MarkLine) + 信号区域(MarkArea) + 结构点/买卖点(MarkPoint)
2. **回测** — 统计KPI网格 + 完整交易表格(方向/入场/出场/SL/TP/收益/R:R/结果)
3. **交易日志** — 全中文可读日志(入场原因/出场原因/质量评分)
4. **监测** — Watchlist (选股列表 + 价格偏离 + 信号日期/理由/位置)
5. **信号** — 信号明细(各信号类型统计 + 方向统计)
6. **配置** — 参数空间和系统配置JSON

#### 颜色约定

- Bull/Long/买入: `#3fb950` (绿色)
- Bear/Short/卖出: `#f85149` (红色)
- 中性/统计: `#d29922` (黄色), `#58a6ff` (蓝色)
- 背景: `#0d1117` (深色), 卡片 `#161b22`

## 启动方式

```bash
# WebUI (主入口) — 端口8881
cd ~/.hermes/scripts && python3 v9/smc_webui.py --port 8881

# 程序化使用 (Python)
from v9 import smc_config, smc_hubble, smc_signals, smc_backtest, smc_annotations, smc_watchlist

# 信号扫描 + 标注
ohlcv, atr, n = smc_hubble.fetch_and_prepare('600519.SH')
params = smc_config.get_param_space(defaults=True)
params.update({'sl_pct': 1.0, 'tp_pct': 3.0})
signals = smc_signals.detect_all_signals(ohlcv, params)
bt_result = smc_backtest.evaluate_trades(ohlcv, params)
annotations = smc_annotations.generate_chart_data(ohlcv, signals, bt_result.get('trades', []))

# 全市场扫描
watchlist = smc_watchlist.scan_and_build_watchlist(limit_stocks=50, min_score=2.0)
```

## 关键注意事项 / 常见陷阱

1. **Hubble API数据顺序**: V2 API返回 newest-first，必须反转
2. **Annotations导入错误**: smc_annotations.py 中 `import json` 必须在模块级别（曾因缺失导致 SyntaxError）
3. **Backtest日志函数**: `_format_trade_log` 是模块级函数，非类方法 — 在 evaluate_trades 内用 `_format_trade_log(trade)` 而非 `self._format_trade_log(trade)`
4. **参数同步**: 前端参数(sl_pct/tp_pct/score_min/max_trades)必须与后端`calc_atr_sl_tp`的参数对齐
5. **ECharts渲染**: K线标注使用 `markArea`(矩形) + `markLine`(线段) + `markPoint`(点)，确保 `markData` 坐标与OHLCV数组索引对应
6. **全市场扫描超时**: 扫描5400+股票可能耗时较长，建议限制 `limit_stocks=50` 或使用异步批量

## V8.4 → V9 迁移

| 方面 | V8.4 | V9 |
|------|------|----|
| 代码组织 | 2个巨文件 | 9个模块化文件 |
| 配置 | 硬编码 + argparse | YAML + 环境变量 |
| API端点 | 旧端点已404 | V2稳定端点 |
| 数据格式 | list格式 | dict格式 + 自动转换 |
| 缓存 | 单一文件名 | 多级回退 |
| WebUI | 8879端口, 只读 | 8881端口, 全交互式 |
| K线标注 | 无 | 完整趋势线+区域+结构+买卖点 |
| 交易日志 | 纯数字统计 | 全中文入场/出场原因 |
| 市场扫描 | 无 | 全市场5400+A股+ETF+板块+指数 |
| 实时监测 | 无 | Watchlist + 价格偏离 |
| 输出目录 | smc_opt_v83 | smc_opt_v9 |
| 错误处理 | bare except | 结构化重试 + 日志 |
| 导入方式 | 单文件 | 模块化, 支持relative/absolute |

## Hubble API参考

API基址: `http://43.167.234.49:3101` (API Key在config.yaml中配置)
完整243个端点见 `references/hubble-api-endpoints.md`

V2 K线端点:
```
GET /api/v2/cnstock/stocks?symbol=600519.SH&interval=daily&count=200
```
返回格式:
```json
{
  "data": [{"time": "20260430", "open": 1400, "high": 1401.17, "low": 1380, "close": 1384.79, "volume": 52752.67}]
}
```