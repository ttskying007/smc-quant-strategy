# SMC 智能策略项目 —— 全面交接文档

> 生成日期：2026-09-04
> 项目根：`E:\test\smc_project`
> 系统定位：基于 **SMC（Smart Money Concept，聪明钱概念）** 的事件驱动 + 结构确认的 A 股量化选股/纸面交易系统
> 生产策略：**v20f = 事件腿（内部人增持/回购 + SMC 底部）+ 延续腿（MARKUP 结构支撑）**

---

## 目录

1. [架构总览](#一架构总览)
2. [目录蓝图](#二目录蓝图blueprint)
3. [生产流水线调用关系](#三生产流水线调用关系)
4. [核心模块与具体函数](#四核心模块与具体函数)
5. [前端与 API](#五前端与-api)
6. [数据源与数据库](#六数据源与数据库)
7. [生产约束与安全边界](#七生产约束与安全边界)
8. [部署与运维](#八部署与运维)
9. [已知边界与待办](#九已知边界与待办)

---

## 一、架构总览

```
                    ┌─────────────────────────────────────────────┐
                    │             Windows 计划任务                │
                    │  15:30 daily_combo_run.py (主流程)           │
                    │  08:00 daily_combo_run.py --fallback-only    │
                    │  盘中每1分钟 sim_scheduler.py --loop          │
                    └──────────────┬──────────────────────────────┘
                                   │
        ┌──────────────────────────┼──────────────────────────┐
        ▼                          ▼                          ▼
┌───────────────┐        ┌──────────────────┐       ┌──────────────────┐
│  wdh/ 数据层  │        │ research/ 策略层  │       │ hermes/ 前端监控  │
│ 增量刷新/公告  │──K线──▶│ 扫描器+选股+模拟   │──JSON─▶│ smc_unified.py    │
│ 拉取(多源)    │        │ 交易+TP/SL        │       │ HTTP :8890       │
└───────────────┘        └──────────────────┘       │ /monitor /live   │
        ▲                        │                   │ /uzi /kline ...  │
        │                        ▼                   └──────────────────┘
┌───────────────┐        ┌──────────────────┐
│ announce/     │        │ smc_monitor/     │
│ 公告事件库     │        │ 生产注册表/账本    │
│ smc_announce.db│◀──────│ paper_ledger     │
└───────────────┘        │ selection_result │
                         └──────────────────┘
```

### 数据流（每日主流程）

```
公告拉取 → 全市场K线增量刷新 → 关键股Sina刷新
  → current_scanner（事件+SMC候选）
  → continuation_scanner（延续腿候选）
  → sim_scheduler --daily（选股/挂单/TP-SL）
  → finalize_dashboard（同步前端JSON）
  → 盘中 sim_scheduler --loop（实时监控/成交/平仓）
```

---

## 二、目录蓝图（Blueprint）

```
E:\test\smc_project\
├── research\                ★策略核心（507 文件 / 96 MB）
│   ├── daily_combo_run.py       每日流水线总调度（计划任务入口）
│   ├── current_scanner.py       当日扫描：SMC TP2-R20 + 内部人事件
│   ├── continuation_scanner.py  延续腿扫描：MARKUP 结构支撑 + VWAP10%
│   ├── sim_scheduler.py         模拟交易调度（--daily 选股 / --loop 实时）
│   ├── paper_sim.py             纸面交易引擎（选股/成交/TP-SL/账本）
│   ├── finalize_dashboard.py    汇总前端 dashboard JSON
│   ├── gen_v20f.py              生成 v20f 生产组合回测
│   ├── finalize_v20f.py         升级生产注册表 + 报告
│   ├── data_health_check.py     数据源健康检查
│   ├── paper_ledger.json        生产账本（OPEN/CLOSED/FILLED）
│   ├── selection_result.json    选股结果
│   ├── combo_dashboard.json     前端组合展示数据
│   ├── run_status.json          每日运行状态
│   ├── monitor.pid              实时监控进程 PID
│   ├── handover\                交接文档与代码地图（本目录）
│   ├── combo_v10~v20f*.py       历史版本回测脚本（研究）
│   ├── iter_*.py                单维度研究脚本（研究）
│   └── *_report.md / *_研究*.md  研究报告
│
├── hermes\                    ★前端 + 数据缓存 + 历史产物（15283 文件 / 11.8 GB）
│   ├── scripts\
│   │   ├── smc_unified.py        统一前端服务器（HTTP :8890，164 个函数）
│   │   ├── smc_engine_v5~v62.py  历史 SMC 引擎版本
│   │   ├── v25\                  现行引擎门控链（v167/v172/v296/v353/v360...）
│   │   └── 其他研究/工具脚本
│   ├── smc_monitor\              生产监控镜像（registry/ledger/positions）
│   ├── kline_cache_*\            各周期 K 线缓存（tencent/15min/60min/weekly）
│   ├── smc_audit\                历史审计产物（4.8 GB）
│   ├── smc_opt_*\                各版本优化产物（数据量大，非代码）
│   └── crawl_data\               外部资讯数据
│
├── wdh\                       ★数据拉取层（53 文件）
│   ├── incremental_refresh.py    全市场增量刷新（3 并发）
│   ├── pull_announce_daily.py    每日公告拉取
│   ├── pull_tencent.py           腾讯 K 线
│   ├── pull_sina_daily.py        Sina K 线
│   ├── pull_eastmoney_daily.py   东方财富 K 线
│   ├── pull_baostock60_bg.py     BaoStock 60 分钟
│   ├── refresh_holdings_sina.py  持仓/事件股 Sina 刷新
│   ├── pull_blocktrade.py        大宗交易
│   ├── pull_lhb.py               龙虎榜
│   ├── wdh_engine.py             数据引擎（16 KB）
│   └── TP2_*.csv / W1D1D4_*.csv  历史信号/交易样本
│
├── announce\                   ★公告事件库
│   ├── smc_announce.db           事件 SQLite（195 MB）
│   ├── pull_announce*.py         公告拉取/解析
│   └── event_*.py                事件研究脚本
│
├── uzi\                        前端辅助面板（uzi_analyzer/uzi_llm/uzi_panel）
├── margin\                     融资融券相关
├── smc_backtest_report\        回测报告
└── downloads\                  下载缓存
```

---

## 三、生产流水线调用关系

### 3.1 每日主流程 `daily_combo_run.py`（15:30）

```
main()
├── _pause_monitor()               # 暂停实时监控（防并发限流）
├── data_health_check.py           # 数据源健康检查
├── 0a. pull_announce_daily.py     # 公告（wdh/，超时600s）
├── 0.  incremental_refresh.py --workers 3   # 全市场增量刷新（wdh/，超时10800s）
├── 1.  refresh_holdings_sina.py   # 关键股 Sina 刷新（wdh/，超时1200s）
├── 2.  current_scanner.py --refresh   # 当日扫描（超时2400s）
├── 2b. continuation_scanner.py    # 延续腿扫描（超时1800s）
├── 3.  sim_scheduler.py --daily   # 选股+挂单+TP/SL（超时1200s）
├── 4.  finalize_dashboard.py      # 汇总 dashboard
│      └── 复制 combo_dashboard.json / paper_ledger.json 到
│          hermes\smc_monitor\ 与 E:\root\.hermes\smc_monitor\
└── _resume_monitor()              # 恢复实时监控（sim_scheduler --loop）
```

### 3.2 兜底流程 `--fallback-only`（08:00）

```
检查 run_status.json → data_complete==False 时补跑：
  sim_scheduler.py --daily → finalize_dashboard.py → 同步镜像
```

### 3.3 盘中实时 `sim_scheduler.py --loop`（每 1 分钟）

```
loop_once()
├── paper_sim.realtime_prices()    # Sina 实时价格（≤50只/请求）
├── PENDING_ORDER → price<=entry → FILLED
├── FILLED → 触发 TP1~TP4/SL1~SL2 → CLOSED
├── _append_realtime_log()         # 实时价格日志
└── _append_trade_log()            # 交易日志
```

---

## 四、核心模块与具体函数

> 完整函数级清单见 `handover/code_map_functions.md`（1642 个 Python 文件自动提取）。
> 以下为生产关键文件的核心函数。

### 4.1 `research/paper_sim.py`（纸面交易引擎 ★核心）

| 函数 | 职责 |
|---|---|
| `load_ledger()` / `save_ledger(led)` | 账本读写（paper_ledger.json） |
| `realtime_prices(codes)` | Sina 实时价格批量获取 |
| `sub_signals_event(bs, i, sig_date)` | 事件腿子信号（阶段确认/ADX≥20/披露日/入场日） |
| `sub_signals_cont(bs, entry_idx, support_date)` | 延续腿子信号（MARKUP/支撑回踩/VWAP/入场） |
| `stage_and_deep(bs, i)` | 行为阶段 + DEEP 质量过滤 |
| `weekly_trend_of(bs, i)` | 周线趋势（5日聚合，MA10 周线） |
| `_market_proxy(code)` | 市场状态代理（200只采样 20 日均涨跌） |
| `adaptive_hold(base_hold, proxy)` | 自适应持有期（反弹20日/震荡12日/弱市20日） |
| `adx14_of(bs, i)` | ADX14 |
| `bars_of(code)` | 读取 K 线 |
| `is_swing_high/low(bs, j)` | 摆动高低点判定 |
| `structural_sltp(code, signal_date, src, stage, adx)` | ★SMC 策略化分层 TP/SL（TP1~TP4/SL1~SL2 动态锚点） |
| `daily_selection()` | 每日选股（新事件 → PENDING_ORDER） |
| `realtime_monitor()` | 实时监控（挂单成交 + TP/SL 平仓） |
| `_append_realtime_log()` / `_append_trade_log()` | 日志记录 |

### 4.2 `research/current_scanner.py`（当日扫描）

| 函数 | 职责 |
|---|---|
| `bars(path)` | 读取单股 K 线 JSON |
| `market_latest()` | 从 Sina 实时确定最新交易日（权威） |
| `refresh_key_stocks()` | 强制刷新持仓+近期事件股（小集合快刷） |
| `scan_one(p, latest)` | 单股扫描：SMC TP2-R20 / 事件候选（新鲜度门控） |

### 4.3 `research/continuation_scanner.py`（延续腿）

| 函数 | 职责 |
|---|---|
| `bars(path)` | 读 K 线 |
| `is_swing_low(bs, j)` | 摆动低点 |
| `stage_detailed(bs, i)` | 行为阶段细分 |
| `compute_median()` | 波动率中位基准 |

### 4.4 `research/sim_scheduler.py`（调度）

| 函数 | 职责 |
|---|---|
| `daily()` | 每日选股（调用 paper_sim.daily_selection） |
| `loop_once()` | 单次实时循环 |
| `main()` | 参数分发（--daily / --loop / --interval） |

### 4.5 `research/gen_v20f.py`（生产组合生成）

| 函数 | 职责 |
|---|---|
| `bars_of(code)` | 读 K 线 |
| `is_strong(title)` | 事件强度（回购/增持首次等） |
| `adx14(bs, i)` | ADX14 |
| `stage_of(bs, i)` | SMC 行为阶段（ACCUM/DOWNTREND/MARKUP/UPTREND） |
| `weekly_trend_of(bs, i)` | 周线趋势 |

### 4.6 `research/finalize_v20f.py`（生产升级）

| 函数 | 职责 |
|---|---|
| `stats(rs)` | 组合统计 → 更新 production_registry + 报告 |

### 4.7 `research/data_health_check.py`

| 函数 | 职责 |
|---|---|
| `check_source(name, url, timeout)` | 数据源连通性检查 |

---

## 五、前端与 API

### 5.1 服务器 `hermes/scripts/smc_unified.py`（164 个函数，HTTP :8890）

页面路由（`build_*`）：

| 路由 | 页面 |
|---|---|
| `/` | 首页 |
| `/monitor` | ★生产监控（v20f 持仓/挂单/TP-SL/实时价格/候选） |
| `/live` | 实时监控页（AJAX 局部刷新） |
| `/trade` | 实时交易模拟页 |
| `/uzi` | UZI 面板 |
| `/kline?symbol=` | 个股 K 线（版本路由） |
| `/backtest` | 回测页 |
| `/compare` | 版本对比 |
| `/analysis` / `/autopsy` | 分析/复盘 |
| `/resonance` | 多周期共振 |
| `/diagnostics` | V30 SMC 诊断（队列分解/根因归因） |
| `/logs` / `/docs` | 日志/文档 |
| `/historical-artifacts` | 旧系统历史审计 |

数据访问（`get_*` / `load_*` / `build_*`）：

| 函数 | 职责 |
|---|---|
| `_production_registry()` | 生产注册表（当前策略/版本） |
| `_v526_live_production()` / `_v526_state()` | V526 实时生产状态 |
| `get_version_trades(version)` | 版本交易缓存（大文件优化） |
| `get_active_picks()` | 当前选股 |
| `build_kline(symbol, version)` | K 线构建 |
| `build_dashboard(qs)` | 组合 dashboard |
| `build_equity_curve_data()` | 组合权益曲线 |
| `build_monitor()` | 监控页组装 |
| `normalize_v27_trades/picks()` | 前端字段契约统一 |
| `_apply_smc_field_contract()` | SMC 字段契约填充 |

### 5.2 前端技术形态

- 单文件 Python http.server Handler（`http.server.BaseHTTPRequestHandler`）
- 内嵌 HTML/CSS/JS 模板字符串 + 少量 jQuery/AJAX
- 深色主题（GitHub 风格 #0d1117）

---

## 六、数据源与数据库

| 数据源 | 用途 | 文件/入口 |
|---|---|---|
| 腾讯（Tencent） | 日 K 线主力源 | `wdh/pull_tencent.py` → `hermes/kline_cache_tencent/` |
| Sina | 实时价格/关键股 | `wdh/refresh_holdings_sina.py` |
| 东方财富（EastMoney） | 日 K 线备源 | `wdh/pull_eastmoney_daily.py` |
| BaoStock | 60 分钟 K 线 | `wdh/pull_baostock60_bg.py` |
| 公告（巨潮等） | 内部人增持/回购事件 | `wdh/pull_announce_daily.py` → `announce/smc_announce.db` |
| 大宗交易 / 龙虎榜 | 辅助信号 | `wdh/pull_blocktrade.py` / `pull_lhb.py` |

K 线缓存目录（hermes/）：

| 目录 | 内容 |
|---|---|
| `kline_cache_tencent/` | 日 K（289 MB，4662 股）★主 |
| `kline_cache_15min/` / `kline_cache_60min/` | 分钟线 |
| `kline_cache_weekly/` | 周 K |
| `kline_cache_etf/` | ETF |

数据库：`announce/smc_announce.db`（SQLite，195 MB，事件公告）

---

## 七、生产约束与安全边界

### 7.1 生产合同（严禁破坏）

| 文件 | 内容 | 哈希（MD5） |
|---|---|---|
| `hermes/smc_monitor/production_registry.json` | 生产注册表（策略=COMBO_SMC_EVENT） | `99763059B55897338DFDDCA1D199C525` |
| `research/paper_ledger.json` | 生产账本 | 会随交易变化 |
| `research/selection_result.json` | 选股结果 | 会随扫描变化 |

### 7.2 关键约束

1. **`production_registry.json` 是生产合同**：`production_strategy`、`buy_enabled`、版本指针。任何升级必须通过 `finalize_*.py` 原子更新，哈希变化需告警。
2. **选股新鲜度门控**：只产生 K 线最新日 == 市场最新日的候选（防陈旧信号）。
3. **T+1 纪律**：信号日次日开盘买入（`buy_tomorrow` 语义）。
4. **实时监控防并发**：每日主流程先 `_pause_monitor()` 后 `_resume_monitor()`（8/21 故障修复）。
5. **研究只读**：iter_*/combo_* 研究脚本只写研究产物，不碰生产文件。
6. **兜底机制**：`--fallback-only` 在数据未完整时补跑选股 + dashboard。

### 7.3 不应被删除/篡改的文件

- `production_registry.json`、`paper_ledger.json`、`selection_result.json`
- `combo_dashboard.json`、`current_scanner_result.json`、`run_status.json`
- `announce/smc_announce.db`
- 各 `kline_cache_*/`（数据资产）

---

## 八、部署与运维

### 8.1 Python 环境

| 用途 | 解释器 |
|---|---|
| 生产流水线（daily_combo_run 调用） | `C:\Users\Administrator\AppData\Roaming\uv\python\cpython-3.12.13-windows-x86_64-none\python.exe` |
| 研究/回测（本会话使用） | `C:\Users\Administrator\.workbuddy\binaries\python\versions\3.13.12\python.exe` |

### 8.2 Windows 计划任务（参考 `research/每日自动化说明.md`）

| 时间 | 命令 |
|---|---|
| 15:30 | `python research\daily_combo_run.py` |
| 08:00 | `python research\daily_combo_run.py --fallback-only` |
| 盘中每 1 分钟 | `python research\sim_scheduler.py --loop --interval 30`（后台常驻） |

### 8.3 前端启动

```
python hermes\scripts\smc_unified.py     # HTTP :8890
```

### 8.4 健康检查

- `/monitor` 应显示最新交易日数据与持仓
- `research/run_status.json` 的 `data_complete` 应为 true
- 前端页面 /monitor /live /uzi 均应 HTTP 200

---

## 九、已知边界与待办

1. **数据源时效**：Sina/腾讯为免费源，存在限流与延迟；`refresh_holdings_sina.py` 与实时监控并发可能导致失败（已有 pause/resume 机制）。
2. **历史引擎繁多**：`smc_engine_v5~v62`、`smc_opt_*` 为历史研究产物，仅 `v25/` 现行引擎链与 `smc_unified.py` 前端为生产相关。
3. **大文件性能**：v101_trades.json 等大文件已加缓存（`get_version_trades` 5.9s→缓存）。
4. **研究脚本堆积**：`iter_*.py` 为单维度研究，可归档但勿删（结论沉淀在 `策略思路全景与迭代框架.md`）。
5. **A 股交易限制**：涨跌停无法成交、T+1 卖出限制、退市风险股需过滤（回测中 -97% 极端样本）。

---

## 附：交接包内容

- `handover/code_map.json` — 1642 个 py 文件的函数/类/参数自动提取
- `handover/code_map_functions.md` — 函数级可读清单
- `本交接文档` — 架构/蓝图/调用/函数/运维

---

*本文档由自动化盘点 + 源码函数提取生成，函数清单以 `code_map_functions.md` 为准；生产合同以 `production_registry.json` 为准。*
