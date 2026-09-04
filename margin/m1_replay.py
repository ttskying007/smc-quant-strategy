# -*- coding: utf-8 -*-
"""M1 vs M0 frozen strict T+1 replay + economic gate comparison."""
import csv, io, json, os, sys

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
sys.path.insert(0, r"E:\test\smc_project\smc_backtest_report")
from smc_gates import check_economic_gate

HERMES = r"E:\test\smc_project\hermes"
KLINE = os.path.join(HERMES, "kline_cache")
MARGIN_DIR = r"E:\test\smc_project\margin"
MAX_HOLD = 40
FEE = 0.20
SL_BUFFER = 0.99


def f(x, d=0.0):
    try:
        return float(x) if x not in (None, "") else d
    except Exception:
        return d


def bars_for(path):
    try:
        raw = json.load(open(path, encoding="utf-8"))
    except Exception:
        return []
    out = []
    for r in raw if isinstance(raw, list) else []:
        t = "".join(c for c in str(r.get("t") or r.get("date") or "") if c.isdigit())[:8]
        o, h, l, c = f(r.get("o")), f(r.get("h")), f(r.get("l")), f(r.get("c"))
        if t and o and h and l and c:
            out.append({"t": t, "o": o, "h": h, "l": l, "c": c})
    out.sort(key=lambda b: b["t"])
    return out


def replay(seed, ks):
    entry_idx = int(seed["entry_idx"])
    if entry_idx >= len(ks) - 1:
        return None
    ep = f(seed["entry_price"])
    sl = f(seed["zone_low"]) * SL_BUFFER
    tgt = f(seed["target"])
    risk = ep - sl
    if risk <= 0 or tgt <= ep:
        return None
    mfe, mae = -999.0, 999.0
    exit_price, reason, hold = ep, "TIME_STOP", 0
    for k in range(entry_idx + 1, min(len(ks), entry_idx + MAX_HOLD + 1)):
        b = ks[k]
        hold += 1
        hi, lo, cl = b["h"], b["l"], b["c"]
        mfe = max(mfe, (hi / ep - 1) * 100)
        mae = min(mae, (lo / ep - 1) * 100)
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
        last = ks[min(len(ks), entry_idx + MAX_HOLD) - 1]
        exit_price = last["c"]
    gross = (exit_price / ep - 1) * 100
    return {
        "symbol": seed["symbol"], "entry_date": seed["entry_date"],
        "net_pnl_pct": round(gross - FEE, 4), "reason": reason,
        "hold_bars": hold, "t1_violation": False,
        "entry_price": round(ep, 4), "target": round(tgt, 4), "stop": round(sl, 4),
        "mfe_r": round(mfe / risk * ep / 100, 4) if mfe != -999 else 0,
        "mae_r": round(mae / risk * ep / 100, 4) if mae != 999 else 0,
    }


def load_seeds(path):
    with open(path, encoding="utf-8-sig") as fh:
        rows = list(csv.DictReader(fh))
    # strip BOM from first key if present
    out = []
    for r in rows:
        clean = {k.lstrip("\ufeff"): v for k, v in r.items()}
        out.append(clean)
    return out


def run(label, seeds, cache):
    trades = []
    for sd in seeds:
        sym = sd["symbol"]
        ks = cache.get(sym)
        if ks is None:
            p = os.path.join(KLINE, sym.replace(".", "_") + "_daily_750.json")
            if not os.path.exists(p):
                continue
            ks = bars_for(p)
            cache[sym] = ks
        tr = replay(sd, ks)
        if tr:
            trades.append(tr)
    gate = check_economic_gate(trades)
    print(f"\n{'='*60}\n{label}: n={len(trades)}\n{'='*60}")
    for c in gate["checks"]:
        print(f"  {'PASS' if c['pass'] else 'FAIL'} {c['name']}: {c['detail']}")
    print("  gate_pass:", gate["gate_pass"])
    print("  yearly:", {y: gate["yearly"][y] for y in ("2023", "2024", "2025", "2026")})
    return trades, gate


def main():
    cache = {}
    m0 = load_seeds(os.path.join(MARGIN_DIR, "M0_seeds.csv"))
    m1 = load_seeds(os.path.join(MARGIN_DIR, "M1_seeds.csv"))
    print(f"M0 seeds={len(m0)}, M1 seeds={len(m1)}")
    t0, g0 = run("M0 (纯 SMC 主轴)", m0, cache)
    t1, g1 = run("M1 (SMC + 融资确认)", m1, cache)
    # write
    for label, trades in (("M0", t0), ("M1", t1)):
        with open(os.path.join(MARGIN_DIR, f"{label}_trades.csv"), "w", newline="", encoding="utf-8-sig") as fh:
            w = csv.DictWriter(fh, fieldnames=list(trades[0].keys()) if trades else ["symbol"])
            w.writeheader()
            for t in trades:
                w.writerow(t)
    result = {
        "M0": {"n": g0["overall"]["n"], "wr": g0["overall"]["wr"], "avg": g0["overall"]["avg"],
               "pf": g0["overall"]["pf"], "payoff": g0["overall"]["payoff"], "gate_pass": g0["gate_pass"]},
        "M1": {"n": g1["overall"]["n"], "wr": g1["overall"]["wr"], "avg": g1["overall"]["avg"],
               "pf": g1["overall"]["pf"], "payoff": g1["overall"]["payoff"], "gate_pass": g1["gate_pass"]},
    }
    with open(os.path.join(MARGIN_DIR, "M1_vs_M0_result.json"), "w", encoding="utf-8") as fh:
        json.dump(result, fh, ensure_ascii=False, indent=2)
    print("\nM1 vs M0 对照:")
    print(json.dumps(result, ensure_ascii=False, indent=2))
    # verdict: margin confirmation must improve WR/AvgNet/PF vs M0
    imp = result["M1"]["wr"] > result["M0"]["wr"] and result["M1"]["avg"] > result["M0"]["avg"]
    print("\n融资确认增量价值:", "有 (M1 优于 M0)" if imp else "无 (M1 未显著优于 M0 -> 本体关闭)")


if __name__ == "__main__":
    main()
