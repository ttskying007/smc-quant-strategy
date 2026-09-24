# -*- coding: utf-8 -*-
"""SMC 项目统一配置（审计 P1 修复：消除生产关键路径/解释器硬编码）。
生产关键脚本（daily_combo_run / current_scanner / continuation_scanner /
paper_sim / sim_scheduler / finalize_dashboard）应引用本模块；
历史研究脚本（combo_vN_run / iter_*，已移入 archive/）保留各自硬编码并标注 legacy。

FIX(2026-09-13, 第八轮审计 6.5): 路径环境变量化 —— SMC_DATA_ROOT(项目根)与
SMC_FRONTEND_ROOT(第二镜像前端目录)环境变量优先, 缺省回落本机路径(向后兼容)。
生产入口应调用 validate_paths() 做存在性检查(缺失非零退出), 研究脚本可不调。
"""
import os
import sys as _sys

# ---- 项目根（第八轮 6.5: SMC_DATA_ROOT 环境变量优先; 缺省 repo 推导, 兼容原行为）----
_env_root = os.environ.get("SMC_DATA_ROOT")
PROJECT_ROOT = _env_root if _env_root else os.path.dirname(os.path.dirname(os.path.abspath(__file__)))  # E:\test\smc_project
RESEARCH_DIR = os.path.join(PROJECT_ROOT, "research")
HERMES_DIR = os.path.join(PROJECT_ROOT, "hermes")
WDH_DIR = os.path.join(PROJECT_ROOT, "wdh")
ANNOUNCE_DIR = os.path.join(PROJECT_ROOT, "announce")
ARCHIVE_DIR = os.path.join(RESEARCH_DIR, "archive")

# ---- 数据目录 ----
KT_CACHE = os.path.join(HERMES_DIR, "kline_cache_tencent")
ETF_CACHE = os.path.join(HERMES_DIR, "kline_cache_etf")
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

# ---- 镜像目录（前端同步; 第八轮 6.5: SMC_FRONTEND_ROOT 环境变量优先）----
_env_fe = os.environ.get("SMC_FRONTEND_ROOT")
MIRROR_DIRS = [os.path.join(HERMES_DIR, "smc_monitor")]
_default_fe = os.path.join(PROJECT_ROOT, ".hermes", "smc_monitor")
_mirror_fe = _env_fe if _env_fe else _default_fe
if os.path.abspath(_mirror_fe) != os.path.abspath(MIRROR_DIRS[0]):
    MIRROR_DIRS.append(_mirror_fe)

# ---- 生产输出 ----
# 生产状态文件与研究代码同属项目根，禁止调用方引用不存在的 OUTPUT_ROOT。
OUTPUT_ROOT = RESEARCH_DIR


def _env_bool(name, default):
    value = os.environ.get(name)
    if value is None:
        return bool(default)
    return value.strip().lower() in {"1", "true", "yes", "on"}


def validate_paths(required=("RESEARCH_DIR", "WDH_DIR", "KT_CACHE", "ANNOUNCE_DB", "MONITOR_DIR")):
    """R19(第八轮 6.5): 生产路径存在性检查 —— 缺失打印全部问题并返回 False,
    调用方(daily_combo_run 等)据此非零退出; 研究脚本不强制调用。
    同时打印解析后的绝对路径(审计: '启动时打印解析后的绝对路径并检查存在性')。"""
    import sys
    ok = True
    print(f"[paths] SMC_DATA_ROOT={'set' if _env_root else 'unset(默认repo推导)'} "
          f"PROJECT_ROOT={PROJECT_ROOT}", flush=True)
    for name in required:
        p = globals().get(name)
        if not p or not os.path.exists(p):
            print(f"[paths] FAIL: {name} = {p} 不存在", flush=True)
            ok = False
        else:
            print(f"[paths] OK: {name} = {p}", flush=True)
    return ok

# ---- 解释器（环境变量优先；默认使用当前运行解释器）----
PY_PRODUCTION = os.environ.get("SMC_PYTHON", _sys.executable)
PY_RESEARCH = os.environ.get("SMC_RESEARCH_PYTHON", PY_PRODUCTION)

# ---- 撮合参数 ----
FEE_PCT = 0.20          # 双边费用 %
SLIPPAGE = 0.001        # 单边滑点 0.1%
MAX_HOLD = 12           # 日线最长持有（审计 F11: 5→12）
PENDING_EXPIRE_DAYS = 3  # PENDING 挂单 valid_from 后 N 交易日未成交 → EXPIRED（审计12: 防长期阻塞）

# ---- 策略腿开关（复审 P0-3）----
# SMC 腿经五重证据（去伪 OOS -0.60% / SL-ATR -0.94% / HHI 0.369 / WF 3正4负 / D5 净负）
# 确认无稳定样本外 edge → 默认禁用独立开仓，仅作 HTF_BIAS 研究特征。
# 事件腿（唯一有 OOS edge: +5.43% PF7.75, bootstrap CI[7.13,8.76]）为生产主腿。
# Default contract: ENABLE_EVENT_LEG = True; ENABLE_SMC_LEG = False.
ENABLE_SMC_LEG = _env_bool("SMC_ENABLE_SMC_LEG", False)
ENABLE_EVENT_LEG = _env_bool("SMC_ENABLE_EVENT_LEG", True)
# CONT remains off by default until its stricter freshness/threshold evidence is
# promoted; operators must opt in explicitly with SMC_ENABLE_CONT_LEG=1.
ENABLE_CONT_LEG = _env_bool("SMC_ENABLE_CONT_LEG", False)

# ---- EVENT 腿 rank 门槛（R38ab 接线, 2026-09-16 用户批准）----
# 依据: 全链路审计(r38_rank_chain.py) + 研究分叉(r38_gen_v20f_rank3.py) 双路径逐项一致:
#   全组合 n=1735 | IS n=1243 PF3.44 | OOS n=492 PF3.67
# 预期效果(相对无门槛基线 n=1861 PF3.35 MDD-415):
#   PF 3.35→3.52 | OOS 3.57→3.67 | MDD -415→-383 | avg +4.054→+4.297%
#   代价: 候选量 -126 笔(-6.8%), EVENT 腿保留约 89%(OOS)
# 作用范围: **仅 EVENT 腿**(paper_sim EVENT 筛选链); CONT 腿 rank 恒=3 不经该门槛。
# 关键纪律(勿忘): 回测口径 7 特征 ≠ 生产口径 9 特征(R38w), 故本门槛必须用
#   **生产 rank_score**(含增持占比≥1% / 金额≥1亿 两项)判定 —— paper_sim 正是该口径。
#   若将来回测/生产特征集再变动, 需重跑 r38_rank_chain.py 重定阈值(勿照搬 3)。
# 回滚: 设 SMC_EVENT_RANK_GATE_MIN=0 即刻恢复旧行为(无需改代码)。
try:
    EVENT_RANK_GATE_MIN = int(os.environ.get("SMC_EVENT_RANK_GATE_MIN", "3"))
except ValueError:
    EVENT_RANK_GATE_MIN = 3
if EVENT_RANK_GATE_MIN < 0:
    EVENT_RANK_GATE_MIN = 0

# ---- 弱市加权（2026-09-08 regime 发现正向应用 → 2026-09-08 WF 复核后禁用）----
# 事件腿为逆向策略: 弱市(proxy<0)信号质量最高(avg+6.6%/PF6.6 vs 强市+1.3%)。
# 启用历史: A/B 双段(OOS+IS) k=2/4/8 单调提升风险调整收益(b4d8e35)。
# 禁用决策(V2 R10, 2026-09-08): 两次 Walk-Forward 滚动复核(混合口径 V1迭代4 + 纯净口径 R10)
#   均显示 k 无滚动稳健性——纯净 8 窗中 k=2 从未被选中(5 窗选 k=1, 3 窗选 k=3),
#   WF 累计净值 选择k=1.0499 ≈ 固定k=1 1.0497(+0.02%差异, 噪声级)。
#   IS 单调性证据是样本内拟合; WF 滚动证据不足 → 按研究纪律(蓝图 §71/§94)禁用生产,
#   保留研究开关与代码路径供后续 Regime 真值层(V2 迭代 6)重建后再验证。
WEAK_MARKET_WEIGHT = False         # 总开关(WF 不稳健 → 禁用, 2026-09-08)
WEAK_MARKET_K = 2.0                # 加权系数: w = clip(1 - k×proxy, 0.3, 2.0)
WEAK_MARKET_W_MIN = 0.3            # 最小权重(强市降仓下限)
WEAK_MARKET_W_MAX = 2.0            # 最大权重(弱市加仓上限)

# ---- R108 (goal round 19): v23_v2 狠打影子 → 生产挂单权重桥 (复盘日决定) ----
# 等权 v24 v1 生产 挂单从 R70 起只打 v23 (旧 pivot=3 链 + 非自适应 enrich).
# R94/R101 已完毕 v2 全链凭据: 2024段 PF +1.01 / 2026 OOS PF +0.32, 分股权翼健康.
# 本 flag 只在 2026-10-23 复盘后判定 v1(/audit 中"未召升") 才切换;
# 默认 False (不发生生产 推动 / 决策), True 时 paper_sim._v23v2_of 的狠打公式会
# 计 算被入生产 order 使的 stack — 外置: 不改默认, 需用户亲和并确认.
V23_V2_AS_PRODUCER = _env_bool("SMC_V23V2_AS_PRODUCER", False)

