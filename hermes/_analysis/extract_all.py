# -*- coding: utf-8 -*-
"""Extract per-version backtest metrics from smc_opt_v*/ reports and smc_audit closures."""
import json, os, glob, re, csv, sys

ROOT = r"E:\test\smc_project\hermes"
MAXSIZE = 10 * 1024 * 1024

# ---------------------------------------------------------------- helpers
def num(v):
    if isinstance(v, (int, float)):
        return v
    if isinstance(v, str):
        try:
            return float(v.replace("%", "").replace(",", ""))
        except Exception:
            return None
    return None

def get(d, *path):
    cur = d
    for p in path:
        if isinstance(cur, dict) and p in cur:
            cur = cur[p]
        else:
            return None
    return cur

# ---------------------------------------------------------------- version number from dir/file name
def version_of(path):
    dm = re.search(r"smc_opt_v(\d+[a-f]?[_\d]*)", os.path.basename(os.path.dirname(path)))
    if dm:
        return dm.group(1).replace("_", ".")
    fm = re.search(r"[vV](\d+[a-f]?[_\d]*)", os.path.basename(path))
    if fm:
        return fm.group(1).replace("_", ".")
    return "?"

# ---------------------------------------------------------------- recursive metric-block search
SKIP_KEYS = {"by_year", "year", "yearly", "months", "monthly", "by_market_state", "by_exit_reason",
             "by_exit", "by_family", "by_tier", "by_path", "by_mtf_score", "by_sl_mode", "by_tp_mode",
             "by_entry_mode", "by_combo", "by_gate", "by_gate_recent", "by_recovery_substate",
             "by_known_target", "by_event_type", "by_month", "by_year_wr", "by_year_baseline",
             "by_year_v95", "tradable_AB_by_year", "ABC_by_year", "production_by_year",
             "year_counts", "year_wr", "buckets", "top_results", "leaderboard_top50", "matrix_rows",
             "tested_candidates", "candidate", "candidates", "top_gates", "gate_metrics", "layers",
             "buckets_base", "buckets_best", "selected_buckets", "combo_table", "rows", "data"}

def looks_metric_block(d):
    if not isinstance(d, dict):
        return False
    has_n = any(k in d for k in ("n", "n_trades", "trade_count", "closed_trade_count"))
    has_wr = any(k in d for k in ("wr", "raw_wr", "win_rate", "net_wr_ge_0_8", "gross_wr", "gross_wr_pct"))
    has_pnl = any(k in d for k in ("avg_pnl", "avg", "avg_net_pnl", "avg_net_pnl_pct", "avg_net", "avg_realized_R", "avg_realized_r"))
    return has_n and has_wr and has_pnl

def recursive_metric_blocks(d, path="", depth=0):
    """Yield (path, block) for dicts that look like metric blocks."""
    if depth > 6 or not isinstance(d, dict):
        return
    if looks_metric_block(d) and len(d) <= 25:
        yield path, d
    for k, v in d.items():
        if k in SKIP_KEYS:
            continue
        if isinstance(v, dict):
            yield from recursive_metric_blocks(v, path + "/" + str(k), depth + 1)

PREFERRED = ["trades", "production_stats", "production_candidate", "metrics", "selected_metrics",
             "v172_metrics", "v185_metrics", "overall", "overall_metrics", "tradable_AB",
             "lc_core_valid", "v74_core_gate", "v76_strict_gate", "v77_gate", "v78_full_gate",
             "v79_lifecycle_valid", "v80_original_exit", "v82_selected", "v83_selected",
             "v84_selected", "v85_production", "v85_selected", "v86_selected", "v87_selected",
             "v88_trades", "v90_summary", "v91_summary", "v95_exit_contract", "v102",
             "v103a", "v104b_core", "v105a_clean", "best_by_score", "base_v71", "base_v74",
             "v74_selected", "v71_metrics", "base_metrics", "metrics_weighted", "selected",
             "best_variant", "best", "stats", "overall", "global", "production", "result",
             "summary", "production_stats", "production_candidate", "best_production_like",
             "best_production_like_candidate", "best_wr_candidate", "elite_mtf_rr_candidate"]

def pick_metrics_block(d):
    """Pick best metrics block: preferred keys first, then recursive search."""
    # 1. preferred key paths
    for key in PREFERRED:
        v = d.get(key)
        if isinstance(v, dict) and looks_metric_block(v):
            return key, v
        if isinstance(v, list):
            for it in v:
                if isinstance(it, dict) and looks_metric_block(it):
                    return key + "[0]", it
    # 2. flat (v97/v98 style)
    if isinstance(d.get("production_trades"), (int, float)):
        return "flat", {
            "n": d.get("production_trades"),
            "wr": d.get("production_wr"),
            "avg_pnl": d.get("production_avg_pnl"),
            "cum": d.get("production_cum_pnl"),
            "sl_rate": d.get("production_sl_rate"),
        }
    # 3. v175 flat
    if "win_rate" in d and "avg_pnl" in d:
        return "flat175", {
            "n": d.get("n"),
            "wr": d.get("win_rate"),
            "avg_pnl": d.get("avg_pnl"),
            "sl_rate": d.get("sl_rate"),
        }
    # 4. v104 metrics
    if isinstance(d.get("metrics"), dict) and isinstance(d["metrics"].get("n"), (int, float)):
        m = d["metrics"]
        if "net_wr_ge_0_8" in m:
            return "metrics", m
    # 5. recursive search
    best = None
    for path, block in recursive_metric_blocks(d):
        # prefer blocks with cum or sl_rate too
        score = 0
        if get_metric(block, "cum") is not None:
            score += 2
        if get_metric(block, "sl_rate") is not None:
            score += 1
        if get_metric(block, "avg_rr") is not None:
            score += 1
        if best is None or score > best[0]:
            best = (score, path, block)
    if best:
        return best[1], best[2]
    return None, None

def get_metric(m, field):
    if not isinstance(m, dict):
        return None
    keys = {
        "n": ["n", "n_trades", "trade_count", "closed_trade_count"],
        "wr": ["wr", "raw_wr", "win_rate", "net_wr_ge_0_8", "gross_wr", "gross_wr_pct",
               "net_win_rate_ge_0_8", "gross_wr_gt_0"],
        "avg_pnl": ["avg_pnl", "avg", "avg_net_pnl", "avg_net_pnl_pct", "avg_net", "avg_realized_R",
                    "avg_realized_r", "average_net", "avg_net_pnl_pct"],
        "cum": ["cum", "cum_pnl", "total_pnl", "cum_net_pnl", "total_net_pnl_pct", "total_net",
                "cum_net_pnl", "total_pnl_pct"],
        "avg_rr": ["avg_rr", "avg_realized_r", "avg_realized_R", "realized_rr", "rr", "payoff_rr",
                   "payoff_ratio", "payoff"],
        "sl_rate": ["sl_rate", "sl", "loss_rate", "loss_pct", "sl_rate_pct"],
    }
    for k in keys[field]:
        v = m.get(k)
        if v is not None:
            nv = num(v)
            if nv is not None:
                return nv
    return None

def get_decision(d):
    out = []
    for k in ["decision", "promotion_decision", "promotion_reason", "production_blocker",
              "verdict", "conclusion", "final_verdict", "production_ready", "production_readiness",
              "promotion_candidate", "effect_pass", "production_pass", "promotion_gate",
              "release_gate", "gate", "production_acceptance", "headline", "acceptance"]:
        v = d.get(k)
        if isinstance(v, str):
            out.append(v)
        elif isinstance(v, dict):
            if "decision" in v and isinstance(v["decision"], str):
                out.append(v["decision"])
            if "pass" in v:
                out.append("pass=" + str(v["pass"]))
            if "reason" in v and isinstance(v["reason"], str):
                out.append(str(v["reason"])[:200])
            if isinstance(v.get("production_gate"), dict):
                out.append("prod_gate=" + json.dumps(v["production_gate"], ensure_ascii=False)[:150])
    return " | ".join(out)[:500]

def get_by_year(d):
    by_year = None
    for key in ["by_year", "tradable_AB_by_year", "year", "production_by_year", "yearly", "by_year_v95"]:
        v = d.get(key)
        if isinstance(v, dict):
            by_year = v
            break
    if not by_year:
        return ""
    rows = []
    for y, m in by_year.items():
        if isinstance(m, dict) and isinstance(y, str) and re.match(r"^20\d\d$", y):
            n = get_metric(m, "n")
            wr = get_metric(m, "wr")
            ap = get_metric(m, "avg_pnl")
            rows.append((y, n, wr, ap))
    rows.sort()
    parts = []
    for y, n, wr, ap in rows:
        s = f"{y}:n={n}"
        if wr is not None:
            s += f",wr={wr:.1f}"
        if ap is not None:
            s += f",avg={ap:.2f}"
        parts.append(s)
    return "; ".join(parts)

# ---------------------------------------------------------------- process each report
report_files = []
for d in sorted(glob.glob(os.path.join(ROOT, "smc_opt_v*"))):
    if not os.path.isdir(d):
        continue
    for f in sorted(glob.glob(os.path.join(d, "*.json"))):
        bn = os.path.basename(f).lower()
        if "report" not in bn and "summary" not in bn and "gate" not in bn and "matrix" not in bn:
            continue
        if os.path.getsize(f) > MAXSIZE:
            continue
        report_files.append(f)

rows = []
for f in report_files:
    try:
        with open(f, "r", encoding="utf-8") as fh:
            d = json.load(fh)
    except Exception as e:
        rows.append({"file": f, "version": version_of(f), "error": str(e)})
        continue
    if not isinstance(d, dict):
        rows.append({"file": f, "version": version_of(f), "error": "not dict"})
        continue
    key, m = pick_metrics_block(d)
    if m is None:
        rows.append({"file": f, "version": version_of(f), "engine": d.get("engine"), "error": "no metrics block"})
        continue
    row = {
        "file": f,
        "version": version_of(f),
        "engine": d.get("engine") or d.get("version") or d.get("profile") or key,
        "date": d.get("generated_at") or d.get("latest_market_date") or d.get("latest_date") or d.get("run_at") or "",
        "n": get_metric(m, "n"),
        "wr": get_metric(m, "wr"),
        "avg_pnl": get_metric(m, "avg_pnl"),
        "cum": get_metric(m, "cum"),
        "avg_rr": get_metric(m, "avg_rr"),
        "sl_rate": get_metric(m, "sl_rate"),
        "by_year": get_by_year(d),
        "decision": get_decision(d),
    }
    rows.append(row)

out_csv = os.path.join(ROOT, "_analysis", "versions_report.csv")
with open(out_csv, "w", newline="", encoding="utf-8-sig") as fh:
    w = csv.DictWriter(fh, fieldnames=["file", "version", "engine", "date", "n", "wr", "avg_pnl", "cum", "avg_rr", "sl_rate", "by_year", "decision", "error"])
    w.writeheader()
    for r in rows:
        w.writerow(r)

print("rows:", len(rows))
for r in rows:
    if r.get("error"):
        print("ERR", r["version"], r["file"], r["error"])
