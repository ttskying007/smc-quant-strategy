#!/usr/bin/env python3
"""V179 research-only 60min probe for V175 TIME rows.

Assumptions:
- Read-only research except refreshing local 60min cache files for involved symbols.
- Tencent 60min endpoint only provides recent bars; old 2023-2025 TIME rows are expected to remain uncovered.
- T+1: intraday path starts from the first 60min bar whose date is later than entry_date.
- This is a feasibility probe, not a production candidate.
"""
import csv
import json
import time
import urllib.request
from collections import Counter, defaultdict
from datetime import datetime
from pathlib import Path

HOME = Path.home()
TRADES_PATH = HOME / ".hermes/smc_opt_v175_semantic_split/v175_trades.json"
CACHE = HOME / ".hermes/kline_cache"
OUT = HOME / f".hermes/smc_audit/v179_v175_time_60min_probe_{datetime.now().strftime('%Y%m%d_%H%M%S')}"


def f(x, default=0.0):
    try:
        if x is None or x == "":
            return default
        return float(x)
    except Exception:
        return default


def market_code(symbol):
    code, exch = symbol.split(".")
    return ("sh" if exch == "SH" else "sz") + code


def cache_path(symbol):
    return CACHE / f"{symbol.replace('.', '_')}_60min_500.json"


def fetch_60(symbol):
    m = market_code(symbol)
    url = f"http://ifzq.gtimg.cn/appstock/app/kline/mkline?param={m},m60,,500"
    raw = urllib.request.urlopen(url, timeout=20).read().decode("utf-8", "ignore")
    obj = json.loads(raw)
    rows = obj.get("data", {}).get(m, {}).get("m60", [])
    bars = []
    for r in rows:
        if len(r) < 5:
            continue
        bars.append({"t": str(r[0]), "o": f(r[1]), "c": f(r[2]), "h": f(r[3]), "l": f(r[4]), "v": f(r[5]) if len(r) > 5 else 0})
    if len(bars) < 20:
        raise RuntimeError(f"too_few_60min_rows={len(bars)}")
    p = cache_path(symbol)
    p.write_text(json.dumps(bars, ensure_ascii=False), encoding="utf-8")
    return bars


def load_60(symbol):
    p = cache_path(symbol)
    if not p.exists() or p.stat().st_size < 100:
        return []
    bars = json.loads(p.read_text())
    bars = [{"t": str(b.get("t", "")), "o": f(b.get("o")), "h": f(b.get("h")), "l": f(b.get("l")), "c": f(b.get("c"))} for b in bars]
    bars = [b for b in bars if b["t"] and b["o"] and b["h"] and b["l"] and b["c"]]
    if len(bars) >= 2 and bars[0]["t"] > bars[1]["t"]:
        bars.reverse()
    return bars


def classify_60(row):
    if not row["covered"]:
        return "NO_60MIN_COVERAGE"
    if row["hit_tp_intraday"]:
        return "INTRADAY_TP_WAS_REACHABLE"
    if row["max_r_60"] >= 1.2 and row["giveback_r_60"] >= 0.7:
        return "INTRADAY_NEAR_TP_GIVEBACK"
    if 0.5 <= row["max_r_60"] < 1.2 and row["giveback_r_60"] >= 0.4:
        return "INTRADAY_MID_MFE_GIVEBACK"
    if row["max_r_60"] < 0.5:
        return "INTRADAY_NO_FOLLOW_THROUGH"
    return "INTRADAY_HELD_REASONABLE"


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    trades = json.loads(TRADES_PATH.read_text())
    time_trades = [t for t in trades if str(t.get("exit_reason")) == "TIME"]
    symbols = sorted({t["symbol"] for t in time_trades})
    fetch_results = []
    for sym in symbols:
        try:
            bars = fetch_60(sym)
            fetch_results.append({"symbol": sym, "ok": True, "rows": len(bars), "first": bars[0]["t"], "last": bars[-1]["t"], "path": str(cache_path(sym))})
        except Exception as e:
            fetch_results.append({"symbol": sym, "ok": False, "error": str(e), "path": str(cache_path(sym))})
        time.sleep(0.03)

    rows = []
    for t in time_trades:
        sym = t["symbol"]
        entry = f(t.get("entry_price", t.get("price")))
        sl = f(t.get("sl", t.get("sl_price")))
        tp = f(t.get("tp", t.get("tp1")))
        risk = entry - sl
        entry_date = str(t.get("entry_date"))[:8]
        exit_date = str(t.get("exit_date"))[:8]
        bars = load_60(sym)
        path = [b for b in bars if entry_date < b["t"][:8] <= exit_date]
        covered = bool(path) and path[0]["t"][:8] > entry_date and path[-1]["t"][:8] == exit_date and risk > 0
        row = {
            "symbol": sym,
            "entry_date": entry_date,
            "exit_date": exit_date,
            "year": entry_date[:4],
            "pnl_pct": round(f(t.get("pnl_pct")), 4),
            "entry": round(entry, 4),
            "sl": round(sl, 4),
            "tp": round(tp, 4),
            "covered": covered,
            "m60_bars": len(path),
            "first_m60": path[0]["t"] if path else "",
            "last_m60": path[-1]["t"] if path else "",
        }
        if covered:
            max_h = max(b["h"] for b in path)
            min_l = min(b["l"] for b in path)
            exit_c = path[-1]["c"]
            max_r = (max_h - entry) / risk
            final_r = (exit_c - entry) / risk
            row.update({
                "max_r_60": round(max_r, 4),
                "final_r_60": round(final_r, 4),
                "giveback_r_60": round(max(0, max_r - final_r), 4),
                "hit_tp_intraday": max_h >= tp,
                "hit_sl_intraday": min_l <= sl,
                "max_pct_60": round((max_h / entry - 1) * 100, 4),
                "exit_close_pct_60": round((exit_c / entry - 1) * 100, 4),
            })
        else:
            row.update({"max_r_60": 0, "final_r_60": 0, "giveback_r_60": 0, "hit_tp_intraday": False, "hit_sl_intraday": False, "max_pct_60": 0, "exit_close_pct_60": 0})
        row["class_60"] = classify_60(row)
        rows.append(row)

    def group(key):
        g = defaultdict(list)
        for r in rows:
            g[r[key]].append(r)
        out = {}
        for k, xs in sorted(g.items(), key=lambda kv: (-len(kv[1]), kv[0])):
            covered = [r for r in xs if r["covered"]]
            out[k] = {
                "n": len(xs),
                "covered": len(covered),
                "coverage_rate": round(len(covered) / len(xs) * 100, 2),
                "avg_pnl": round(sum(r["pnl_pct"] for r in xs) / len(xs), 4),
                "avg_max_r_covered": round(sum(r["max_r_60"] for r in covered) / len(covered), 4) if covered else None,
                "avg_giveback_r_covered": round(sum(r["giveback_r_60"] for r in covered) / len(covered), 4) if covered else None,
            }
        return out

    decision = "V179_60MIN_COVERAGE_INSUFFICIENT_FOR_PRODUCTION__NO_WRITE"
    covered_total = sum(1 for r in rows if r["covered"])
    summary = {
        "decision": decision,
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "production_write": False,
        "frontend_write": False,
        "watchlist_write": False,
        "time_rows": len(rows),
        "covered_rows": covered_total,
        "coverage_rate": round(covered_total / len(rows) * 100, 2) if rows else 0,
        "fetch_ok": sum(1 for x in fetch_results if x["ok"]),
        "fetch_total": len(fetch_results),
        "class_counts": dict(Counter(r["class_60"] for r in rows)),
        "by_class_60": group("class_60"),
        "by_year": group("year"),
        "fetch_results": fetch_results,
        "artifact_dir": str(OUT),
        "boundary": "Tencent 60min only covered recent rows; historical 2023-2025 TIME rows cannot be validated from current 60min cache/API, so no production/research gate can be claimed.",
    }
    (OUT / "summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    with open(OUT / "time_60min_probe_rows.csv", "w", newline="", encoding="utf-8") as fp:
        if rows:
            w = csv.DictWriter(fp, fieldnames=list(rows[0].keys()))
            w.writeheader(); w.writerows(rows)
    md = []
    md.append("# V179 V175 TIME 60min executable probe")
    md.append("")
    md.append(f"Decision: **{decision}**")
    md.append("")
    md.append("No production/frontend/watchlist write was performed.")
    md.append("")
    md.append("## 60min classes")
    md.append("| class | n | covered | coverage | AvgPnL | avg maxR covered | avg givebackR covered |")
    md.append("|---|---:|---:|---:|---:|---:|---:|")
    for k, v in summary["by_class_60"].items():
        md.append(f"| {k} | {v['n']} | {v['covered']} | {v['coverage_rate']:.2f}% | {v['avg_pnl']:.4f}% | {v['avg_max_r_covered']} | {v['avg_giveback_r_covered']} |")
    md.append("")
    md.append("## Boundary")
    md.append(summary["boundary"])
    (OUT / "report.md").write_text("\n".join(md), encoding="utf-8")
    print(json.dumps({
        "decision": decision,
        "summary": str(OUT / "summary.json"),
        "report": str(OUT / "report.md"),
        "csv": str(OUT / "time_60min_probe_rows.csv"),
        "coverage": {"covered": covered_total, "total": len(rows), "rate": summary["coverage_rate"]},
        "class_counts": summary["class_counts"],
    }, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
