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
import config as CFG  # 审计 P1: 统一路径/参数

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
        ex = "sh" if c.startswith("6") else "sz"
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
                        # FIX(2026-08-22): skip 0.00 prices (Sina off-hours / failure) — don't return 0
                        if _px > 0:
                            out[sym[2:]] = {"px": _px, "prev": _prev, "vol": _vol}
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


def _is_limit_up(px_info, side="buy"):
    """粗略涨跌停判定（主板 10%；创业板 30/688 20% 在此简化按 10% 主板规则）。
    返回 True 表示"无法成交"（买入时涨停、卖出时跌停）。无昨收时返回 False（不拦截）。"""
    px = (px_info or {}).get("px")
    prev = (px_info or {}).get("prev") or 0
    if not px or prev <= 0:
        return False
    chg = (px / prev - 1)
    if side == "buy":
        return chg >= 0.095  # 触及涨停 ≈ 无法按市价买入
    return chg <= -0.095  # 触及跌停 ≈ 无法按市价卖出


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
    """Behavior stage + DEEP flag (backtest-consistent quality filter, FIX 2026-08-22)."""
    if i < 91:
        return None, False
    w90 = bs[i - 90:i]
    w60 = bs[i - 60:i]
    w20 = bs[i - 20:i]
    ret90 = w90[-1]["c"] / w90[0]["c"] - 1
    ret60 = w60[-1]["c"] / w60[0]["c"] - 1
    v20 = sum(b["v"] for b in w20) / len(w20)
    v60 = sum(b["v"] for b in w60) / len(w60)
    v90 = sum(b["v"] for b in w90) / len(w90)
    vt60 = v20 / v60 if v60 else 1
    vt90 = v20 / v90 if v90 else 1
    deep = ret90 < -0.20 and vt90 < 0.75
    if ret60 < -0.15 and vt60 < 0.9:
        return "ACCUM", deep
    if ret60 > 0.30 and vt60 > 1.3:
        return "DISTRIB", deep
    if ret60 > 0.20 and vt60 > 1.1:
        return "MARKUP", deep
    if ret60 > 0:
        return "UPTREND", deep
    return "DOWNTREND", deep


def stage_and_deep_quantile(bs, i):
    """FIX(2026-09-05, 审计 F12): 阶段识别分位化 —— 用每股自身滚动分位代替全市场硬阈值。
    对每根 bar 计算过去 250 根内 ret60 的分位与 量比 的分位：
      - ret60 分位 < 0.25 且 量比分位 < 0.40 → ACCUM（吸筹）
      - ret60 分位 > 0.75 且 量比分位 > 0.70 → MARKUP（拉升）
      - ret60 分位 > 0.55 → UPTREND
      - ret60 分位 < 0.40 → DOWNTREND
    兼容旧签名：返回 (stage, deep)。"""
    if i < 91:
        return None, False
    w90 = bs[i - 90:i]
    w60 = bs[i - 60:i]
    w20 = bs[i - 20:i]
    ret60 = w60[-1]["c"] / w60[0]["c"] - 1
    ret90 = w90[-1]["c"] / w90[0]["c"] - 1
    v20 = sum(b["v"] for b in w20) / len(w20)
    v60 = sum(b["v"] for b in w60) / len(w60)
    v90 = sum(b["v"] for b in w90) / len(w90)
    vt60 = v20 / v60 if v60 else 1
    vt90 = v20 / v90 if v90 else 1
    deep = ret90 < -0.20 and vt90 < 0.75
    # 每股自身滚动分位（过去 250 根）
    hist_ret = []
    hist_vt = []
    for k in range(max(90, i - 250), i):
        w60k = bs[k - 60:k]
        w20k = bs[k - 20:k]
        if len(w60k) < 60 or len(w20k) < 20:
            continue
        r60 = w60k[-1]["c"] / w60k[0]["c"] - 1
        v2 = sum(x["v"] for x in w20k) / len(w20k)
        v6 = sum(x["v"] for x in w60k) / len(w60k)
        hist_ret.append(r60)
        hist_vt.append(v2 / v6 if v6 else 1)
    if len(hist_ret) < 30:
        return None, deep
    ret_pct = sum(1 for x in hist_ret if x < ret60) / len(hist_ret)
    vt_pct = sum(1 for x in hist_vt if x < vt60) / len(hist_vt)
    if ret_pct < 0.25 and vt_pct < 0.40:
        return "ACCUM", deep
    if ret_pct > 0.75 and vt_pct > 0.70:
        return "MARKUP", deep
    if ret_pct > 0.55:
        return "UPTREND", deep
    if ret_pct < 0.40:
        return "DOWNTREND", deep
    return "UPTREND", deep


def weekly_trend_of(bs, i):
    """周线趋势（真实自然周聚合，MA10 周线上/下行）—— 研究：周线 down 事件 +7.50% vs up +1.00%
    FIX(2026-09-04, 审计 P3): 旧实现每 5 根日线近似周线（非真实自然周），
    改为按日期 ISO 自然周分组，取每周最后一个收盘价。"""
    import datetime as _dt
    week_map = {}   # (year, week) -> 该周最后一根收盘
    for k in range(i, -1, -1):
        t = str(bs[k]["t"])
        try:
            iso = _dt.datetime.strptime(t[:8], "%Y%m%d").isocalendar()[:2]
        except Exception:
            continue
        week_map.setdefault(iso, bs[k]["c"])  # 从 i 往前遍历，首次遇到=该周最后收盘
        if len(week_map) >= 20:
            break
    week_close = [week_map[k] for k in sorted(week_map.keys())]
    if len(week_close) < 12:
        return None
    ma10 = sum(week_close[-10:]) / 10
    ma_prev = sum(week_close[-12:-2]) / 10
    return "up" if ma10 > ma_prev else "down"


# FIX(2026-08-22) 审计: 全市场代理（200 只采样 20 日平均涨跌）—— 弱市是抄底甜蜜区，强市(proxy>2%)事件无 alpha
_MKT_SAMPLE = None
_MKT_PROXY_CACHE = {}

def _market_proxy(code):
    """计算给定股票 signal 日期的市场状态（200 只采样 20 日平均涨跌，决策时点可得）。
    FIX(2026-09-04, 审计 P2):
      ① 采样快照落盘 hermes/kline_cache_tencent/.mkt_sample.json —— 避免每个新交易日重读 200 个 JSON；
      ② 标注幸存者偏差：采样来源是"当前缓存中存在 K 线"的股票（退市/长期停牌股无数据被排除），
         因此 proxy 存在正向幸存者偏差，仅作相对强弱参考，不做绝对市场判断。"""
    global _MKT_SAMPLE, _MKT_PROXY_CACHE
    bs = bars_of(code)
    if not bs:
        return None
    dates = [b["t"] for b in bs]
    if not dates:
        return None
    d8 = dates[-1]  # 当前数据日
    if d8 in _MKT_PROXY_CACHE:
        return _MKT_PROXY_CACHE[d8]
    kt = r"E:\test\smc_project\hermes\kline_cache_tencent"
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
    if i < 30:
        return None
    plus_dm = minus_dm = tr_sum = 0.0
    for k in range(i - 14, i):
        h, l, pc = bs[k]["h"], bs[k]["l"], bs[k - 1]["c"]
        up = h - bs[k - 1]["h"]
        dn = bs[k - 1]["l"] - l
        plus_dm += up if (up > dn and up > 0) else 0
        minus_dm += dn if (dn > up and dn > 0) else 0
        tr = max(h - l, abs(h - pc), abs(l - pc))
        tr_sum += tr
    if tr_sum <= 0:
        return None
    pdi = 100 * plus_dm / tr_sum
    mdi = 100 * minus_dm / tr_sum
    if pdi + mdi == 0:
        return None
    return 100 * abs(pdi - mdi) / (pdi + mdi)


def bars_of(code):
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


def is_swing_high(bs, j):
    if j < PIVOT or j + PIVOT >= len(bs):
        return False
    return bs[j]["h"] > max(bs[k]["h"] for k in range(j - PIVOT, j)) and bs[j]["h"] >= max(bs[k]["h"] for k in range(j + 1, j + PIVOT + 1))


def is_swing_low(bs, j):
    if j < PIVOT or j + PIVOT >= len(bs):
        return False
    return bs[j]["l"] < min(bs[k]["l"] for k in range(j - PIVOT, j)) and bs[j]["l"] <= min(bs[k]["l"] for k in range(j + 1, j + PIVOT + 1))


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
    for j in range(i - 1, max(0, i - 60), -1):
        if len(highs) < 4 and is_swing_high(bs, j):
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
def daily_selection():
    """Scan new insider events -> create PENDING_ORDER entries.
    entry price = disclosure day close (limit order: buy only at or below)."""
    import sqlite3
    conn = sqlite3.connect(r"E:\test\smc_project\announce\smc_announce.db")
    cur = conn.cursor()
    cur.execute("SELECT DISTINCT date FROM announce ORDER BY date DESC LIMIT 5")
    recent_days = [r[0] for r in cur.fetchall()]
    led = load_ledger()
    known = {(t["code"], t.get("signal_date", "")) for t in led}
    # also block codes already PENDING/FILLED for same signal date
    seen_orders = set()
    new_orders = []
    _sel_stats = {"scanned": 0, "selected": 0, "skipped_stage": 0, "skipped_adx": 0,
                  "skipped_strong": 0, "skipped_nodata": 0, "skipped_dup": 0}
    _skipped_detail = []  # FIX(2026-08-26): 跳过明细（代码/名称/原因）
    for dd in recent_days:
        cur.execute("SELECT stock_code, stock_name, title FROM announce WHERE date=? AND (title LIKE '%增持%' OR title LIKE '%回购%') AND title NOT LIKE '%完成%' AND title NOT LIKE '%进度%' AND title NOT LIKE '%前十名%'", (dd,))
        for code, name, title in cur.fetchall():
            _sel_stats["scanned"] += 1
            d8 = str(dd).replace("-", "")
            if (code, dd) in known or (code, dd) in seen_orders:
                _sel_stats["skipped_dup"] += 1
                continue
            seen_orders.add((code, dd))
            bs = bars_of(code)
            if not bs:
                _sel_stats["skipped_nodata"] += 1
                _skipped_detail.append({"code": code, "name": name, "date": dd, "reason": "无K线数据"})
                continue
            dates = [b["t"] for b in bs]
            if d8 not in dates:
                _sel_stats["skipped_nodata"] += 1
                _skipped_detail.append({"code": code, "name": name, "date": dd, "reason": "K线无此日期"})
                continue
            i = dates.index(d8)
            # FIX(2026-08-22 audit): apply backtest-consistent quality filter
            # (ACCUM/DOWNTREND stage + ADX>=20 — combo-level test: ADX30 no combo gain, keep 20 for more samples)
            st, deep = stage_and_deep(bs, i)
            if st not in ("ACCUM", "DOWNTREND"):
                _sel_stats["skipped_stage"] += 1
                _skipped_detail.append({"code": code, "name": name, "date": dd, "reason": f"阶段={st}(非ACCUM/DOWNTREND)"})
                continue
            adx = adx14_of(bs, i)
            if adx is None or adx < 20:
                _sel_stats["skipped_adx"] += 1
                _skipped_detail.append({"code": code, "name": name, "date": dd, "reason": f"ADX={adx}<20"})
                continue
            close_px = bs[i]["c"]
            if close_px <= 0:
                continue
            # FIX(2026-08-22): event leg uses T+1 open price (market order, matching backtest)
            # Previously used limit order at disclosure close — caused PENDING never filling.
            entry_idx = i + 1
            if entry_idx >= len(bs):
                continue
            entry_px = bs[entry_idx]["o"]
            if entry_px <= 0:
                continue
            adx_v = adx14_of(bs, i) or 0
            tp1, tp2, tp3, tp4, sl1, sl2, anchor_note = structural_sltp(code, d8, src='EVENT', stage=st, adx=adx_v)
            # FIX(2026-08-25): tp4/sl2 可能 None（结构不足，ACCUM/DOWNTREND 非强趋势时）—— 回退
            if tp1 is None or sl1 is None or tp4 is None or tp4 <= entry_px or sl2 is None:
                tp1 = round(entry_px * 1.03, 3)
                tp2 = round(entry_px * 1.06, 3)
                tp3 = round(entry_px * 1.10, 3)
                tp4 = round(entry_px * 1.15, 3)
                sl1 = round(entry_px * 0.96, 3)
                sl2 = round(entry_px * 0.90, 3)
                anchor_note = "回退:固定比例(结构不足)"
            is_buyback = "回购" in str(title)
            sig = "BUYBACK_STRONG" if is_buyback else "HOLDER_INCREASE"
            subs = sub_signals_event(bs, i, dd)
            avg_v = sum(bs[k]["v"] for k in range(i + 1 - 20, i + 1)) / 20 if i + 1 >= 20 else 0
            v_ratio = round(bs[entry_idx]["v"] / avg_v, 2) if (avg_v and entry_idx < len(bs)) else 1.0
            # FIX(2026-08-22): 连续放量（大资金持续入场，研究 iter_vol_cont: 连续放量 +15.55%/PF 9.30）
            v2_ratio = round(bs[entry_idx + 1]["v"] / avg_v, 2) if (avg_v and entry_idx + 1 < len(bs)) else 0
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
            # FIX(2026-08-22) 审计: 强市过滤（proxy>2% 时事件腿跳过，弱市是抄底甜蜜区 +10.39% vs 强市 +1.04%）
            _pr = _market_proxy(code)
            if _pr is not None and _pr > 0.02:
                _sel_stats["skipped_strong"] += 1
                _skipped_detail.append({"code": code, "name": name, "date": dd, "reason": f"强市proxy={_pr:.1%}>2%"})
                continue  # 强市事件无 alpha（研究：+1.04% 无意义）
            # FIX(2026-08-22): 回踩挂单（披露日收盘×0.99，回落成交；否则 T+1 开盘兜底）—— 研究 +0.47pp
            # limit = disclosure close × 0.99; if T+1 low <= limit → fill at limit; else fill at T+1 open
            limit_px = round(close_px * 0.99, 3)
            t1_open = round(entry_px, 3)
            # FIX(2026-09-05, 审计 F17): 解析增持金额/占比，作为事件强度字段 + rank 加分
            _amt, _shr, _pct, _mag_hint = _parse_insider_magnitude(title)
            if _pct is not None and _pct >= 1.0:
                rank_score += 1  # 实质增持（≥1%）
            if _amt is not None and _amt >= 10000:  # ≥1亿元
                rank_score += 1
            # FIX(2026-09-05, 审计 F18): 风险归一仓位 —— 固定风险预算 / (入场-SL)，替代等权
            _risk_budget = 0.01  # 单笔账户风险 1%
            _risk_dist = (limit_px - sl1) if sl1 and limit_px > sl1 else None
            _position_pct = round(_risk_budget / (_risk_dist / limit_px), 4) if _risk_dist else 0.01
            _position_pct = min(_position_pct, 0.25)  # 单票上限 25%
            led.append({
                "code": code, "name": name, "signal_combo": sig,
                "signal_date": dd, "trigger": f"回踩挂单(披露收盘×0.99={limit_px})，回落成交；否则开盘({t1_open})兜底",
                "entry_price": limit_px, "tp_price": round(tp4, 3), "sl_price": round(sl1, 3),
                "tp1": round(tp1, 3), "tp2": round(tp2, 3), "tp3": round(tp3, 3), "tp4": round(tp4, 3),
                "sl1": round(sl1, 3), "sl2": round(sl2, 3), "anchor_note": anchor_note,
                "status": "PENDING_ORDER", "paper": True, "source": "EVENT",
                "created_at": time.strftime("%Y-%m-%d"), "pick_date": time.strftime("%Y-%m-%d"),
                "sub_signals": subs, "stage": st, "v_ratio": v_ratio, "rank_score": rank_score,
                "stage_span": _stage_span, "adx_span": _adx_span, "weekly_trend": _wt,
                "insider_amount_wan": _amt, "insider_pct": _pct, "insider_hint": _mag_hint,
                "position_pct": _position_pct, "risk_dist_pct": round(_risk_dist / limit_px * 100, 2) if _risk_dist else None,
                "filled_price": None, "filled_at": None,
                "exit_reason": None, "pnl_pct": None, "entry_mode": "retrace", "t1_open": t1_open,
            })
            new_orders.append((code, name, dd, limit_px))
    conn.close()
    # continuation candidates from scanner result (T+1 open entry, hold 10)
    try:
        scan = json.load(open(os.path.join(ROOT, "current_scanner_result.json"), encoding="utf-8"))
        cont_cands = scan.get("continuation_candidates") or []
        for c in cont_cands:
            code = str(c.get("symbol", "")).split(".")[0]
            sig_d = str(c.get("signal_date", ""))
            if (code, sig_d) in known or (code, sig_d) in seen_orders:
                continue
            seen_orders.add((code, sig_d))
            ep = c.get("entry_price", 0)
            support = c.get("support", 0)
            tp = ep * 1.15 if ep else 0
            sl = support * 0.99 if support else (ep * 0.90 if ep else 0)
            bs2 = bars_of(code)
            subs2 = []
            if bs2 and ep:
                ed2 = str(c.get("entry_date", ""))
                dates2 = [b["t"] for b in bs2]
                ei2 = dates2.index(ed2) if ed2 in dates2 else -1
                if ei2 >= 60:
                    subs2 = sub_signals_cont(bs2, ei2, str(c.get("signal_date", "")))
            led.append({
                "code": code, "name": code, "signal_combo": "CONTINUATION_MARKUP",
                "signal_date": sig_d, "trigger": "MARKUP结构支撑+VWAP5%+低波动：次日开盘直接买入，固定10日",
                "entry_price": round(ep, 3) if ep else 0, "tp_price": round(tp, 3), "sl_price": round(sl, 3),
                "status": "FILLED" if ep else "PENDING_ORDER", "paper": True, "source": "CONT",
                "created_at": time.strftime("%Y-%m-%d"), "pick_date": time.strftime("%Y-%m-%d"),
                "sub_signals": subs2,
                "filled_price": round(ep, 3) if ep else None,
                "filled_at": time.strftime("%Y-%m-%d %H:%M:%S"),
                "exit_reason": None, "pnl_pct": None, "hold": 10,
            })
            new_orders.append((code, code, sig_d, ep))
    except Exception:
        pass
    save_ledger(led)
    # FIX(2026-08-22): 选股结果日志（前端显示最新选股执行结果）
    _sel_stats["selected"] = len(new_orders)
    try:
        json.dump({"selected_at": time.strftime("%Y-%m-%d %H:%M:%S"),
                   "days": recent_days, "stats": _sel_stats,
                   "new_orders": [{"code": o[0], "name": o[1], "date": o[2], "price": o[3]} for o in new_orders],
                   "skipped_detail": _skipped_detail[-50:]},
                  open(os.path.join(ROOT, "selection_result.json"), "w", encoding="utf-8"),
                  ensure_ascii=False, indent=2)
    except Exception:
        pass
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
    """Check pending orders (price<=entry -> FILLED) and filled (TP/SL -> CLOSED)."""
    led = load_ledger()
    pending = [t for t in led if t.get("status") == "PENDING_ORDER"]
    filled = [t for t in led if t.get("status") == "FILLED"]
    targets = [t for t in pending + filled]
    if not targets:
        return 0, 0
    codes = sorted({t["code"] for t in targets})
    px = realtime_prices(codes)
    n_fill = 0
    n_close = 0
    for t in targets:
        _info = px.get(t["code"])
        # 兼容新旧结构：dict（新，含 prev）或 float（旧）
        cur_px = _info.get("px") if isinstance(_info, dict) else _info
        # FIX(2026-08-22): skip 0/None prices — Sina returns 0.00 off-hours/failure;
        # treating 0 as "break SL" caused mass -100% SL_HIT on all positions.
        if cur_px is None or cur_px <= 0:
            continue
        # FIX(2026-08-22): record price snapshot for analysis/review
        _append_realtime_log({
            "ts": time.strftime("%Y-%m-%d %H:%M:%S"),
            "code": t["code"], "name": t.get("name", ""), "price": cur_px,
            "status": t["status"],
            "mark_pnl_pct": round((cur_px / (t.get("filled_price") or t.get("entry_price") or 1) - 1) * 100, 2)
            if (t.get("filled_price") or t.get("entry_price")) else None,
        })
        if t["status"] == "PENDING_ORDER":
            # FIX(2026-09-04, 审计 P2): 停牌无法买入（量=0，跳过）
            if _is_suspended(_info):
                continue
            # FIX(2026-09-04, 审计 P2): 涨停无法买入（挂单不成交，等待回落）
            if _is_limit_up(_info, side="buy"):
                continue
            # FIX(2026-08-22): retrace limit fill (研究: +0.47pp vs pure open)
            # fill at limit if price retraces to it; else fallback to T+1 open
            # FIX(2026-09-04): 成交价加买入滑点 (× (1+SLIPPAGE))，对齐实盘成本
            _was_pending = True
            if t.get("entry_mode") == "retrace":
                if cur_px <= t["entry_price"]:
                    t["status"] = "FILLED"
                    t["filled_price"] = round(t.get("entry_price") * (1 + SLIPPAGE), 3)
                    t["filled_at"] = time.strftime("%Y-%m-%d %H:%M:%S")
                    n_fill += 1
                elif t.get("t1_open") and not t.get("_retrace_open_done"):
                    # first check after open with no retrace → fallback to T+1 open
                    t["status"] = "FILLED"
                    t["filled_price"] = round(t.get("t1_open") * (1 + SLIPPAGE), 3)
                    t["filled_at"] = time.strftime("%Y-%m-%d %H:%M:%S")
                    n_fill += 1
                elif not t.get("_retrace_open_done"):
                    # no t1_open known → fill at current
                    t["status"] = "FILLED"
                    t["filled_price"] = round(cur_px * (1 + SLIPPAGE), 3)
                    t["filled_at"] = time.strftime("%Y-%m-%d %H:%M:%S")
                    n_fill += 1
            elif t.get("entry_mode") == "next_open":
                t["status"] = "FILLED"
                t["filled_price"] = round(t.get("entry_price") * (1 + SLIPPAGE), 3)
                t["filled_at"] = time.strftime("%Y-%m-%d %H:%M:%S")
                n_fill += 1
            elif cur_px <= t["entry_price"]:
                t["status"] = "FILLED"
                t["filled_price"] = round(cur_px * (1 + SLIPPAGE), 3)
                t["filled_at"] = time.strftime("%Y-%m-%d %H:%M:%S")
                n_fill += 1
            # FIX(2026-08-22): 买入交易日志（时间/信号/动作/TP/SL）
            if t["status"] == "FILLED" and not t.get("_trade_logged_buy"):
                t["_trade_logged_buy"] = True
                _append_trade_log({
                    "ts": time.strftime("%Y-%m-%d %H:%M:%S"), "code": t["code"], "name": t.get("name", ""),
                    "action": "BUY", "signal_combo": t.get("signal_combo", t.get("source", "")),
                    "signal_date": t.get("signal_date", ""), "entry_price": t.get("filled_price") or t.get("entry_price"),
                    "tp_price": t.get("tp4", t.get("tp_price")), "sl_price": t.get("sl1", t.get("sl_price")),
                    "trigger": t.get("trigger", "T+1开盘/回踩"), "pnl_pct": None,
                })
        elif t["status"] == "FILLED":
            # FIX(2026-09-04, 审计 P2): 停牌无法卖出（量=0，跳过平仓判定）
            if _is_suspended(_info):
                continue
            # FIX(2026-09-04, 审计 P2): 跌停无法卖出（跳过平仓判定，避免按跌停价错误成交）
            if _is_limit_up(_info, side="sell"):
                continue
            ep = t["filled_price"] or t["entry_price"]
            # FIX(2026-09-04, 策略层): 卖出执行价 = 实时价 × (1 - SLIPPAGE)（卖出滑点）
            _sell_px = cur_px * (1 - SLIPPAGE)
            # FIX(2026-08-22): A股 T+1 规则 —— 买入当日不可卖出，TP/SL 无法生效
            _today = time.strftime("%Y-%m-%d")
            if t.get("filled_at") and str(t["filled_at"])[:10] == _today:
                t["mark_price"] = cur_px
                t["mark_pnl_pct"] = round((cur_px / ep - 1) * 100, 4)
                t["t1_locked"] = True  # T+1 锁定（今日买入不可卖）
                continue
            t["t1_locked"] = False
            # continuation leg: adaptive hold (market state) — FIX(2026-08-28)
            if t.get("source") == "CONT" and t.get("filled_at"):
                hold = int(t.get("hold") or 10)
                try:
                    _pr_hold = _market_proxy(t["code"])
                    if _pr_hold is not None:
                        hold = adaptive_hold(hold, _pr_hold)
                except Exception:
                    pass
                # compute exit when hold days elapsed (approx: use filled_at + hold days vs now)
                try:
                    from datetime import datetime as _dt
                    fdt = _dt.strptime(str(t["filled_at"])[:10], "%Y-%m-%d")
                    days = (time.time() - fdt.timestamp()) / 86400
                    if days >= hold:
                        t["status"] = "CLOSED"
                        t["exit_reason"] = "HOLD_EXIT"
                        t["pnl_pct"] = round((_sell_px / ep - 1) * 100 - FEE, 4)
                        n_close += 1
                except Exception:
                    pass
            if t["status"] == "FILLED":
                # FIX(2026-08-22): multi-tiered TP/SL (swing + FVG + BSL)
                # FIX(2026-08-22): 合同对齐回测 —— TP1 30% 部分平仓（记录 realized_pnl），剩余 70% 继续
                tp1 = t.get("tp1") or 0
                tp2 = t.get("tp2") or 0
                tp3 = t.get("tp3") or 0
                tp4 = t.get("tp4") or t.get("tp_price") or 0
                sl1 = t.get("sl1") or t.get("sl_price") or 0
                sl2 = t.get("sl2") or 0
                # FIX(2026-08-22) P1: SL 距离 >8% → 降仓标记（风险控制）
                if not t.get("_sl_far_flagged") and (ep - sl1) / ep > 0.08:
                    t["_sl_far_flagged"] = True
                    t["position_scale"] = 0.5  # 降仓 50%
                active_sl = sl1
                if t.get("tp1_hit") and t.get("sl_price", 0) < ep:
                    active_sl = ep  # breakeven after TP1
                if t.get("tp2_hit") and t.get("sl_price", 0) < (tp1 or ep):
                    active_sl = tp1 or ep  # lock TP1 profit after TP2
                # FIX(2026-08-22) P1: 5 交易日时间止损（入场后未触 TP1 全仓离场）
                if not t.get("tp1_hit") and t.get("filled_at"):
                    try:
                        _bs = bars_of(t["code"])
                        _ds = [b["t"] for b in _bs]
                        _fd = str(t["filled_at"])[:10].replace("-", "")
                        if _fd in _ds:
                            _fi = _ds.index(_fd)
                            _today = _ds[-1] if _ds else ""
                            if _fi + 5 < len(_ds) and _ds[_fi + 5] <= _today:
                                t["status"] = "CLOSED"
                                t["exit_reason"] = "TIME_STOP"
                                _rem = 1.0
                                t["pnl_pct"] = round((t.get("realized_pnl", 0) or 0) + _rem * (_sell_px / ep - 1) * 100 - FEE * _rem, 4)
                                n_close += 1
                    except Exception:
                        pass
                if cur_px <= active_sl:
                    t["status"] = "CLOSED"
                    t["exit_reason"] = "SL_HIT"
                    _rem = 0.7 if t.get("tp1_hit") else 1.0
                    t["pnl_pct"] = round((t.get("realized_pnl", 0) or 0) + _rem * (_sell_px / ep - 1) * 100 - FEE * _rem, 4)
                    n_close += 1
                elif not t.get("tp1_hit") and tp1 > 0 and cur_px >= tp1:
                    t["tp1_hit"] = True
                    # TP1 30% 部分平仓（与回测合同一致）
                    t["realized_pnl"] = 0.3 * (tp1 / ep - 1) * 100 - FEE * 0.3
                    t["note"] = (t.get("note", "") + " | TP1(swing high)触发：30%平仓+" + str(round((tp1/ep-1)*100,2)) + "%，SL移保本").strip()
                elif not t.get("tp2_hit") and t.get("tp1_hit") and tp2 > 0 and cur_px >= tp2:
                    t["tp2_hit"] = True
                    t["realized_pnl"] = (t.get("realized_pnl", 0) or 0) + 0.7 * (tp2 / ep - 1) * 100 - FEE * 0.7
                    t["note"] = (t.get("note", "") + " | TP2(FVG/BSL)触发：70%平仓+" + str(round((tp2/ep-1)*100,2)) + "%").strip()
                elif not t.get("tp3_hit") and t.get("tp2_hit") and tp3 > 0 and cur_px >= tp3:
                    t["tp3_hit"] = True
                    t["note"] = (t.get("note", "") + " | TP3(流动性池)触发").strip()
                elif t.get("tp3_hit") and tp4 > 0 and cur_px >= tp4:
                    t["status"] = "CLOSED"
                    t["exit_reason"] = "TP4_RUNNER"
                    t["pnl_pct"] = round((t.get("realized_pnl", 0) or 0) + 0.7 * (_sell_px / ep - 1) * 100 - FEE * 0.7, 4)
                    n_close += 1
            t["mark_price"] = cur_px
            t["mark_pnl_pct"] = round((cur_px / ep - 1) * 100, 4)
            # FIX(2026-08-22): 卖出交易日志（时间/信号/动作/TP/SL/触发类型/盈亏）
            if t["status"] == "CLOSED" and not t.get("_trade_logged_sell"):
                t["_trade_logged_sell"] = True
                _append_trade_log({
                    "ts": time.strftime("%Y-%m-%d %H:%M:%S"), "code": t["code"], "name": t.get("name", ""),
                    "action": "SELL", "signal_combo": t.get("signal_combo", t.get("source", "")),
                    "signal_date": t.get("signal_date", ""), "entry_price": t.get("filled_price") or t.get("entry_price"),
                    "tp_price": t.get("tp4", t.get("tp_price")), "sl_price": t.get("sl1", t.get("sl_price")),
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
