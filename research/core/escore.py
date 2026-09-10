# -*- coding: utf-8 -*-
"""core/escore.py —— V4 D1 环境门 E-score 生产模块(单一真相源)
D1 审计证据: 全期五分位 ρ=0.924 完美单调(Q1 −0.47/PF0.82 → Q5 +5.31/PF7.72),
WFO 3/4 窗稳健。D2v2/D3 弃案后, E 是事件腿唯一被确认的环境因子。

因子(决策时点 d8 无前视):
  F1 = 全市场 20D 新高占比(赚钱效应广度) —— 由调用方传入(需全市场K线, 昂贵)
  F2 = 中证1000ETF(512100) 20D 距高点(小盘风格) —— 本模块读 kline_cache_etf
  F3 = 上证指数 20D 动量
  E = 0.4×clip(F1/0.15) + 0.4×clip(−F2/0.10) + 0.2×clip(F3/0.05) ∈ [0,1]

数据陈旧处理(fail-safe 不 fail-closed: E 用于排序/仓位而非杀单):
  指数数据 > 10 个自然日未更新 → asof_stale=True, 调用方决定降权;
  512100 缺 → 回退 000300(标注 mid_proxy='000300')。

用法(研究已验, 生产接入待 SHADOW 60 日双臂后):
  from core.escore import escore_for_date, breadth_newhigh_pct
  e = escore_for_date(d8, f1=breadth_newhigh_pct(daily_map, d8))
  # 或每日累积器 escore_daily.py 预计算快照 → handover/escore_history.json
"""
import glob, json, os

ETF_DIR = r"E:\test\smc_project\hermes\kline_cache_etf"
KT = r"E:\test\smc_project\hermes\kline_cache_tencent"
STALE_DAYS = 10

_version_ = "escore_v1"


def _load_index(name):
    fp = os.path.join(ETF_DIR, name)
    if not os.path.exists(fp):
        return []
    try:
        j = json.load(open(fp, encoding="utf-8"))
    except Exception:
        return []
    bars = j if isinstance(j, list) else j.get("data") or j.get("bars") or []
    out = []
    for b in bars:
        t = str(b.get("t") or b.get("date") or "")[:10].replace("-", "")
        if len(t) == 8:
            out.append((t, float(b["c"])))
    out.sort()
    return out


def _idx_at(arr, d8, days=20):
    w = [x for x in arr if x[0] <= d8]
    if len(w) < days + 1:
        return None
    return {"r20": w[-1][1] / w[-1 - days][1] - 1,
            "off_high": w[-1][1] / max(x[1] for x in w[-days * 3:]) - 1,
            "asof": w[-1][0]}


def breadth_newhigh_pct(d8, kt_dir=KT, min_sample=200, _cache={}):
    """F1: d8 当日全市场 20D 新高占比(0-1)。结果按 d8 缓存(重复调用只算一次)。"""
    if d8 in _cache:
        return _cache[d8]
    nh = {"hit": 0, "n": 0}
    for fp in sorted(glob.glob(os.path.join(kt_dir, "*_daily_800.json"))):
        try:
            raw = json.load(open(fp, encoding="utf-8"))
        except Exception:
            continue
        cl = sorted((str(b.get("t"))[:8], float(b["c"])) for b in raw if b.get("t"))
        # 二分定位 ≤d8 的最后一根, 回看 20 根
        lo, hi = 0, len(cl)
        while lo < hi:
            mid = (lo + hi) // 2
            if cl[mid][0] <= d8:
                lo = mid + 1
            else:
                hi = mid
        k = lo - 1
        if k < 20:
            continue
        if cl[k][0] != d8:          # 当日无数据(停牌/未更新) → 不计入样本
            continue
        nh["n"] += 1
        if cl[k][1] >= max(x[1] for x in cl[k - 20:k]):
            nh["hit"] += 1
    pct = (nh["hit"] / nh["n"]) if nh["n"] >= min_sample else None
    _cache[d8] = pct
    return pct


def escore_for_date(d8, f1=None, with_meta=False):
    """决策时点 E-score。f1 可外部传入(预计算广度); None 则现算(慢, 全市场扫)。
    返回 E∈[0,1] 或 None(数据不足); with_meta=True 时返回 (E, meta)。"""
    d8 = str(d8)[:8]
    meta = {"version": _version_, "d8": d8, "f1_source": "given" if f1 is not None else "computed"}
    if f1 is None:
        f1 = breadth_newhigh_pct(d8)
    meta["f1"] = None if f1 is None else round(f1, 4)
    if f1 is None:
        return (None, meta) if with_meta else None
    # F2: 中证1000 —— 优先 canonical(SH_512100_daily.json, 由 wdh/pull_index_daily.py
    # 每日刷新); 回退 legacy 命名; 最后 000300(标注)
    mid = (_load_index("SH_512100_daily.json")
           or _load_index("512100_SH_day.json"))
    meta["mid_proxy"] = "512100"
    if not mid:
        mid = _load_index("000300_SH_day.json")
        meta["mid_proxy"] = "000300"
    sh = _load_index("SH_000001_daily.json") or _load_index("000001_SH_day.json")
    # canonical 文件优先(pull_index_daily 每日刷新); legacy 双命名兼容
    m2 = _idx_at(mid, d8)
    s3 = _idx_at(sh, d8)
    if not m2 or not s3:
        return (None, meta) if with_meta else None
    meta["f2_off_high"] = round(m2["off_high"], 4)
    meta["f3_r20"] = round(s3["r20"], 4)
    # 陈旧检测: 指数 asof 距 d8 > STALE_DAYS 自然日 → 标注(降权由调用方)
    try:
        from datetime import datetime
        dd = (datetime.strptime(d8, "%Y%m%d") - datetime.strptime(m2["asof"], "%Y%m%d")).days
        meta["mid_stale_days"] = dd
        meta["asof_stale"] = dd > STALE_DAYS
    except Exception:
        meta["asof_stale"] = None
    e = 0.4 * min(1, max(0, f1 / 0.15)) \
        + 0.4 * min(1, max(0, -m2["off_high"] / 0.10)) \
        + 0.2 * min(1, max(0, s3["r20"] / 0.05))
    e = round(e, 4)
    meta["e"] = e
    return (e, meta) if with_meta else e


def exposure_coef(e, floor=0.3):
    """E → 仓位系数映射(D1B 结论: 排序降仓不杀单)。
    预注册映射(SHADOW 验证前不进生产): E<0.33(Q1) → 0.3; 0.33-0.44 → 0.5;
    0.44-0.54 → 0.75; >0.54 → 1.0。floor 为最低系数。"""
    if e is None:
        return 1.0                     # 数据缺失 → 满仓(不杀单纪律)
    if e < 0.33:
        return floor
    if e < 0.44:
        return 0.5
    if e < 0.54:
        return 0.75
    return 1.0