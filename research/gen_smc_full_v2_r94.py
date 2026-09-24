# -*- coding: utf-8 -*-
r"""R94 — enrich 字段全量在 v2/norm detector 下重铸 (combo_v22_smc_full_v2.csv)

R93 发现: s1/s7 (chain v2 字段) 不行没法治住 v24 掉到 5.63;
而 s8~s12 这 5 个手术仍用的是 v25 fixed detector 产的 sweep/mss/ote/ob/fvg 字段,
另一个毒系 (固定 wing/pen) 未一起 norm —— 本轮把这 5 个也换 norm.

数据族路线: 同 r76 (gen_smc_full_r76.py) 但:
  1. detector 用 mode='norm' (R90 的参数自适应)
  2. OTE find_swings 用 pick_wing_by_density 选的 wing
  3. 输出改 combo_v22_smc_full_v2.csv (不动 r76 产物)
"""
import csv, os, json, sys, io, time
from collections import defaultdict

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
ROOT = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(ROOT, "..", "hermes", "scripts", "v25"))
from smc_detector import detect_smc_signals, find_swings, pick_wing_by_density  # noqa: E402

LEGS = os.path.join(ROOT, "combo_v22_trades.csv")
KC = os.path.normpath(os.path.join(ROOT, "..", "hermes", "kline_cache_tencent"))
OUT_CSV = os.path.join(ROOT, "combo_v22_smc_full_v2.csv")


def sym_file(sym):
    s = sym.replace(".", "_")
    if not any(s.endswith(x) for x in ("_SZ", "_SH", "_BJ")):
        if s.startswith(("6", "9")): s += "_SH"
        elif s.startswith(("4", "8")): s += "_BJ"
        else: s += "_SZ"
    return os.path.join(KC, s + "_daily_800.json")


rows = list(csv.DictReader(open(LEGS, encoding="utf-8-sig")))
out = []
cache = {}
t0 = time.time()
for idx, r in enumerate(rows):
    sym = r["symbol"]
    if sym not in cache:
        p = sym_file(sym)
        cache[sym] = json.load(open(p, encoding="utf-8")) if os.path.exists(p) else None
    bars = cache[sym]
    if not bars:
        continue
    entry_d = r["entry_date"]
    seg = [b for b in bars if str(b["t"]) <= entry_d]
    if len(seg) < 30:
        continue
    kl = [{"t": str(b["t"]), "o": float(b["o"]), "h": float(b["h"]),
           "l": float(b["l"]), "c": float(b["c"]), "v": float(b["v"])} for b in seg]
    sigs = detect_smc_signals(kl, mode='norm')
    entry_px = float(r["buy_price"] or kl[-1]["c"])
    last_close = kl[-1]["c"]

    sweeps = [s for s in sigs if "Sweep" in s.type]
    sweeps_10b = [s for s in sweeps if s.bar >= len(kl) - 12]
    my_sweep_dir = None
    if sweeps_10b:
        my_sweep_dir = "bull" if sum(1 for s in sweeps_10b if s.dir == "bull") > sum(1 for s in sweeps_10b if s.dir == "bear") else "bear"
    obs = [s for s in sigs if s.type.startswith("OB")]
    recent_ob = obs[-1] if obs else None
    in_ob = False
    ob_far = None
    if recent_ob:
        meta = recent_ob.meta or {}
        lo = float(meta.get("ob_low") or recent_ob.price)
        hi = float(meta.get("ob_high") or recent_ob.price)
        in_ob = lo <= entry_px <= hi
        if not in_ob:
            ob_far = (entry_px - hi) / hi * 100 if entry_px > hi else (lo - entry_px) / lo * -100

    fvgs = []
    n = len(kl)
    for i in range(1, n - 1):
        if kl[i + 1]["l"] > kl[i - 1]["h"]:
            fvgs.append(("bull", kl[i - 1]["h"], kl[i + 1]["l"], i))
        if kl[i + 1]["h"] < kl[i - 1]["l"]:
            fvgs.append(("bear", kl[i + 1]["h"], kl[i - 1]["l"], i))
    active_fvgs = [f for f in fvgs if f[3] >= n - 60]
    in_fvg = None
    fvg_gap_to_entry = None
    for kind, lo, hi, b in reversed(active_fvgs):
        if lo <= entry_px <= hi:
            in_fvg = kind
            break
        if kind == "bull" and entry_px < lo:
            fvg_gap_to_entry = round((lo - entry_px) / entry_px * 100, 2)
        elif kind == "bear" and entry_px > hi:
            fvg_gap_to_entry = round((entry_px - hi) / hi * 100, 2)

    highs = sorted([s for s in sigs if "swing_price" in (s.meta or {}) and s.type in ("BOS_Bull", "CHOCH_Bull")],
                   key=lambda s: -s.bar)
    lows = sorted([s for s in sigs if "swing_price" in (s.meta or {}) and s.type in ("BOS_Bear", "CHOCH_Bear")],
                  key=lambda s: -s.bar)
    bsl = highs[0].meta["swing_price"] if highs else None
    ssl = lows[0].meta["swing_price"] if lows else None
    tp = float(r.get("tp") or 0) or None
    sl = float(r.get("sl") or 0) or None

    mss = [s for s in sigs if s.type.startswith("MSS")]
    recent_mss = mss[-1] if mss else None
    mss_dir = recent_mss.dir if recent_mss else None
    mss_bars_ago = (len(kl) - 1 - recent_mss.bar) if recent_mss else None

    # OTE — 用自适应 wing
    wing, _ = pick_wing_by_density(kl)
    h_sw, l_sw = find_swings(kl, min_bars=wing)
    ote_zone = None
    if len(h_sw) >= 2 and len(l_sw) >= 2:
        candidates = [(l, h) for l in l_sw for h in h_sw if h['bar'] > l['bar'] and h['bar'] - l['bar'] < 30]
        if candidates:
            l0, h0 = candidates[-1]
            impulse_hi, impulse_lo = h0['price'], l0['price']
            if impulse_hi > impulse_lo:
                ote_lo = impulse_hi - (impulse_hi - impulse_lo) * 0.79
                ote_hi_ = impulse_hi - (impulse_hi - impulse_lo) * 0.618
                ote_zone = (ote_lo, ote_hi_)
    in_ote = False
    if ote_zone:
        in_ote = ote_zone[0] <= entry_px <= ote_zone[1]

    # LV
    atr14 = 0.0
    trs = []
    for i in range(1, len(kl)):
        b, pb = kl[i], kl[i-1]
        trs.append(max(b["h"]-b["l"], abs(b["h"]-pb["c"]), abs(b["l"]-pb["c"])))
        atr14 = sum(trs[-14:]) / min(14, len(trs))
    lvs = []
    for i in range(n - 1, max(0, n - 60), -1):
        b, pb = kl[i], kl[i-1]
        gap_up = b["l"] > pb["h"] * 1.01
        gap_dn = b["h"] < pb["l"] * 0.99
        body_m = abs(b["c"] - b["o"])
        if (gap_up or gap_dn) and body_m > atr14 * 1.5:
            lvs.append((i, "up" if gap_up else "dn", pb["c"], b["o"], body_m / max(atr14, 1e-9)))
    in_lv = False
    if lvs:
        recent_lv = lvs[0]
        _, lv_dir, lv_lo, lv_hi, _ = recent_lv
        # in_lv: 入场价在 LV 覆盖带内
        in_lv = min(lv_lo, lv_hi) <= entry_px <= max(lv_lo, lv_hi)

    out.append({**r,
                "clean_close": last_close,
                "in_fvg": in_fvg if in_fvg else "none", "fvg_gap_to_entry": fvg_gap_to_entry,
                "mss_dir": mss_dir, "mss_bars_ago": mss_bars_ago,
                "in_ote": in_ote,
                "ote_zone": [round(ote_zone[0], 2), round(ote_zone[1], 2)] if ote_zone else None,
                "in_lv": in_lv, "lvs_60b": len(lvs),
                "sweeps_10b": len(sweeps_10b), "sweep_dir": my_sweep_dir,
                "in_ob": in_ob, "ob_gap_pct": round(ob_far, 2) if ob_far else (0 if in_ob else None),
                "bsl": bsl, "ssl": ssl,
                "dist_to_ssl": round((entry_px - ssl) / ssl * 100, 2) if ssl else None,
                "dist_to_bsl": round((bsl - entry_px) / entry_px * 100, 2) if bsl else None,
                "tp_above_bsl": (tp > bsl) if (tp and bsl) else None,
                "sl_below_ssl": (sl < ssl) if (sl and ssl) else None,
                "pnl": float(r["net_pnl_pct"] or 0)})
    if idx % 300 == 299:
        print(f"  {idx+1}/{len(rows)} t={time.time()-t0:.0f}s")

print(f"R94 norm enrich legs: {len(out)} ({time.time()-t0:.0f}s)")
cols = list(out[0].keys())
with open(OUT_CSV, "w", encoding="utf-8-sig", newline="") as fh:
    w = csv.DictWriter(fh, fieldnames=cols)
    w.writeheader()
    w.writerows(out)
print(f"写完成 {os.path.basename(OUT_CSV)}")

# 快速桶对比 v1 vs v2 (仅 sweep_dir/in_ob/in_ote/mss_dir)
# 注意: out 内存对象是 bool, 需要读回 CSV 转为字符串才能比较
v1 = {r['symbol'] + '|' + r['entry_date']: r
      for r in csv.DictReader(open(os.path.join(ROOT, 'combo_v22_smc_full.csv'), encoding='utf-8-sig'))}
v2 = {r['symbol'] + '|' + r['entry_date']: r
      for r in csv.DictReader(open(OUT_CSV, encoding='utf-8-sig'))}
for fld in ('sweep_dir', 'in_ob', 'in_ote', 'mss_dir'):
    flips = sum(1 for k, r in v2.items() if (v1.get(k) or {}).get(fld) != r.get(fld))
    print(f"  {fld}: 翻转 {flips}/{len(v2)} = {flips/len(v2)*100:.1f}%")
# 各桶落地分布
for fld in ('in_ob', 'in_ote', 'sweep_dir'):
    from collections import Counter as _C
    c1 = _C(v1[k].get(fld) or '(none)' for k in v1)
    c2 = _C(v2[k].get(fld) or '(none)' for k in v2)
    print(f"  {fld} v1: {dict(c1)}")
    print(f"  {fld} v2: {dict(c2)}")
