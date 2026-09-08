# -*- coding: utf-8 -*-
"""弱市仓位加权 A/B 验证（regime 发现的正面应用）
背景: regime_gate_ab 发现事件腿为逆向策略 —— 弱市(proxy<0)信号质量最高(avg+6.6%/PF6.6)，
      但反向闸门(只做弱市)因错过一半交易绝对收益反降(-16%)。
本验证: 不跳过信号, 而是"弱市加仓" —— 保留全部交易, 仓位按市场状态加权:
  权重 w = clip(w_base × (1 - k×proxy), 0.3, 2.0)  (proxy 越弱仓位越大)
  对比 OOS 组合: 等权基线 vs 弱市加权(k=2/4/8)
  指标: 累计收益(绝对) + 组合MDD(等权下=avg序列) + 风险调整(收益/MDD)
预注册: 若 OOS 加权后 累计收益提升 且 MDD 不显著恶化 → 建议启用弱市加权
"""
import csv, io, json, os, sys, random
import numpy as np
sys.path.insert(0, r"E:\test\smc_project\research")
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

KT = r"E:\test\smc_project\hermes\kline_cache_tencent"

# ---- 市场 proxy 重建（同 regime_gate_ab）----
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

def proxy_at(d8):
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

_cal_raw = json.load(open(os.path.join(KT, "000001_SZ_daily_800.json"), encoding="utf-8"))
_cal = []
for r in _cal_raw:
    t = "".join(c for c in str(r.get("t") or "") if c.isdigit())[:8]
    if t:
        _cal.append(t)
_cal.sort()
_cal_set = set(_cal)

def prev_td(d8):
    i = _cal.index(d8) if d8 in _cal_set else -1
    return _cal[i - 1] if i > 0 else None

# ---- 事件腿交易 + proxy ----
CSV = r"E:\test\smc_project\research\combo_v20f_trades.csv"
rows = [r for r in csv.DictReader(open(CSV, encoding="utf-8-sig"))
        if r.get("src") == "EVENT" and r.get("net_pnl_pct") not in (None, "", "None")]
for r in rows:
    r["net_pnl_pct"] = float(r["net_pnl_pct"])

proxy_cache = {}
trades_p = []
for r in rows:
    sig_d = prev_td(r["entry_date"])
    if not sig_d:
        continue
    if sig_d not in proxy_cache:
        proxy_cache[sig_d] = proxy_at(sig_d)
    p = proxy_cache[sig_d]
    if p is None:
        continue
    trades_p.append({"r": r, "proxy": p, "oos": r["entry_date"] >= "20250701"})
print(f"带proxy交易: {len(trades_p)} | OOS: {sum(1 for t in trades_p if t['oos'])}")

# ---- 组合模拟（按交易顺序累计, 真实仓位模型）----
def position_pct(r):
    """paper_sim 风险归一仓位: 固定风险预算1% / (入场-SL)%, 单票上限25%。
    FIX: 用 CSV 的 risk_pct 字段(risk/entry%) 还原 position_pct。"""
    rp = r.get("risk_pct")
    try:
        rp = float(rp)
    except (TypeError, ValueError):
        return 0.01
    if rp is None or rp <= 0:
        return 0.01
    p = min(1.0 / rp, 0.25)  # 1% 风险预算 / 风险距离%
    return max(0.01, p)


def simulate(ts, k):
    """k=加权系数: w = clip(1 - k*proxy, 0.3, 2.0)。等权=全1。
    FIX: 每笔收益贡献 = position_pct × (net/100) × w —— 真实仓位, 非全仓复利。"""
    equity = 1.0
    peak = 1.0
    mdd = 0.0
    for t in ts:
        w = 1.0
        if k > 0:
            w = max(0.3, min(2.0, 1.0 - k * t["proxy"]))
        pos = position_pct(t["r"])
        pnl = (t["r"]["net_pnl_pct"] / 100) * pos * w  # 仓位权重 × 真实仓位
        equity *= (1 + pnl)
        peak = max(peak, equity)
        mdd = max(mdd, (peak - equity) / peak)
    return equity, mdd


def report(ts, k):
    eq, mdd = simulate(ts, k)
    pn = [t["r"]["net_pnl_pct"] for t in ts]
    w = [x for x in pn if x > 0]
    l = [x for x in pn if x <= 0]
    pf = sum(w) / abs(sum(l)) if l else 99
    # 风险调整: 每单位回撤的累计收益
    ret_ratio = (eq - 1) / mdd if mdd > 0 else 0
    return {"eq": round(eq, 4), "mdd": round(mdd * 100, 2), "avg": round(sum(pn) / len(pn), 3),
            "pf": round(pf, 2), "ret_mdd": round(ret_ratio, 2)}

oos = [t for t in trades_p if t["oos"]]
print("\n== OOS 组合模拟 ==")
print(f"  等权基线:      {report(oos, 0)}")
res = {}
for k in (2, 4, 8):
    r = report(oos, k)
    res[k] = r
    print(f"  弱市加权 k={k}: {r}")

# 预注册判定
base = report(oos, 0)
best = max(res.items(), key=lambda kv: kv[1]["ret_mdd"])
verdict = "建议启用弱市加权" if best[1]["eq"] > base["eq"] and best[1]["mdd"] <= base["mdd"] * 1.3 else "不建议(绝对收益未提升或MDD恶化)"
print(f"\n最优: k={best[0]} eq={best[1]['eq']} vs 基线{base['eq']} | mdd={best[1]['mdd']}% vs {base['mdd']}% | ret/mdd={best[1]['ret_mdd']} vs {base['ret_mdd']}")
print(f"结论: {verdict}")

out = {"asof": __import__("time").strftime("%Y-%m-%d %H:%M:%S"),
       "baseline": report(oos, 0), "weighted": res, "best_k": best[0], "verdict": verdict}
with open(r"E:\test\smc_project\research\handover\弱市仓位加权AB验证.json", "w", encoding="utf-8") as fh:
    json.dump(out, fh, ensure_ascii=False, indent=2)
print("已写 handover/弱市仓位加权AB验证.json")