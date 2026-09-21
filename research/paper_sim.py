# -*- coding: utf-8 -*-
"""模拟交易引擎（paper_sim.py）— 替代固定持有的模拟挂单系统
用户需求：
- 选股（每日0点触发扫描）→ 纳入挂单观察
- 模拟挂单：entry 目标价，实时监控（约1分钟更新实时价格）
  - 价格达到 entry（≤entry）→ 直接算已买入（FILLED）
  - 价格高于 entry（未回落）→ 挂单不生效（EXPIRED）
- 成交后：实时检查 TP/SL，触发则卖出（CLOSED）
- 前端显示：信号组合/信号日期/触发条件/TP/SL/状态；点击跳转 K 线

字段：code,name,signal_combo,signal_date,trigger,entry_price,tp_price,sl_price,
      status(PENDING_ORDER/FILLED/CLOSED/EXPIRED),filled_price,filled_at,exit_reason,pnl_pct
"""
import io, json, os, sys, time, urllib.request
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import config as CFG
from core.time_cn import cn_now, cn_today  # R21(第八轮 P1-11): 上海时区时间单源  # 审计 P1: 统一路径/参数

ROOT = CFG.RESEARCH_DIR
KT = CFG.KT_CACHE
LEDGER = CFG.LEDGER
# FIX(2026-08-22): auto-sync to frontend mirrors on every save
MIRRORS = [os.path.join(m, "paper_ledger.json") for m in CFG.MIRROR_DIRS]
UA = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)", "Referer": "https://finance.sina.com.cn/"}
PIVOT = 3
FEE = CFG.FEE_PCT
# FIX(2026-09-04, 策略层): 撮合加滑点（买入上浮 0.1%、卖出下浮 0.1%），
# 消除"无滑点"造成的纸面收益系统性高估（审计发现）。
SLIPPAGE = CFG.SLIPPAGE  # 0.1% 单边


def load_ledger():
    """读取账本。FIX(2026-09-04, P0): 解析失败返回 [] 会让主流程用空账本覆盖全部持仓。
    语义：文件不存在（首次运行）→ 返回 []；文件存在但解析失败 → 抛异常（保留原文件待人工恢复）。"""
    if not os.path.exists(LEDGER):
        return []
    try:
        with open(LEDGER, encoding="utf-8") as fh:
            data = json.load(fh)
        if not isinstance(data, list):
            raise ValueError("账本格式错误（应为 list）")
        return data
    except Exception as e:
        # 保留损坏文件以便人工恢复，绝不静默返回 []
        raise RuntimeError(f"paper_ledger.json 读取/解析失败，已保留原文件待人工恢复: {e}") from e


def _atomic_write_json(path, obj):
    """原子写：先写临时文件再 os.replace，避免中途被杀产生半截 JSON。"""
    import tempfile
    d = os.path.dirname(path)
    os.makedirs(d, exist_ok=True)
    fd, tmp = tempfile.mkstemp(prefix=".ledger_", suffix=".tmp", dir=d)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            json.dump(obj, fh, ensure_ascii=False, indent=2)
            fh.flush()
            os.fsync(fh.fileno())
        os.replace(tmp, path)
    except Exception:
        try:
            os.unlink(tmp)
        except Exception:
            pass
        raise


def save_ledger(led):
    """FIX(2026-09-04, P0): 原子写主文件 + 镜像；任一镜像失败不阻断主流程但告警。"""
    _atomic_write_json(LEDGER, led)
    # FIX(2026-08-22): auto-sync to frontend mirrors (was only main file — frontend showed stale data)
    for _m in MIRRORS:
        try:
            _atomic_write_json(_m, led)
        except Exception as e:
            print(f"镜像同步失败(继续): {_m}: {e}", flush=True)


# ---------- realtime price (Sina) ----------
def realtime_prices(codes):
    """Fetch realtime current prices for codes (up to ~50 per request).
    FIX(2026-09-04, 审计 P2): 返回 {code: {"px": 当前价, "prev": 昨收, "vol": 成交量(股)}}，
    供涨跌停/停牌判断；旧调用方取 .get(code) 仍得到价格（兼容）。"""
    syms = []
    for c in codes:
        # FIX(2026-09-13, 第八轮审计 P1-12): 交易所前缀映射 —— 原"非6即sz"把北交所
        # (4/8/9开头, Sina 前缀 bj)错误映射为 sz。当前 K 线缓存无北交所股票(数据源
        # 不覆盖, 见 bars_of), 实际影响 0 只; 修复为防御性正确实现。
        if c.startswith("6"):
            ex = "sh"
        elif c.startswith(("4", "8", "9")) and len(c) == 6:
            ex = "bj"
        else:
            ex = "sz"
        syms.append(ex + c)
    out = {}
    for i in range(0, len(syms), 50):
        batch = syms[i:i + 50]
        url = "https://hq.sinajs.cn/list=" + ",".join(batch)
        req = urllib.request.Request(url, headers=UA)
        try:
            with urllib.request.urlopen(req, timeout=15) as r:
                b = r.read().decode("gbk", errors="replace")
            for line in b.strip().split("\n"):
                if "hq_str_" not in line:
                    continue
                parts = line.split('="', 1)
                sym = parts[0].split("_")[-1]
                vals = parts[1].rstrip('";').split(",")
                if len(vals) > 5 and vals[3]:
                    try:
                        _px = float(vals[3])
                        _prev = float(vals[2]) if len(vals) > 2 and vals[2] else 0.0
                        _vol = float(vals[8]) if len(vals) > 8 and vals[8] else 0.0
                        # FIX(2026-09-05, 审计 G05): 返回今开 open（vals[1]），供 next_open 实时成交
                        _open = float(vals[1]) if len(vals) > 1 and vals[1] else 0.0
                        # FIX(2026-09-13, 第七轮审计 P0-2): 透传当日 high/low（vals[4]/vals[5]），
                        # 供 try_exit 盘中触发判定 —— 修复"只看当前价遗漏盘中 TP/SL 触发"，
                        # 使实时纸面与日线回测的 OHLC 触发语义一致（盘中触过即算，不看当前价回落）。
                        _high = float(vals[4]) if len(vals) > 4 and vals[4] else 0.0
                        _low = float(vals[5]) if len(vals) > 5 and vals[5] else 0.0
                        # FIX(2026-08-22): skip 0.00 prices (Sina off-hours / failure) — don't return 0
                        if _px > 0:
                            # FIX(2026-09-14, R34): 报价日期 vals[30]("YYYY-MM-DD") ——
                            # 快照新鲜度守卫的判据: 盘中当日快照 date==cn_today();
                            # 盘后/休市 Sina 返回上一交易日日期。R27 事故根因即
                            # "无日期判据只能依赖滞后日历" —— 此字段使撮合前可用
                            # 真数据验证新鲜度(替代 is_td(今天) 的结构性误判)。
                            _dt_str = vals[30] if len(vals) > 30 and vals[30] else ""
                            out[sym[2:]] = {"px": _px, "prev": _prev, "vol": _vol, "open": _open,
                                            "high": _high, "low": _low, "date": _dt_str}
                    except Exception:
                        pass
        except Exception:
            pass
    return out


def _is_suspended(px_info):
    """停牌判定：Sina 成交量=0 视为停牌/无成交（跳过撮合）。
    FIX(2026-09-04, 审计 P2): 停牌无法买卖，不应按停牌价成交。"""
    vol = (px_info or {}).get("vol")
    return vol == 0


def _is_limit_up(px_info, side="buy", code=None):
    """涨跌停判定 —— FIX(2026-09-08, 审计 P0-5): 统一委托 core.execution.is_limit_up
    （按板块/代码区分主板10% / 创业板/科创20% / 北交所30%），删除手写 10% 主板简化。
    兼容旧调用：未传 code 时按主板 10% 处理（保持安全默认）。"""
    from core.execution import is_limit_up as _core_limit
    return _core_limit(px_info, side=side, code=code)


# ---------- kline helpers (for structure SL/TP) ----------
def sub_signals_event(bs, i, sig_date):
    """Event-leg sub-signals: 阶段确认日 / ADX≥20 确认日 / 披露日 / 入场日."""
    dates = [b["t"] for b in bs]
    subs = [{"name": "披露日(增持/回购)", "date": sig_date, "detail": "内部人公告：增持/回购披露"}]
    # stage confirm: first day in 60d window with 60d ret<0 (ACCUM/DOWNTREND base)
    if i >= 61:
        for k in range(max(60, i - 20), i + 1):
            w60 = bs[k - 60:k]
            if w60[-1]["c"] / w60[0]["c"] - 1 < 0:
                subs.append({"name": "吸筹阶段确认", "date": dates[k], "detail": "60日下跌(ACCUM/DOWNTREND 阶段)"})
                break
    # ADX>=20 confirm
    if i >= 30:
        for k in range(max(30, i - 10), i + 1):
            a = adx14_of(bs, k)
            if a is not None and a >= 20:
                subs.append({"name": "ADX≥20 确认", "date": dates[k], "detail": f"趋势强度 ADX={a:.0f}"})
                break
    subs.append({"name": "入场(T+1)", "date": dates[i + 1] if i + 1 < len(bs) else sig_date, "detail": "次日开盘买入"})
    return subs


def sub_signals_cont(bs, entry_idx, support_date):
    """Continuation-leg sub-signals: MARKUP 确认 / 支撑回踩 / VWAP≥10% / 入场.
    FIX(2026-09-04, 审计 P2): VWAP 阈值统一为 10%（与生产回测/文档一致；
    研究确认 VWAP10% = +8.56% 优于 5%，p2_cont_refresh/gen_cont_v20f 均为 10%）。"""
    dates = [b["t"] for b in bs]
    subs = []
    # MARKUP confirm (60d ret>0.2 + vol ratio>1.1)
    for k in range(max(60, entry_idx - 15), entry_idx + 1):
        w60 = bs[k - 60:k]
        if len(w60) < 60:
            continue
        ret60 = w60[-1]["c"] / w60[0]["c"] - 1
        v20 = sum(x["v"] for x in bs[k - 20:k]) / 20
        v60 = sum(x["v"] for x in bs[k - 60:k]) / 60
        if ret60 > 0.2 and (v20 / v60 if v60 else 1) > 1.1:
            subs.append({"name": "MARKUP 确认", "date": dates[k], "detail": f"60日+{ret60*100:.0f}% 放量拉升"})
            break
    if support_date:
        subs.append({"name": "结构支撑回踩", "date": support_date, "detail": "回踩 swing low 支撑后收回"})
    # VWAP>=10%（生产口径，与回测一致）
    for k in range(max(20, entry_idx - 10), entry_idx + 1):
        pv = sum(bs[j]["c"] * bs[j]["v"] for j in range(k - 19, k + 1))
        vol = sum(bs[j]["v"] for j in range(k - 19, k + 1))
        if vol > 0:
            vw = pv / vol
            if (bs[k]["c"] - vw) / vw >= 0.10:
                subs.append({"name": "VWAP≥10% 确认", "date": dates[k], "detail": "强趋势偏离 VWAP"})
                break
    subs.append({"name": "入场(次日开盘)", "date": dates[entry_idx], "detail": "开盘买入 固定10日"})
    return subs


def stage_and_deep(bs, i):
    """FIX(2026-09-05, 审计 F14): 引用 core.structure（消除重复实现）。"""
    return _csd(bs, i)


def stage_and_deep_quantile(bs, i):
    """FIX(2026-09-05, 审计 F12/F14): 分位化阶段，引用 core.structure。"""
    return _csdq(bs, i)


def weekly_trend_of(bs, i):
    """FIX(2026-09-05, 审计 P3/F14): 自然周趋势，引用 core.structure。"""
    return _cwt(bs, i)




# FIX(2026-08-22) 审计: 全市场代理（200 只采样 20 日平均涨跌）—— 弱市是抄底甜蜜区，强市(proxy>2%)事件无 alpha
_MKT_SAMPLE = None
_MKT_PROXY_CACHE = {}

def _market_proxy(code, d8=None):
    """计算给定股票 signal 日期的市场状态（200 只采样 20 日平均涨跌，决策时点可得）。
    FIX(2026-09-04, 审计 P2):
      ① 采样快照落盘 hermes/kline_cache_tencent/.mkt_sample.json —— 避免每个新交易日重读 200 个 JSON；
      ② 标注幸存者偏差：采样来源是"当前缓存中存在 K 线"的股票（退市/长期停牌股无数据被排除），
         因此 proxy 存在正向幸存者偏差，仅作相对强弱参考，不做绝对市场判断。
    FIX(2026-09-13, 第八轮审计 5.6): 显式 signal 日期参数 —— 原实现 d8=dates[-1]
    (该股最新数据日), 历史事件被"当前最新市场状态"重新赋权, 时间口径错误
    (审计 §5.6: "同一股票的历史事件可能被当前最新市场状态重新赋权")。
    调用方应传事件 signal 日; 缺省 None 时保持旧行为(最新日, 兼容监控路径
    的当日 mark-to-market 场景)。"""
    global _MKT_SAMPLE, _MKT_PROXY_CACHE
    bs = bars_of(code)
    if not bs:
        return None
    dates = [b["t"] for b in bs]
    if not dates:
        return None
    # R16(第八轮 5.6): 显式 signal 日优先; 缺省回退最新日(监控 mark-to-market 场景)
    d8 = d8 or dates[-1]
    if d8 not in dates:
        return None  # signal 日不在该股 K 线中(如长期停牌) → 无环境分数, 不用错日替代
    # R16(第八轮 5.6): 缓存键= d8(市场日) —— 采样是全市场 200 只同一日的截面,
    # 结果只依赖 d8, 不依赖 code; (code,d8) 查询统一退化为 d8。
    if d8 in _MKT_PROXY_CACHE:
        return _MKT_PROXY_CACHE[d8]
    # FIX(2026-09-13, 第八轮 6.5): 引用 CFG.KT_CACHE(SMC_DATA_ROOT 环境变量优先) —— 原硬编码绝对路径
    kt = CFG.KT_CACHE
    snap = os.path.join(kt, ".mkt_sample.json")
    if _MKT_SAMPLE is None:
        # 优先读固定快照（跨进程/跨日稳定），无则采样一次并落盘
        try:
            _snap = json.load(open(snap, encoding="utf-8"))
            if isinstance(_snap, list) and _snap:
                _MKT_SAMPLE = _snap
        except Exception:
            pass
        if _MKT_SAMPLE is None:
            import random
            random.seed(42)
            files = sorted(f for f in os.listdir(kt) if f.endswith("_daily_800.json"))
            _MKT_SAMPLE = random.sample(files, min(200, len(files)))
            try:
                json.dump(_MKT_SAMPLE, open(snap, "w", encoding="utf-8"), ensure_ascii=False)
            except Exception:
                pass
    rets = []
    for f in _MKT_SAMPLE:
        try:
            raw = json.load(open(os.path.join(kt, f), encoding="utf-8"))
            b2 = []
            for r in raw:
                t = "".join(c for c in str(r.get("t") or "") if c.isdigit())[:8]
                if t and r.get("o") and r.get("c"):
                    b2.append({"t": t, "c": float(r["c"])})
            b2.sort(key=lambda x: x["t"])
            ds = [x["t"] for x in b2]
            if d8 not in ds:
                continue
            i = ds.index(d8)
            if i < 20:
                continue
            rets.append(b2[i]["c"] / b2[i - 20]["c"] - 1)
        except Exception:
            continue
    v = sum(rets) / len(rets) if rets else None
    _MKT_PROXY_CACHE[d8] = v
    return v


# FIX(2026-08-28): 自适应持有期 —— 按市场状态（proxy）调整：
# 反弹市(proxy>2%) 持20日（研究 +12.22% 最长最优）
# 震荡市(-2%~2%) 持12日（研究 10-15 最优区间）
# 弱市(proxy<-2%) 持20日（研究 20日略好）
def adaptive_hold(base_hold=10, proxy=None):
    if proxy is None:
        return base_hold
    if proxy > 0.02:
        return 20
    if proxy < -0.02:
        return 20
    return 12


def adx14_of(bs, i):
    """R22(第八轮审计 P1-7): ADX 单源化 —— 实现迁移 core/indicators.py
    (审计: "把 ADX 放进 core/indicators.py, 回测和生产只调用一个实现"),
    本函数保留为兼容入口(内部调用点不动), 语义与 2026-09-12 Wilder 修复版
    逐位一致(golden fixtures 锁定)。任何新代码应直接 import
    core.indicators.adx14_of。"""
    from core.indicators import adx14_of as _adx_core
    return _adx_core(bs, i)


def bars_of(code):
    # FIX(2026-09-13, 第八轮审计 P1-12): 腾讯缓存命名 SH/SZ 双前缀 —— 北交所
    # (4/8/9开头)不在该缓存(数据源边界), 显式返回空而非误读 SZ 文件名。
    if code.startswith(("4", "8", "9")) and len(code) == 6:
        return []
    ex = "SH" if code.startswith("6") else "SZ"
    p = os.path.join(KT, f"{code}_{ex}_daily_800.json")
    if not os.path.exists(p):
        return []
    raw = json.load(open(p, encoding="utf-8"))
    bs = []
    for x in raw:
        t = "".join(c for c in str(x.get("t") or "") if c.isdigit())[:8]
        if t and x.get("o") and x.get("c"):
            # FIX(2026-08-20 audit): include volume 'v' — stage/量能 indicators require it
            try:
                v = float(x.get("v") or 0)
            except Exception:
                v = 0
            bs.append({"t": t, "o": float(x["o"]), "h": float(x["h"]), "l": float(x["l"]), "c": float(x["c"]), "v": v})
    bs.sort(key=lambda b: b["t"])
    return bs


# FIX(2026-09-05, 审计 F14): 结构/阶段统一引用 core.structure（消除重复实现）
from core.structure import (is_swing_high as _csh, is_swing_low as _csl,
                            stage_and_deep as _csd, stage_and_deep_quantile as _csdq,
                            weekly_trend_of as _cwt)


def _chain_of(bs, i):
    """R60: 信号链快照(软失败置空, 绝不阻断选股) — 单源 core/chain.build_chain"""
    try:
        from core.chain import build_chain as _bc
        return _bc(bs, i)
    except Exception:
        return {}


def _alpha_of(chain, stage):
    """R61: Jensen Alpha 期望(软失败 None) — 单源 core/alpha, PF后验基准"""
    try:
        from core.alpha import alpha_expect as _axp
        return _axp(chain, stage)
    except Exception:
        return None


# R64(用户指令: 外挂判断模型 Jev(TypeSafe System One)) — 影子判断, 不做决策
_JEV_QUESTIONS = {
    "executable_now": {"type": "noul",
                       "instructions": "仅根据给出的结构化交易信号状态, 这笔A股事件驱动买入挂单此刻是否值得"
                                        "执行(仅信号质量, 不考虑大盘)?"},
    "event_kind": {"type": "choice",
                   "instructions": "该事件最接近以下哪种 SMC 叙事?",
                   "criteria": {"bottom_accumulation": "内部人增持/回购出现在低位区(Downtrend末端), 主力吸筹含义",
                                "markup_retrace": "已有上涨趋势后回踩结构支撑, 趋势延续含义",
                                "false_signal": "结构/叙事与价位矛盾, 假信号风险",
                                "unclear": "信息不足以归类"}},
    "expected_excess": {"type": "score",
                        "instructions": "未来2周内该笔交易相对市场(等权组合)的超额收益预期区间?",
                        "criteria": ["负超额(大概率跑输)", "无显著超额", "小幅正超额(+0~3%)", "显著正超额(+3%以上)"]},
}
_JEV_LOG = os.path.join(os.path.dirname(os.path.abspath(__file__)), "jev_shadow_log.jsonl")


def _jev_of(order, chain):
    """R64: Jev 影子判断(软失败 None, 绝不阻断; 若 key 未设直接 None)"""
    if not os.environ.get("TYPESAFE_API_KEY"):
        return None
    try:
        from core.jev_client import judge_verbose
        st = {"code": order.get("code"), "signal_combo": order.get("signal_combo"),
              "signal_date": order.get("signal_date"), "entry_price": order.get("entry_price"),
              "stage": order.get("stage"), "v_ratio": order.get("v_ratio"),
              "rank_score": order.get("rank_score"), "alpha_expect": order.get("alpha_expect"),
              "sub_signals": [s.get("name") for s in (order.get("sub_signals") or [])][:6],
              "trigger": order.get("trigger"),
              "chain": {"trend": (chain or {}).get("trend_state"),
                        "breakout": (chain or {}).get("breakout"),
                        "retrace_state": ((chain or {}).get("retrace") or {}).get("state")}}
        ans = judge_verbose(st, _JEV_QUESTIONS)
        a = (ans or {}).get("answers") or {}
        out = {"p_executable": a.get("executable_now", {}).get("noul"),
               "event_kind": a.get("event_kind", {}).get("choice"),
               "event_kind_conf": a.get("event_kind", {}).get("confidence"),
               "excess_score": a.get("expected_excess", {}).get("score"),
               "excess_conf": a.get("expected_excess", {}).get("confidence"),
               "model": (ans or {}).get("model"),
               "date": datetime.date.today().isoformat()}
        # 影子日志(jsonl): 瞳孔采样, 供后续本地校准
        try:
            with open(_JEV_LOG, "a", encoding="utf-8") as fh:
                fh.write(json.dumps({"code": order.get("code"), "date": out["date"],
                                     "signal_combo": order.get("signal_combo"), **out},
                                    ensure_ascii=False) + "\n")
        except Exception:
            pass
        return out
    except Exception:
        return None


def is_swing_high(bs, j):
    return _csh(bs, j, PIVOT)


def is_swing_low(bs, j):
    return _csl(bs, j, PIVOT)


def structural_sltp(code, signal_date, src='EVENT', stage='DOWNTREND', adx=0.0):
    """SMC 策略化结构分层 TP/SL —— 锚点指标按信号类型/行为阶段动态选择（非固定映射）。

    策略逻辑：
    - EVENT 腿（反转/吸筹）：
      · ACCUM（底部吸筹）：大资金建仓区 → TP 用"结构恢复"锚点（近 swing high → FVG → 前高/BSL），
        SL 用"扫损容忍"（事件前 swing low，给吸筹波动空间）
      · DOWNTREND（下跌反弹）：超卖反弹 → TP 用"反弹目标"（近 swing high → FVG），
        SL 用"快速结构"（最近 swing low，跌破即反弹失败）
    - CONT 腿（趋势延续）：
      · MARKUP（拉升）：趋势维护 → TP 用"延续目标"（BOS 后前高 → 流动性池），
        SL 用"回踩支撑"（结构支撑下沿，窄止损）
    - 高 ADX（强趋势）→ TP 偏远端流动性（BSL/60日前高），SL 仍结构（近）；
      低 ADX（震荡）→ TP 偏近端（swing high/FVG），避免目标太远达不到。

    返回 (tp1, tp2, tp3, tp4, sl1, sl2, anchor_note) —— anchor_note 说明每个位置用什么指标"""
    bs = bars_of(code)
    dates = [b["t"] for b in bs]
    if signal_date not in dates:
        prev = [d for d in dates if d < signal_date]
        if not prev:
            return None, None, None, None, None, None, ""
        i = dates.index(prev[-1])
    else:
        i = dates.index(signal_date)
    highs = []
    lows = []
    _sig_close = bs[i]["c"] if i < len(bs) else 0
    # FIX(2026-09-05, 审计 G07): 摆动点须在 signal 日(i)前确认 —— j + PIVOT <= i，
    # 原 is_swing_high(bs,j) 需要 j+1..j+3 即 i,i+1,i+2 的未来K（前视，与回测 gen_v20f 不同）
    # 另：highs 只保留 > 信号收盘的结构位（TP 锚点必须在入场价上方，避免 tp1 < 入场价）
    for j in range(i - 1, max(0, i - 60), -1):
        if j + PIVOT > i:
            continue  # 尚未确认（需 j 右侧 PIVOT 根收完）
        if len(highs) < 4 and is_swing_high(bs, j) and bs[j]["h"] > _sig_close:
            highs.append(bs[j]["h"])
        if len(lows) < 3 and is_swing_low(bs, j):
            lows.append(bs[j]["l"])
        if len(highs) >= 4 and len(lows) >= 3:
            break
    if not highs or not lows:
        return None, None, None, None, None, None, ""
    highs.sort()  # ascending price: highs[0]=nearest, highs[-1]=60d high
    # FVG anchors (bullish top / bearish bottom within 20 bars before signal)
    fvg_tops = [bs[k]["l"] for k in range(max(2, i - 20), i) if bs[k]["l"] > bs[k - 2]["h"] and bs[k]["l"] > highs[0]]
    fvg_bots = [bs[k]["h"] for k in range(max(2, i - 20), i) if bs[k]["h"] < bs[k - 2]["l"] and bs[k]["h"] < lows[0] * 0.99]
    fvg_top = min(fvg_tops) if fvg_tops else None
    fvg_bot = min(fvg_bots) if fvg_bots else None

    strong = adx >= 30  # strong trend → far liquidity targets

    # FIX(2026-08-22) P1: SL 重设 —— sweep low − 0.5×ATR（A股可执行，避免裸 swing low 超跌停不可触及）
    _atr = 0
    if i >= 15:
        _trs = []
        for k in range(i - 14, i):
            _tr = max(bs[k]["h"] - bs[k]["l"], abs(bs[k]["h"] - bs[k - 1]["c"]), abs(bs[k]["l"] - bs[k - 1]["c"]))
            _trs.append(_tr)
        _atr = sum(_trs) / 14 if _trs else 0

    # --- strategy-based anchor selection ---
    if src == 'CONT' and stage in ('MARKUP', 'UPTREND'):
        # continuation: trend targets; tight SL on support
        tp1 = highs[0] if highs[0] > 0 else None
        tp2 = fvg_top if fvg_top and fvg_top > (tp1 or 0) else (highs[1] if len(highs) > 1 else None)
        tp3 = highs[2] if len(highs) > 2 else None      # prior high = BSL pool
        tp4 = highs[-1] if strong else (highs[2] if len(highs) > 2 else None)  # far target only if strong
        sl1 = (lows[0] - 0.5 * _atr) if _atr > 0 else lows[0] * 0.99
        sl2 = fvg_bot if fvg_bot else (min(lows) * 0.97 if len(lows) > 1 else sl1 * 0.95)
        note = "延续:TP1=最近swing高 TP2=FVG上沿 TP3=前高/BSL TP4=60日前高(强趋势) | SL1=支撑−0.5ATR SL2=FVG下沿"
    elif stage == 'ACCUM':
        # bottom accumulation: structural recovery targets; wider SL tolerance
        tp1 = highs[0]
        tp2 = fvg_top if fvg_top else (highs[1] if len(highs) > 1 else None)
        tp3 = highs[2] if len(highs) > 2 else None      # BSL pool
        tp4 = highs[-1] if strong else None             # far liquidity target if strong trend
        sl1 = (lows[0] - 0.5 * _atr) if _atr > 0 else lows[0] * 0.99
        sl2 = min(lows) * 0.97 if len(lows) > 1 else sl1 * 0.95
        note = "ACCUM:TP1=最近swing高(恢复) TP2=FVG上沿 TP3=前高/BSL TP4=60日前高(强趋势) | SL1=事件前swing低−0.5ATR SL2=深层(容忍吸筹)"
    else:
        # DOWNTREND rebound: near rebound targets; fast structural SL
        tp1 = highs[0]
        tp2 = fvg_top if fvg_top else (highs[1] if len(highs) > 1 else None)
        tp3 = highs[2] if len(highs) > 2 else None
        tp4 = highs[-1] if strong else None
        sl1 = (lows[0] - 0.5 * _atr) if _atr > 0 else lows[0] * 0.99
        sl2 = fvg_bot if fvg_bot else (min(lows) * 0.97 if len(lows) > 1 else sl1 * 0.95)
        note = "DOWNTREND:TP1=最近swing高(反弹) TP2=FVG上沿 TP3=前高 TP4=60日前高(强趋势) | SL1=swing低−0.5ATR SL2=FVG下沿/深层"

    return tp1, tp2, tp3, tp4, sl1, sl2, note


# ---------- selection (daily 0:00 trigger) ----------
def _next_td(dates, d8):
    """FIX(2026-09-05, 审计 G05/G09): signal_date(d8) 之后第一个交易日（T+1 可成交日）。
    FIX(2026-09-08, 审计 P0-2): 当 d8 是当前最后交易日（今日刚披露、明日K线尚未生成）时，
    不能再返回 d8 自身，否则 monitor 会把"今日"当成可成交日提前撮合。
    退化为按周末日历推算下一交易日（A股休市以周六/周日为主，节假日由数据源对齐）；
    有可用 K 线日期则优先用其映射。"""
    from datetime import date, timedelta
    if d8 in dates:
        idx = dates.index(d8)
        if idx + 1 < len(dates):
            return dates[idx + 1]
        # d8 是当前数据最后交易日（今日刚披露、明日K线尚未生成）→ 按日历推下一交易日
        # FIX(2026-09-13, 第八轮审计 P1-11): 优先 core.trading_calendar(节假日对齐),
        # 原纯周末循环在法定节假日(春节/国庆)会把假日误判为 T+1。
        if d8 == dates[-1]:
            try:
                from core.trading_calendar import next_td
                _nt = next_td(d8)
                if _nt:
                    return _nt
            except Exception:
                pass
            try:
                d = date(int(d8[:4]), int(d8[4:6]), int(d8[6:8]))
                for _ in range(8):  # 最多推进 8 天必然遇到工作日
                    d += timedelta(days=1)
                    if d.weekday() < 5:  # 周一~周五
                        return d.strftime("%Y%m%d")
            except Exception:
                pass
        return d8
    # signal_date 不在 K 线中（公告日非交易日）→ 取之后第一个交易日
    # FIX(2026-09-13, 第八轮审计 P1-11): 无未来 K 线可用时(新上市/数据未更新),
    # 原回退返回 d8 自身(可能是周末/节假日公告日) → 改为优先 core.
    # trading_calendar.next_td(数据源对齐节假日, 全市场 4662 只聚合),
    # 日历不可用再退周末规则 —— 消除"公告日非交易日被当成 T+1"的节假日错判。
    _future = next((x for x in dates if x > d8), None)
    if _future:
        return _future
    try:
        from core.trading_calendar import next_td
        _nt = next_td(d8)
        if _nt:
            return _nt
    except Exception:
        pass
    return d8


def _parse_insider_magnitude(title):
    """FIX(2026-09-05, 审计 F17): 从公告标题解析增持/回购规模（金额、股数、占总股本比）。
    返回 (amount_wan, shares_wan, pct, raw_hint)。解析失败返回 (None,None,None,'')。
    A股公告常见格式："增持公司股份约 1.2亿元" / "增持 500万股，占总股本 0.35%" /
    "回购金额不低于 3亿元不超过 5亿元" / "增持比例达到 1%"。
    """
    import re
    s = str(title or "")
    amount = None
    shares = None
    pct = None
    # 金额：X亿元 / X万元（取首个明确数值）
    m = re.search(r"([0-9]+(?:\.[0-9]+)?)\s*亿(?:元)?", s)
    if m:
        amount = float(m.group(1)) * 10000  # 万元
    else:
        m = re.search(r"([0-9]+(?:\.[0-9]+)?)\s*万(?:元)?", s)
        if m:
            amount = float(m.group(1))
    # 股数：X万股 / X亿股
    m = re.search(r"([0-9]+(?:\.[0-9]+)?)\s*万(?:股)?", s)
    if m:
        shares = float(m.group(1))  # 万股
    else:
        m = re.search(r"([0-9]+(?:\.[0-9]+)?)\s*亿(?:股)?", s)
        if m:
            shares = float(m.group(1)) * 10000
    # 占比：X% / 达到 X% / 占总股本 X%
    m = re.search(r"([0-9]+(?:\.[0-9]+)?)\s*%", s)
    if m:
        pct = float(m.group(1))
    hint = []
    if amount:
        hint.append(f"金额≈{amount:.0f}万")
    if shares:
        hint.append(f"股数≈{shares:.0f}万")
    if pct:
        hint.append(f"占比{pct:.2f}%")
    return amount, shares, pct, " ".join(hint)

# ---------- reject ledger (第七轮审计 §9.2 被拒候选前向收益追踪, R5 2026-09-13) ----------
REJECT_LEDGER_FILE = os.path.join(ROOT, "reject_ledger.json")

def _tri_decompose(raw, hard, soft, soft_delta, skipped_stage, skipped_adx, nodata, dup, orders,
                   bad_sl=0, capacity=0):
    """审计§4.3 三分解: 无新股归因 = 源头供给 / 质量拒绝 / 容量拒绝(含数据缺失)。
    纯函数, tests_reject_ledger 覆盖守恒: raw = quality + data_missing + dup + bad_sl
    + capacity + orders。
    R8: bad_sl(sl>=entry 非法几何 fail-closed 拒单)计入 quality_reject
    (合同失败属于可修复质量问题, 非市场容量约束)。
    R15(第八轮审计 P1-9): capacity=PortfolioGate 组合拒绝(总暴露/单日/持仓上限/kill
    switch), 与策略质量拒绝分开 —— "组合 gate 拒绝不能与策略拒绝混淆"。"""
    quality = hard + soft + soft_delta + skipped_stage + skipped_adx + bad_sl
    return {
        "source_supply": raw,
        "quality_reject": quality,
        "data_missing": nodata,
        "execution_capacity": {"dup": dup, "portfolio_gate": capacity, "bad_sl": bad_sl,
                               "note": "portfolio_gate=组合容量拒绝(R15 接线: 总暴露≤0.8/单日≤5/持仓≤10/kill switch); dup=同股同日重复挂单去重; bad_sl=sl>=entry 非法几何 fail-closed 拒单(R8)"},
        "orders_created": orders,
        "conservation_note": "raw = quality_reject(分类+阶段+ADX+bad_sl) + data_missing + dup + portfolio_gate + orders",
    }

def _persist_rejects(records, root=None, cap=6000):
    """拒绝账本持久化: 按(code,date,stage)去重追加(阶段变迁允许新增记录), cap 保最近;
    原子写, 失败不阻断生产链。DUP_EXISTING 类已被主账本跟踪, 评估器跳过。"""
    try:
        fp = REJECT_LEDGER_FILE if root is None else os.path.join(root, "reject_ledger.json")
        try:
            prev = json.load(open(fp, encoding="utf-8"))
            if not isinstance(prev, list):
                prev = []
        except Exception:
            prev = []
        seen = {(r.get("code"), str(r.get("date", "")).replace("-", ""), r.get("stage")) for r in prev}
        ts = cn_now("%Y-%m-%d %H:%M:%S")
        for r in records:
            k = (r.get("code"), str(r.get("date", "")).replace("-", ""), r.get("stage"))
            if k in seen:
                continue
            seen.add(k)
            _r = dict(r)
            _r["date"] = k[1]
            _r["ts"] = ts
            prev.append(_r)
        if len(prev) > cap:
            prev = prev[-cap:]
        _atomic_write_json(fp, prev)
        return len(prev)
    except Exception as _e:
        print(f"拒绝账本写入失败(不阻断): {_e}", flush=True)
        return -1

def daily_selection():
    """Scan new insider events -> create PENDING_ORDER entries.
    entry price = disclosure day close (limit order: buy only at or below)."""
    # FIX(2026-09-13, 第八轮审计 P0-4): ENABLE_EVENT_LEG 开关接线 —— 原开关在
    # config 定义但事件循环无条件执行, 关闭 EVENT 腿仍会产生 EVENT 订单(审计 §1.2)。
    # 接线后: 开关关闭 → 跳过事件选股, 但不能阻断已启用的 CONT/SMC 腿。
    _event_enabled = bool(getattr(CFG, "ENABLE_EVENT_LEG", True))
    if not _event_enabled:
        _st = {"event_leg_disabled": True, "orders_created": 0,
               "note": "ENABLE_EVENT_LEG=False: 事件腿选股跳过(可审计/可回滚)"}
        print("[P0-4] ENABLE_EVENT_LEG=False → 事件腿选股跳过", flush=True)
        try:
            _atomic_write_json(os.path.join(CFG.OUTPUT_ROOT, "event_leg_status.json"), _st)
        except Exception:
            pass
        if not (getattr(CFG, "ENABLE_CONT_LEG", False) or getattr(CFG, "ENABLE_SMC_LEG", False)):
            return _st
    import sqlite3
    # FIX(2026-09-13, 第七轮审计 P1-5): 生产硬编码 → config.py 统一路径
    conn = sqlite3.connect(CFG.ANNOUNCE_DB)
    cur = conn.cursor()
    if _event_enabled:
        cur.execute("SELECT DISTINCT date FROM announce ORDER BY date DESC LIMIT 5")
        recent_days = [r[0] for r in cur.fetchall()]
    else:
        recent_days = []
    led = load_ledger()
    known = {(t["code"], t.get("signal_date", "")) for t in led}
    # also block codes already PENDING/FILLED for same signal date
    seen_orders = set()
    new_orders = []
    _sel_stats = {"scanned": 0, "selected": 0, "skipped_stage": 0, "skipped_adx": 0,
                  "skipped_strong": 0, "skipped_nodata": 0, "skipped_dup": 0}
    _skipped_detail = []  # FIX(2026-08-26): 跳过明细（代码/名称/原因）
    # FIX(2026-09-08, 复审 P1-4): 每股每日只记一个最终拒绝阶段（互斥/守恒证明）。
    # 分类: DATA_MISSING(无K线/无此日期) 与 STRATEGY_REJECT(阶段/ADX/去重) 分开计数。
    _reject_stage = {}  # {(code, dd): final funnel stage}
    _positive_keys = set()
    _event_order_count = 0
    _data_missing = 0   # 数据缺失单独计数（不计入策略拒绝）
    _reject_records = []  # R5(§9.2): 持久化拒绝记录(前向收益评估输入)

    def _mark_funnel(key, stage):
        """Keep one terminal state per positive event for a conservation audit."""
        _reject_stage.setdefault(key, stage)

    def _portfolio_gate(order):
        """One fail-closed gate shared by EVENT, CONT and SMC order creation."""
        try:
            from core.portfolio import portfolio_exposure_check, throttle_open, kill_switch as _ks
            # R35(第八轮审计, 行业上限数据源): sector_counts 接真实行业映射
            # (此前恒空 dict —— max_sector=3 门存在但无数据)。候选桶只计
            # live 条目(不含本单); UNKNOWN 不归桶(缺映射 fail-open, 不误杀)。
            from core.industry_map import sector_counts as _sector_counts, get_industry as _get_industry
            live = [t for t in led if t.get("status") in ("PENDING_ORDER", "FILLED")
                    and t is not order]
            positions = [{"code": t.get("code"),
                          "position_pct": float(t.get("position_pct") or 0.01)}
                         for t in live]
            positions.append({"code": order.get("code"),
                              "position_pct": float(order.get("position_pct") or 0.01)})
            ok_exposure, why_exposure, total = portfolio_exposure_check(positions)
            today = cn_now("%Y-%m-%d")
            # R37(2026-09-15, 000157 误拒复盘): ①行业门语义 = 候选股自己行业
            #   满桶才拒(V3-A DailyPortfolioEngine L308-313 同语义), 不传全行业
            #   桶(否则任一行业满 3 拒一切新开仓 —— 09:30:15 C39 桶=3(002655 重复
            #   条目×2+688035)误拒无关行业 C35 的 000157)。②单日新开数 =
            #   当日 bool 数而非全部条目数(len(daily_opens) 含 False 历史持仓,
            #   6 旧仓+本单=7≥5 恒触发 MAX_DAILY_OPEN)。
            day_opens = [t.get("created_at") == today for t in live] + [True]
            _cand_ind = _get_industry(order.get("code"))
            _cand_bucket = {_cand_ind: _sector_counts(
                [t.get("code") for t in live], exclude=order.get("code")).get(_cand_ind, 0)} \
                if _cand_ind != "UNKNOWN" else {}
            ok_throttle, why_throttle = throttle_open(day_opens, _cand_bucket, max_positions=10,
                                                       max_sector=3, max_daily_opens=5)
            recent = [float(t.get("pnl_pct") or 0) / 100 for t in live
                      if t.get("pnl_pct") is not None][-20:]
            kill_result = _ks(recent, window="daily")
            kill_on = kill_result[0] if isinstance(kill_result, tuple) else bool(kill_result)
            if not ok_exposure:
                return False, why_exposure, total
            if not ok_throttle:
                return False, why_throttle, total
            if kill_on:
                return False, "KILL_SWITCH", total
            return True, "OK", total
        except Exception as exc:
            return False, f"PORTFOLIO_GATE_ERROR:{exc}", 0.0

    for dd in recent_days:
        # FIX(2026-09-05, 审计 G25): 改为全量拉取增持/回购候选，Python 端用 core.events.classify_title
        # 统一过滤（否定词全集：终止/完毕/解除/…/减持/完成/进度/前十名，scanner 与 selection 同一套）
        cur.execute("SELECT stock_code, stock_name, title FROM announce WHERE date=? AND (title LIKE '%增持%' OR title LIKE '%回购%')", (dd,))
        for code, name, title in cur.fetchall():
            try:
                from core.events import classify_title
                _is_ev, _kind, _pol, _amt2, _pct2 = classify_title(title)
                if not _is_ev or _pol < 0:
                    _sel_stats["skipped_noise"] = _sel_stats.get("skipped_noise", 0) + 1
                    _reject_records.append({"code": code, "name": name, "date": dd, "stage": "EVENT_FILTER", "title": title[:80]})
                    continue
            except Exception as _classify_error:
                # Classification failure is an input-quality failure, not a
                # reason to treat an unknown title as a tradable event.
                _sel_stats["classify_error"] = _sel_stats.get("classify_error", 0) + 1
                _reject_records.append({"code": code, "name": name, "date": dd,
                                        "stage": "EVENT_CLASSIFY_ERROR",
                                        "error": str(_classify_error),
                                        "title": title[:80]})
                continue
            _sel_stats["scanned"] += 1
            d8 = str(dd).replace("-", "")
            _key = (str(code), str(dd))
            _positive_keys.add(_key)
            if (code, dd) in known or (code, dd) in seen_orders:
                _sel_stats["skipped_dup"] += 1
                _mark_funnel(_key, "DUP_EXISTING")
                _reject_records.append({"code": code, "name": name, "date": dd, "stage": "DUP_EXISTING", "title": title[:80]})
                continue
            seen_orders.add((code, dd))
            bs = bars_of(code)
            if not bs:
                _sel_stats["skipped_nodata"] += 1
                _data_missing += 1
                _mark_funnel(_key, "DATA_MISSING")
                _skipped_detail.append({"code": code, "name": name, "date": dd, "reason": "无K线数据"})
                _reject_records.append({"code": code, "name": name, "date": dd, "stage": "DATA_MISSING", "title": title[:80]})
                continue
            dates = [b["t"] for b in bs]
            if d8 not in dates:
                # FIX(2026-09-20, R45): 公告日=周末/节假日时 d8 不在 dates
                # 旧行为: 当无数据丢弃(14/44 中 31.8% 是由此而来)
                # 改为: 顺延到 d8 之前的最近交易日(盘面未开, 该收盘状态就是决策态),
                # 以 T+1=下个交易日的开盘为 entry。正确时序, 无前视。
                import bisect as _bisect
                _i0 = _bisect.bisect_left(dates, d8)  # 首个 >= d8 的位置
                if _i0 >= 1:
                    i = _i0 - 1  # 公告日之前的最后交易日 = 信号日
                    _sel_stats["rolled_weekend"] = _sel_stats.get("rolled_weekend", 0) + 1
                else:
                    _sel_stats["skipped_nodata"] += 1
                    _data_missing += 1
                    _mark_funnel(_key, "DATA_MISSING")
                    _skipped_detail.append({"code": code, "name": name, "date": dd, "reason": "K线无此日期(及之前)"})
                    _reject_records.append({"code": code, "name": name, "date": dd, "stage": "DATA_MISSING", "title": title[:80]})
                    continue
            else:
                i = dates.index(d8)
            # FIX(2026-08-22 audit): apply backtest-consistent quality filter
            # (ACCUM/DOWNTREND stage + ADX>=20 — combo-level test: ADX30 no combo gain, keep 20 for more samples)
            st, deep = stage_and_deep(bs, i)
            if st not in ("ACCUM", "DOWNTREND"):
                _sel_stats["skipped_stage"] += 1
                _mark_funnel(_key, f"STAGE_{st}")
                _skipped_detail.append({"code": code, "name": name, "date": dd, "reason": f"阶段={st}(非ACCUM/DOWNTREND)"})
                _reject_records.append({"code": code, "name": name, "date": dd, "stage": f"STAGE_{st}", "adx": adx14_of(bs, i), "title": title[:80]})
                continue
            adx = adx14_of(bs, i)
            if adx is None or adx < 20:
                _sel_stats["skipped_adx"] += 1
                _mark_funnel(_key, "ADX_LT20")
                _skipped_detail.append({"code": code, "name": name, "date": dd, "reason": f"ADX={adx}<20"})
                _reject_records.append({"code": code, "name": name, "date": dd, "stage": "ADX_LT20", "adx": adx, "title": title[:80]})
                continue
            close_px = bs[i]["c"]
            if close_px <= 0:
                _mark_funnel(_key, "BAD_CLOSE")
                _reject_records.append({"code": code, "name": name, "date": dd,
                                        "stage": "BAD_CLOSE", "title": title[:80]})
                continue
            # FIX(2026-08-22): event leg uses T+1 open price (market order, matching backtest)
            # FIX(2026-09-08, 审计 P0-2): 不再要求 T+1 K 线已存在。
            # 原 `entry_idx>=len(bs) -> continue` 会让"今日收盘后刚披露"的公告因明日K线尚未生成而整单跳过
            # （实盘信号天然滞后/漏选）。现改为：只要 signal 日(披露日收盘)可得即可生成挂单，
            # 成交价由 monitor 在 valid_from 日以实时 open 撮合，v_ratio 用信号日可得数据计算。
            entry_idx = i + 1
            adx_v = adx14_of(bs, i) or 0
            tp1, tp2, tp3, tp4, sl1, sl2, anchor_note = structural_sltp(code, d8, src='EVENT', stage=st, adx=adx_v)
            # FIX(2026-09-20, R52): 回退条件补 tp2/tp3 — ACCUM/DOWNTREND 分支在
            # len(highs)<=2 时 tp2/tp3=None, 旧守卫只查 tp1/tp4/sl1/sl2 → 到 round(tp3,3) 崩
            if tp1 is None or tp2 is None or tp3 is None or tp4 is None or sl1 is None or tp4 <= close_px or sl2 is None:
                tp1 = round(close_px * 1.03, 3)
                tp2 = round(close_px * 1.06, 3)
                tp3 = round(close_px * 1.10, 3)
                tp4 = round(close_px * 1.15, 3)
                sl1 = round(close_px * 0.96, 3)
                sl2 = round(close_px * 0.90, 3)
                anchor_note = "回退:固定比例(结构不足)"
            is_buyback = "回购" in str(title)
            sig = "BUYBACK_STRONG" if is_buyback else "HOLDER_INCREASE"
            # FIX(2026-09-13, R8 执行合同缺口): sl1 >= 挂单价 → fail-closed 拒单。
            # 审计§6.2: "sl >= entry 必须 fail-closed"; 但 R8 fill-level 回放发现
            # 生产账本 5/139 笔 sl1>=entry_price(DOWNTREND 反弹锚点在回踩价上方),
            # 回测 simulate 对此几何 BAD_ENTRY skip, 纸面却成交(4 笔 CLOSED 净值 -8.26pp)
            # —— 回测/纸面语义现行分裂实例。守卫消除分裂: 生产链同样拒单,
            # 拒绝入 reject ledger(quality_reject 类, 非源头稀缺), 不静默。
            # limit_px must be defined before this geometry gate.  The old order
            # raised UnboundLocalError exactly when a valid event reached it.
            limit_px = round(close_px * 0.99, 3)
            if sl1 is not None and sl1 >= limit_px:
                _sel_stats["skipped_bad_sl"] = _sel_stats.get("skipped_bad_sl", 0) + 1
                _mark_funnel(_key, "BAD_SL_GE_ENTRY")
                _reject_records.append({"code": code, "name": name, "date": d8,
                                        "stage": "BAD_SL_GE_ENTRY",
                                        "title": str(title)[:80]})
                continue
            subs = sub_signals_event(bs, i, dd)
            avg_v = sum(bs[k]["v"] for k in range(i + 1 - 20, i + 1)) / 20 if i + 1 >= 20 else 0
            # FIX(2026-09-08, 审计 P0-2): v_ratio 用披露日(决策时点)可得量 bs[i]["v"]，
            # 原 bs[entry_idx]["v"] 是 T+1 成交量 —— 实盘开盘前不可知，且今日披露时 entry_idx 尚不存在。
            v_ratio = round(bs[i]["v"] / avg_v, 2) if avg_v else 1.0
            # FIX(2026-08-22): 连续放量（大资金持续入场，研究 iter_vol_cont: 连续放量 +15.55%/PF 9.30）
            # FIX(2026-09-05, 审计 G22): v2_ratio 用 bs[i-1]（signal 日前一日量，决策时点可得），
            # 原 bs[entry_idx+1] 是未来量（T+2）→ 与回测 gen_v20f 口径不一致
            v2_ratio = round(bs[i - 1]["v"] / avg_v, 2) if (avg_v and i >= 1) else 0
            # FIX(2026-08-22): 跨度特征加分（研究 iter_span_combo: 阶段6-15 +1 / ADX>15 +1 → 组合 +13.02%/PF 10.52）
            _stage_span = 0
            for _j in range(i, max(0, i - 60), -1):
                if stage_and_deep(bs, _j)[0] == st:
                    _stage_span += 1
                else:
                    break
            _adx_span = 0
            for _j in range(i, max(0, i - 40), -1):
                if (adx14_of(bs, _j) or 0) >= 20:
                    _adx_span += 1
                else:
                    break
            rank_score = (2 if st == "ACCUM" else 1) + (1 if v_ratio > 1.2 else 0) + (1 if v_ratio >= 2.0 else 0) + (1 if ("方案" in str(title) or "首次" in str(title) or "计划" in str(title)) else 0)
            rank_score += (1 if 6 <= _stage_span <= 15 else 0) + (1 if _adx_span > 15 else 0)
            # FIX(2026-08-28): 自适应研究记录 —— 弱市放量特征弱(≥1.2x 仅 +2.75%)，但非负；保持放量加分（不取消，避免弱市信号过少）
            # FIX(2026-08-22): 周线 down +1（研究 iter_triple_filter: 三重过滤 +13.36%/PF 10.99）
            _wt = weekly_trend_of(bs, i)
            rank_score += 1 if _wt == "down" else 0
            # FIX(2026-08-22): 连续放量 +1（大资金持续入场，研究 iter_vol_cont: 连续放量 PF 10.48）
            if v2_ratio and v_ratio >= 1.5 and v2_ratio >= 1.5:
                rank_score += 1
            # FIX(2026-08-22) 审计: 强市过滤 —— 改为仓位系数（G11 软化）：
            # proxy>2% 不跳过，而是降仓（position × clip(1-(proxy-0.02)/0.04, 0.3, 1)）
            # FIX(2026-09-13, 第八轮审计 5.6): proxy 按事件 signal 日(dd)取值 ——
            # 原缺省用该股最新数据日, 历史事件被当前市场状态错误赋权。
            _pr = _market_proxy(code, d8)
            _risk_coef = 1.0
            if _pr is not None and _pr > 0.02:
                _risk_coef = max(0.3, 1.0 - (_pr - 0.02) / 0.04)
                _sel_stats["scaled_strong"] = _sel_stats.get("scaled_strong", 0) + 1
            # FIX(2026-09-08, regime 发现正向应用): 弱市加权 —— 事件腿为逆向策略,
            # 弱市(proxy<0)信号质量最高(avg+6.6%/PF6.6 vs 强市+1.3%)。
            # weak_market_consistency 双段(OOS+IS)验证 k=2/4/8 单调提升风险调整收益。
            # w = clip(1 - k×proxy, 0.3, 2.0): 弱市加仓(≤2x), 强市降仓(≥0.3x), 与强市降仓系数相乘。
            _regime_coef = 1.0
            if CFG.WEAK_MARKET_WEIGHT and _pr is not None:
                _regime_coef = max(CFG.WEAK_MARKET_W_MIN,
                                   min(CFG.WEAK_MARKET_W_MAX, 1.0 - CFG.WEAK_MARKET_K * _pr))
                _risk_coef = round(_risk_coef * _regime_coef, 4)
                _sel_stats["regime_weighted"] = _sel_stats.get("regime_weighted", 0) + 1
            # FIX(2026-08-22): 回踩挂单（披露日收盘×0.99，回落成交；否则 T+1 开盘兜底）—— 研究 +0.47pp
            # limit = disclosure close × 0.99; if T+1 low <= limit → fill at limit; else fill at T+1 open
            # FIX(2026-09-08, 审计 P0-2): t1_open 已删除 —— monitor 以 valid_from 日实时 open 撮合，
            # 不再用 T+1 历史开盘价回退（历史价不可当实盘成交参考）。
            # FIX(2026-09-05, 审计 F17): 解析增持金额/占比，作为事件强度字段 + rank 加分
            _amt, _shr, _pct, _mag_hint = _parse_insider_magnitude(title)
            if _pct is not None and _pct >= 1.0:
                rank_score += 1  # 实质增持（≥1%）
            if _amt is not None and _amt >= 10000:  # ≥1亿元
                rank_score += 1
            # ══ R38ab 接线(2026-09-16 用户批准): EVENT 腿 rank 门槛 ══
            # 依据: 全链路审计 + 研究分叉双路径逐项一致(r38_rank_chain / r38_gen_v20f_rank3)
            # 预期: 组合 PF 3.35→3.52 / OOS 3.57→3.67 / MDD -415→-383(保留约 62% 候选)
            # 仅作用于 EVENT 腿; CONT 腿(rank 恒=3)不经此处, 不受影响。
            # 开关: CFG.EVENT_RANK_GATE_MIN(0 = 关闭, 保持旧行为 → 可一键回滚)。
            _rank_gate = int(getattr(CFG, "EVENT_RANK_GATE_MIN", 0) or 0)
            if _rank_gate > 0 and rank_score < _rank_gate:
                _sel_stats["skipped_rank"] = _sel_stats.get("skipped_rank", 0) + 1
                _mark_funnel(_key, "RANK_LT%d" % _rank_gate)
                _skipped_detail.append({"code": code, "name": name, "date": dd,
                                        "reason": f"rank_score={rank_score}<{_rank_gate}"})
                _reject_records.append({"code": code, "name": name, "date": dd,
                                        "stage": "RANK_LT%d" % _rank_gate,
                                        "adx": adx, "title": title[:80]})
                continue
            # FIX(2026-09-05, 审计 F18): 风险归一仓位 —— 固定风险预算 / (入场-SL)，替代等权
            _risk_budget = 0.01  # 单笔账户风险 1%
            _risk_dist = (limit_px - sl1) if sl1 and limit_px > sl1 else None
            _position_pct = round(_risk_budget / (_risk_dist / limit_px), 4) if _risk_dist else 0.01
            _position_pct = min(_position_pct, 0.25)  # 单票上限 25%
            # FIX(2026-09-05, 审计 G11): 强市降仓系数（不跳过，保留信号但控风险）
            _position_pct = round(_position_pct * _risk_coef, 4)
            # R60(用户指令: 选股挂单带完整 SMC 信号链): 单源 core/chain, 信号日因果
            _chain_snap = _chain_of(bs, i)
            # R61(用户指令: Jensen Alpha 联动): 前向期望 α —— PF后验基准表(冻结窗),
            # 1日滞后口径; 软失败(无表)时 _alpha=None, 不影响下单
            _alpha = None
            try:
                from core.alpha import alpha_expect as _axp
                _alpha = _axp(_chain_snap, st)
            except Exception:
                _alpha = None
            # R61 shadow gate: 记录"拦截会拦掉什么"到漏斗统计, 不拦(shadow 模式默认)
            if _alpha and _alpha.get("alpha_expect") is not None:
                if _alpha["alpha_expect"] < float(getattr(CFG, "ALPHA_SHADOW_MIN", -1.0) or -1.0):
                    _sel_stats["alpha_shadow_low"] = _sel_stats.get("alpha_shadow_low", 0) + 1
            led.append({
                "code": code, "name": name, "signal_combo": sig,
                "signal_date": dd, "trigger": f"回踩挂单(披露收盘×0.99={limit_px})，回落成交；次日开盘兜底(实时open)",
                # FIX(2026-09-05, 审计 G05/G09): valid_from = signal_date 之后第一个交易日，
                # monitor 只在该日开盘后以实时快照 open 成交（不再用 t1_open 历史价回退）
                "valid_from": _next_td(dates, d8),
                # tp_price is the executable runner target. tp4 remains a
                # research/display level but is not consumed by core.execution.
                "entry_price": limit_px, "tp_price": round(tp2, 3), "sl_price": round(sl1, 3),
                "tp1": round(tp1, 3), "tp2": round(tp2, 3), "tp3": round(tp3, 3), "tp4": round(tp4, 3),
                "sl1": round(sl1, 3), "sl2": round(sl2, 3), "anchor_note": anchor_note,
                "status": "PENDING_ORDER", "paper": True, "source": "EVENT",
                "created_at": cn_now("%Y-%m-%d"), "pick_date": cn_now("%Y-%m-%d"),
                "sub_signals": subs, "stage": st, "v_ratio": v_ratio, "rank_score": rank_score,
                "stage_span": _stage_span, "adx_span": _adx_span, "weekly_trend": _wt,
                # R60: 完整 SMC 信号链 + R61: Jensen Alpha 期望
                "chain": _chain_snap,
                "alpha_expect": (_alpha["alpha_expect"] if _alpha else None),
                "alpha_bucket": (_alpha["bucket_key"] if _alpha else None),
                "alpha_bucket_n": (_alpha["bucket_n"] if _alpha else None),
                "alpha_global_avg": (_alpha["global_avg"] if _alpha else None),
                "insider_amount_wan": _amt, "insider_pct": _pct, "insider_hint": _mag_hint,
                "position_pct": _position_pct, "risk_dist_pct": round(_risk_dist / limit_px * 100, 2) if _risk_dist else None,
                "filled_price": None, "filled_at": None,
                "exit_reason": None, "pnl_pct": None,
                # FIX(2026-09-13, 第七轮审计 P0-1): entry_mode 显式化 —— 旧名 "retrace" 是
                # core.execution 的废弃别名(= limit_or_open 语义: 触价优先, 否则开盘兜底),
                # 与账本 order_type="LIMIT_RETRACE" 字面矛盾。事件单设计意图就是"回踩限价+
                # 开盘兜底"(研究 +0.47pp, F10 对账语义依赖), 故显式改写 limit_or_open;
                # 严格限价单(未触价永不成交)才用 limit_retrace。
                "entry_mode": "limit_or_open",
                # FIX(2026-09-08, 复审 P1-1): 订单类型显式化 —— 每笔记录类型与时间边界。
                # limit_or_open = 触价优先(披露收盘×0.99), 未触则 T+1 实时 open 兜底; next_open = MARKET_T1_OPEN。
                # submitted_at=信号生成日, eligible_at=valid_from(可成交首日), fill_rule=撮合规则。
                "order_type": "LIMIT_OR_OPEN", "submitted_at": cn_now("%Y-%m-%d %H:%M:%S"),
                "eligible_at": _next_td(dates, d8),
                "fill_rule": "回踩挂单: low<=limit×0.99 成交, 否则 T+1 开盘兜底(实时open)",
                "not_filled_reason": None,
                # FIX(2026-09-13, 第八轮审计 P0-4): 开关快照 —— 每笔订单记录当时的
                # 三腿开关状态(可审计: 事后能回答"该单产生时哪个腿是开着的")。
                "leg_flags": {"event": bool(getattr(CFG, "ENABLE_EVENT_LEG", True)),
                              "cont": bool(getattr(CFG, "ENABLE_CONT_LEG", False)),
                              "smc": bool(getattr(CFG, "ENABLE_SMC_LEG", False))},
            })
            # FIX(2026-09-13, 第八轮审计 P1-9): PortfolioGate 订单创建前接线(最小实现) ——
            # 总暴露(已成交+待成交+本单) ≤0.8 / 单票 ≤0.25 / 单日新开 ≤5 / kill switch。
            # gate 拒绝写 capacity_reject(与策略拒绝分开, 审计 §P1-9), 不进正式订单。
            _gate_ok, _gate_why, _gate_total = _portfolio_gate(led[-1])
            if not _gate_ok:
                led.pop()  # 撤回该订单
                _sel_stats["capacity_reject"] = _sel_stats.get("capacity_reject", 0) + 1
                if str(_gate_why).startswith("PORTFOLIO_GATE_ERROR:"):
                    _sel_stats["gate_error"] = _sel_stats.get("gate_error", 0) + 1
                _mark_funnel(_key, "CAPACITY_REJECT")
                _reject_records.append({"code": code, "name": name, "date": dd,
                                        "stage": "CAPACITY_REJECT", "title": title[:80],
                                        "why": _gate_why, "total_exposure": round(_gate_total, 4)})
                continue
            _mark_funnel(_key, "PASSED_TO_ORDER")
            # R64: Jev 影子判断(过闸后采样, 只记录/不影响任何决策; key 未设自动跳过)
            _j = _jev_of(led[-1], _chain_snap)
            if _j is not None:
                led[-1]["jev"] = _j
                _sel_stats["jev_judged"] = _sel_stats.get("jev_judged", 0) + 1
            new_orders.append((code, name, dd, limit_px))
            _event_order_count += 1
    conn.close()
    # continuation candidates from scanner result (T+1 open entry, hold 10)
    # FIX(2026-09-13, 第八轮审计 P0-4): ENABLE_CONT_LEG 接线 —— 与 EVENT/SMC 同语义,
    # 开关关闭跳过延续腿选股(零新订单, 统计落盘 event_leg_status.json 同文件)。
    if not getattr(CFG, "ENABLE_CONT_LEG", True):
        print("[P0-4] ENABLE_CONT_LEG=False → 延续腿选股跳过", flush=True)
        try:
            _st2 = {"cont_leg_disabled": True, "orders_created": 0}
            _atomic_write_json(os.path.join(CFG.OUTPUT_ROOT, "event_leg_status.json"), _st2)
        except Exception:
            pass
    else:
        try:
            scan = json.load(open(os.path.join(ROOT, "current_scanner_result.json"), encoding="utf-8"))
            cont_cands = scan.get("continuation_candidates") or []
            for c in cont_cands:
                code = str(c.get("symbol", "")).split(".")[0]
                sig_d = str(c.get("signal_date", ""))
                if (code, sig_d) in known or (code, sig_d) in seen_orders:
                    continue
                seen_orders.add((code, sig_d))
                ep = c.get("reference_price") or c.get("entry_price") or 0
                support = c.get("support", 0)
                tp = ep * 1.15 if ep else 0
                sl = support * 0.99 if support else (ep * 0.90 if ep else 0)
                bs2 = bars_of(code)
                subs2 = []
                dates2 = []
                if bs2 and ep:
                    # FIX(2026-09-08, 审计 P0-3): 子信号基于 signal 日(决策时点)计算，
                    # 不再依赖已删除的 entry_date（历史 entry 日）。
                    sig_d8 = sig_d.replace("-", "")
                    dates2 = [b["t"] for b in bs2]
                    ei2 = dates2.index(sig_d8) if sig_d8 in dates2 else -1
                    if ei2 >= 60:
                        subs2 = sub_signals_cont(bs2, ei2, sig_d)
                _cont_risk = (ep - sl) if ep and sl else 0
                _cont_pos = min(0.01 / (_cont_risk / ep), 0.25) if _cont_risk > 0 else 0.01
                # R60/R61: 股挂单带 chain + alpha (软失败安全)
                _c_cont = _chain_of(bs2, dates2.index(sig_d8)) if (bs2 and dates2 and sig_d8 in dates2) else {}
                _a_cont = _alpha_of(_c_cont, "DOWNTREND")
                _cont_order = {
                    "code": code, "name": code, "signal_combo": "CONTINUATION_MARKUP",
                    # FIX(2026-09-05, 审计 G04): 延续腿不再当日 FILLED —— 信号 bar 用 ≤signal 数据过滤，
                    # 次日开盘挂单(valid_from)由 monitor 以实时 open 成交，禁止"知今日涨9%按今开买"
                    # FIX(2026-09-08, 审计 P0-3): entry_price 用 signal 收盘参考价，成交价由 monitor 实时 open 撮合
                    "signal_date": sig_d, "trigger": "MARKUP结构支撑+VWAP10%+低波动：次日开盘买入，固定10日",
                    "valid_from": c.get("valid_from") or (_next_td(dates2, sig_d8) if (bs2 and ep) else ""),
                "entry_price": round(ep, 3) if ep else 0, "tp_price": round(tp, 3), "sl_price": round(sl, 3),
                # FIX(2026-09-13, 第八轮审计 P1-4): CONT 目标价接线 —— 原订单只写
                # tp_price(展示字段), try_exit 只读 tp1/tp2 → 15% 目标在生产退出链
                # 不可执行(只能 SL/TIME_STOP 出场)。tp2=tp_price 使单目标可触发;
                # tp1 保持 None(单目标语义, 不部分平仓/不移保本)。
                "tp2": round(tp, 3),
                "status": "PENDING_ORDER", "paper": True, "source": "CONT",
                "created_at": cn_now("%Y-%m-%d"), "pick_date": cn_now("%Y-%m-%d"),
                "sub_signals": subs2, "entry_mode": "next_open",
                "chain": _c_cont,
                "alpha_expect": (_a_cont["alpha_expect"] if _a_cont else None),
                "alpha_bucket": (_a_cont["bucket_key"] if _a_cont else None),
                "alpha_bucket_n": (_a_cont["bucket_n"] if _a_cont else None),
                "alpha_global_avg": (_a_cont["global_avg"] if _a_cont else None),
                "filled_price": None,
                "filled_at": None,
                "exit_reason": None, "pnl_pct": None, "hold": 10,
                # FIX(2026-09-08, 复审 P1-1): 订单类型显式化
                "order_type": "MARKET_T1_OPEN", "submitted_at": cn_now("%Y-%m-%d %H:%M:%S"),
                "eligible_at": c.get("valid_from") or (_next_td(dates2, sig_d8) if (bs2 and ep) else ""),
                "fill_rule": "T+1开盘市价(实时open, 带滑点)", "not_filled_reason": None,
                # FIX(2026-09-13, 第八轮审计 P0-4): 开关快照(同 EVENT 订单)
                "position_pct": round(_cont_pos, 4),
                "leg_flags": {"event": bool(getattr(CFG, "ENABLE_EVENT_LEG", True)),
                               "cont": bool(getattr(CFG, "ENABLE_CONT_LEG", True)),
                               "smc": bool(getattr(CFG, "ENABLE_SMC_LEG", False))},
                }
                led.append(_cont_order)
                _gate_ok, _gate_why, _gate_total = _portfolio_gate(_cont_order)
                if not _gate_ok:
                    led.pop()
                    _sel_stats["capacity_reject"] = _sel_stats.get("capacity_reject", 0) + 1
                    if str(_gate_why).startswith("PORTFOLIO_GATE_ERROR:"):
                        _sel_stats["gate_error"] = _sel_stats.get("gate_error", 0) + 1
                    continue
            new_orders.append((code, code, sig_d, ep))
            # R64: Jev 影子判断(CONT 腿同样采样, 只记录)
            _jc = _jev_of(led[-1], _c_cont)
            if _jc is not None:
                led[-1]["jev"] = _jc
                _sel_stats["jev_judged"] = _sel_stats.get("jev_judged", 0) + 1
        except Exception:
            pass
    # FIX(2026-09-05, 审计 G03): SMC 腿接入生产选股 —— 读取 smc_candidates → PENDING(next_open)
    # FIX(2026-09-05, 复审 P0-3): SMC 无稳定 OOS edge → 由 config.ENABLE_SMC_LEG 门控（默认禁用，
    # 仅作 HTF_BIAS 研究特征，不独立开仓）
    if getattr(CFG, "ENABLE_SMC_LEG", False):
        try:
            scan = json.load(open(os.path.join(ROOT, "current_scanner_result.json"), encoding="utf-8"))
            smc_cands = scan.get("smc_candidates") or []
            for c in smc_cands:
                code = str(c.get("symbol", "")).split(".")[0]
                ev_d = str(c.get("event_date", ""))
                sig_d = str(c.get("confirmed_at") or c.get("reclaim_date") or c.get("entry_date", ""))
                if (code, ev_d) in known or (code, sig_d) in seen_orders:
                    continue
                seen_orders.add((code, sig_d))
                try:
                    ep = float(c.get("entry_price") or 0)
                    zl = float(c.get("zone_low") or 0)
                    sw = float(c.get("sweep_low") or 0)
                    tgt = float(c.get("target") or 0)
                    r20 = c.get("r20")
                    if not (ep > 0 and zl > 0):
                        continue
                except Exception:
                    continue
                bs3 = bars_of(code)
                dates3 = [b["t"] for b in bs3] if bs3 else []
                sl_smc = (min(zl, sw) if sw else zl) * 0.99
                risk = ep - sl_smc
                if risk <= 0:
                    continue
                tp_smc = max(tgt, ep + 1.5 * risk) if tgt > ep else ep + 1.5 * risk
                _pos = min(0.01 / (risk / ep), 0.25) if risk > 0 else 0.01
                _smc_order = {
                    "code": code, "name": code, "signal_combo": "SMC_W1D1D4", "source": "SMC",
                    "signal_date": sig_d or ev_d, "trigger": "SMC: 扫损+位移+POI回踩确认(8阶段) → 次日开盘",
                    "valid_from": _next_td(dates3, (sig_d or ev_d).replace("-", "")),
                    "entry_price": round(ep, 3), "tp_price": round(tp_smc, 3), "sl_price": round(sl_smc, 3),
                    "tp1": round(ep + risk, 3), "tp2": round(tp_smc, 3),
                    "sl1": round(sl_smc, 3),
                    "status": "PENDING_ORDER", "paper": True,
                    "created_at": cn_now("%Y-%m-%d"), "pick_date": cn_now("%Y-%m-%d"),
                    "position_pct": round(_pos, 4),
                    "r20": r20, "filled_price": None, "filled_at": None,
                    "exit_reason": None, "pnl_pct": None, "entry_mode": "next_open",
                    # FIX(2026-09-08, 复审 P1-1): 订单类型显式化
                    "order_type": "MARKET_T1_OPEN", "submitted_at": cn_now("%Y-%m-%d %H:%M:%S"),
                    "eligible_at": _next_td(dates3, (sig_d or ev_d).replace("-", "")),
                    "fill_rule": "T+1开盘市价(实时open, 带滑点)", "not_filled_reason": None,
                    "leg_flags": {"event": bool(getattr(CFG, "ENABLE_EVENT_LEG", True)),
                                  "cont": bool(getattr(CFG, "ENABLE_CONT_LEG", False)),
                                  "smc": bool(getattr(CFG, "ENABLE_SMC_LEG", False))},
                }
                led.append(_smc_order)
                _gate_ok, _gate_why, _gate_total = _portfolio_gate(_smc_order)
                if not _gate_ok:
                    led.pop()
                    _sel_stats["capacity_reject"] = _sel_stats.get("capacity_reject", 0) + 1
                    if str(_gate_why).startswith("PORTFOLIO_GATE_ERROR:"):
                        _sel_stats["gate_error"] = _sel_stats.get("gate_error", 0) + 1
                    continue
                new_orders.append((code, code, sig_d, ep))
                _sel_stats["smc_selected"] = _sel_stats.get("smc_selected", 0) + 1
        except Exception as _e:
            print(f'SMC 腿接入失败(不阻断): {_e}', flush=True)
    save_ledger(led)
    # FIX(2026-08-22): 选股结果日志（前端显示最新选股执行结果）
    # FIX(2026-09-08, R14 日历三态): day_status 区分 周末/无数据(节假日)/正常无信号/有信号
    _day_status = "OK"
    try:
        from datetime import date as _date_cls
        _today = _date_cls.today()
        if _today.weekday() >= 5:
            _day_status = "WEEKEND"
        elif not recent_days:
            _day_status = "HOLIDAY_OR_NO_DATA"  # 无可评估的交易日(节假日/数据未更新)
        elif not new_orders:
            _day_status = "NO_SIGNAL"  # 交易日且数据OK但无符合条件信号
        # else OK: 有新订单
    except Exception:
        pass
    _sel_stats["selected"] = len(new_orders)
    try:
        json.dump({"selected_at": cn_now("%Y-%m-%d %H:%M:%S"),
                   "days": recent_days, "stats": _sel_stats,
                   "day_status": _day_status,
                   "new_orders": [{"code": o[0], "name": o[1], "date": o[2], "price": o[3]} for o in new_orders],
                   "skipped_detail": _skipped_detail[-50:]},
                  open(os.path.join(ROOT, "selection_result.json"), "w", encoding="utf-8"),
                  ensure_ascii=False, indent=2)
    except Exception:
        pass
    # FIX(2026-09-08, 审计方向7/漏斗归因): 完整每日选股漏斗 JSON ——
    # 每层触发/拒绝计数 + 拒因分布，无新股时可定位"是市场没机会还是系统坏了"。
    try:
        from core.events import classify_title_detailed
        _raw = _kline_hit = _ev_cnt = 0
        _soft_delta = _hard = _soft = 0
        import sqlite3 as _sq3
        # FIX(2026-09-13, 第七轮审计 P1-5): 生产硬编码 → config.py 统一路径
        _c2 = _sq3.connect(CFG.ANNOUNCE_DB)
        _cur2 = _c2.cursor()
        for _dd2 in recent_days:
            _cur2.execute("SELECT title FROM announce WHERE date=? AND (title LIKE '%增持%' OR title LIKE '%回购%')", (_dd2,))
            for (_tt,) in _cur2.fetchall():
                _raw += 1
                _l = classify_title_detailed(_tt)[5]
                if _l == "HARD_REJECT":
                    _hard += 1
                elif _l == "PROGRESS_WITH_DELTA":
                    _soft_delta += 1
                elif _l == "SOFT_REJECT":
                    _soft += 1
                elif _l == "EVENT":
                    _ev_cnt += 1
        _c2.close()
        # R5(第七轮审计 §4.3/§9.2): 拒绝账本持久化 + 漏斗三分解
        _persist_rejects(_reject_records)
        _tri = _tri_decompose(_raw, _hard, _soft, _soft_delta,
                               _sel_stats.get("skipped_stage", 0), _sel_stats.get("skipped_adx", 0),
                               _sel_stats.get("skipped_nodata", 0), _sel_stats.get("skipped_dup", 0),
                               _event_order_count, bad_sl=_sel_stats.get("skipped_bad_sl", 0),
                               capacity=_sel_stats.get("capacity_reject", 0))
        _terminal_counts = {}
        for _stage_name in _reject_stage.values():
            _terminal_counts[_stage_name] = _terminal_counts.get(_stage_name, 0) + 1
        _positive_total = len(_positive_keys)
        _terminal_total = sum(_terminal_counts.values())
        _strategy_reject = _positive_total - _terminal_counts.get("DATA_MISSING", 0) - _event_order_count
        funnel = {
            "generated_at": cn_now("%Y-%m-%d %H:%M:%S"),
            "days": recent_days,
            "raw_announcements": _raw,
            "contains_buyback_or_increase": _raw,
            "classified_positive": _positive_total,
            "tri_decompose": _tri,
            "reject_by_reason": {
                "event_filter_hard": _hard,
                "event_filter_soft": _soft,
                "event_filter_soft_with_delta_research": _soft_delta,
                "stage": _sel_stats.get("skipped_stage", 0),
                "adx": _sel_stats.get("skipped_adx", 0),
                "nodata": _sel_stats.get("skipped_nodata", 0),
                "dup": _sel_stats.get("skipped_dup", 0),
                # FIX(2026-09-20, R52): 周末/节假日披露顺延量 — 原"K线无此日期"假缺失口径已迁出
                "rolled_weekend": _sel_stats.get("rolled_weekend", 0),
            },
            # R61: Jensen Alpha shadow gate 统计(α_expect < ALPHA_SHADOW_MIN 的腿数, 不拦截只记录)
            "alpha_shadow_low": _sel_stats.get("alpha_shadow_low", 0),
            # R64: Jev 影子判断采样数(本日新过闸挂单中被 Jev 打分的笔数; 未设 key → 0)
            "jev_judged": _sel_stats.get("jev_judged", 0),
            "orders_created": _event_order_count,
            "all_orders_created": len(new_orders),
            "terminal_stage_counts": _terminal_counts,
            "note": "漏斗逐层：公告总数→含增持/回购→分类为正事件→去重→有K线→阶段→ADX→挂单。"
                    "soft_with_delta 为研究候选（进展类含金额/比例增量），默认流仍拒绝。",
            # FIX(2026-09-08, 复审 P1-4): 守恒证明 —— 每股每日恰一个最终阶段；
            # 阶段计数总和 = universe_total（每股每日去重后）；DATA_MISSING 单列不计入策略拒绝。
            "conservation": {
                "universe_total": _positive_total,
                "data_missing": _terminal_counts.get("DATA_MISSING", 0),
                "strategy_reject": _strategy_reject,
                "passed_to_order": _event_order_count,
                "terminal_state_count": _terminal_total,
                "mutex_check": _terminal_total == _positive_total,
                "note": "positive event keys = data_missing + strategy_reject + event_orders（每股每日唯一终态）",
            },
        }
        json.dump(funnel, open(os.path.join(ROOT, "selection_funnel.json"), "w", encoding="utf-8"),
                  ensure_ascii=False, indent=2)
        for _m in MIRRORS:
            try:
                _atomic_write_json(_m.replace("paper_ledger.json", "selection_funnel.json"), funnel)
            except Exception:
                pass
    except Exception as _e:
        print(f"漏斗生成失败(不阻断): {_e}", flush=True)
    return new_orders


# ---------- realtime monitor (1-min) ----------
LOG_FILE = os.path.join(ROOT, "realtime_log.json")  # price snapshots for analysis

def _append_realtime_log(snapshot):
    """Append price snapshot to realtime_log.json (keep last 2000)."""
    try:
        try:
            prev = json.load(open(LOG_FILE, encoding="utf-8"))
        except Exception:
            prev = []
        prev.append(snapshot)
        if len(prev) > 2000:
            prev = prev[-2000:]
        with open(LOG_FILE, "w", encoding="utf-8") as fh:
            json.dump(prev, fh, ensure_ascii=False)
    except Exception:
        pass


# ---------- trade log ----------
TRADE_LOG = os.path.join(ROOT, "trade_log.json")


def _append_trade_log(rec):
    """记录交易日志（买入/卖出）—— 时间/信号/动作/TP/SL/触发类型/盈亏"""
    try:
        try:
            prev = json.load(open(TRADE_LOG, encoding="utf-8"))
        except Exception:
            prev = []
        prev.append(rec)
        if len(prev) > 5000:
            prev = prev[-5000:]
        with open(TRADE_LOG, "w", encoding="utf-8") as fh:
            json.dump(prev, fh, ensure_ascii=False)
    except Exception:
        pass


def realtime_monitor():
    """Check pending orders (price<=entry -> FILLED) and filled (TP/SL -> CLOSED).
    FIX(2026-09-14, R27 交易时段守卫): 非 A 股交易时段(上海 09:30-11:30/13:00-15:00)
    不执行撮合/平仓判定 —— R26 事故复盘发现午夜 monitor 用上一交易日极值回溯
    撮合(002203 于 01:00 用周五价格触价, 靠 R8 几何守卫才未造成损害; 若其
    几何合法即成错误成交)。Sina 盘后返回旧快照(px/open/high/low 全为上一
    交易日值), 任何时段撮合=用历史数据回溯成交。守卫: 非时段直接跳过撮合
    循环(不撤单不成交不平仓, 仅记一条日志) —— 订单在下一交易时段以当日
    实时数据正常处理。R25 TTL 推进同样被时段守卫暂停(盘后到下一交易时段
    才可能过期) —— 保守方向: 晚撤不早撤, 挂单最多多活一个时段, 不会
    用旧快照提前处置。"""
    # 交易时段守卫: 上海时区 HH:MM 判定
    # FIX(2026-09-14, R34): 原用 is_td(cn_today()) 判定当日是否交易日 ——
    # trading_calendar 由日线缓存聚合(只覆盖到上一交易日 20260911), 盘中
    # 查"今天"永远不在日历 → **每个交易日的盘中都被判 OFF_SESSION**(09-14
    # 实弹: 09:30-15:00 全天 OFF_SESSION, 131 条日志零撮合; 000157 开盘窗口
    # 空转, FILLED 持仓的盘中 TP/SL 判定同样被跳过)。结构性误判而非数据竞态。
    # 修正判据: 周末规则(周六/周日必然休市) + **快照日期新鲜度**(realtime_prices
    # 解析 Sina vals[30] 报价日期; 盘中当日快照 date==cn_today(), 盘后/休市
    # Sina 返回旧日期 → 用真数据判旧快照, 不用永远滞后的日历)。日历退化为
    # 周末守卫(节假日由快照日期兜底: 节假日 Sina 无当日快照)。
    # 失效模式: 快照不可达(网络断) → date 字段缺失 → 保守 OFF_SESSION(暂停
    # 撮合, 等待恢复) —— 旧 R27 的"解析失败继续跑"在 R34 语义下不再安全:
    # 无日期的快照无法证明新鲜度, fail-closed。
    try:
        from core.time_cn import shanghai_now
        _h, _m = shanghai_now().hour, shanghai_now().minute
        _hm = _h * 100 + _m
        _in_session = (930 <= _hm <= 1130) or (1300 <= _hm <= 1500)
        # 周末必然休市(周六/周日; 法定节假日由下方快照日期守卫兜底)
        _wd = shanghai_now().weekday()
        if _wd >= 5:
            _in_session = False
    except Exception:
        _in_session = False  # R34: 时区不可用 → fail-closed 暂停(旧语义"继续跑"
        #  会用无日期快照回溯撮合, R26 事故同型)
    if not _in_session:
        _append_realtime_log({
            "ts": cn_now("%Y-%m-%d %H:%M:%S"), "code": "-", "name": "时段守卫",
            "price": None, "status": "OFF_SESSION",
            "note": "非交易时段: 跳过撮合/平仓判定(防上一交易日快照回溯), 下一交易时段恢复",
        })
        return 0, 0
    led = load_ledger()
    pending = [t for t in led if t.get("status") == "PENDING_ORDER"]
    filled = [t for t in led if t.get("status") == "FILLED"]
    targets = [t for t in pending + filled]
    if not targets:
        return 0, 0
    codes = sorted({t["code"] for t in targets})
    px = realtime_prices(codes)
    # R34: 快照日期新鲜度守卫 —— 撮合前验证快照携带当日日期。盘中正常时
    # Sina vals[30]="YYYY-MM-DD"==cn_today(); 休市/节假日/盘后返回旧日期;
    # 网络失败 date 缺失 → 全部按非当日处理, 拒绝撮合(旧快照回溯防线)。
    _today = cn_today()
    _fresh = {c: str((v or {}).get("date") or "").replace("-", "") == _today
              for c, v in px.items()}
    _stale_all = px and all(not _fresh[c] for c in px)  # 有快照但全旧 → 休市/盘后
    if _stale_all:
        _append_realtime_log({
            "ts": cn_now("%Y-%m-%d %H:%M:%S"), "code": "-", "name": "快照新鲜度",
            "price": None, "status": "OFF_SESSION",
            "note": f"快照日期非当日(最新={next(iter(px.values()), {}).get('date', '?')}) "
                    f"→ 休市/盘后旧快照, 跳过撮合(R34 防回溯)",
        })
        return 0, 0
    n_fill = 0
    n_close = 0
    for t in targets:
        _info = px.get(t["code"])
        # 兼容新旧结构：dict（新，含 prev）或 float（旧）
        cur_px = _info.get("px") if isinstance(_info, dict) else _info
        # FIX(2026-08-22): skip 0/None prices — Sina returns 0.00 off-hours/failure;
        # treating 0 as "break SL" caused mass -100% SL_HIT on all positions.
        if cur_px is None or cur_px <= 0:
            # FIX(2026-09-13, 第八轮审计 P1-10): 行情不可用时仍推进订单生命周期 ——
            # 原直接 continue 使行情连续失败时 TTL 永不执行(审计: "价格为空就 continue,
            # 因此行情连续失败时不执行过期逻辑")。规则: PENDING 单仍按交易日历计 TTL
            # (挂单过期与行情无关——valid_from 后 N 交易日未成交即撤, 无论是否有价),
            # 标注 PRICE_UNAVAILABLE; 持仓(FILLED)不能无价强平 → 保持 continue(仅记日志)。
            if t.get("status") == "PENDING_ORDER":
                try:
                    _vf3 = t.get("valid_from", "")
                    if _vf3:
                        from core.trading_calendar import td_between, add_td_days
                        _n_td3 = td_between(_vf3, cn_today())
                        _need3 = int(getattr(CFG, "PENDING_EXPIRE_DAYS", 3))
                        if _n_td3 > _need3:
                            t["status"] = "EXPIRED"
                            t["expire_reason"] = "TIMEOUT"
                            t["note"] = (t.get("note", "") +
                                         f" | R25 TTL(行情不可用推进): valid_from起{_n_td3}交易日>"
                                         f"{_need3}未成交(PRICE_UNAVAILABLE)").strip()
                            _append_realtime_log({
                                "ts": cn_now("%Y-%m-%d %H:%M:%S"), "code": t["code"],
                                "name": t.get("name", ""), "price": None,
                                "status": "EXPIRED",
                                "note": "PENDING TTL 到期(行情不可用, 生命周期仍推进)",
                            })
                except Exception:
                    pass  # 日历不可用 → 保持 PENDING(不误过期, fail-closed)
            continue
        # FIX(2026-08-22): record price snapshot for analysis/review
        _append_realtime_log({
            "ts": cn_now("%Y-%m-%d %H:%M:%S"),
            "code": t["code"], "name": t.get("name", ""), "price": cur_px,
            "status": t["status"],
            "mark_pnl_pct": round((cur_px / (t.get("filled_price") or t.get("entry_price") or 1) - 1) * 100, 2)
            if (t.get("filled_price") or t.get("entry_price")) else None,
        })
        # R34: 个股级快照新鲜度守卫 —— "全旧"检查只拦休市/盘后; 个别股数据源
        # 滞后/故障返回旧日期时, 该股快照不得进入撮合(旧价格回溯成交风险与
        # R26 事故同型, 只是范围缩小到个股)。旧日期 → 跳过该股撮合(不撤单
        # 不成交, 下一轮新快照恢复)。PENDING TTL 推进与价格不可用分支一致
        # (挂单生命周期与行情新鲜度无关)。
        if isinstance(_info, dict) and not _fresh.get(t["code"], False):
            if t.get("status") == "PENDING_ORDER":
                try:
                    _vf4 = t.get("valid_from", "")
                    if _vf4:
                        from core.trading_calendar import td_between as _tdb
                        _n4 = _tdb(_vf4, cn_today())
                        if _n4 > int(getattr(CFG, "PENDING_EXPIRE_DAYS", 3)):
                            t["status"] = "EXPIRED"
                            t["expire_reason"] = "TIMEOUT"
                            t["note"] = (t.get("note", "") +
                                         f" | R34 个股旧快照TTL推进: valid_from起{_n4}交易日"
                                         f">{getattr(CFG, 'PENDING_EXPIRE_DAYS', 3)}未成交").strip()
                except Exception:
                    pass
            continue
        if t["status"] == "PENDING_ORDER":
            # FIX(2026-09-08, 审计 P0-4): 撮合判定统一委托 core.execution.try_fill
            # （停牌/涨跌停(板块)/valid_from/入场模式 一套语义，回测与纸面共用；本处只管写账本）
            from core.execution import try_fill as _core_fill
            _snap = dict(_info or {})
            _snap["today"] = cn_today()
            # FIX(2026-09-13, 第八轮审计 P1-2): 快照带报价时点 —— try_fill 的
            # next_open 开盘窗口守卫(09:30-10:15)消费 now; 迟到启动的监控不再
            # 回溯用历史 open 成交。
            _snap["now"] = cn_now("%Y-%m-%d %H:%M:%S")
            # FIX(2026-09-13, 第七轮审计 P0-1): 旧 entry_mode="retrace"(废弃别名)统一映射为
            # limit_or_open(其真实语义: 触价优先+开盘兜底)——与 daily_selection 写入的显式
            # entry_mode="limit_or_open" 一致, 消除"字段字面 vs 撮合语义"不一致。
            _fo = {"code": t["code"], "entry_mode": t.get("entry_mode") or "retrace",
                   "reference_price": t.get("entry_price"),
                   "planned_sl": t.get("sl1") or t.get("sl_price"),
                   "planned_tp": t.get("tp2") or t.get("tp_price"),
                   "valid_from": t.get("valid_from", "")}
            _fr = _core_fill(_fo, _snap)
            # FIX(2026-09-13, R8 执行合同): 成交时几何守卫 —— fill 价 >= SL 即时撤单。
            # 订单生成时 limit(×0.99) 可能 < sl1(DOWNTREND 反弹锚点在回踩价上方, 已有
            # 5/139 历史实例), 触价成交必然亏损 SL; 开盘兜底价若 >= SL 同理非法。
            # simulate 对此几何 BAD_ENTRY skip —— 纸面必须在成交点同语义 fail-closed,
            # 消除回测/纸面分裂(R8 fill-level 回放发现)。
            if _fr.get("filled") and float(_fr["price"] or 0) >= float(
                    _fo.get("planned_sl") or 0) > 0:
                t["status"] = "EXPIRED"
                t["expire_reason"] = "BAD_GEOMETRY_FILL_GE_SL"
                t["not_filled_reason"] = "BAD_GEOMETRY_FILL_GE_SL"
                t["note"] = (t.get("note", "") + f" | R8合同守卫: fill价{_fr['price']}>=" +
                             f"SL{_fo.get('planned_sl')} → 撤单(回测BAD_ENTRY同语义)").strip()
                _append_realtime_log({
                    "ts": cn_now("%Y-%m-%d %H:%M:%S"), "code": t["code"],
                    "name": t.get("name", ""), "price": _fr["price"], "status": "EXPIRED",
                    "note": "BAD_GEOMETRY_FILL_GE_SL(R8 守卫)",
                })
                print(f"[R8守卫] {t['code']} fill价{_fr['price']}>=SL{_fo.get('planned_sl')} → 撤单(与回测BAD_ENTRY同语义)", flush=True)
            elif _fr.get("filled"):
                # FIX(2026-09-13, 第八轮审计 P1-9): 成交前二次校验 —— 订单创建时的
                # gate 结果在成交时点可能已失效(同日其它订单先成交推高总暴露/持仓
                # 数, 审计 §P1-9 "订单创建前和成交前都调用")。此处对"含本单成交后"
                # 的组合状态再过 gate; 拒绝 → 本单撤销(EXPIRED, CAPACITY_REJECT_FILL
                # 入 not_filled_reason, 与创建前拒绝分开可审计)。
                _gate_ok = True
                _gate_why = ""
                try:
                    from core.portfolio import portfolio_exposure_check, throttle_open
                    # R35: 成交前二次校验同样接行业映射(与创建前同源, 防同行业
                    # 先成交后本单成交突破 max_sector)。
                    from core.industry_map import sector_counts as _sector_counts, get_industry as _get_industry
                    _others = [t2 for t2 in led if t2.get("status") in ("PENDING_ORDER", "FILLED")
                              and t2 is not t]
                    # 模拟成交后: 本单转 FILLED, 其余 PENDING 保持(潜在暴露), 已 FILLED 计入
                    _pos_after = [{"code": t2["code"],
                                   "position_pct": float(t2.get("position_pct") or 0.01)}
                                  for t2 in _others]
                    _pos_after.append({"code": t["code"],
                                       "position_pct": float(t.get("position_pct") or 0.01)})
                    _g_ok_e, _g_why_e, _ = portfolio_exposure_check(_pos_after)
                    # R37(000157 误拒复盘, 与创建前 gate 同语义修复):
                    # ①行业门只查候选股自己行业的桶(不传全行业桶);
                    # ②单日新开 = 当日 bool 数(sum) 而非全部条目数(len)。
                    _today = cn_now("%Y-%m-%d")
                    _day_opens = [t2.get("filled_at", "").startswith(_today) for t2 in _others
                                  if t2.get("status") == "FILLED"] + [True]
                    _cand_ind2 = _get_industry(t["code"])
                    _cand_bucket2 = {_cand_ind2: _sector_counts(
                        [t2["code"] for t2 in _others if t2.get("status") == "FILLED"],
                        exclude=t["code"]).get(_cand_ind2, 0)} \
                        if _cand_ind2 != "UNKNOWN" else {}
                    _g_ok_t, _g_why_t = throttle_open(_day_opens, _cand_bucket2, max_positions=10,
                                                     max_sector=3, max_daily_opens=5)
                    if not _g_ok_e:
                        _gate_ok, _gate_why = False, _g_why_e
                    elif not _g_ok_t:
                        _gate_ok, _gate_why = False, _g_why_t
                except Exception:
                    _gate_ok = True  # gate 自身异常不阻断成交(创建前已过一次; 记录)
                if not _gate_ok:
                    t["status"] = "EXPIRED"
                    t["expire_reason"] = "CAPACITY_REJECT_FILL"
                    t["not_filled_reason"] = "CAPACITY_REJECT_FILL"
                    t["note"] = (t.get("note", "") + f" | R18成交前gate: {_gate_why} → 撤单").strip()
                    _append_realtime_log({
                        "ts": cn_now("%Y-%m-%d %H:%M:%S"), "code": t["code"],
                        "name": t.get("name", ""), "price": _fr["price"], "status": "EXPIRED",
                        "note": f"CAPACITY_REJECT_FILL({_gate_why})",
                    })
                    print(f"[R18成交前gate] {t['code']} {_gate_why} → 撤单(创建前gate通过但成交时点组合状态已变)", flush=True)
                else:
                    t["status"] = "FILLED"
                    t["filled_price"] = _fr["price"]
                    t["filled_at"] = cn_now("%Y-%m-%d %H:%M:%S")
                    # FIX(2026-09-08, 复审 P1-1): 成交记录撮合规则与价格来源
                    t["fill_rule"] = _fr.get("fill_rule") or t.get("fill_rule") or "core.execution:try_fill"
                    t["fill_price_source"] = _fr.get("price_source", "core")
                    n_fill += 1
            else:
                # FIX(2026-09-08, 复审 P1-1): 未成交原因显式记录（停牌/涨停/未到日/待回落）
                t["not_filled_reason"] = _fr.get("why") or "unknown"
                # FIX(2026-09-08, 审计12): PENDING 过期机制 —— valid_from 后 PENDING_EXPIRE_DAYS
                # 个交易日内未成交（停牌/涨停/未回落）→ EXPIRED，避免长期 pending 阻塞同代码后续信号
                # （known/seen_orders 按.signal_date 去重，EXPIRED 后同代码新信号可正常进入）
                # FIX(2026-09-13, 第七轮审计 P1 清单#3): TTL 改真实交易日计数
                # （原 ×2 自然日近似在春节/国庆长假会把 3 交易日误当 6-8 自然日用不满,
                #  周末密集期又提前到期; 统一委托 core.trading_calendar）
                try:
                    _vf2 = t.get("valid_from", "")
                    if _vf2:
                        from core.trading_calendar import td_between, add_td_days
                        _expd = add_td_days(_vf2, int(getattr(CFG, "PENDING_EXPIRE_DAYS", 3)))
                        _n_td = td_between(_vf2, _snap["today"])
                        if _expd and _n_td > int(getattr(CFG, "PENDING_EXPIRE_DAYS", 3)) \
                                and t.get("status") == "PENDING_ORDER":
                            t["status"] = "EXPIRED"
                            t["expire_reason"] = _fr.get("why") or "TIMEOUT"
                            t["note"] = (t.get("note", "") + f" | PENDING过期(valid_from起{_n_td}个交易日>PENDING_EXPIRE_DAYS={getattr(CFG, 'PENDING_EXPIRE_DAYS', 3)}未成交: {_fr.get('why')})").strip()
                except Exception:
                    pass
            # 未成交原因（停牌/涨停/未到日/待回落）由核心统一返回，本处不重复判定
            # FIX(2026-08-22): 买入交易日志（时间/信号/动作/TP/SL）
            # FIX(2026-09-10, F10 Replay Gate): entry_price 语义统一 —— 台账对账字段。
            # 旧版写 t.filled_price(含滑点实价) —— 但部分旧记录是信号日收盘(27.5 vs 27.324 挂单价),
            # 两种语义混存导致 Replay Gate L1 无法对账。统一为: limit_entry(挂单价, ledger 同源) +
            # filled_price(实成交价, 可空) 双字段, 消费方按需取用。
            if t["status"] == "FILLED" and not t.get("_trade_logged_buy"):
                t["_trade_logged_buy"] = True
                _append_trade_log({
                    "ts": cn_now("%Y-%m-%d %H:%M:%S"), "code": t["code"], "name": t.get("name", ""),
                    "action": "BUY", "signal_combo": t.get("signal_combo", t.get("source", "")),
                    "signal_date": t.get("signal_date", ""),
                    "limit_entry": t.get("entry_price"),                       # F10: 挂单价(与 ledger 同源)
                    "entry_price": t.get("filled_price") or t.get("entry_price"),  # 兼容旧读方: 实成交价
                    "filled_price": t.get("filled_price"),                     # F10: 实成交价(显式)
                    "fill_rule": t.get("fill_rule"), "price_source": t.get("fill_price_source"),
                    "tp_price": t.get("tp2", t.get("tp_price")), "sl_price": t.get("sl1", t.get("sl_price")),
                    "trigger": t.get("trigger", "T+1开盘/回踩"), "pnl_pct": None,
                })
        elif t["status"] == "FILLED":
            # FIX(2026-09-19, R13 生产化): 每笔持仓累计 MFE/MAE, 无视 suspend/limit-up(反映价格轨迹)
            _ep0 = t["filled_price"] or t["entry_price"]
            if cur_px > (t.get("mfe_px") or _ep0):
                t["mfe_px"] = cur_px
            if cur_px < (t.get("mae_px") or _ep0):
                t["mae_px"] = cur_px
            # FIX(2026-09-04, 审计 P2): 停牌无法卖出（量=0，跳过平仓判定）
            if _is_suspended(_info):
                continue
            # FIX(2026-09-04, 审计 P2): 跌停无法卖出（跳过平仓判定，避免按跌停价错误成交）
            if _is_limit_up(_info, side="sell", code=t["code"]):
                continue
            ep = t["filled_price"] or t["entry_price"]
            # FIX(2026-09-04, 策略层): 卖出执行价 = 实时价 × (1 - SLIPPAGE)（卖出滑点）
            _sell_px = cur_px * (1 - SLIPPAGE)
            # FIX(2026-08-22): A股 T+1 规则 —— 买入当日不可卖出，TP/SL 无法生效
            _today = cn_now("%Y-%m-%d")
            if t.get("filled_at") and str(t["filled_at"])[:10] == _today:
                t["mark_price"] = cur_px
                t["mark_pnl_pct"] = round((cur_px / ep - 1) * 100, 4)
                t["t1_locked"] = True  # T+1 锁定（今日买入不可卖）
                continue
            t["t1_locked"] = False
            # FIX(2026-09-13, 第七轮审计 P1-1): 删除 CONT 独立自然日 HOLD_EXIT 分支
            # （原实现按 Unix 自然日差退出, 混入周末/节假日, 且绕开统一 TP/SL/时间止损合同）。
            # 延续腿持有期统一由 core.execution.try_exit 的时间止损判定:
            # bars_since_fill(交易日 bar 计数) >= hold(写入 position 的 max_hold) → TIME_STOP。
            # 旧行为对照: HOLD_EXIT(自然日) → 新行为 TIME_STOP(交易日 bar) — 语义更严: 周末不计时。
            if t["status"] == "FILLED":
                # FIX(2026-09-08, 审计 P0-4 完结): 离场判定统一委托 core.execution.try_exit。
                # 判定顺序(T+1锁→SL/BE→TP1部分→TP2全平→时间止损)与 simulate 逐 bar 完全一致，
                # 本处只负责账本语义（realized_pnl 分批、note、pnl 汇总），不再自行判 TP/SL。
                from core.execution import try_exit as _core_exit
                tp1 = t.get("tp1") or 0
                tp2 = t.get("tp2") or 0
                sl1 = t.get("sl1") or t.get("sl_price") or 0
                # bars_since_fill：filled 日到最新K线日的交易日数（供时间止损判定）
                _bars_sf = None
                try:
                    _bs2 = bars_of(t["code"])
                    _ds2 = [b["t"] for b in _bs2]
                    _fd2 = str(t["filled_at"])[:10].replace("-", "")
                    if _fd2 in _ds2:
                        _bars_sf = len(_ds2) - 1 - _ds2.index(_fd2)
                except Exception:
                    pass
                # FIX(2026-09-13, 第七轮审计 P1-1): max_hold 按腿透传 —— CONT 用自身
                # hold(默认10)+adaptive_hold 市场状态自适应(语义保留, 从独立自然日分支
                # 改为 try_exit 的 bar 计数参数); EVENT 用 CFG.MAX_HOLD(12)缺省。
                _max_hold_4core = None
                if t.get("source") == "CONT":
                    _mh = int(t.get("hold") or 10)
                    try:
                        # mark-to-market 场景: 评估"当前"持有期 → 用最新日(5.6 的
                        # signal 日口径仅适用于历史事件回看, 此处是当日决策)
                        _pr_hold = _market_proxy(t["code"])
                        if _pr_hold is not None:
                            _mh = adaptive_hold(_mh, _pr_hold)
                    except Exception:
                        pass
                    _max_hold_4core = _mh
                _pos4core = {"code": t["code"], "filled_price": ep, "sl": sl1,
                             "tp1": tp1, "tp2": tp2, "tp1_hit": bool(t.get("tp1_hit")),
                             # R29(第八轮 P1-3 差异②): tp3 透传 —— try_exit TP3 runner
                             # 与 simulate(L174)同条件对齐(be_active 且 tp3>tp2 直达)。
                             "tp3": t.get("tp3"),
                             "filled_at": t.get("filled_at", ""), "max_hold": _max_hold_4core,
                             # FIX(2026-09-13, 第七轮审计 P1-2): SL 状态版本随持仓传递
                             "sl_version": int(t.get("sl_version") or 0)}
                _snap4core = dict(_info or {})
                _snap4core["today"] = cn_today()
                _snap4core["bars_since_fill"] = _bars_sf
                _xr = _core_exit(_pos4core, _snap4core)
                if _xr.get("exit"):
                    t["status"] = "CLOSED"
                    t["exit_reason"] = _xr["reason"]
                    t["exit_price"] = _xr.get("price")
                    # FIX(2026-09-13, 第七轮审计 P1-2): SL 状态持久化（成交时落账本,
                    # sl_version/sl_reason/sl_updated_at 与 try_exit 返回一致, 供对账）
                    _slst = _xr.get("sl_state")
                    if _slst:
                        t["active_sl_at_exit"] = _slst.get("active_sl")
                        t["sl_version"] = _slst.get("sl_version")
                        t["sl_reason"] = _slst.get("sl_reason")
                        t["sl_updated_at"] = _slst.get("sl_updated_at")
                    if _xr["reason"] in ("TP2_RUNNER",):
                        t["tp2_hit"] = True
                        _rem = 0.7 if t.get("tp1_hit") else 1.0
                        _exit_px = float(_xr.get("price") or tp2)
                        t["realized_pnl"] = (t.get("realized_pnl", 0) or 0) + _rem * (_exit_px / ep - 1) * 100 - FEE * _rem
                        t["pnl_pct"] = round(t.get("realized_pnl", 0), 4)
                        # FIX(2026-09-08): 原 % 格式串含裸 '%平' 字符 → ValueError；改 f-string
                        t["note"] = (t.get("note", "") +
                                      f" | TP2(FVG/BSL)触发：剩余{_rem:.0%}平仓+{(_exit_px/ep-1)*100:.2f}%（100%已平）").strip()
                    else:
                        _rem = 0.7 if t.get("tp1_hit") else 1.0
                        t["pnl_pct"] = round((t.get("realized_pnl", 0) or 0) + _rem * (_xr["price"] / ep - 1) * 100 - FEE * _rem, 4)
                    # R13 生产化: 亏损单的 20 类归因(归因在平仓 vol 点后执行不外溢)
                    if t["pnl_pct"] is not None and t["pnl_pct"] < 0:
                        try:
                            from core.attribution import attribute_trade as _attr
                            _ep = t.get("filled_price") or t.get("entry_price") or 0
                            _sl1 = t.get("sl1") or t.get("sl_price") or 0
                            _sl_d = (abs(_ep - _sl1) / _ep * 100) if _ep and _sl1 else None
                            _mfe_pct = round((t.get("mfe_px", _ep) / _ep - 1) * 100, 4) if _ep else None
                            _mae_pct = round((_ep - t.get("mae_px", _ep)) / _ep * 100, 4) if _ep else None
                            # 用 MFE 反推 R(mfe 距离 / 风险距离)
                            _mfe_r = None
                            if _sl_d and _sl_d > 0 and _mfe_pct is not None:
                                _mfe_r = round(_mfe_pct / _sl_d, 2)
                            t["loss_attribution"] = _attr(
                                tr=t["pnl_pct"], mae_pct=_mae_pct,
                                mfe_pct=_mfe_pct, sl_dist_pct=_sl_d,
                                mfe_r=_mfe_r, hold_bars=_bars_sf,
                                reason=t.get("exit_reason"), rank=t.get("rank_score"),
                            )
                        except Exception:
                            pass  # R13 软失败: 归因失败不影响卖出订单
                    n_close += 1
                elif _xr.get("partial") == "TP1" and not t.get("tp1_hit"):
                    # TP1 部分平仓（与回测合同一致：30%平，SL移保本）
                    t["tp1_hit"] = True
                    if _xr.get("new_state") and _xr["new_state"].get("sl") is not None:
                        t["sl1"] = _xr["new_state"]["sl"]
                    # FIX(2026-09-13, 第七轮审计 P1-2): SL 状态版本化 —— 移保本是一次
                    # 显式 SL 变更, 落 sl_version/sl_reason/sl_updated_at 供逐笔对账
                    t["sl_version"] = int(t.get("sl_version") or 0) + 1
                    t["sl_reason"] = "TP1_MOVE_TO_BE"
                    t["sl_updated_at"] = cn_today()
                    _tp1_exit_px = float(_xr.get("price") or (tp1 * (1 - SLIPPAGE)))
                    t["realized_pnl"] = 0.3 * (_tp1_exit_px / ep - 1) * 100 - FEE * 0.3
                    t["note"] = (t.get("note", "") + " | TP1(swing high)触发：30%平仓+" + str(round((_tp1_exit_px/ep-1)*100,2)) + "%，SL移保本").strip()
                # SL 距离 >8% → 降仓标记（风险控制，账本侧）
                if not t.get("_sl_far_flagged") and (ep - sl1) / ep > 0.08:
                    t["_sl_far_flagged"] = True
                    t["position_scale"] = 0.5
            t["mark_price"] = cur_px
            t["mark_pnl_pct"] = round((cur_px / ep - 1) * 100, 4)
            # FIX(2026-08-22): 卖出交易日志（时间/信号/动作/TP/SL/触发类型/盈亏）
            if t["status"] == "CLOSED" and not t.get("_trade_logged_sell"):
                t["_trade_logged_sell"] = True
                _append_trade_log({
                    "ts": cn_now("%Y-%m-%d %H:%M:%S"), "code": t["code"], "name": t.get("name", ""),
                    "action": "SELL", "signal_combo": t.get("signal_combo", t.get("source", "")),
                    "signal_date": t.get("signal_date", ""), "entry_price": t.get("filled_price") or t.get("entry_price"),
                    "tp_price": t.get("tp2", t.get("tp_price")), "sl_price": t.get("sl1", t.get("sl_price")),
                    "trigger_type": t.get("exit_reason", ""), "pnl_pct": t.get("pnl_pct"),
                })
    save_ledger(led)
    return n_fill, n_close


if __name__ == "__main__":
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument("--select", action="store_true", help="每日0点选股（生成挂单）")
    ap.add_argument("--monitor", action="store_true", help="实时监控（约1分钟调用）")
    args = ap.parse_args()
    if args.select:
        new = daily_selection()
        print(f"选股: 新增 {len(new)} 笔挂单")
        for c, n, d, ep in new[:10]:
            print(f"  {c} {n} 披露={d} 挂单价={ep}")
    if args.monitor:
        nf, nc = realtime_monitor()
        print(f"监控: 成交 {nf} 笔, 平仓 {nc} 笔")
        led = load_ledger()
        from collections import Counter
        print("状态分布:", dict(Counter(t["status"] for t in led)))
