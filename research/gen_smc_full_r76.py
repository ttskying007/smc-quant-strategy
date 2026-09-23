# -*- coding: utf-8 -*-
"""gen_smc_full_r76.py — R76: 用引擎真·信号链重铸 1858 腿(approve R62 口径)
从 hermes/scripts/v25/smc_detector.detect_smc_signals(klines) 取全族信号:
  BOS_Bull/Bear / CHOCH_Bull/Bear / Sweep_* / OB_* / MSS_*
每条腿, 只用入场日闭市前数据(无前视窗口), 统计:
  - sweeps_before: 近10bar之内是否有 liquidity sweep, 方向
  - dist_to_ssl/dist_to_bsl: 入场价距离最近决定性 swing 低/高的 %
  - entry_in_ob: 入场价是否落在最近 OB 内 (bull OB → 看多回踩)
  - tp_vs_bsl: TP 相对最近 BSL 的位置 (>%? TP 在 BSL 上方=撞上流动性)
  - sl_vs_ssl: SL 相对最近 SSL 的位置 (<%? SL 紧贴 SSL 下方=极容易, 反者=被扫)
  - chain_last_structure: 入场前最后一次结构事件 (BOS/CHOCH/MSS + 方向)
输出 combo_v22_smc_full.csv + R76 审计报告"""
import csv, os, json, sys, io
from collections import defaultdict

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
ROOT = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(ROOT, "..", "hermes", "scripts", "v25"))
from smc_detector import detect_smc_signals  # noqa: E402

LEGS = os.path.join(ROOT, "combo_v22_trades.csv")
KC = os.path.normpath(os.path.join(ROOT, "..", "hermes", "kline_cache_tencent"))
OUT_CSV = os.path.join(ROOT, "combo_v22_smc_full.csv")
OUT_MD = os.path.join(ROOT, "handover", "R76_smc_full_audit.md")


def sym_file(sym):
    s = sym.replace(".", "_")
    if not any(s.endswith(x) for x in ("_SZ", "_SH", "_BJ")):
        if s.startswith(("6", "9")): s += "_SH"
        elif s.startswith(("4", "8")): s += "_BJ"
        else: s += "_SZ"
    return os.path.join(KC, s + "_daily_800.json")


def load(sym):
    p = sym_file(sym)
    if not os.path.exists(p):
        return None
    return json.load(open(p, encoding="utf-8"))


def st(rs):
    n = len(rs)
    if not n:
        return n, 0, 0, 0
    p = [r["pnl"] for r in rs]
    pos = sum(v for v in p if v > 0); neg = -sum(v for v in p if v < 0)
    return n, round(sum(p) / n, 2), round(sum(1 for v in p if v > 0) / n * 100, 1), round(pos / neg, 2) if neg else 999


def bucket_dist(d):
    if d is None:
        return "NA"
    if d < 2:
        return "0-2%"
    if d < 5:
        return "2-5%"
    if d < 10:
        return "5-10%"
    return "10%+"


rows = list(csv.DictReader(open(LEGS, encoding="utf-8-sig")))
out = []
cache = {}
for r in rows:
    sym = r["symbol"]
    if sym not in cache:
        cache[sym] = load(sym)
    bars = cache[sym]
    if not bars:
        continue
    entry_d = r["entry_date"]
    seg = [b for b in bars if str(b["t"]) <= entry_d]
    if len(seg) < 30:
        continue
    kl = [{"t": str(b["t"]), "o": float(b["o"]), "h": float(b["h"]),
           "l": float(b["l"]), "c": float(b["c"]), "v": float(b["v"])} for b in seg]
    sigs = detect_smc_signals(kl)
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
        # R77 FIX: meta key 是 ob_high/ob_low(detector 真实字段), 不是 zone_lo/zone_hi ——
        # R76 用错 key 导致 "in_ob 只 1 腿命中" 假阴性; 本节已修
        lo = float(meta.get("ob_low") or recent_ob.price)
        hi = float(meta.get("ob_high") or recent_ob.price)
        in_ob = lo <= entry_px <= hi
        if not in_ob:
            ob_far = (entry_px - hi) / hi * 100 if entry_px > hi else (lo - entry_px) / lo * -100

    # ═══ R77: FVG 自主检测(detector 不出 FVG) — 3-bar 形态, 最近60bar窗 ═══
    fvgs = []  # (kind, lo, hi, bar)
    n = len(kl)
    for i in range(1, n - 1):
        h_prev, h_next = kl[i - 1]["h"], kl[i + 1]["l"]
        l_prev, l_next = kl[i - 1]["l"], kl[i + 1]["h"]
        # bullish FVG: i+1 的 low > i-1 的 high (跳空)
        if h_next > h_prev:
            fvgs.append(("bull", h_prev, h_next, i))
        # bearish FVG: i+1 的 high < i-1 的 low (向下跳空)
        if l_next < l_prev:
            fvgs.append(("bear", l_next, l_prev, i))
    active_fvgs = [f for f in fvgs if f[3] >= n - 60]  # 近 60 bar 内形成
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
    # BSL = 最近被攻克的摆动高点 / SSL = 最近被攻克的摆动低点
    bsl = highs[0].meta["swing_price"] if highs else None
    ssl = lows[0].meta["swing_price"] if lows else None
    tp = float(r.get("tp") or 0) or None
    sl = float(r.get("sl") or 0) or None
    # ═══ R78: MSS (Market Structure Shift) — CHOCH 被跟进确认 ═══
    mss = [s for s in sigs if s.type.startswith("MSS")]
    recent_mss = mss[-1] if mss else None
    mss_dir = recent_mss.dir if recent_mss else None
    mss_bars_ago = (len(kl) - 1 - recent_mss.bar) if recent_mss else None

    # ═══ R79: OTE (Optimal Trade Entry) — 最近脉冲摆动的 61.8%-79% 回测带 ═══
    # 从 detector 的 swing 列表重建最近一段脉冲, 算 fib 区
    from smc_detector import find_swings
    h_sw, l_sw = find_swings(kl, min_bars=3)
    ote_zone = None
    if len(h_sw) >= 2 and len(l_sw) >= 2:
        # 最近脉冲: swing_low 后 swing_high (向上脉冲)
        # 找最近的 (l_sw 高点) 序
        if h_sw and l_sw:
            # 理想: 最后 swing_low → swing_high (后者 bar > 前者 bar)
            candidates = [(l, h) for l in l_sw for h in h_sw if h['bar'] > l['bar'] and h['bar'] - l['bar'] < 30]
            if candidates:
                l0, h0 = candidates[-1]  # 最近的摆动对
                impulse_hi = h0['price']
                impulse_lo = l0['price']
                if impulse_hi > impulse_lo:
                    ote_lo = impulse_hi - (impulse_hi - impulse_lo) * 0.79
                    ote_hi = impulse_hi - (impulse_hi - impulse_lo) * 0.618
                    ote_zone = (ote_lo, ote_hi)
    in_ote = False
    if ote_zone:
        in_ote = ote_zone[0] <= entry_px <= ote_zone[1]

    # ═══ R80: LV(Liquidity Void) — 极速填充间隙, 近60bar内出现 ═══
    atr14 = 0.0
    trs = []
    for i in range(1, len(kl)):
        b, pb = kl[i], kl[i-1]
        trs.append(max(b["h"]-b["l"], abs(b["h"]-pb["c"]), abs(b["l"]-pb["c"])))
        atr14 = sum(trs[-14:]) / min(14, len(trs))
    lvs = []
    for i in range(n - 1, max(0, n - 60), -1):
        b, pb = kl[i], kl[i-1]
        gap_up = b["l"] > pb["h"] * 1.01  # 上跳空
        gap_dn = b["h"] < pb["l"] * 0.99
        body_m = abs(b["c"] - b["o"])
        if (gap_up or gap_dn) and body_m > atr14 * 1.5:
            lvs.append((i, "up" if gap_up else "dn", pb["c"], b["o"], body_m / max(atr14, 1e-9)))
    in_lv = False
    if lvs:
        recent_lv = lvs[0]
        _, lv_dir, lv_lo, lv_hi, _ = recent_lv
        in_lv = min(lv_lo, lv_hi) <= entry_px <= max(lv_lo, lv_hi)

    out.append({**r,
                "clean_close": last_close,
                "in_fvg": in_fvg if in_fvg else "none", "fvg_gap_to_entry": fvg_gap_to_entry,
                "mss_dir": mss_dir, "mss_bars_ago": mss_bars_ago,
                "in_ote": in_ote, "ote_zone": [round(ote_zone[0], 2), round(ote_zone[1], 2)] if ote_zone else None,
                "in_lv": in_lv, "lvs_60b": len(lvs),
                "sweeps_10b": len(sweeps_10b), "sweep_dir": my_sweep_dir,
                "in_ob": in_ob, "ob_gap_pct": round(ob_far, 2) if ob_far else (0 if in_ob else None),
                "bsl": bsl, "ssl": ssl,
                "dist_to_ssl": round((entry_px - ssl) / ssl * 100, 2) if ssl else None,
                "dist_to_bsl": round((bsl - entry_px) / entry_px * 100, 2) if bsl else None,
                "tp_above_bsl": (tp > bsl) if (tp and bsl) else None,
                "sl_below_ssl": (sl < ssl) if (sl and ssl) else None,
                "pnl": float(r["net_pnl_pct"] or 0)})

print(f"R76 腿 enriched: {len(out)}")

cols = list(out[0].keys())
with open(OUT_CSV, "w", encoding="utf-8-sig", newline="") as fh:
    w = csv.DictWriter(fh, fieldnames=cols)
    w.writeheader()
    w.writerows(out)

md = ["# R76 — 引擎全信号链审计(BSL/SSL/OB/Sweep, v25 detector)", f"腿数: {len(out)}\n"]

for title, fn in [
    ("入场前10bar内是否有 sweep(SMC 经典动机)", lambda r: f"sweeps={r['sweeps_10b']}"),
    ("sweep 方向(多单应期望 bull sweep = 扫低再回拉)", lambda r: r["sweep_dir"] or "无sweep"),
    ("入场价是否落在最近 OB 区", lambda r: str(r["in_ob"])),
    ("入场价是否落在最近 FVG(近60bar)", lambda r: str(r["in_fvg"])),
    ("入场前最近一次 MSS 方向(结构确认)", lambda r: f"mss={r['mss_dir'] or '无'}@{r['mss_bars_ago']} bar前"),
    ("入场在 OTE(61.8-79%蝶形) 内", lambda r: str(r["in_ote"])),
    ("入场在 LV(流动性真空, 近60bar) 内", lambda r: str(r["in_lv"])),
    ("LV 数量(市场情绪级)", lambda r: f"lvs={r['lvs_60b']}"),
    ("入场价距最近被攻克的 SSL 距离", lambda r: bucket_dist(r["dist_to_ssl"])),
    ("入场价距最近被攻克的 BSL 距离", lambda r: bucket_dist(r["dist_to_bsl"])),
    ("TP 是否在 BSL 上方(撞向被吞流动性)", lambda r: str(r["tp_above_bsl"])),
    ("SL 是否在 SSL 下方(被扫盘保护)", lambda r: str(r["sl_below_ssl"])),
]:
    g = defaultdict(list)
    for r in out:
        g[fn(r)].append(r)
    md.append(f"\n## {title}")
    md.append("| 桶 | n | avg% | WR% | PF |")
    md.append("|---|---|---|---|---|")
    for k, v in sorted(g.items(), key=lambda kv: -len(kv[1])):
        md.append("| " + " | ".join(str(x) for x in [k, *st(v)]) + " |")

open(OUT_MD, "w", encoding="utf-8").write("\n".join(md))
print(f"R76 → {OUT_MD}")
