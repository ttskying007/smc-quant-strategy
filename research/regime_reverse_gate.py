# -*- coding: utf-8 -*-
"""补充验证: 事件腿逆向特性 —— 反向闸门(只做弱市) OOS 表现
regime_gate_ab 发现: 弱市(proxy<q33)事件腿表现最佳(avg6.6%/PF6.6)
本脚本验证 OOS 内反向闸门是否提升, 并确认"事件腿=逆向策略"结论。
"""
import csv, io, json, os, sys, random
import numpy as np
sys.path.insert(0, r"E:\test\smc_project\research")
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

KT = r"E:\test\smc_project\hermes\kline_cache_tencent"

# ---- 固定采样 ----
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

# 交易日历
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

# 事件腿交易
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
print(f"带proxy交易: {len(trades_p)}")

def stats(pn):
    if not pn:
        return {"n": 0, "avg": 0.0, "wr": 0.0, "pf": 0.0}
    w = [x for x in pn if x > 0]
    l = [x for x in pn if x <= 0]
    return {"n": len(pn), "avg": round(sum(pn) / len(pn), 4),
            "wr": round(len(w) / len(pn), 4),
            "pf": round(sum(w) / abs(sum(l)), 3) if l and sum(l) != 0 else 99.0}

base_oos = [t for t in trades_p if t["oos"]]
s_base = stats([t["r"]["net_pnl_pct"] for t in base_oos])
print(f"基线 OOS(n={s_base['n']}): avg={s_base['avg']}% PF={s_base['pf']}")
print("\n== 反向闸门 OOS(proxy < T 才交易) ==")
for T in (-0.02, -0.04, -0.0678):
    kept = [t for t in base_oos if t["proxy"] < T]
    s = stats([t["r"]["net_pnl_pct"] for t in kept])
    print(f"  只做 proxy<{T:.4f}: n={s['n']} avg={s['avg']}% PF={s['pf']} (保留{len(kept)/len(base_oos)*100:.0f}%)")

oos_px = sorted(t["proxy"] for t in base_oos)
q33_oos = np.percentile(oos_px, 33)
weak = [t for t in base_oos if t["proxy"] < q33_oos]
s_w = stats([t["r"]["net_pnl_pct"] for t in weak])
print(f"\nOOS 内弱市三分位(q33={q33_oos:.4f}): n={s_w['n']} avg={s_w['avg']}% PF={s_w['pf']} (保留{len(weak)/len(base_oos)*100:.0f}%)")

print("\n== 结论 ==")
print("若弱市OOS表现仍显著优于基线 → 事件腿为逆向策略, 不应启用正向regime闸门;")
print("反向闸门(只做弱市)样本仅~33-52%, 集中度风险高, 需权衡。")