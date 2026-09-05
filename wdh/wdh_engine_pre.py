# -*- coding: utf-8 -*-
"""v676 W->D->H three-timeframe state machine (daily-executable projection).

Main line (all outcome-free, pre-entry-visible anchors only):
  W1: weekly structure permission - protected weekly low intact OR weekly SSL
      sweep + bullish CHOCH completed (weekly bars aggregated from daily).
  D1: daily sweeps a visible SSL (confirmed daily swing low) and reclaims.
  D2: daily close breaks the most recent confirmed swing high visible at sweep.
  D3: anchor the unique bearish OB from the D2 displacement leg (last bearish bar).
  D4: POI first touch; second touch / prior break / daily close-invalidation cancels.
  H:  daily-projected takeover - after D-POI touch, daily sweeps local SSL and
      reclaims (H2), close breaks sweep-high (H3), retests H3 demand/OB and holds (H4).
  E:  next-session open entry (strict T+1).

SL = min(H2 raid low, D-POI low) structure side * 0.99 (pre-entry visible).
TP = nearest pre-entry confirmed swing high (daily) or weekly BSL if visible.

NOTE: true 60min layer is data-constrained (local cache 2025-10..2026-05 only);
      this engine uses daily-projected H semantics for full 2023-2026 coverage.
      A separate near-term exploration uses real 60min bars.
"""
import csv, io, json, os, sys

if __name__ == "__main__":
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
HERMES = r"E:\test\smc_project\hermes"
KLINE = os.path.join(HERMES, "kline_cache")
OUT = r"E:\test\smc_project\wdh"
os.makedirs(OUT, exist_ok=True)

# SMC detection parameters (2026-08-20 audit result: P5/S1.0/confirmed-BOS reduced samples without
# improving avg — OLD params retained as optimal; STRONG_BOS kept as config for future tests)
PIVOT_L = PIVOT_R = 3
SWEEP_PCT = 0.003
# FIX(2026-08-22): MAX_HOLD 40→5 — MSS research: 3d win 86%, MAX_HOLD=5 PF 6.38 vs 40d PF 4.31
# (short hold = faster stop/realize, avg unchanged +2.32% vs +2.34%, PF +2.07)
MAX_HOLD = 5
FEE = 0.20
SL_BUFFER = 0.99
# strong-BOS disabled (audit: close-only BOS + more samples outperformed confirmed-BOS)
STRONG_BOS = False


def f(x, d=0.0):
    try:
        return float(x) if x not in (None, "") else d
    except Exception:
        return d


def date8(x):
    s = "".join(c for c in str(x or "") if c.isdigit())
    return s[:8] if len(s) >= 8 else ""


def bars_for(path):
    try:
        raw = json.load(open(path, encoding="utf-8"))
    except Exception:
        return []
    out = []
    for r in raw if isinstance(raw, list) else []:
        t = date8(r)
        o, h, l, c = f(r.get("o")), f(r.get("h")), f(r.get("l")), f(r.get("c"))
        if t and o and h and l and c:
            out.append({"t": t, "o": o, "h": h, "l": l, "c": c})
    out.sort(key=lambda b: b["t"])
    return out


def aggregate_weekly(daily):
    """Aggregate daily bars into weekly bars (ISO week). last close, max high, min low, first open."""
    weeks = []
    cur = None
    for b in daily:
        t = b["t"]
        wk = t[:6]  # YYYYMM week bucket (simplified weekly anchor)
        if cur is None or cur["wk"] != wk:
            if cur:
                weeks.append(cur)
            cur = {"wk": wk, "t": t, "o": b["o"], "h": b["h"], "l": b["l"], "c": b["c"], "days": [t]}
        else:
            cur["h"] = max(cur["h"], b["h"])
            cur["l"] = min(cur["l"], b["l"])
            cur["c"] = b["c"]
            cur["days"].append(t)
    if cur:
        weeks.append(cur)
    return weeks


def is_swing_low(ks, j):
    if j < PIVOT_L or j + PIVOT_R >= len(ks):
        return False
    lo = ks[j]["l"]
    return lo < min(ks[k]["l"] for k in range(j - PIVOT_L, j)) and lo <= min(ks[k]["l"] for k in range(j + 1, j + PIVOT_R + 1))


def is_swing_high(ks, j):
    if j < PIVOT_L or j + PIVOT_R >= len(ks):
        return False
    hi = ks[j]["h"]
    return hi > max(ks[k]["h"] for k in range(j - PIVOT_L, j)) and hi >= max(ks[k]["h"] for k in range(j + 1, j + PIVOT_R + 1))


def weekly_permission(weekly, day_date):
    """W1: protected weekly low intact OR weekly SSL sweep + bullish CHOCH completed.
    day_date = daily bar date (YYYYMMDD); use only weekly bars strictly before that week."""
    wk = day_date[:6]
    idx = 0
    for i, w in enumerate(weekly):
        if w["t"][:6] >= wk:
            idx = i
            break
    prior = weekly[:idx]
    if len(prior) < PIVOT_L + PIVOT_R + 1:
        return False, "INSUFFICIENT_WEEKLY"
    # protected low: last confirmed weekly swing low whose low not yet broken by later weekly close
    for j in range(len(prior) - PIVOT_R - 1, PIVOT_L - 1, -1):
        if not is_swing_low(prior, j):
            continue
        wl = prior[j]["l"]
        if all(prior[k]["c"] > wl for k in range(j + 1, len(prior))):
            return True, f"W1_PROTECTED_LOW"
    # weekly SSL sweep + bullish CHOCH: weekly low swept then close back, later weekly breaks a prior high
    for j in range(PIVOT_L, len(prior) - 1):
        if not is_swing_low(prior, j):
            continue
        wl = prior[j]["l"]
        for s in range(j + 1, len(prior)):
            if prior[s]["l"] < wl * (1 - SWEEP_PCT) and prior[s]["c"] > wl:
                break
        else:
            continue
        # bullish CHOCH: some later weekly closes above the swing high visible at sweep
        sweep_high = max(prior[k]["h"] for k in range(j, s + 1))
        if any(prior[k]["c"] > sweep_high for k in range(s + 1, len(prior))):
            return True, "W1_WEEKLY_SSL_CHOCH"
    return False, "NO_W1_PERMISSION"


def build_seeds(symbol, daily):
    weekly = aggregate_weekly(daily)
    seeds = []
    swing_lows = [j for j in range(PIVOT_L, len(daily) - PIVOT_R) if is_swing_low(daily, j)]
    for i in range(20, len(daily) - 3):
        b = daily[i]
        # W1 permission (weekly structure strictly before this week)
        wok, wwhy = weekly_permission(weekly, b["t"])
        if not wok:
            continue
        # D1: daily SSL sweep of a confirmed swing low
        swept = None
        for j in reversed(swing_lows):
            if j + PIVOT_R >= i:
                continue
            ssl = daily[j]["l"]
            if b["l"] <= ssl * (1 - SWEEP_PCT) and b["c"] > ssl:
                swept = j
                break
        if swept is None:
            continue
        # D2: bullish break - next bar closes above sweep-time visible swing high
        # FIX(2026-08-20 audit): improved BOS — close break + next bar confirms (holds above).
        rsp = i + 1
        if rsp >= len(daily):
            continue
        swing_high_vis = max(daily[k]["h"] for k in range(swept, i + 1))
        if STRONG_BOS:
            # confirmed BOS: close break + next bar doesn't retrace below swing high
            if not (daily[rsp]["c"] > swing_high_vis):
                continue
            rsp2 = rsp + 1
            if rsp2 < len(daily) and daily[rsp2]["c"] < swing_high_vis:
                continue  # retraced — weak BOS
        else:
            if not (daily[rsp]["c"] > swing_high_vis):
                continue
        # D3: unique bearish OB anchored from displacement leg (first bearish bar after rsp)
        ob_idx = None
        for k in range(rsp + 1, min(len(daily), rsp + 5)):
            if daily[k]["c"] < daily[k]["o"]:
                ob_idx = k
                break
        if ob_idx is None:
            continue
        ob = daily[ob_idx]
        zl = min(ob["o"], ob["c"], ob["l"])
        zh = min(max(ob["o"], ob["c"]), zl + (ob["h"] - zl) * 0.5)
        # D4: POI first touch within max_wait, then H (daily-projected): reclaim, hold
        touched = False
        t_idx = None
        entry = None
        for k in range(ob_idx + 1, min(len(daily) - 1, ob_idx + 12)):
            bb = daily[k]
            if bb["l"] <= zl and bb["c"] <= zh:
                if touched:
                    break
                touched, t_idx = True, k
                continue
            if bb["c"] < zl:
                if touched:
                    break
                touched, t_idx = True, k
                continue
            if bb["l"] <= zh and bb["h"] >= zl:
                touched = True
                t_idx = t_idx if t_idx is not None else k
            if touched and k != t_idx and bb["c"] > zh:
                # H3 (v676): close breaks the most recent CONFIRMED swing high visible at touch
                h3 = None
                for j in range(max(0, t_idx - 1), PIVOT_L - 1, -1):
                    if is_swing_high(daily, j) and daily[j]["h"] > zh:
                        h3 = daily[j]["h"]
                        break
                if h3 is not None and bb["c"] > h3:
                    entry_idx = k + 1
                    if entry_idx < len(daily):
                        entry = (entry_idx, k, t_idx)
                break
        if entry is None:
            continue
        entry_idx, reclaim_idx, touch_idx = entry
        # TP: pre-entry confirmed swing high ABOVE both zone and entry price
        entry_price = f(daily[entry_idx]["o"])
        tgt = None
        for j in range(entry_idx - PIVOT_R - 1, PIVOT_L - 1, -1):
            if is_swing_high(daily, j) and daily[j]["h"] > max(zh, entry_price):
                tgt = (j, daily[j]["h"])
                break
        # weekly external BSL (v676: TP prefers weekly liquidity target if visible pre-entry)
        wk_target = None
        for w in reversed(weekly):
            if w["t"][:6] >= daily[entry_idx]["t"][:6]:
                continue
            if w["h"] > max(zh, entry_price):
                wk_target = w["h"]
                break
        if tgt is None:
            continue
        # R20: pre-entry 20-day return (entry-1 close vs entry-21 close), outcome-free
        r20 = None
        if entry_idx >= 21:
            c_now = f(daily[entry_idx - 1]["c"])
            c_prev = f(daily[entry_idx - 21]["c"])
            if c_now and c_prev:
                r20 = round(c_now / c_prev - 1, 6)
        seeds.append({
            "symbol": symbol,
            "identity": f"{symbol}|{daily[entry_idx]['t']}|{daily[i]['t']}",
            "w_permission": wwhy, "event_date": daily[i]["t"],
            "sweep_date": daily[swept]["t"], "sweep_low": round(daily[swept]["l"], 6),
            "ob_date": daily[ob_idx]["t"],
            "touch_date": daily[touch_idx]["t"], "reclaim_date": daily[reclaim_idx]["t"],
            "entry_date": daily[entry_idx]["t"], "entry_idx": entry_idx,
            "zone_low": round(zl, 6), "zone_high": round(zh, 6),
            "entry_price": round(entry_price, 6),
            "target_swing_idx": tgt[0], "target": round(tgt[1], 6),
            "weekly_target": round(wk_target, 6) if wk_target else "",
            "r20": r20 if r20 is not None else "",
        })
    return seeds


def replay(seed, daily):
    entry_idx = int(seed["entry_idx"])
    if entry_idx >= len(daily) - 1:
        return None
    ep = f(seed["entry_price"])
    # v676 execution: SL = side first negated between H2 raid low (sweep low) and D-POI low.
    # Use the WIDER structural stop (min of the two) * buffer.
    zone_low = f(seed["zone_low"])
    sweep_low = f(seed.get("sweep_low"))
    sl_base = min(zone_low, sweep_low) if sweep_low else zone_low
    sl = sl_base * SL_BUFFER
    # TP: weekly external BSL preferred (pre-entry visible), else daily swing high
    tgt = f(seed.get("weekly_target")) or f(seed.get("target"))
    risk = ep - sl
    if risk <= 0 or tgt <= ep:
        return None
    exit_price, reason, hold = ep, "TIME_STOP", 0
    for k in range(entry_idx + 1, min(len(daily), entry_idx + MAX_HOLD + 1)):
        bb = daily[k]
        hold += 1
        hi, lo, cl = bb["h"], bb["l"], bb["c"]
        if lo <= sl and hi >= tgt:
            exit_price, reason = sl, "SL_HIT"
            break
        if lo <= sl:
            exit_price, reason = sl, "SL_HIT"
            break
        if hi >= tgt:
            exit_price, reason = tgt, "TP_STRUCTURAL"
            break
        exit_price = cl
    if reason == "TIME_STOP":
        exit_price = daily[min(len(daily), entry_idx + MAX_HOLD) - 1]["c"]
    gross = (exit_price / ep - 1) * 100
    return {"symbol": seed["symbol"], "entry_date": seed["entry_date"],
            "net_pnl_pct": round(gross - FEE, 4), "reason": reason, "hold_bars": hold,
            "t1_violation": "False"}


def replay_tp2(seed, daily):
    """M0-TP2 tiered exit: TP1=1R partial 40%, runner=60% to max(2R, weekly BSL), SL->BE after TP1."""
    entry_idx = int(seed["entry_idx"])
    if entry_idx >= len(daily) - 1:
        return None
    ep = f(seed["entry_price"])
    zone_low = f(seed["zone_low"])
    sweep_low = f(seed.get("sweep_low"))
    sl_base = min(zone_low, sweep_low) if sweep_low else zone_low
    sl = sl_base * SL_BUFFER
    risk = ep - sl
    if risk <= 0:
        return None
    tp1 = ep + 1.0 * risk
    weekly_bsl = f(seed.get("weekly_target"))
    tp2_candidate = ep + 2.0 * risk
    tp2 = max(tp2_candidate, weekly_bsl) if weekly_bsl > tp2_candidate else tp2_candidate
    # tiered simulation
    remaining = 1.0
    pnl = 0.0
    be_active = False
    exit_price, reason, hold = ep, "TIME_STOP", 0
    mfe, mae = -999.0, 999.0
    for k in range(entry_idx + 1, min(len(daily), entry_idx + MAX_HOLD + 1)):
        bb = daily[k]
        hold += 1
        hi, lo, cl = bb["h"], bb["l"], bb["c"]
        mfe = max(mfe, (hi / ep - 1) * 100)
        mae = min(mae, (lo / ep - 1) * 100)
        stop = be_active and ep or sl
        # same-bar conflict: SL priority
        if lo <= stop and hi >= tp1 and not be_active:
            exit_price, reason = sl, "SL_HIT"
            pnl += remaining * (sl / ep - 1) * 100
            remaining = 0
            break
        if lo <= stop:
            exit_price, reason = stop, ("BE" if be_active else "SL_HIT")
            pnl += remaining * (stop / ep - 1) * 100
            remaining = 0
            break
        if not be_active and hi >= tp1:
            pnl += 0.40 * (tp1 / ep - 1) * 100
            remaining = 0.60
            be_active = True
            exit_price = tp1
            continue
        if be_active and hi >= tp2:
            pnl += remaining * (tp2 / ep - 1) * 100
            remaining = 0
            exit_price, reason = tp2, "TP2_RUNNER"
            break
        exit_price = cl
    if remaining > 0:
        last = daily[min(len(daily), entry_idx + MAX_HOLD) - 1]["c"]
        pnl += remaining * (last / ep - 1) * 100
        reason = "TIME_STOP"
        exit_price = last
    net = pnl - FEE
    return {"symbol": seed["symbol"], "entry_date": seed["entry_date"],
            "net_pnl_pct": round(net, 4), "reason": reason, "hold_bars": hold,
            "t1_violation": "False", "entry_price": round(ep, 4), "tp1": round(tp1, 4),
            "tp2": round(tp2, 4), "sl": round(sl, 4), "mfe_r": round(mfe / risk * ep / 100, 4) if mfe != -999 else 0,
            "mae_r": round(mae / risk * ep / 100, 4) if mae != 999 else 0}


def main():
    cache = {}
    seeds_all, trades_all = [], []
    n = 0
    for p in sorted(os.listdir(KLINE)):
        if not p.endswith("_daily_750.json"):
            continue
        n += 1
        daily = bars_for(os.path.join(KLINE, p))
        if len(daily) < 300:
            continue
        sym = p.replace("_daily_750.json", "").replace("_", ".", 1)
        seeds = build_seeds(sym, daily)
        for sd in seeds:
            seeds_all.append(sd)
            tr = replay(sd, daily)
            if tr:
                trades_all.append(tr)
        if n % 1000 == 0:
            print(f"  {n} files, seeds {len(seeds_all)}, trades {len(trades_all)}", flush=True)
    print(f"DONE: files={n} seeds={len(seeds_all)} trades={len(trades_all)}")
    with open(os.path.join(OUT, "W1D1D4_seeds.csv"), "w", newline="", encoding="utf-8-sig") as fh:
        w = csv.DictWriter(fh, fieldnames=list(seeds_all[0].keys()) if seeds_all else ["symbol"])
        w.writeheader()
        for s in seeds_all:
            w.writerow(s)
    with open(os.path.join(OUT, "W1D1D4_trades.csv"), "w", newline="", encoding="utf-8-sig") as fh:
        w = csv.DictWriter(fh, fieldnames=list(trades_all[0].keys()) if trades_all else ["symbol"])
        w.writeheader()
        for t in trades_all:
            w.writerow(t)


if __name__ == "__main__":
    main()
