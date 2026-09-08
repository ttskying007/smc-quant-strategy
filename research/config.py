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
MAX_HOLD = 12           # 日线最长持有（审计 F11: 5→12）
PENDING_EXPIRE_DAYS = 3  # PENDING 挂单 valid_from 后 N 交易日未成交 → EXPIRED（审计12: 防长期阻塞）

# ---- 策略腿开关（复审 P0-3）----
# SMC 腿经五重证据（去伪 OOS -0.60% / SL-ATR -0.94% / HHI 0.369 / WF 3正4负 / D5 净负）
# 确认无稳定样本外 edge → 默认禁用独立开仓，仅作 HTF_BIAS 研究特征。
# 事件腿（唯一有 OOS edge: +5.43% PF7.75, bootstrap CI[7.13,8.76]）为生产主腿。
ENABLE_SMC_LEG = False
ENABLE_EVENT_LEG = True

# ---- 弱市加权（2026-09-08 regime 发现正向应用）----
# 事件腿为逆向策略: 弱市(proxy<0)信号质量最高(avg+6.6%/PF6.6 vs 强市+1.3%)。
# weak_market_weight_ab / weak_market_consistency 双段(OOS+IS)验证:
#   k=2/4/8 单调提升风险调整收益(IS r/m 27→113, OOS r/m 19→44), MDD 仅小幅抬升。
# 启用保守 k=2（仓位加权 clip(1-2×proxy, 0.3, 2.0)），单票上限仍 25% 兜底。
WEAK_MARKET_WEIGHT = True          # 总开关
WEAK_MARKET_K = 2.0                # 加权系数: w = clip(1 - k×proxy, 0.3, 2.0)
WEAK_MARKET_W_MIN = 0.3            # 最小权重(强市降仓下限)
WEAK_MARKET_W_MAX = 2.0            # 最大权重(弱市加仓上限)
