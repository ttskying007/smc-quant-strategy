# SMC 项目接管与全面偏离诊断报告

- 报告日期：2026-08-17
- 远程主机：10.0.1.203（Ubuntu 26.04 LTS，VMware 虚拟机，16G RAM，147G 磁盘）
- 接管通道：SSH `lei/wzht@123` → `sudo` root（root 直连 SSH 被拒，lei 属 sudo/docker 组）
- 本地落点：`E:\test\smc_project\`（含 hermes 全量镜像、4 个下载包、审核脚本）

---

## 一、接管完成情况

| 项目 | 状态 |
|---|---|
| 网络/SSH | ✅ 可达，22 端口，SSH 登录成功，sudo 提权 root 成功 |
| 代码打包 | ✅ `smc_code.tar.gz` 44MB（scripts 351MB + smc_source + smc-webui* + 文档，排除 pycache/pyc/log） |
| 数据打包 | ✅ `smc_opt_data.tar.gz` 409MB（smc_opt_* 共 6.4GB）；`smc_misc_data.tar.gz` 9.9MB；`smc_audit_small.tar.gz` 728MB（排除 >50MB 大文件） |
| 传输校验 | ✅ 4 个包 MD5 与远程逐一一致（首次并行下载曾因打包未完成而损坏，已用 scp 重下并校验） |
| 本地解包 | ✅ 12.4GB / 14,580 文件；1435/1435 完整（3 个 Windows 无法解压项：1 个换行脏文件名 + 2 个符号链接） |
| 本地运行 | ✅ Python 3.12（uv 托管）直接运行 `smc_unified.py`，`http://127.0.0.1:8890` HTTP 200，**Active: V88** |
| **K线缓存补充** | ✅ 8-17 补打 `smc_kline_cache.tar.gz`（227MB）：kline_cache 19,192 文件 / 15min 4,653 / 60min 9,104 / etf / weekly，MD5 校验一致；本地 `/api/kline` 全周期验证通过（600519.SH daily 750 根→2026-08-14、000001.SZ 60min 500 根、weekly 200 根） |
| 路径兼容 | ✅ 创建 `C:\root\.hermes` 与 `E:\root\.hermes` 双 junction → 本地镜像，透明兼容全部 `/root/.hermes` 硬编码 |

> 说明：远程项目约 84.5% 的 .py 硬编码 `/root/.hermes` 绝对路径，Windows 下 Python 将其解析为当前盘 `\root\...`，故用 junction 映射（不需要改动任何源码）。

---

## 二、项目全貌

### 规模（本地镜像实测，非文档数据）
- **1,339 个 .py，309,280 行**（scripts 根 1339 文件；`v11/` 306 文件 99,471 行；`v25/` 803 文件 141,108 行 —— 当前迭代主线）
- **72 个 `smc_opt_*` 版本目录**（v25 → v185，含 v69_matrix 2.3GB、v50_signal 738MB 巨型数据）
- 脚本文件名版本标记：**v1 → v701**（v11 时代 v1-v116；v25 时代 v463-v701）
- 审计目录 `smc_audit/`：5,495 项（9.4GB，最大单文件 1.36GB CSV）

### 运行体系（远程实测）
- `smc-frontend-8890.service`：8890 SMC 仪表盘（`smc_unified.py`，root）
- `smc-v536-sina-cache.service`：Sina 数据源隔离缓存补全
- root crontab：`smc_frontend_watch.sh` 每分钟看门狗；`proxy_guardian.sh` 每分钟；`daily_skill_crawl.sh` 每日 6 点
- `/etc/cron.d/`：`smc-v526-live-execution`（V526 盘中执行，9:31-9:45/10-11/13-14 工作日）、`smc-v54-daily-picks`（18:10 实际运行 **v701** post-close observer，见偏离 3.6）
- 今日活动：v526 monitor 空转（open=0/closed=0，EMPTY_BOOK），前端看门狗 HEALTHY

---

## 三、偏离诊断（核心结论）

### 3.1 文档与现实严重脱节
- `SMC_PROJECT_GRAPH.md`（2026-05-23）：记录 **593 文件 / 143,770 行 / 迭代到 V88**
- 实际（2026-08-17）：**1,339 文件 / 309,280 行 / 迭代到 v701**
- 文档声称的关键模块规模（如 smc_unified.py 2,749 行）实际已膨胀到 **7,331 行**
- V88 release report 引用的 `smc_daily_ops.py` 已不存在 —— 文档与代码互相失联

### 3.2 无版本控制（偏离根源）
- `scripts/` **不是 git 仓库**；`.gitnexus/` 只是 2026-07-01 建的代码图谱索引（ladybugdb，48199 符号），`lastCommit` 为空
- 全部"版本"= 文件名里的 v 数字 → **无法追溯、无法 diff、无法回滚**
- Hermes 每次迭代生成新文件（v517→v701 三个月 184 个版本），旧文件从不清理

### 3.3 生产契约混乱
- `smc_unified.py` 的 `ACTIVE_VERSION` 为硬编码 fallback 链，**只查到 V88**（6-13 正式发布，532 笔 WR 80.08%）
- 但后续版本并存且互相冲突：
  - **V167**（6-23）`production_write=true`（793 笔 WR 82.09%）—— 与 ACTIVE_VERSION=V88 矛盾
  - **V185**（6-26）被明确拒绝（`V185_REJECTED_CAUSALITY__RESEARCH_HISTORY_ONLY`），目录却仍叫 `combined_production_candidate`
  - **V100** 系列 `gate pass=false`（未过生产门槛）仍保留为生产候选目录
- 前端混源：`ACTIVE_TRADE_FILE` 指向 V88 trades，同时 `v517_frontend_adapter` 只读展示 V517-V525 研究审计产物 → **生产视图与研究视图在同一个仪表盘并存**

### 3.4 数据/目录污染
- `smc_opt_v102_balanced_volume_gate/`、`smc_opt_v103a_risk_gate/` 内是 **v101 的报告**（复制未改名）
- `smc_opt_v69_90wr_search/`、`v69_high_wr_probe/`、`v70_high_confidence/` 为**空目录**
- 巨型数据文件：v69_matrix_trades.json 2.3GB、v50_signal_snapshot.json 738MB、>100MB 文件 18 个
- 脏文件：`scripts/\n/root/.hermes/skills/trading/multi_source_stock_cache.py\n`（**文件名含换行符**，某脚本把路径当文件名写入）

### 3.5 代码质量
- **1132/1339** 个 .py 硬编码 `/root/.hermes`（84.5%），单机绑定、不可移植
- **v44_engine.py / _a / _b / _c 四个文件 98-99% 逐行相同**（复制改名即"新版本"）
- `signals_v11.py` 与 `signals_v11_backup_v37.py` 96% 相同
- **1,214 个文件不被任何其它文件 import** —— 大量一次性/孤立脚本（hermes 生成式开发，无清理）
- 零 TODO/FIXME/HACK —— 无维护性注释

### 3.6 运行体系新旧并存（cron 名不副实）
- 定时任务文件 `smc-v54-daily-picks` 实际执行的是 **v701** 脚本（8-14 新建）
- V526 盘中执行当前 **EMPTY_BOOK 空转**（无仓位），但仍每分钟消耗资源
- 旧版 cron 残留与新主线（v517+ pure SMC）并行运行

### 3.7 版本演进时间线（实测重建）
| 时间 | 事件 |
|---|---|
| 2026-04-28 | Hermes 部署（hermes-agent.zip 出现在 /home/lei/hermes） |
| 2026-05-02 ~ 06-13 | V7→V88 密集迭代（v11 目录时代）；5-23 文档定格 V88；6-13 V88 生产契约发布（release report） |
| 2026-06-14 ~ 07-17 | V89→V185 研究 gate 系列（72 个 smc_opt 目录成型）；V88 生产数据持续刷新至 7-17 |
| 2026-07-01 | .gitnexus 图索引（无 git 历史） |
| 2026-07 ~ 08-14 | v517→v701 pure SMC 新主线（v25 目录 803 文件）；v526 live cron、v701 收盘观察器上线 |
| 2026-08-17 | 接管日：V88 前端生产 + v526 空转 + v536 缓存 + v701 每日任务 + hermes 网关活跃 |

---

## 四、风险清单

1. **生产与研发脱节**：生产契约停在 V88（6-13），迭代已达 v701（8-14）——约 600 个版本的研究成果未沉淀、未评估、未投产，且无记录说明取舍原因
2. **无版本控制**：任何误改/误删无法回滚；本次接管前项目从未有可审计的历史
3. **单机绑定**：硬编码路径 84.5%，迁移/双机/备份恢复成本高
4. **数据膨胀失控**：12.4GB+（远程 16GB 内存机器，2.3GB 单文件 JSON 会拖垮内存型处理）
5. **幽灵任务**：cron 名字与执行内容不符、空转任务、旧版服务并存 —— 无人能说清"系统今天实际在跑什么"
6. **远程仍在活跃迭代**：hermes 网关（微信/QQ/webhook 已连接）接管后仍可能继续写生产数据 → 需立即冻结决策

---

## 五、接管后续建议（待确认执行）

1. **冻结远程**：停用 smc-frontend-8890 / smc-v536 / smc cron 任务，防止远程继续写入生产（可保留 hermes 网关）
2. **建立基线**：本地 `git init`，将当前镜像作为基线提交（第一个可审计版本）
3. **版本主线梳理**：确认生产采用 V88 契约还是 v517+ 新主线，明确 gate 决策记录
4. **重构**：路径硬编码 → 配置化；删除 v44_engine a/b/c 等重复文件；清理空目录/脏文件/巨型冗余数据
5. **生产契约管理**：建立"哪个版本、何时、为何投产"的单一事实来源（替代文件名 v 数字）

---

## 附：本地资产清单
- `E:\test\smc_project\hermes\` —— 项目全量镜像（12.4GB）
- `E:\test\smc_project\downloads\` —— 4 个原始包（MD5 已校验）
- `E:\test\smc_project\audit_scan.py` / `code_quality.py` / `check_sources.py` —— 审核脚本
- `E:\test\rssh.ps1` / `download.ps1` / `askpass.exe` —— 远程访问与传输工具
- 本地运行中：`http://127.0.0.1:8890`（SMC 仪表盘，Active=V88）
