# -*- coding: utf-8 -*-
"""M2/M3 frozen replay + gates (reuses m1_replay logic)."""
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
    exit_price, reason, hold = ep, "TIME_STOP", 0
    for k in range(entry_idx + 1, min(len(ks), entry_idx + MAX_HOLD + 1)):
        b = ks[k]
        hold += 1
        hi, lo, cl = b["h"], b["l"], b["c"]
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
        exit_price = ks[min(len(ks), entry_idx + MAX_HOLD) - 1]["c"]
    gross = (exit_price / ep - 1) * 100
    return {"symbol": seed["symbol"], "entry_date": seed["entry_date"],
            "net_pnl_pct": round(gross - FEE, 4), "reason": reason, "hold_bars": hold,
            "t1_violation": False}


def load_seeds(path):
    with open(path, encoding="utf-8-sig") as fh:
        rows = list(csv.DictReader(fh))
    return [{k.lstrip("\ufeff"): v for k, v in r.items()} for r in rows]


def main():
    cache = {}
    result = {}
    for mode in ("M2", "M3"):
        seeds = load_seeds(os.path.join(MARGIN_DIR, f"{mode}_seeds.csv"))
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
        print(f"\n{'='*60}\n{mode}: n={len(trades)} gate_pass={gate['gate_pass']}\n{'='*60}")
        for c in gate["checks"]:
            print(f"  {'PASS' if c['pass'] else 'FAIL'} {c['name']}: {c['detail']}")
        result[mode] = {"n": gate["overall"]["n"], "wr": gate["overall"]["wr"],
                        "avg": gate["overall"]["avg"], "pf": gate["overall"]["pf"],
                        "payoff": gate["overall"]["payoff"], "gate_pass": gate["gate_pass"],
                        "yearly": {y: gate["yearly"][y] for y in ("2023", "2024", "2025", "2026")}}
        with open(os.path.join(MARGIN_DIR, f"{mode}_trades.csv"), "w", newline="", encoding="utf-8-sig") as fh:
            w = csv.DictWriter(fh, fieldnames=list(trades[0].keys()) if trades else ["symbol"])
            w.writeheader()
            for t in trades:
                w.writerow(t)
    with open(os.path.join(MARGIN_DIR, "M2_M3_result.json"), "w", encoding="utf-8") as fh:
        json.dump(result, fh, ensure_ascii=False, indent=2)
    print("\nM2/M3 结果:", json.dumps(result, ensure_ascii=False, indent=2))
    print("\n对照 M0 (WR 51.61 / avg +0.07 / PF 1.03):")
    for m in ("M2", "M3"):
        r = result[m]
        imp = r["wr"] > 51.61 and r["avg"] > 0.07
        print(f"  {m}: WR={r['wr']} avg={r['avg']} PF={r['pf']} -> 增量{'有' if imp else '无'}")


if __name__ == "__main__":
    main()
