# SMC 量化策略项目（Smart Money Concept）

基于 **SMC（聪明钱概念）** 的 A 股事件驱动 + 结构确认量化选股/纸面交易系统。

- **生产策略**：v20f = 事件腿（内部人增持/回购 + SMC 底部）+ 延续腿（MARKUP 结构支撑）
- **当前状态**：纸面交易（PAPER_PRODUCTION_COMBO），`buy_enabled: true`
- **代码语言**：Python 3（生产 3.12 / 研究 3.13）

---

## 快速导航

| 入口 | 路径 | 说明 |
|---|---|---|
| **交接文档（必读）** | `research/handover/SMC策略项目交接文档.md` | 架构、蓝图、调用关系、函数级说明 |
| **函数地图** | `research/handover/code_map_functions.md` | 1642 个 Python 文件的函数/参数/说明自动提取 |
| **每日流水线** | `research/daily_combo_run.py` | 15:30 主流程（数据刷新→扫描→选股→dashboard） |
| **扫描器** | `research/current_scanner.py` | SMC TP2-R20 + 内部人事件当日候选 |
| **延续腿扫描** | `research/continuation_scanner.py` | MARKUP 结构支撑 + VWAP10% 候选 |
| **纸面交易引擎** | `research/paper_sim.py` | 选股/成交/TP-SL/账本 |
| **模拟调度** | `research/sim_scheduler.py` | `--daily` 选股 / `--loop` 盘中实时 |
| **前端服务器** | `hermes/scripts/smc_unified.py` | HTTP :8890（/monitor /live /uzi /kline） |
| **数据拉取层** | `wdh/` | 腾讯/Sina/东财/BaoStock/公告/大宗/龙虎榜 |
| **公告事件库** | `announce/smc_announce.db` | SQLite 事件库（本地数据，不入库） |
| **仓库完整性审计** | `research/handover/check_repo_completeness.py` | 对比工作区 vs git 跟踪 |

---

## 目录结构

```
├── research\          策略核心（扫描/选股/模拟交易/回测/报告/handover 交接文档）
├── hermes\
│   ├── scripts\       前端 smc_unified.py + 引擎链（v25\ 现行）+ 历史引擎 v5~v62
│   ├── smc_monitor\   生产监控镜像（本地数据，不入库）
│   └── skills\        技能文档（832 文件）
├── wdh\               数据拉取层（增量刷新/公告/多源 K 线）
├── announce\          公告事件库（拉取脚本 + smc_announce.db 本地）
├── uzi\               前端辅助面板
├── margin\            融资融券研究
└── smc_backtest_report\  回测报告
```

## 每日运行（Windows 计划任务）

| 时间 | 命令 |
|---|---|
| 15:30 | `python research\daily_combo_run.py` |
| 08:00 | `python research\daily_combo_run.py --fallback-only`（兜底） |
| 盘中 | `python research\sim_scheduler.py --loop --interval 30`（实时监控） |
| 前端 | `python hermes\scripts\smc_unified.py` → http://127.0.0.1:8890 |

## 生产约束（审计重点）

1. **`production_registry.json` 是生产合同**（本地 `hermes/smc_monitor/`，**不入库**）：`production_strategy=COMBO_SMC_EVENT`、`buy_enabled`、版本指针。
2. **账本/选股不入库**：`paper_ledger.json`、`selection_result.json`、`run_status.json` 等运行时数据均在 `.gitignore` 排除（保护敏感持仓信息）。
3. **数据缓存不入库**：K 线缓存、审计产物、优化产物、公告 DB 均为可再生数据，体积巨大（11.8 GB），未入库。
4. **T+1 纪律**：信号日次日开盘买入。
5. **选股新鲜度门控**：仅 K 线最新日 == 市场最新日的候选生效。

## 如何审计本仓库

1. 先读 `research/handover/SMC策略项目交接文档.md`（架构 + 调用关系 + 核心函数）
2. 用 `research/handover/code_map_functions.md` 检索任意模块的函数级说明
3. 运行 `python research/handover/check_repo_completeness.py` 验证仓库完整性
4. 数据类文件（K线/账本/DB）需在运行环境获取，本仓库只含代码与文档

## 环境要求

- Python 3.12（生产，uv 管理）或 3.13（研究）
- 依赖：pandas / numpy / requests / 等（各脚本头部注明）
- K 线数据：`wdh/incremental_refresh.py --workers 3` 全市场重建（约 75 分钟）

---

*维护者：ttskying007 | 最近更新：2026-09-04*
