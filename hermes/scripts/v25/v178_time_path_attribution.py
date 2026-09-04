#!/usr/bin/env python3
"""V178 research-only TIME-row bar path attribution for V175.

Assumptions:
- Read-only research: no production/frontend/watchlist writes.
- V175 trades are the source of truth; this script only attributes TIME exits.
- A-share T+1 remains enforced: path begins from entry_idx + 1.
- Daily OHLC cannot prove intraday ordering; 60min availability is reported, not inferred.
"""
import csv
import json
from collections import Counter, defaultdict
from datetime import datetime
from pathlib import Path

HOME = Path.home()
TRADES_PATH = HOME / ".hermes/smc_opt_v175_semantic_split/v175_trades.json"
CACHE = HOME / ".hermes/kline_cache"
OUT = HOME / f".hermes/smc_audit/v178_v175_time_path_attribution_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
BASELINE = {"n": 247, "wr": 83.81, "avg": 6.0493, "time_n": 65}


def f(x, default=0.0):
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
        "raw_t": str(b.get("t") or b.get("date") or b.get("time") or ""),
        "o": f(b.get("o", b.get("open"))),
        "h": f(b.get("h", b.get("high"))),
        "l": f(b.get("l", b.get("low"))),
        "c": f(b.get("c", b.get("close"))),
    }


def load_bars(symbol, suffix):
    p = CACHE / f"{symbol.replace('.', '_')}_{suffix}.json"
    if not p.exists() or p.stat().st_size < 100:
        return [], str(p)
    data = json.loads(p.read_text())
    bars = [norm_bar(x) for x in data]
    bars = [b for b in bars if b["t"] and b["o"] and b["h"] and b["l"] and b["c"]]
    if len(bars) >= 2 and bars[0]["raw_t"] > bars[1]["raw_t"]:
        bars.reverse()
    return bars, str(p)


def pnl_pct(px, entry):
    return (px / entry - 1.0) * 100.0


def find_idx(bars, date, fallback=-1):
    if 0 <= fallback < len(bars) and bars[fallback]["t"] == date:
        return fallback
    return next((i for i, b in enumerate(bars) if b["t"] == date), -1)


def classify(row):
    max_r = row["max_high_r"]
    final_r = row["final_r"]
    giveback = row["giveback_r"]
    close_below_zone = row["close_below_zone"]
    low_below_sl = row["low_below_sl"]
    target_r = row["target_r"]
    if low_below_sl:
        return "DAILY_REPLAY_SL_AMBIGUITY"
    if max_r >= target_r:
        return "DAILY_REPLAY_TP_AMBIGUITY"
    if close_below_zone:
        return "ZONE_CLOSE_WEAKNESS"
    if max_r < 0.5:
        return "NO_FOLLOW_THROUGH_LT_0P5R"
    if 0.5 <= max_r < 1.2 and final_r < 0.5:
        return "MID_MFE_0P5_1P2R_GIVEBACK"
    if max_r >= 1.2 and giveback >= 0.7:
        return "NEAR_TP_OR_LARGE_GIVEBACK"
    if final_r >= 0.8:
        return "TIME_WINNER_HELD_OK"
    return "MIXED_SMALL_EDGE"


def summarize(rows, key):
    out = {}
    groups = defaultdict(list)
    for r in rows:
        groups[r[key]].append(r)
    for name, xs in sorted(groups.items(), key=lambda kv: (-len(kv[1]), kv[0])):
        n = len(xs)
        out[name] = {
            "n": n,
            "wr": round(sum(1 for r in xs if r["pnl_pct"] > 0) / n * 100, 2),
            "avg_pnl": round(sum(r["pnl_pct"] for r in xs) / n, 4),
            "avg_final_r": round(sum(r["final_r"] for r in xs) / n, 4),
            "avg_max_high_r": round(sum(r["max_high_r"] for r in xs) / n, 4),
            "avg_giveback_r": round(sum(r["giveback_r"] for r in xs) / n, 4),
            "median_max_high_r": round(sorted(r["max_high_r"] for r in xs)[n // 2], 4),
            "avg_holding_bars": round(sum(r["path_bars"] for r in xs) / n, 2),
            "m60_covered_rate": round(sum(1 for r in xs if r["m60_covers_entry_exit"]) / n * 100, 2),
        }
    return out


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    trades = json.loads(TRADES_PATH.read_text())
    time_trades = [t for t in trades if str(t.get("exit_reason")) == "TIME"]
    rows = []
    errors = []
    for t in time_trades:
        sym = t.get("symbol")
        bars, daily_path = load_bars(sym, "daily_750")
        if not bars:
            errors.append({"symbol": sym, "reason": "missing_daily_750"})
            continue
        entry = f(t.get("entry_price", t.get("price")))
        sl = f(t.get("sl", t.get("sl_price")))
        tp = f(t.get("tp", t.get("tp1")))
        entry_date = str(t.get("entry_date") or t.get("join_date") or "")[:8]
        exit_date = str(t.get("exit_date") or "")[:8]
        entry_i = find_idx(bars, entry_date, int(f(t.get("entry_idx"), -1)))
        exit_i = find_idx(bars, exit_date, int(f(t.get("exit_idx"), -1)))
        if entry_i < 0 or exit_i < 0 or exit_i <= entry_i or not entry or not sl or not tp:
            errors.append({"symbol": sym, "entry_date": entry_date, "exit_date": exit_date, "reason": "bad_anchor"})
            continue
        risk = entry - sl
        if risk <= 0:
            errors.append({"symbol": sym, "reason": "bad_risk"})
            continue
        path = bars[entry_i + 1: exit_i + 1]
        max_high = max(b["h"] for b in path)
        min_low = min(b["l"] for b in path)
        max_close = max(b["c"] for b in path)
        exit_close = bars[exit_i]["c"]
        max_high_r = (max_high - entry) / risk
        final_r = (exit_close - entry) / risk
        giveback_r = max(0.0, max_high_r - final_r)
        target_r = (tp - entry) / risk
        close_below_zone = any(b["c"] < f(t.get("zone_low", t.get("dz_low"))) for b in path)
        low_below_sl = any(b["l"] <= sl for b in path)
        m60, m60_path = load_bars(sym, "60min_500")
        m60_dates = {b["t"] for b in m60}
        m60_covers = bool(m60_dates) and entry_date in m60_dates and exit_date in m60_dates
        row = {
            "symbol": sym,
            "entry_date": entry_date,
            "exit_date": exit_date,
            "entry_i": entry_i,
            "exit_i": exit_i,
            "path_bars": len(path),
            "entry": round(entry, 4),
            "sl": round(sl, 4),
            "tp": round(tp, 4),
            "target_r": round(target_r, 4),
            "pnl_pct": round(f(t.get("pnl_pct")), 4),
            "official_rr_realized": round(f(t.get("rr_realized")), 4),
            "final_r": round(final_r, 4),
            "max_high_r": round(max_high_r, 4),
            "max_close_r": round((max_close - entry) / risk, 4),
            "min_low_r": round((min_low - entry) / risk, 4),
            "giveback_r": round(giveback_r, 4),
            "max_high_pct": round(pnl_pct(max_high, entry), 4),
            "exit_close_pct": round(pnl_pct(exit_close, entry), 4),
            "close_below_zone": close_below_zone,
            "low_below_sl": low_below_sl,
            "market_state": str(t.get("market_state", "")),
            "reclaim_class": str(t.get("v132_reclaim_class", "")),
            "zone_width_pct": round(f(t.get("v85_zone_width_pct")), 4),
            "post_pullback_depth_3": round(f(t.get("v132_post_zone_pullback_depth_pct_3")), 4),
            "reclaim_body_pct": round(f(t.get("v132_reclaim_bull_body_pct")), 4),
            "entry_chase_above_zone_pct": round(f(t.get("entry_chase_above_zone_pct")), 4),
            "m60_covers_entry_exit": m60_covers,
            "m60_file": m60_path if m60_covers else "",
            "daily_file": daily_path,
        }
        row["path_class"] = classify(row)
        if 0.5 <= row["max_high_r"] <= 1.2:
            row["opportunity_band"] = "MFE_0P5_1P2R"
        elif row["max_high_r"] < 0.5:
            row["opportunity_band"] = "MFE_LT_0P5R"
        else:
            row["opportunity_band"] = "MFE_GT_1P2R"
        rows.append(row)

    by_class = summarize(rows, "path_class")
    by_band = summarize(rows, "opportunity_band")
    by_year = summarize(rows, "entry_date_year") if False else {}
    years = defaultdict(list)
    for r in rows:
        years[r["entry_date"][:4]].append(r)
    by_year = {y: {
        "n": len(xs),
        "wr": round(sum(1 for r in xs if r["pnl_pct"] > 0)/len(xs)*100, 2),
        "avg_pnl": round(sum(r["pnl_pct"] for r in xs)/len(xs), 4),
        "dominant_class": Counter(r["path_class"] for r in xs).most_common(1)[0][0],
    } for y, xs in sorted(years.items())}

    decision = "V178_TIME_PATH_ATTRIBUTION_ONLY__NO_PRODUCTION_WRITE"
    summary = {
        "decision": decision,
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "source": str(TRADES_PATH),
        "production_write": False,
        "frontend_write": False,
        "watchlist_write": False,
        "baseline_v175": BASELINE,
        "time_rows": len(rows),
        "time_rows_expected": len(time_trades),
        "errors": errors,
        "path_class_counts": dict(Counter(r["path_class"] for r in rows)),
        "opportunity_band_counts": dict(Counter(r["opportunity_band"] for r in rows)),
        "by_class": by_class,
        "by_band": by_band,
        "by_year": by_year,
        "m60_coverage": {
            "covered": sum(1 for r in rows if r["m60_covers_entry_exit"]),
            "total": len(rows),
            "rate": round(sum(1 for r in rows if r["m60_covers_entry_exit"]) / len(rows) * 100, 2) if rows else 0,
        },
        "root_cause_boundary": [
            "TIME exits are not one homogeneous problem; generic BE/partial rules failed in V177 because winner truncation dominates.",
            "Daily OHLC attribution identifies the subset that needs 60min executable validation; it is not itself a production rule.",
        ],
        "artifact_dir": str(OUT),
    }
    (OUT / "summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    with open(OUT / "time_rows_attribution.csv", "w", newline="", encoding="utf-8") as fp:
        if rows:
            writer = csv.DictWriter(fp, fieldnames=list(rows[0].keys()))
            writer.writeheader(); writer.writerows(rows)

    md = []
    md.append("# V178 V175 TIME row path attribution")
    md.append("")
    md.append(f"Decision: **{decision}**")
    md.append("")
    md.append("No production/frontend/watchlist write was performed.")
    md.append("")
    md.append("## TIME path classes")
    md.append("| class | n | WR | AvgPnL | avg maxR | avg finalR | avg givebackR | 60min coverage |")
    md.append("|---|---:|---:|---:|---:|---:|---:|---:|")
    for name, m in by_class.items():
        md.append(f"| {name} | {m['n']} | {m['wr']:.2f}% | {m['avg_pnl']:.4f}% | {m['avg_max_high_r']:.4f} | {m['avg_final_r']:.4f} | {m['avg_giveback_r']:.4f} | {m['m60_covered_rate']:.2f}% |")
    md.append("")
    md.append("## Opportunity bands")
    md.append("| band | n | WR | AvgPnL | avg maxR | avg givebackR |")
    md.append("|---|---:|---:|---:|---:|---:|")
    for name, m in by_band.items():
        md.append(f"| {name} | {m['n']} | {m['wr']:.2f}% | {m['avg_pnl']:.4f}% | {m['avg_max_high_r']:.4f} | {m['avg_giveback_r']:.4f} |")
    md.append("")
    md.append("## Boundary")
    md.append("V178 is attribution only. It does not define a production candidate because the sample is only the 65 TIME rows and 60min coverage is measured separately. The next executable test should target only the MID_MFE_0P5_1P2R_GIVEBACK / NEAR_TP_OR_LARGE_GIVEBACK rows with real 60min bars, not the whole V175 universe.")
    (OUT / "report.md").write_text("\n".join(md), encoding="utf-8")

    print(json.dumps({
        "decision": decision,
        "summary": str(OUT / "summary.json"),
        "report": str(OUT / "report.md"),
        "csv": str(OUT / "time_rows_attribution.csv"),
        "time_rows": len(rows),
        "class_counts": summary["path_class_counts"],
        "m60_coverage": summary["m60_coverage"],
    }, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
