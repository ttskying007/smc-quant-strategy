# -*- coding: utf-8 -*-
"""core/alpha.py — Jensen Alpha 期望引擎(单源)

R61(用户指令: "PF-后验反推基准 + rank/gate/面板三线接入")。

口径(与冻结纪律兼容):
  基准 = combo_v22_trades.csv 全量 EVENT 腿的"同类条件后验平均净收益",
  按 (trend_state, retrace_state, stage类) 条件桶分箱 —— PF-后验反推:
    α_leg = 该腿实际净收益 − 同桶历史平均净收益  (已实现腿的后验 α)
    α_expect(新候选) = 候选命中最细桶的历史平均净收益 − 全体平均净收益
      (前向期望超额, 1日滞后: 候选评估只用上一数据周期产出的基准表)
  手续费已在 net_pnl_pct 中扣除(cost_model v1), α 为净超额。

基准表由 gen_alpha_benchmark.py 生成 → research/alpha_benchmark.json。
alpha 引擎运行时只读该文件; 文件缺失时软失败(返回 None 或 naive), 绝不阻断选股。

三层消费(全部不破坏现有行为):
  1) rank 分量: paper_sim 在挂单单字典中加入 alpha_score/alpha_bucket(仅记录)
  2) gate:  CFG.ALPHA_GATE_MODE ('shadow'|'enforce'|'off')
      shadow=记录"若拦截会拦掉什么"到 selection_funnel/ledger 但不弃单;
      enforce=α_expect < CFG.ALPHA_GATE_MIN (默认 -1.0%) 才拒绝
  3) 面板: 前端 /kline 链面板 + /monitor 挂单表显示 α_expect
"""
import json, os
from collections import defaultdict

ROOT_BENCH = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                          "alpha_benchmark.json")

_bench_cache = {"mtime": None, "data": None}


def _load_bench():
    try:
        m = os.path.getmtime(ROOT_BENCH)
        if _bench_cache["data"] is not None and _bench_cache["mtime"] == m:
            return _bench_cache["data"]
        with open(ROOT_BENCH, encoding="utf-8") as fh:
            _bench_cache["data"] = json.load(fh)
            _bench_cache["mtime"] = m
        return _bench_cache["data"]
    except Exception:
        return None


def _bucket_keys(chain, stage):
    if not chain or not (chain or {}).get("trend_state") or (chain.get("trend_state") == "none"):
        return None  # 无链信息 → alpha 无基准意义, 软失败
    trend = chain["trend_state"]
    retr = ((chain or {}).get("retrace") or {}).get("state") or "no_retrace"
    stg = stage if stage in ("ACCUM", "DOWNTREND") else "OTHER"
    return trend, retr, stg


def alpha_expect(chain, stage="DOWNTREND"):
    """前向期望 Jensen Alpha(净超额, 百分数)。无基准表 → None(软失败)。
    返回 dict: {alpha_expect, bucket_n, bucket_key, bench_avg, global_avg, bench_date}"""
    b = _load_bench()
    if not b:
        return None
    keys = _bucket_keys(chain, stage)
    if keys is None:
        return None
    trend, retr, stg = keys
    buckets = b.get("buckets", {})
    b = _load_bench()
    if not b:
        return None
    trend, retr, stg = _bucket_keys(chain, stage)
    buckets = b.get("buckets", {})
    ga = float(b.get("global_avg") or 0)
    # 最细桶 → 逐级退化
    for key in (f"{trend}|{retr}|{stg}", f"{trend}|{retr}|*", f"{trend}|*|*", "*|*|*"):
        cell = buckets.get(key)
        if cell and cell.get("n", 0) >= 10:
            return {"alpha_expect": round(cell["avg"] - ga, 2),
                    "bucket_n": cell["n"], "bucket_key": key,
                    "bucket_avg": round(cell["avg"], 2), "global_avg": round(ga, 2),
                    "bench_date": b.get("generated_at", "")}
    return None


def alpha_realized(net_pnl_pct, chain, stage="DOWNTREND"):
    """已实现腿的后验 α = 实际净收益 − 同桶历史平均。用于回测审计列。"""
    b = _load_bench()
    if not b:
        return None
    trend, retr, stg = _bucket_keys(chain, stage)
    buckets = b.get("buckets", {})
    ga = float(b.get("global_avg") or 0)
    for key in (f"{trend}|{retr}|{stg}", f"{trend}|{retr}|*", f"{trend}|*|*", "*|*|*"):
        cell = buckets.get(key)
        if cell and cell.get("n", 0) >= 10:
            return round(float(net_pnl_pct) - cell["avg"], 2)
    return round(float(net_pnl_pct) - ga, 2)
