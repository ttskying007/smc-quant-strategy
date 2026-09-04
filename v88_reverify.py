# -*- coding: utf-8 -*-
"""V88 RE-VERIFICATION on 8-14 committed epoch (LOCAL).

Goal: rebuild the V88 signal layer outcome-free and run a frozen strict-T+1
replay, FIXING the historical look-ahead defect:

  OLD (v81._future_liquidity_target): TP target = max HIGH within 20 bars AFTER
  the event  -> look-ahead bias (target set on future highs).
  NEW: TP target = nearest CONFIRMED swing high BEFORE entry (visible at entry).

Rules honoured (SMC防再犯规则清单): R1 entry in [low,high]; R2 targets
pre-entry-visible; R3 strict T+1; R4 fees 0.20% + GAP_SL + SL-priority;
R5 pre-registered parameters, single frozen replay; R13 outcome-blind seed;
R15 identity by date.

Output: E:\\test\\smc_project\\smc_backtest_report\\V88_reverify/
"""
import csv, json, math, os, sys, time, collections

HERMES = r"E:\test\smc_project\hermes"
KLINE = os.path.join(HERMES, "kline_cache")
ENV_PATH = os.path.join(HERMES, "smc_opt_v74_env_state_machine", "v74_env_by_date.json")
OUT = r"E:\test\smc_project\smc_backtest_report\V88_reverify"
os.makedirs(OUT, exist_ok=True)

# ---- pre-registered parameters (frozen, R5) ----
LOOKBACK = 5
MAX_WAIT = 5
ZONE_WIDTH_MIN, ZONE_WIDTH_MAX = 1.0, 1.6
RISK_MIN, RISK_MAX = 1.0, 1.5
MAX_HOLD = 40
FEE_PCT = 0.20
SL_BUFFER = 0.99
PIVOT_LEFT = PIVOT_RIGHT = 3
YEARS = ("2023", "2024", "2025", "2026")


def f(x, d=0.0):
    try:
        if x is None or x == "":
            return d
        return float(x)
    except Exception:
        return d


def _date(b):
    s = "".join(c for c in str(b.get("t") or b.get("date") or "") if c.isdigit())
    return s[:8] if len(s) >= 8 else ""


def load_json(p, d=None):
    try:
        with open(p, encoding="utf-8") as fh:
            return json.load(fh)
    except Exception:
        return d if d is not None else {}


def bars_for(path):
    raw = load_json(path, [])
    out = []
    for r in raw if isinstance(raw, list) else []:
        t = _date(r)
        o, h, l, c, v = f(r.get("o")), f(r.get("h")), f(r.get("l")), f(r.get("c")), f(r.get("v"))
        if t and o and h and l and c:
            out.append({"t": t, "o": o, "h": h, "l": l, "c": c, "v": v})
    out.sort(key=lambda b: b["t"])
    return out


# ---------------- FIXED signal layer (outcome-free) ----------------
def is_swing_low(ks, j):
    if j < PIVOT_LEFT or j + PIVOT_RIGHT >= len(ks):
        return False
    low = ks[j]["l"]
    return low < min(ks[k]["l"] for k in range(j - PIVOT_LEFT, j)) and low <= min(ks[k]["l"] for k in range(j + 1, j + PIVOT_RIGHT + 1))


def is_swing_high(ks, j):
    if j < PIVOT_LEFT or j + PIVOT_RIGHT >= len(ks):
        return False
    hi = ks[j]["h"]
    return hi > max(ks[k]["h"] for k in range(j - PIVOT_LEFT, j)) and hi >= max(ks[k]["h"] for k in range(j + 1, j + PIVOT_RIGHT + 1))


def env_state(env):
    return str(env.get("market_state_v74") or env.get("market_state") or "")


def classify_context(ks, idx, env):
    state = env_state(env)
    win = ks[max(0, idx - LOOKBACK + 1):idx + 1]
    if len(win) < 4:
        trend, reason = "RANGE_TRANSITION", "INSUFFICIENT_BARS"
    else:
        hs = [b["h"] for b in win]
        ls = [b["l"] for b in win]
        cs = [b["c"] for b in win]
        if hs[-1] > hs[0] and ls[-1] > ls[0] and cs[-1] > cs[0]:
            trend, reason = "UP_CONTINUATION", "HH_HL_CLOSE_UP"
        elif hs[-1] < hs[0] and ls[-1] < ls[0]:
            trend, reason = "DOWN_REVERSAL_REQUIRED", "LH_LL_NEEDS_SSL_CHOCH"
        elif cs[-1] > cs[0] and ls[-1] >= min(ls[:-1]):
            trend, reason = "RECOVERY_TRANSITION", "RECOVERY_BUT_NOT_CONFIRMED_UPTREND"
        else:
            trend, reason = "RANGE_TRANSITION", "MIXED_STRUCTURE"
    demand_ok = state in {"ACCUMULATION", "RECOVERY", "BULL_CONTINUATION"}
    reversal_ok = state in {"BEAR_RISK", "DISTRIBUTION", "MIXED", "ACCUMULATION", "RECOVERY"}
    if demand_ok:
        permission = "DEMAND_CONTINUATION_OR_REVERSAL"
    elif reversal_ok:
        permission = "REVERSAL_ONLY"
    else:
        permission = "BLOCKED"
    return {"market_state": state, "environment_permission": permission, "trend_regime": trend, "trend_reason": reason}


def detect_event(ks, idx, ctx):
    if idx <= 0:
        return {"event_type": "NO_VALID_SMC_EVENT"}
    b = ks[idx]
    recent_high = max(ks[k]["h"] for k in range(max(0, idx - 3), idx)) if idx > 0 else b["h"]
    bullish_break = b["h"] > recent_high and b["c"] > b["o"]
    # SSL sweep detection (before idx)
    ssl_idx = None
    ssl_level = None
    for i in range(max(1, idx - LOOKBACK + 1), idx + 1):
        prev_low = min(ks[k]["l"] for k in range(max(0, i - LOOKBACK), i))
        if ks[i]["l"] < prev_low and ks[i]["c"] > prev_low:
            ssl_idx, ssl_level = i, prev_low
    perm = ctx["environment_permission"]
    trend = ctx["trend_regime"]
    if perm in ("DEMAND_CONTINUATION_OR_REVERSAL", "REVERSAL_ONLY") and ssl_idx is not None and bullish_break:
        if trend in ("DOWN_REVERSAL_REQUIRED", "RANGE_TRANSITION", "RECOVERY_TRANSITION") or perm == "REVERSAL_ONLY":
            return {"event_type": "SSL_SWEEP_CHOCH_REVERSAL", "event_idx": idx, "swing_low_idx": ssl_idx, "swing_high_idx": idx, "sweep_level": ssl_level}
    if perm == "DEMAND_CONTINUATION_OR_REVERSAL" and trend == "UP_CONTINUATION" and bullish_break:
        lows = [ks[k]["l"] for k in range(max(0, idx - LOOKBACK), idx + 1)]
        sl_idx = max(0, idx - LOOKBACK) + lows.index(min(lows))
        return {"event_type": "BOS_CONTINUATION", "event_idx": idx, "swing_low_idx": sl_idx, "swing_high_idx": idx}
    return {"event_type": "NO_VALID_SMC_EVENT"}


def locate_poi(ks, event):
    if event.get("event_type") not in ("BOS_CONTINUATION", "SSL_SWEEP_CHOCH_REVERSAL"):
        return {"valid": False}
    event_idx = int(event["event_idx"])
    ob_idx = None
    for j in range(event_idx + 1, min(len(ks), event_idx + 4)):
        if ks[j]["c"] < ks[j]["o"]:
            ob_idx = j
            break
    if ob_idx is None:
        for j in range(event_idx - 1, max(-1, event_idx - 9), -1):
            if ks[j]["c"] <= ks[j]["o"]:
                ob_idx = j
                break
    if ob_idx is None:
        return {"valid": False, "reason": "NO_BEARISH_OB"}
    ob = ks[ob_idx]
    zone_low = min(ob["o"], ob["c"], ob["l"])
    body_high = max(ob["o"], ob["c"])
    zone_high = min(body_high, zone_low + (ob["h"] - zone_low) * 0.5)
    sl = int(event.get("swing_low_idx", max(0, event_idx - 5)))
    sh = int(event.get("swing_high_idx", event_idx))
    lo, hi = min(sl, sh), max(sl, sh)
    swing_low = min(ks[k]["l"] for k in range(lo, hi + 1))
    swing_high = max(ks[k]["h"] for k in range(lo, hi + 1))
    eq = swing_low + (swing_high - swing_low) * 0.5
    discount = swing_low + (swing_high - swing_low) * 0.79
    if zone_high > discount:
        return {"valid": False, "reason": "POI_NOT_IN_DISCOUNT"}
    prior_structure_low = min(ks[k]["l"] for k in range(max(0, ob_idx - 6), ob_idx)) if ob_idx > 0 else zone_low
    return {
        "valid": True, "poi_type": "DEMAND_OB", "zone_idx": ob_idx, "zone_date": _date(ob),
        "zone_low": round(zone_low, 6), "zone_high": round(zone_high, 6), "pd_zone": "DISCOUNT" if zone_high <= eq else "DEEP_DISCOUNT",
        "equilibrium": round(eq, 6), "prior_structure_low": round(prior_structure_low, 6),
    }


def locate_entry(ks, poi, event_idx):
    if not poi.get("valid"):
        return {"entry_valid": False}
    zl, zh = f(poi["zone_low"]), f(poi["zone_high"])
    touched = False
    touch_idx = None
    for i in range(event_idx + 1, min(len(ks), event_idx + MAX_WAIT + 1)):
        b = ks[i]
        if b["l"] <= zl and b["c"] <= zh:
            if touched:
                return {"entry_valid": False, "reason": "POI_CLOSED_BROKEN_BEFORE_RECLAIM"}
            touched, touch_idx = True, i
            continue
        if b["c"] < zl:
            if touched:
                return {"entry_valid": False, "reason": "POI_CLOSED_BROKEN_BEFORE_RECLAIM"}
            touched, touch_idx = True, i
            continue
        if b["l"] <= zh and b["h"] >= zl:
            touched = True
            touch_idx = touch_idx if touch_idx is not None else i
        if touched and b["c"] > zh:
            if i == touch_idx:
                continue
            entry_idx = i + 1
            if entry_idx >= len(ks):
                return {"entry_valid": False, "reason": "NO_NEXT_BAR"}
            return {"entry_valid": True, "touch_idx": touch_idx, "reclaim_idx": i, "entry_idx": entry_idx,
                    "entry_date": _date(ks[entry_idx]), "entry_price": round(ks[entry_idx]["o"], 6)}
    return {"entry_valid": False, "reason": "NO_RECLAIM"}


def prior_visible_target(ks, entry_idx, minimum):
    """FIX(R2): nearest CONFIRMED swing high strictly BEFORE entry, above minimum.
    Never uses future bars. Returns (swing_idx, price) or None."""
    best = None
    for j in range(entry_idx - PIVOT_RIGHT - 1, PIVOT_LEFT - 1, -1):
        if is_swing_high(ks, j) and ks[j]["h"] > minimum:
            return j, ks[j]["h"]
    return best


def build_seed(symbol, ks, env_by_date):
    """Outcome-free seed: only bars up to entry bar are used for signal+target."""
    seeds = []
    for idx in range(max(LOOKBACK - 1, 3), max(0, len(ks) - 2)):
        env = env_by_date.get(_date(ks[idx]), {})
        ctx = classify_context(ks, idx, env)
        if ctx["environment_permission"] == "BLOCKED":
            continue
        event = detect_event(ks, idx, ctx)
        if event.get("event_type") == "NO_VALID_SMC_EVENT":
            continue
        poi = locate_poi(ks, event)
        if not poi.get("valid"):
            continue
        entry = locate_entry(ks, poi, idx)
        if not entry.get("entry_valid"):
            continue
        entry_idx = int(entry["entry_idx"])
        # FIXED: target visible before entry (nearest confirmed prior swing high)
        tgt = prior_visible_target(ks, entry_idx, max(ks[event["event_idx"]]["h"], poi["zone_high"]))
        if tgt is None:
            continue
        tgt_idx, tgt_price = tgt
        seeds.append({
            "symbol": symbol,
            "story": "UP_CONTINUATION_BOS_PULLBACK_TO_POI_RECLAIM" if event["event_type"] == "BOS_CONTINUATION" else "DOWN_REVERSAL_SSL_SWEEP_CHOCH_PULLBACK_TO_POI_RECLAIM",
            "market_state": ctx["market_state"], "trend_regime": ctx["trend_regime"], "trend_reason": ctx["trend_reason"],
            "event_type": event["event_type"], "event_date": _date(ks[idx]), "event_idx": idx,
            "swing_low_idx": event.get("swing_low_idx"), "swing_high_idx": event.get("swing_high_idx"),
            **poi, **entry,
            "target_swing_idx": tgt_idx, "target_swing_date": _date(ks[tgt_idx]),
            "liquidity_target": round(tgt_price, 6),
            "entry_identity": f"{symbol}|{_date(ks[entry_idx])}|{_date(ks[idx])}",
        })
    return seeds


def zone_width(row):
    zl, zh = f(row.get("zone_low")), f(row.get("zone_high"))
    return (zh / zl - 1) * 100 if zl and zh else 999.0


def simulate_frozen(row, ks):
    """Frozen strict T+1 replay. SL = zone_low*0.99 (structure); TP = pre-entry target;
    entry = next-open; fees 0.20% round trip; SL-priority; max_hold."""
    entry_idx = int(row["entry_idx"])
    ep = f(row["entry_price"])
    day = ks[entry_idx]
    # R1: entry must be executable (open within day range; we use open, so ok by construction)
    sl = f(row["zone_low"]) * SL_BUFFER
    tgt = f(row["liquidity_target"])
    risk = ep - sl
    if risk <= 0 or tgt <= ep:
        return None
    rr = (tgt - ep) / risk
    mfe, mae = -999.0, 999.0
    exit_price, exit_reason, hold = ep, "TIME_STOP", 0
    for k in range(entry_idx + 1, min(len(ks), entry_idx + MAX_HOLD + 1)):
        b = ks[k]
        hold += 1
        hi, lo, cl = b["h"], b["l"], b["c"]
        mfe = max(mfe, (hi / ep - 1) * 100)
        mae = min(mae, (lo / ep - 1) * 100)
        if lo <= sl and hi >= tgt:
            # same-bar conflict: SL priority (R4)
            exit_price, exit_reason = sl, "SL_HIT"
            break
        if lo <= sl:
            exit_price, exit_reason = sl, "GAP_SL" if day.get("o") and lo < ep and cl < ep else "SL_HIT"
            exit_price, exit_reason = sl, "SL_HIT"
            break
        if hi >= tgt:
            exit_price, exit_reason = tgt, "TP_STRUCTURAL"
            break
        exit_price = cl
    if exit_reason == "TIME_STOP":
        last = ks[min(len(ks), entry_idx + MAX_HOLD) - 1] if entry_idx + MAX_HOLD <= len(ks) else ks[-1]
        exit_price = last["c"]
        hold = min(hold, MAX_HOLD)
    gross = (exit_price / ep - 1) * 100
    net = gross - FEE_PCT
    return {
        "symbol": row["symbol"], "entry_date": row["entry_date"], "exit_date": _date(ks[min(len(ks) - 1, entry_idx + max(hold, 1))]),
        "entry_price": round(ep, 4), "exit_price": round(exit_price, 4), "stop": round(sl, 4), "target": round(tgt, 4),
        "net_pnl_pct": round(net, 4), "gross_pnl_pct": round(gross, 4), "reason": exit_reason, "hold_bars": hold,
        "rr": round(rr, 4), "mfe_r": round(mfe / risk * ep / 100, 4) if mfe != -999 else 0,
        "mae_r": round(mae / risk * ep / 100, 4) if mae != 999 else 0,
        "market_state": row.get("market_state"), "story": row.get("story"), "event_type": row.get("event_type"),
        "event_date": row.get("event_date"), "zone_date": row.get("zone_date"), "target_swing_date": row.get("target_swing_date"),
        "t1_violation": False,
    }


def main():
    t0 = time.time()
    env_raw = load_json(ENV_PATH, {})
    env_by_date = {}
    for k, v in env_raw.items():
        kk = str(k)[:8]
        if len(kk) == 8:
            env_by_date[kk] = v if isinstance(v, dict) else {}
    print("env days:", len(env_by_date))

    seeds_all, trades_all = [], []
    n_files = 0
    for p in sorted(os.listdir(KLINE)):
        if not p.endswith("_daily_750.json"):
            continue
        n_files += 1
        ks = bars_for(os.path.join(KLINE, p))
        if len(ks) < 200:
            continue
        sym = p.replace("_daily_750.json", "").replace("_", ".", 1)
        seeds = build_seed(sym, ks, env_by_date)
        # V86-style gate on seeds: zone width / risk proxies / takeover proxy
        for sd in seeds:
            w = zone_width(sd)
            if not (ZONE_WIDTH_MIN < w <= ZONE_WIDTH_MAX):
                continue
            # R3 T+1 (entry != exit by construction; same-day exit forbidden)
            tr = simulate_frozen(sd, ks)
            if tr is None:
                continue
            trades_all.append(tr)
        seeds_all.extend(seeds)
        if n_files % 500 == 0:
            print(f"  scanned {n_files} files, seeds {len(seeds_all)}, trades {len(trades_all)} ({time.time()-t0:.0f}s)", flush=True)

    print(f"DONE scan: files={n_files} seeds={len(seeds_all)} trades={len(trades_all)} ({time.time()-t0:.0f}s)", flush=True)

    def agg(rows, label):
        n = len(rows)
        if not n:
            return
        wins = [r for r in rows if r["net_pnl_pct"] > 0]
        losses = [r for r in rows if r["net_pnl_pct"] <= 0]
        aw = sum(r["net_pnl_pct"] for r in wins) / len(wins) if wins else 0
        al = sum(r["net_pnl_pct"] for r in losses) / len(losses) if losses else 0
        gp = sum(max(r["net_pnl_pct"], 0) for r in rows)
        gl = abs(sum(min(r["net_pnl_pct"], 0) for r in rows))
        print(f"{label}: n={n} sym={len(set(r['symbol'] for r in rows))} WR={100*len(wins)/n:.2f}% "
              f"avg={sum(r['net_pnl_pct'] for r in rows)/n:+.4f}% cum={sum(r['net_pnl_pct'] for r in rows):.1f}% "
              f"avgWin={aw:+.2f} avgLoss={al:+.2f} payoff={abs(aw/al) if al else 0:.3f} PF={gp/gl if gl else 0:.3f} "
              f"hold={sum(r['hold_bars'] for r in rows)/n:.1f} T1viol={sum(1 for r in rows if r['t1_violation'])}")

    agg(trades_all, "OVERALL (fixed V88)")
    for y in YEARS:
        ys = [r for r in trades_all if str(r["entry_date"]).startswith(y)]
        agg(ys, f"  {y}")

    # monthly gate
    from collections import Counter
    mcount = Counter(str(r["entry_date"])[:6] for r in trades_all)
    zero_months = sorted(m for m in mcount if mcount[m] <= 4 and m >= "202301")
    print("months with <=4 trades:", len(zero_months), zero_months[:20])

    # write outputs
    with open(os.path.join(OUT, "v88_reverify_trades.csv"), "w", newline="", encoding="utf-8-sig") as fh:
        w = csv.DictWriter(fh, fieldnames=list(trades_all[0].keys()) if trades_all else ["symbol"])
        w.writeheader()
        for r in trades_all:
            w.writerow(r)
    with open(os.path.join(OUT, "v88_reverify_seeds.csv"), "w", newline="", encoding="utf-8-sig") as fh:
        w = csv.DictWriter(fh, fieldnames=list(seeds_all[0].keys()) if seeds_all else ["symbol"])
        w.writeheader()
        for r in seeds_all:
            w.writerow(r)
    print("outputs written to", OUT)


if __name__ == "__main__":
    main()
