# -*- coding: utf-8 -*-
"""SMC 项目统一配置（审计 P1 修复：消除生产关键路径/解释器硬编码）。
生产关键脚本（daily_combo_run / current_scanner / continuation_scanner /
paper_sim / sim_scheduler / finalize_dashboard）应引用本模块；
历史研究脚本（combo_vN_run / iter_*，已移入 archive/）保留各自硬编码并标注 legacy。
"""
import os

# ---- 项目根 ----
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))  # E:\test\smc_project
RESEARCH_DIR = os.path.join(PROJECT_ROOT, "research")
HERMES_DIR = os.path.join(PROJECT_ROOT, "hermes")
WDH_DIR = os.path.join(PROJECT_ROOT, "wdh")
ANNOUNCE_DIR = os.path.join(PROJECT_ROOT, "announce")
ARCHIVE_DIR = os.path.join(RESEARCH_DIR, "archive")

# ---- 数据目录 ----
KT_CACHE = os.path.join(HERMES_DIR, "kline_cache_tencent")
MONITOR_DIR = os.path.join(HERMES_DIR, "smc_monitor")
ANNOUNCE_DB = os.path.join(ANNOUNCE_DIR, "smc_announce.db")

# ---- 生产文件 ----
LEDGER = os.path.join(RESEARCH_DIR, "paper_ledger.json")
SELECTION_RESULT = os.path.join(RESEARCH_DIR, "selection_result.json")
RUN_STATUS = os.path.join(RESEARCH_DIR, "run_status.json")
DASHBOARD = os.path.join(RESEARCH_DIR, "combo_dashboard.json")
SCANNER_RESULT = os.path.join(RESEARCH_DIR, "current_scanner_result.json")
REGISTRY = os.path.join(MONITOR_DIR, "production_registry.json")
MONITOR_PID = os.path.join(RESEARCH_DIR, "monitor.pid")

# ---- 镜像目录（前端同步）----
MIRROR_DIRS = [os.path.join(HERMES_DIR, "smc_monitor"), r"E:\root\.hermes\smc_monitor"]

# ---- 解释器（生产 3.12；研究 3.13 见 README）----
PY_PRODUCTION = r"C:\Users\Administrator\AppData\Roaming\uv\python\cpython-3.12.13-windows-x86_64-none\python.exe"
PY_RESEARCH = r"C:\Users\Administrator\.workbuddy\binaries\python\versions\3.13.12\python.exe"

# ---- 撮合参数 ----
FEE_PCT = 0.20          # 双边费用 %
SLIPPAGE = 0.001        # 单边滑点 0.1%
