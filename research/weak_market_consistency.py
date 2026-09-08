# -*- coding: utf-8 -*-
"""弱市加权一致性检验: IS/OOS 双段 + 加权规则稳定性(k 扫描)
启用前必须确认: ① IS/OOS 方向一致(非OOS巧合) ② k 扫描平滑(非尖峰) ③ 加权不破坏MDD预算
"""
import csv, io, json, os, sys, random
import numpy as np
sys.path.insert(0, r"E:\test\smc_project\research")
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

KT = r"E:\test\smc_project\hermes\kline_cache_tencent"
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

def position_pct(r):
    rp = r.get("risk_pct")
    try:
        rp = float(rp)
    except (TypeError, ValueError):
        return 0.01
    if rp is None or rp <= 0:
        return 0.01
    return max(0.01, min(1.0 / rp, 0.25))

def simulate(ts, k):
    equity = 1.0
    peak = 1.0
    mdd = 0.0
    for t in ts:
        w = 1.0 if k == 0 else max(0.3, min(2.0, 1.0 - k * t["proxy"]))
        pos = position_pct(t["r"])
        equity *= (1 + (t["r"]["net_pnl_pct"] / 100) * pos * w)
        peak = max(peak, equity)
        mdd = max(mdd, (peak - equity) / peak)
    return equity, mdd

IS = [t for t in trades_p if not t["oos"]]
OOS = [t for t in trades_p if t["oos"]]
print(f"IS: {len(IS)} 笔 | OOS: {len(OOS)} 笔")

print("\n== IS/OOS 双段 k 扫描（ret/MDD 风险调整）==")
print("  k   |  IS eq | IS mdd | IS r/m | OOS eq | OOS mdd | OOS r/m")
for k in (0, 2, 4, 8):
    ie, im = simulate(IS, k)
    oe, om = simulate(OOS, k)
    ir = (ie - 1) / im if im > 0 else 0
    orr = (oe - 1) / om if om > 0 else 0
    print(f"  {k:>2} | {ie:6.2f} | {im*100:5.1f}% | {ir:6.1f} | {oe:6.2f} | {om*100:5.1f}% | {orr:6.1f}")

print("\n== 判定 ==")
# IS 与 OOS 都随 k 提升 → 稳健；仅一段提升 → 谨慎
for k in (2, 4, 8):
    ie, im = simulate(IS, k)
    oe, om = simulate(OOS, k)
    base_i = simulate(IS, 0); base_o = simulate(OOS, 0)
    up_i = ie > base_i[0]
    up_o = oe > base_o[0]
    print(f"  k={k}: IS{'↑' if up_i else '↓'}({ie:.2f} vs {base_i[0]:.2f}) | OOS{'↑' if up_o else '↓'}({oe:.2f} vs {base_o[0]:.2f})")

print("\n结论: IS/OOS 双段一致提升 → 弱市加权稳健, 可启用; 仅OOS提升 → 保守(k=2)试用")
# 落盘
out = {"asof": __import__("time").strftime("%Y-%m-%d %H:%M:%S"),
       "scan": {str(k): {"IS_eq": simulate(IS, k)[0], "IS_mdd": round(simulate(IS, k)[1]*100, 2),
                          "OOS_eq": simulate(OOS, k)[0], "OOS_mdd": round(simulate(OOS, k)[1]*100, 2)}
                for k in (0, 2, 4, 8)}}
with open(r"E:\test\smc_project\research\handover\弱市加权一致性检验.json", "w", encoding="utf-8") as fh:
    json.dump(out, fh, ensure_ascii=False, indent=2)
print("已写 handover/弱市加权一致性检验.json")