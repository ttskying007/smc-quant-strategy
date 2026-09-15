# -*- coding: utf-8 -*-
"""industry_map.py —— R35(第八轮审计): A股行业映射单一事实源(行业集中度门数据源).

背景(审计遗留项"行业上限数据源"): DailyPortfolioEngine/throttle_open 早有
max_sector 集中度门, 但生产 paper_sim 的两处 gate 调用(L646/L1367)一直传
空 sector_counts —— 门存在但无数据, 等于没接。R35 落地数据源并接线:

数据源: baostock 证监会行业分类(hermes/data/industry_map.json, 5530 股 /
84 行业, updateDate 2026-06-22, 原始导出于 smc_audit/v225_* 探针)。行业
归属变化低频(季更), 三个月快照可接受; 需刷新时重跑 v225 导出覆盖该文件。

语义设计(fail-open, 与枚举守卫兼容):
  - 缺映射/缺行业字段 → "UNKNOWN"(计入 UNKNOWN 桶, 不误杀订单);
  - 文件缺失/损坏 → get_industry 恒 "UNKNOWN" 并只记一次告警 —— 行业门是
    组合优化约束, 非安全约束, 数据缺失时放行(别把门变成停机单点);
  - 候选桶计数 sector_counts(order_codes) 供 throttle_open: 同行业
    已挂单/持仓数(不含本单), max_sector=3 语义 = "该行业已有 3 单则拒第 4".

缓存: 模块级 dict 单例, 首次调用加载(约 1.2MB/5530 行, <100ms);
生产 monitor 每次撮合调用零额外 IO(dict 查询)。

R35(2026-09-14): 初版。
"""
import json
import os
import threading

_HERE = os.path.dirname(os.path.abspath(__file__))
_DEFAULT_MAP = os.path.normpath(os.path.join(
    _HERE, "..", "..", "hermes", "data", "industry_map.json"))

_lock = threading.Lock()
_cache = None            # code6 -> industry(str, 无映射="UNKNOWN")
_warned_missing = False  # 文件缺失只告警一次(防日志刷屏)


def _load_map(path):
    """读行业映射 → {code6: industry}。异常/缺失 → None(fail-open)。"""
    try:
        with open(path, encoding="utf-8") as f:
            rows = json.load(f)
        m = {}
        for r in rows if isinstance(rows, list) else []:
            sym = str(r.get("symbol") or "")
            ind = str(r.get("industry") or "").strip()
            code6 = sym.split(".")[0]
            if code6.isdigit() and ind:
                m[code6] = ind
        return m if m else None
    except Exception:
        return None


def _get_cache():
    global _cache, _warned_missing
    if _cache is not None:
        return _cache
    with _lock:
        if _cache is not None:
            return _cache
        path = os.environ.get("SMC_INDUSTRY_MAP", _DEFAULT_MAP)
        loaded = _load_map(path) if os.path.exists(path) else None
        if loaded is None and not _warned_missing:
            _warned_missing = True
            # fail-open: 门是组合约束非安全约束 —— 数据缺失放行, 只告警
            print(f"[industry_map] R35: 行业映射缺失/损坏({path}) → 行业门降级 UNKNOWN(放行)",
                  flush=True)
        _cache = loaded if loaded is not None else {}
        return _cache


def get_industry(code):
    """单股行业。code 兼容 '000001'/'000001.SZ'/'sz000001' → code6。
    无映射 → 'UNKNOWN'(fail-open, 不抛异常)。"""
    code6 = "".join(ch for ch in str(code or "").split(".")[0]
                    if ch.isdigit())[:6]
    return _get_cache().get(code6, "UNKNOWN")


def sector_counts(codes, exclude=None):
    """候选行业桶计数(供 throttle_open 的 sector_counts 参数)。
    codes: iterable(账本 live 条目 code); exclude: 跳过的 code(本单自身)。
    返回 {industry: n} —— 只含映射到的行业; UNKNOWN 不参与集中度门
    (无映射股不应因数据缺失被行业门拦截, 也无法归桶)。"""
    out = {}
    for c in codes:
        c6 = str(c or "")
        if exclude is not None and c6 == str(exclude or ""):
            continue
        ind = get_industry(c6)
        if ind == "UNKNOWN":
            continue
        out[ind] = out.get(ind, 0) + 1
    return out


def coverage(codes):
    """覆盖率体检: codes 中有行业映射的比例(测试/巡检用)。"""
    codes = list(codes or [])
    if not codes:
        return {"n": 0, "mapped": 0, "coverage": None}
    mapped = sum(1 for c in codes if get_industry(c) != "UNKNOWN")
    return {"n": len(codes), "mapped": mapped,
            "coverage": round(mapped / len(codes), 4)}


def reset_cache_for_tests():
    """测试钩子: 清缓存 + 重置告警开关(隔离测试)。"""
    global _cache, _warned_missing
    with _lock:
        _cache = None
        _warned_missing = False
