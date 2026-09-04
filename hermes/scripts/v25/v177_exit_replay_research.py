#!/usr/bin/env python3
"""V177 research-only executable exit replay for V175 trades.

Assumptions:
- Long-only A-share replay.
- Entry already occurred on entry_idx/entry_date from V175.
- T+1: exits may only execute from entry_idx + 1 onward.
- Intrabar ordering is conservative for long positions: gap/open SL, then SL, then TP.
- Variants use only prior/current bar information; close-trigger exits execute next open.
- This script writes research artifacts only; it never touches frontend/production/watchlists.
"""
import csv
import json
import math
from collections import Counter, defaultdict
from datetime import datetime
from pathlib import Path

HOME = Path.home()
TRADES_PATH = HOME / ".hermes/smc_opt_v175_semantic_split/v175_trades.json"
CACHE = HOME / ".hermes/kline_cache"
OUT = HOME / f".hermes/smc_audit/v177_v175_executable_exit_replay_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
BASELINE = {"n": 247, "wr": 83.81, "avg": 6.0493, "min_year_n": 38, "all_year_wr_min": 81.71, "micro_profit_pct": 0.81, "t1": 0}


def as_float(x, default=0.0):
    try:
        if x is None or x == "":
            return default
        return float(x)
    except Exception:
        return default


def date_of(b):
    return str(b.get("t") or b.get("date") or b.get("time") or "")[:8].replace("-", "")


def norm_bar(b):
    return {
        "t": date_of(b),
        "o": as_float(b.get("o", b.get("open"))),
        "h": as_float(b.get("h", b.get("high"))),
        "l": as_float(b.get("l", b.get("low"))),
        "c": as_float(b.get("c", b.get("close"))),
        "v": as_float(b.get("v", b.get("volume", b.get("vol"))), 0),
    }


def load_bars(symbol):
    key = symbol.replace(".", "_")
    for suffix in ("daily_750", "daily_300"):
        p = CACHE / f"{key}_{suffix}.json"
        if p.exists() and p.stat().st_size > 100:
            data = json.loads(p.read_text())
            bars = [norm_bar(x) for x in data]
            bars = [b for b in bars if b["t"] and b["o"] and b["h"] and b["l"] and b["c"]]
            if len(bars) >= 50:
                if len(bars) >= 2 and bars[0]["t"] > bars[1]["t"]:
                    bars.reverse()
                return bars, str(p)
    return [], ""


def pnl_pct(price, entry):
    return (price / entry - 1.0) * 100.0


def metrics(rows):
    n = len(rows)
    vals = [r["pnl_pct"] for r in rows]
    wins = [v for v in vals if v > 0]
    years = defaultdict(list)
    for r in rows:
        years[str(r["entry_date"])[:4]].append(r)
    year_counts = {y: len(v) for y, v in sorted(years.items())}
    year_wr = {y: round(sum(1 for r in v if r["pnl_pct"] > 0) / len(v) * 100, 2) for y, v in sorted(years.items())}
    return {
        "n": n,
        "wr": round(len(wins) / n * 100, 2) if n else 0,
        "avg": round(sum(vals) / n, 4) if n else 0,
        "median": round(sorted(vals)[n // 2], 4) if n else 0,
        "loss_n": sum(1 for v in vals if v <= 0),
        "sl_rate": round(sum(1 for r in rows if "SL" in r["exit_reason"]) / n * 100, 2) if n else 0,
        "tp_rate": round(sum(1 for r in rows if "TP" in r["exit_reason"]) / n * 100, 2) if n else 0,
        "time_rate": round(sum(1 for r in rows if "TIME" in r["exit_reason"]) / n * 100, 2) if n else 0,
        "be_rate": round(sum(1 for r in rows if "BE" in r["exit_reason"] or abs(r["pnl_pct"]) < 1e-9) / n * 100, 2) if n else 0,
        "partial_rate": round(sum(1 for r in rows if r.get("partial_taken")) / n * 100, 2) if n else 0,
        "micro_profit_pct": round(sum(1 for v in vals if 0 < v <= 1.0) / n * 100, 2) if n else 0,
        "min_year_n": min(year_counts.values()) if year_counts else 0,
        "year_counts": year_counts,
        "year_wr": year_wr,
        "all_year_wr_min": min(year_wr.values()) if year_wr else 0,
        "t1_violations": sum(1 for r in rows if r.get("exit_i", 10**9) <= r.get("entry_i", -1)),
        "exit_counts": dict(Counter(r["exit_reason"] for r in rows)),
    }


def gate(m):
    prod = (
        m["n"] >= 200 and m["min_year_n"] >= 35 and m["wr"] >= 84 and m["avg"] >= 6.2
        and m["all_year_wr_min"] >= 82 and m["micro_profit_pct"] <= 1 and m["t1_violations"] == 0
        and m["avg"] >= BASELINE["avg"]
    )
    research = (
        m["n"] >= 150 and m["min_year_n"] >= 25 and m["wr"] >= 85 and m["avg"] >= 6.0
        and m["all_year_wr_min"] >= 83 and m["t1_violations"] == 0
    )
    return "PRODUCTION_CANDIDATE" if prod else ("RESEARCH_ONLY_CANDIDATE" if research else "FAIL")


def simulate(t, bars, variant):
    entry = as_float(t.get("entry_price", t.get("price")))
    sl0 = as_float(t.get("sl", t.get("sl_price")))
    tp = as_float(t.get("tp", t.get("tp1")))
    max_hold = int(as_float(t.get("max_hold"), 10) or 10)
    edate = str(t.get("entry_date") or t.get("join_date") or t.get("pick_date"))[:8]
    entry_i = int(as_float(t.get("entry_idx"), -1))
    if entry_i < 0 or entry_i >= len(bars) or bars[entry_i]["t"] != edate:
        entry_i = next((i for i, b in enumerate(bars) if b["t"] == edate), -1)
    if entry_i < 0 or not entry or not sl0 or not tp:
        raise ValueError(f"missing replay anchor {t.get('symbol')} {edate}")
    risk = entry - sl0
    if risk <= 0:
        raise ValueError(f"bad risk {t.get('symbol')} entry={entry} sl={sl0}")

    size_rem = 1.0
    realized = 0.0
    stop = sl0
    partial_taken = False
    armed_close_exit = None
    mfe_r = 0.0
    max_i = min(len(bars) - 1, entry_i + max_hold)
    exit_i = max_i
    exit_px = bars[max_i]["c"]
    exit_reason = "TIME"

    for i in range(entry_i + 1, max_i + 1):
        b = bars[i]
        # Close-triggered executable next-open exit from previous bar.
        if armed_close_exit is not None:
            exit_i = i
            exit_px = b["o"]
            exit_reason = armed_close_exit
            break

        # Conservative intrabar stop/TP ordering.
        if b["o"] <= stop:
            exit_i, exit_px = i, b["o"]
            exit_reason = "GAP_BE_SL" if stop >= entry else "GAP_SL"
            break
        if b["l"] <= stop:
            exit_i, exit_px = i, stop
            exit_reason = "BE_SL" if stop >= entry else "SL"
            break
        if b["h"] >= tp:
            exit_i, exit_px = i, tp
            exit_reason = "TP"
            break

        high_r = (b["h"] - entry) / risk
        close_r = (b["c"] - entry) / risk
        mfe_r = max(mfe_r, high_r)

        name = variant["name"]
        if name == "base_replay":
            pass
        elif name == "be_after_0p8r":
            if high_r >= 0.8:
                stop = max(stop, entry)
        elif name == "lock_0p3r_after_1p0r":
            if high_r >= 1.0:
                stop = max(stop, entry + 0.3 * risk)
        elif name == "lock_0p5r_after_1p2r":
            if high_r >= 1.2:
                stop = max(stop, entry + 0.5 * risk)
        elif name == "partial33_0p8r_be_rest":
            if (not partial_taken) and high_r >= 0.8:
                realized += 0.33 * pnl_pct(entry + 0.8 * risk, entry)
                size_rem -= 0.33
                partial_taken = True
                stop = max(stop, entry)
        elif name == "partial50_1p0r_lock_0p3r":
            if (not partial_taken) and high_r >= 1.0:
                realized += 0.50 * pnl_pct(entry + 1.0 * risk, entry)
                size_rem -= 0.50
                partial_taken = True
                stop = max(stop, entry + 0.3 * risk)
        elif name == "close_fail_after_0p8r_next_open":
            if mfe_r >= 0.8 and close_r < 0.3 and i < max_i:
                armed_close_exit = "MFE_0P8_CLOSE_FAIL_NEXT_OPEN"
        elif name == "close_fail_after_1p0r_next_open":
            if mfe_r >= 1.0 and close_r < 0.5 and i < max_i:
                armed_close_exit = "MFE_1P0_CLOSE_FAIL_NEXT_OPEN"

    final_pnl = realized + size_rem * pnl_pct(exit_px, entry)
    row = {
        "symbol": t.get("symbol"),
        "entry_date": edate,
        "entry_i": entry_i,
        "exit_date": bars[exit_i]["t"],
        "exit_i": exit_i,
        "exit_reason": exit_reason,
        "entry": round(entry, 4),
        "sl": round(sl0, 4),
        "tp": round(tp, 4),
        "pnl_pct": round(final_pnl, 6),
        "base_pnl_pct": as_float(t.get("pnl_pct")),
        "base_exit_reason": t.get("exit_reason"),
        "partial_taken": partial_taken,
        "mfe_r_seen": round(mfe_r, 4),
        "variant": variant["name"],
    }
    return row


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    trades = json.loads(TRADES_PATH.read_text())
    variants = [
        {"name": "base_replay"},
        {"name": "be_after_0p8r"},
        {"name": "lock_0p3r_after_1p0r"},
        {"name": "lock_0p5r_after_1p2r"},
        {"name": "partial33_0p8r_be_rest"},
        {"name": "partial50_1p0r_lock_0p3r"},
        {"name": "close_fail_after_0p8r_next_open"},
        {"name": "close_fail_after_1p0r_next_open"},
    ]
    bars_cache = {}
    rows_by_variant = {v["name"]: [] for v in variants}
    missing = []
    sources = {}
    for t in trades:
        sym = t.get("symbol")
        if sym not in bars_cache:
            bars_cache[sym], sources[sym] = load_bars(sym)
        bars = bars_cache[sym]
        if not bars:
            missing.append({"symbol": sym, "reason": "missing_bars"})
            continue
        for v in variants:
            try:
                rows_by_variant[v["name"]].append(simulate(t, bars, v))
            except Exception as e:
                missing.append({"symbol": sym, "variant": v["name"], "reason": str(e)})

    summary_rows = []
    for name, rows in rows_by_variant.items():
        m = metrics(rows)
        m["decision"] = gate(m)
        m["delta_avg_vs_v175"] = round(m["avg"] - BASELINE["avg"], 4)
        m["delta_wr_vs_v175"] = round(m["wr"] - BASELINE["wr"], 2)
        summary_rows.append({"variant": name, **m})
        with open(OUT / f"{name}_rows.csv", "w", newline="") as f:
            if rows:
                w = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
                w.writeheader(); w.writerows(rows)

    summary_rows.sort(key=lambda x: (x["decision"] != "PRODUCTION_CANDIDATE", x["decision"] != "RESEARCH_ONLY_CANDIDATE", -x["avg"], -x["wr"]))
    best = summary_rows[0]
    production = [r for r in summary_rows if r["decision"] == "PRODUCTION_CANDIDATE"]
    research = [r for r in summary_rows if r["decision"] == "RESEARCH_ONLY_CANDIDATE"]
    final_decision = "V177_PRODUCTION_CANDIDATE_RESEARCH_ONLY__NO_WRITE" if production else ("V177_RESEARCH_ONLY_CANDIDATE__NO_WRITE" if research else "V177_NO_EXECUTION_LAYER_IMPROVEMENT__NO_WRITE")

    # Base replay quality diagnostics, separate from V175 official baseline.
    base_replay = next(r for r in summary_rows if r["variant"] == "base_replay")
    base_rows = rows_by_variant["base_replay"]
    diffs = [abs(r["pnl_pct"] - r["base_pnl_pct"]) for r in base_rows]
    replay_diag = {
        "base_replay_metrics": base_replay,
        "official_baseline": BASELINE,
        "avg_abs_pnl_diff_vs_recorded": round(sum(diffs)/len(diffs), 4) if diffs else None,
        "large_diff_count_gt_1pct": sum(1 for d in diffs if d > 1.0),
        "missing_or_error_count": len(missing),
    }

    out_summary = {
        "decision": final_decision,
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "source": str(TRADES_PATH),
        "production_write": False,
        "frontend_write": False,
        "watchlist_write": False,
        "assumptions": [
            "long-only replay; exits start entry_idx+1 for T+1",
            "conservative intrabar order: stop before TP when both appear in one daily bar",
            "close-fail variants execute on next open, not same close",
            "comparison gate uses official V175 baseline metrics from v175_report.json",
        ],
        "baseline_v175_official": BASELINE,
        "replay_diagnostics": replay_diag,
        "best_variant": best,
        "variant_metrics": summary_rows,
        "missing": missing[:50],
        "artifact_dir": str(OUT),
    }
    (OUT / "summary.json").write_text(json.dumps(out_summary, ensure_ascii=False, indent=2))

    md = []
    md.append("# V177 V175 executable exit replay research")
    md.append("")
    md.append(f"Decision: **{final_decision}**")
    md.append("")
    md.append("No production/frontend/watchlist write was performed.")
    md.append("")
    md.append("## Metrics")
    md.append("| variant | decision | n | WR | AvgPnL | ΔAvg | minYear | allYearWRmin | micro | T+1 | partial | BE | exits |")
    md.append("|---|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---|")
    for r in summary_rows:
        exits = ", ".join(f"{k}:{v}" for k, v in sorted(r["exit_counts"].items()))
        md.append(f"| {r['variant']} | {r['decision']} | {r['n']} | {r['wr']:.2f}% | {r['avg']:.4f}% | {r['delta_avg_vs_v175']:.4f} | {r['min_year_n']} | {r['all_year_wr_min']:.2f}% | {r['micro_profit_pct']:.2f}% | {r['t1_violations']} | {r['partial_rate']:.2f}% | {r['be_rate']:.2f}% | {exits} |")
    md.append("")
    md.append("## Boundary")
    if production:
        md.append("A production-candidate execution rule exists by numeric gate, but this run is research-only and did not write production.")
    elif research:
        md.append("Only research boundary was met; production gate was not met, so no write.")
    else:
        md.append("No executable exit/partial-profit variant passed the production or research gate. The remaining edge is not recoverable by simple bar-level stop/partial exits without either lowering AvgPnL or creating BE/micro pollution.")
    md.append("")
    md.append("## Replay diagnostics")
    md.append(f"- Official V175 baseline: n={BASELINE['n']}, WR={BASELINE['wr']}%, Avg={BASELINE['avg']}%, min_year={BASELINE['min_year_n']}, all_year_WR_min={BASELINE['all_year_wr_min']}%, micro={BASELINE['micro_profit_pct']}%, T+1={BASELINE['t1']}.")
    md.append(f"- Conservative base replay avg_abs_pnl_diff_vs_recorded={replay_diag['avg_abs_pnl_diff_vs_recorded']}, large_diff_count_gt_1pct={replay_diag['large_diff_count_gt_1pct']}. Daily OHLC cannot know intraday order, so official baseline remains the gate reference.")
    md.append(f"- Missing/error count: {len(missing)}.")
    md.append("")
    md.append("## Next root-cause path")
    md.append("Shift from generic execution-layer exits to bar-sequence attribution of TIME rows: classify TIME winners/losses by day-by-day R path, gap behavior, first-pullback depth after reclaim, and whether 60min data can identify executable intraday partial exits. Do not mutate V175 until a full gate passes.")
    (OUT / "report.md").write_text("\n".join(md), encoding="utf-8")
    print(json.dumps({
        "decision": final_decision,
        "artifact_dir": str(OUT),
        "summary": str(OUT / "summary.json"),
        "report": str(OUT / "report.md"),
        "best": {k: best[k] for k in ["variant", "decision", "n", "wr", "avg", "delta_avg_vs_v175", "min_year_n", "all_year_wr_min", "micro_profit_pct", "t1_violations"]},
        "variant_count": len(summary_rows),
        "missing_count": len(missing),
    }, ensure_ascii=False, indent=2))

if __name__ == "__main__":
    main()
