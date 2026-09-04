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
# FIX(2026-09-05, 审计 F11): MAX_HOLD=5 与 TP2=2R/月线高点结构性矛盾（5 根内难到达），
# 绝大多数交易以 TIME_STOP 结束、TP 层级形同虚设。按审计建议调整为日线 12 根，
# 并允许按周期/波动自适应（由调用方覆盖）。
MAX_HOLD = 12
FEE = 0.20
SL_BUFFER = 0.99
# strong-BOS disabled (audit: close-only BOS + more samples outperformed confirmed-BOS)
STRONG_BOS = False
# FIX(2026-09-05, 审计 F10): BOS 窗口 —— 扫损后 N 根内允许出现位移+收盘突破（日线 8 根）
BOS_WINDOW = 8


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
    """Aggregate daily bars into weekly bars (ISO week). last close, max high, min low, first open.
    FIX(2026-09-05, 审计 F01): 旧实现用 t[:6]（YYYYMM=月）分桶，注释却写 ISO week —— 周线实为月线。
    改为 ISO 自然周 (year, week)，并用 last_complete_idx 标记"该周最后一根日线在 daily 中的索引"，
    供调用方只引用已收完的周线（避免本周未收盘周线泄露）。"""
    weeks = []
    cur = None
    import datetime as _dt
    for i, b in enumerate(daily):
        t = b["t"]
        try:
            iso = _dt.datetime.strptime(str(t)[:8], "%Y%m%d").isocalendar()[:2]  # (year, week)
        except Exception:
            continue
        wk = f"{iso[0]}-W{iso[1]:02d}"
        if cur is None or cur["wk"] != wk:
            if cur:
                cur["last_idx"] = i - 1  # 上一周最后一根日线索引（已收完）
                weeks.append(cur)
            cur = {"wk": wk, "t": t, "o": b["o"], "h": b["h"], "l": b["l"], "c": b["c"],
                   "days": [t], "start_idx": i}
        else:
            cur["h"] = max(cur["h"], b["h"])
            cur["l"] = min(cur["l"], b["l"])
            cur["c"] = b["c"]
            cur["days"].append(t)
    if cur:
        cur["last_idx"] = len(daily) - 1
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
    day_date = daily bar date (YYYYMMDD); use only weekly bars strictly before that week.
    FIX(2026-09-05, 审计 F01/F04): 周键为 ISO 周；只引用 last_idx 严格 < day 在 daily 中索引的周线
    （避免本周未收盘周线泄露；调用方传入 day_daily_idx 可选）。"""
    import datetime as _dt
    try:
        iso = _dt.datetime.strptime(str(day_date)[:8], "%Y%m%d").isocalendar()[:2]
    except Exception:
        return False, "BAD_DATE"
    wk = f"{iso[0]}-W{iso[1]:02d}"
    idx = 0
    for i, w in enumerate(weekly):
        if w["wk"] >= wk:
            idx = i
            break
    else:
        idx = len(weekly)
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
        # FIX(2026-09-05, 审计 F09): 扫损根要求量能签名（volZ>=0.5，机构吸筹扫损），
        # 避免把普通波动跌破当作吸筹。
        swept = None
        for j in reversed(swing_lows):
            if j + PIVOT_R >= i:
                continue
            ssl = daily[j]["l"]
            if b["l"] <= ssl * (1 - SWEEP_PCT) and b["c"] > ssl:
                # volZ: 当前量 vs 过去 20 日均量的 z 分数近似（>0 = 放量）
                _v20 = sum(daily[k]["v"] for k in range(max(0, i - 20), i)) / max(1, min(20, i))
                _vz = (b["v"] - _v20) / (_v20 + 1e-9) if _v20 > 0 else 0
                if _vz < 0.5:
                    continue  # 无放量扫损 → 非机构吸筹
                swept = j
                break
        if swept is None:
            continue
        # D2: bullish break - BOS within window (FIX 2026-09-05, 审计 F10):
        # 旧实现只允许扫损后"下一根"收盘突破；真实 sweep→BOS 常需 2-8 根。
        # 改为 bos_window（默认 8 根）内出现 位移K+收盘突破；中途收盘跌破扫损低点则失效。
        # FIX(2026-09-05, 审计 F09): 位移根要求大资金签名 —— 放量(volZ>=1.0)且实体>=1ATR
        swing_high_vis = max(daily[k]["h"] for k in range(swept, i + 1))
        rsp = None
        for _kk in range(i + 1, min(len(daily), i + 1 + BOS_WINDOW)):
            if daily[_kk]["c"] > swing_high_vis:
                rsp = _kk
                break
            if daily[_kk]["c"] < daily[swept]["l"]:
                break  # 中途跌破扫损低 → 失效
        if rsp is None:
            continue
        # 位移根量能/实体签名
        _v20r = sum(daily[k]["v"] for k in range(max(0, rsp - 20), rsp)) / max(1, min(20, rsp))
        _vzr = (daily[rsp]["v"] - _v20r) / (_v20r + 1e-9) if _v20r > 0 else 0
        _atr_r = 0.0
        for _k in range(max(0, rsp - 14), rsp):
            _atr_r += max(daily[_k]["h"] - daily[_k]["l"], abs(daily[_k]["h"] - daily[_k - 1]["c"]), abs(daily[_k]["l"] - daily[_k - 1]["c"]))
        _atr_r = _atr_r / max(1, min(14, rsp))
        if not (_vzr >= 1.0 and _atr_r > 0 and (daily[rsp]["h"] - daily[rsp]["l"]) >= _atr_r):
            continue  # 非大资金推动的位移
        if STRONG_BOS:
            rsp2 = rsp + 1
            if rsp2 < len(daily) and daily[rsp2]["c"] < swing_high_vis:
                continue  # retraced — weak BOS
        # D3: 看涨 OB —— FIX(2026-09-05, 审计 F02):
        # 旧实现取 BOS 后第一根阴线（其实是回踩K，非真 OB）。
        # SMC 看涨 OB = 位移腿之前最后一根反向（阴）K，即位移腿起点前一根。
        # 优先取位移腿内看涨 FVG（bar[k].l > bar[k-2].h），其次位移前最后一根阴线，兜底扫损K实体。
        ob_idx = None
        # 位移腿起点 = rsp（BOS 突破根）；位移前最后一根反向K = rsp-1 之前最近的阴线
        for k in range(rsp - 1, max(0, rsp - 6), -1):
            if daily[k]["c"] < daily[k]["o"]:
                ob_idx = k
                break
        if ob_idx is None:
            ob_idx = rsp - 1  # 兜底：突破前一根实体
        ob = daily[ob_idx]
        # POI 优先用位移腿内看涨 FVG（bar.l > bar[k-2].h），zone 取 FVG 下沿~中值
        fvg_lo = fvg_hi = None
        for k in range(rsp - 1, max(0, rsp - 6), -1):
            if daily[k]["l"] > daily[k - 2]["h"]:  # 看涨 FVG
                fvg_lo, fvg_hi = daily[k - 2]["h"], daily[k]["l"]
                break
        if fvg_lo is not None:
            zl = fvg_lo
            zh = (fvg_lo + fvg_hi) / 2
        else:
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
                # FIX(2026-09-05, 审计 F04): 摆动点确认需在评估bar(k)前完成 —— j + PIVOT_R <= k，
                # 否则"最近确认摆动高"用了未来K线（回测胜率高估）。
                h3 = None
                for j in range(max(0, t_idx - 1), PIVOT_L - 1, -1):
                    if j + PIVOT_R > k:
                        continue  # 尚未确认（需 j 右侧 PIVOT_R 根全部收完）
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
        # FIX(2026-09-05, 审计 F04): TP 摆动点确认窗口须在入场前完成 —— j + PIVOT_R < entry_idx
        for j in range(entry_idx - PIVOT_R - 1, PIVOT_L - 1, -1):
            if is_swing_high(daily, j) and daily[j]["h"] > max(zh, entry_price):
                tgt = (j, daily[j]["h"])
                break
        # weekly external BSL (v676: TP prefers weekly liquidity target if visible pre-entry)
        wk_target = None
        import datetime as _dt
        try:
            _iso_e = _dt.datetime.strptime(str(daily[entry_idx]["t"])[:8], "%Y%m%d").isocalendar()[:2]
            _wk_e = f"{_iso_e[0]}-W{_iso_e[1]:02d}"
        except Exception:
            _wk_e = "9999-W99"
        for w in reversed(weekly):
            if w["wk"] >= _wk_e:
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
    # FIX(2026-09-05, 审计 F08): A 股执行现实
    # ① 一字涨停开盘（open >= 昨收*1.095）买不到 → 跳过（回测前 stat skippedLimitUp）
    # ② 跳空低开（open < SL）→ 按开盘价成交（不再假设能以 SL 成交）
    # ③ 涨跌停按 10% 主板近似（688/30 创业板 20% 未细分，标注）
    _prev_close = daily[entry_idx - 1]["c"] if entry_idx >= 1 else ep
    _limit_up_px = _prev_close * 1.095 if _prev_close else 0
    if _prev_close and daily[entry_idx]["o"] >= _limit_up_px:
        return {"symbol": seed["symbol"], "entry_date": seed["entry_date"], "net_pnl_pct": None,
                "reason": "SKIP_LIMIT_UP", "hold_bars": 0, "t1_violation": "False"}
    exit_price, reason, hold = ep, "TIME_STOP", 0
    for k in range(entry_idx + 1, min(len(daily), entry_idx + MAX_HOLD + 1)):
        bb = daily[k]
        hold += 1
        hi, lo, cl, op = bb["h"], bb["l"], bb["c"], bb["o"]
        # 跳空低开穿越 SL：按开盘价成交（保守，优于假设 SL 价）
        if op < sl:
            exit_price, reason = op, "SL_GAP"
            break
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
    # FIX(2026-09-05, 审计 F06/F19): IS/OOS 切分 + R 倍数指标（样本内/外对照）
    if trades_all:
        t_sorted = sorted(trades_all, key=lambda t: t["entry_date"])
        cut = int(len(t_sorted) * 0.7)
        is_tr, oos_tr = t_sorted[:cut], t_sorted[cut:]
        def _stats(ts):
            pn = [t.get("net_pnl_pct") for t in ts if t.get("net_pnl_pct") is not None]
            if not pn:
                return "n=0"
            wins = [x for x in pn if x > 0]
            pf = sum(wins) / abs(sum(x for x in pn if x <= 0)) if any(x <= 0 for x in pn) else 99
            return f"n={len(pn)} avg={sum(pn)/len(pn):+.2f}% wr={len(wins)/len(pn)*100:.0f}% PF={pf:.2f}"
        print(f"\n[IS/OOS] 样本内(前70%): {_stats(is_tr)}")
        print(f"[IS/OOS] 样本外(后30%): {_stats(oos_tr)}")
        rs = [t.get("mfe_r", 0) for t in trades_all if t.get("mfe_r")]
        if rs:
            print(f"[R倍数] avgMFE_R={sum(rs)/len(rs):.2f}")


if __name__ == "__main__":
    main()
