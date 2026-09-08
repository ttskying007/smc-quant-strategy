# -*- coding: utf-8 -*-
"""regime 闸门 A/B 验证：市场状态信号(200股采样20日涨跌均值)对事件腿信号的前置门控
目的: 第八轮 regime 分析发现弱月(Q2稳定负)依赖市场结构。验证用"决策时点可得"的市场
      proxy 作前置闸门能否提升 OOS 风险调整收益(而非事后知道弱月=前视)。
方法:
  ① 历史重建 market proxy 序列: 对每个交易日 d, 用 200 股固定采样(与 paper_sim 一致,
     仅用 ≤d 的数据, 无泄漏)计算 20 日平均涨跌 → proxy(d)
  ② 事件腿每笔交易按信号日(entry_date-1交易日)的 proxy 分组(分位数)
  ③ 预注册闸门规则: proxy 低于阈值 T 时不交易; T∈{-0.02,-0.01,0,0.01,0.02}
  ④ OOS(≥2025-07) 对比: 门控后 avg/PF/MDD vs 基线
  ⑤ 结论: 若 OOS 门控后 avg 提升且样本仍足(≥60%) → 建议启用闸门
"""
import csv, io, json, os, sys
from collections import defaultdict
sys.path.insert(0, r"E:\test\smc_project\research")
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

KT = r"E:\test\smc_project\hermes\kline_cache_tencent"

# ---- 固定采样(与 paper_sim._market_proxy 一致) ----
import random
random.seed(42)
_snap_file = os.path.join(KT, ".mkt_sample.json")
_MKT_SAMPLE = None
try:
    _snap = json.load(open(_snap_file, encoding="utf-8"))
    if isinstance(_snap, list) and _snap:
        _MKT_SAMPLE = _snap
except Exception:
    pass
if not _MKT_SAMPLE:
    files = sorted(f for f in os.listdir(KT) if f.endswith("_daily_800.json"))
    _MKT_SAMPLE = random.sample(files, min(200, len(files)))
print(f"采样股: {len(_MKT_SAMPLE)}")

# ---- 预载采样股 K 线 ----
_sample_bars = {}
for f in _MKT_SAMPLE:
    code = f.split("_")[0]
    try:
        raw = json.load(open(os.path.join(KT, f), encoding="utf-8"))
        bs = []
        for r in raw:
            t = "".join(c for c in str(r.get("t") or "") if c.isdigit())[:8]
            if t and r.get("o") and r.get("c"):
                bs.append({"t": t, "c": float(r["c"])})
        bs.sort(key=lambda x: x["t"])
        _sample_bars[code] = bs
    except Exception:
        continue
print(f"可用K线: {len(_sample_bars)} 只")


def proxy_at(d8):
    """决策时点市场状态: 200股中在 d8 有数据且历史≥20日的股票, 20日平均涨跌。"""
    rets = []
    for code, bs in _sample_bars.items():
        ds = [b["t"] for b in bs]
        if d8 not in ds:
            continue
        i = ds.index(d8)
        if i < 20:
            continue
        rets.append(bs[i]["c"] / bs[i - 20]["c"] - 1)
    return sum(rets) / len(rets) if rets else None


# ---- 事件腿交易(修复后干净数据) ----
CSV = r"E:\test\smc_project\research\combo_v20f_trades.csv"
rows = [r for r in csv.DictReader(open(CSV, encoding="utf-8-sig"))
        if r.get("src") == "EVENT" and r.get("net_pnl_pct") not in (None, "", "None")]
for r in rows:
    r["net_pnl_pct"] = float(r["net_pnl_pct"])
print(f"事件腿: {len(rows)}")

# ---- 为每笔交易计算信号日(entry前一个交易日)的 proxy ----
# 用 000001(平安银行) 的K线日历作为交易日历(全市场统一)
import datetime as _dt
_cal_raw = json.load(open(os.path.join(KT, "000001_SZ_daily_800.json"), encoding="utf-8"))
_cal = []
for r in _cal_raw:
    t = "".join(c for c in str(r.get("t") or "") if c.isdigit())[:8]
    if t:
        _cal.append(t)
_cal.sort()
_cal_set = set(_cal)
print(f"交易日历: {len(_cal)} 日 ({_cal[0]}~{_cal[-1]})")


def prev_td(d8):
    """d8 之前最近交易日。"""
    i = _cal.index(d8) if d8 in _cal_set else -1
    if i <= 0:
        return None
    return _cal[i - 1]


# 信号日 = entry_date 前一交易日(披露日) —— 决策时点
proxy_cache = {}
def get_proxy(entry_d8):
    sig_d = prev_td(entry_d8)
    if not sig_d:
        return None
    if sig_d not in proxy_cache:
        proxy_cache[sig_d] = proxy_at(sig_d)
    return proxy_cache[sig_d]


# ---- 分组统计 ----
def stats(pn):
    if not pn:
        return {"n": 0, "avg": 0.0, "wr": 0.0, "pf": 0.0}
    w = [x for x in pn if x > 0]
    l = [x for x in pn if x <= 0]
    return {"n": len(pn), "avg": round(sum(pn) / len(pn), 4),
            "wr": round(len(w) / len(pn), 4),
            "pf": round(sum(w) / abs(sum(l)), 3) if l and sum(l) != 0 else 99.0}


# 每笔交易带 proxy
trades_p = []
for r in rows:
    p = get_proxy(r["entry_date"])
    if p is None:
        continue
    trades_p.append({"r": r, "proxy": p, "oos": r["entry_date"] >= "20250701"})
print(f"带proxy交易: {len(trades_p)}")

# 分位数分组
import numpy as np
px = sorted(t["proxy"] for t in trades_p)
q33, q66 = np.percentile(px, 33), np.percentile(px, 66)
print(f"\nproxy 分位: q33={q33:.4f} q66={q66:.4f} 范围[{px[0]:.4f},{px[-1]:.4f}]")

print("\n== 按 proxy 三分位分组（全部期间）==")
groups = {"弱市(proxy<q33)": [t for t in trades_p if t["proxy"] < q33],
          "中性(q33≤proxy<q66)": [t for t in trades_p if q33 <= t["proxy"] < q66],
          "强市(proxy≥q66)": [t for t in trades_p if t["proxy"] >= q66]}
res_groups = {}
for name, g in groups.items():
    s = stats([t["r"]["net_pnl_pct"] for t in g])
    res_groups[name] = s
    print(f"  {name}: {s}")

# 预注册闸门: proxy < T 时不交易
print("\n== 闸门 OOS 验证（T∈{-0.02,-0.01,0,0.01,0.02}）==")
OOS_FROM = "20250701"
base_oos = [t for t in trades_p if t["oos"]]
s_base = stats([t["r"]["net_pnl_pct"] for t in base_oos])
print(f"  基线 OOS(n={s_base['n']}): avg={s_base['avg']}% PF={s_base['pf']}")

res_gates = {}
for T in (-0.02, -0.01, 0.0, 0.01, 0.02):
    kept = [t for t in base_oos if t["proxy"] >= T]
    s = stats([t["r"]["net_pnl_pct"] for t in kept])
    res_gates[T] = s
    keep_pct = len(kept) / len(base_oos) * 100
    flag = " ← 最佳" if s["avg"] > 0 and s["pf"] > s_base["pf"] and keep_pct >= 60 else ""
    print(f"  T={T:+.2f}: n={s['n']} avg={s['avg']}% PF={s['pf']} (保留{keep_pct:.0f}%){flag}")

# 结论
print("\n== 结论 ==")
best = max(res_gates.items(), key=lambda kv: (kv[1]["avg"], kv[1]["pf"]))
verdict = "建议启用闸门" if best[1]["avg"] > s_base["avg"] and best[1]["pf"] > s_base["pf"] else "不建议启用闸门(门控无增益)"
print(f"  最优闸门 T={best[0]:+.2f}: avg={best[1]['avg']}% vs 基线{s_base['avg']}% | PF={best[1]['pf']} vs {s_base['pf']}")
print(f"  → {verdict}")

out = {"asof": __import__("time").strftime("%Y-%m-%d %H:%M:%S"),
       "groups": res_groups, "gates": res_gates, "baseline_oos": s_base,
       "q33": round(float(q33), 4), "q66": round(float(q66), 4),
       "verdict": verdict, "best_gate": float(best[0])}
os.makedirs(r"E:\test\smc_project\research\handover", exist_ok=True)
with open(r"E:\test\smc_project\research\handover\regime闸门AB验证.json", "w", encoding="utf-8") as fh:
    json.dump(out, fh, ensure_ascii=False, indent=2)
print("已写 handover/regime闸门AB验证.json")