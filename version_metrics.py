# -*- coding: utf-8 -*-
"""Summarize all version report metrics from smc_opt_* directories."""
import os, json, re, datetime

ROOT = r"E:\test\smc_project\hermes"

def safe(d, *keys, default=""):
    cur = d
    for k in keys:
        if not isinstance(cur, dict):
            return default
        if k not in cur:
            return default
        cur = cur[k]
    return cur

def fmt(v, nd=2):
    if v in (None, "", 0, "0", 0.0):
        return "-"
    try:
        f = float(v)
        return f"{f:.{nd}f}"
    except (TypeError, ValueError):
        return str(v)

rows = []
for d in sorted(os.listdir(ROOT)):
    if not d.startswith("smc_opt_"):
        continue
    full = os.path.join(ROOT, d)
    if not os.path.isdir(full):
        continue
    # find report json files (small ones)
    for f in sorted(os.listdir(full)):
        if not f.endswith(".json"):
            continue
        if not re.search(r"report|summary|gate", f, re.I):
            continue
        p = os.path.join(full, f)
        try:
            if os.path.getsize(p) > 2_000_000:
                continue
            data = json.load(open(p, encoding="utf-8"))
        except Exception:
            continue
        if not isinstance(data, dict):
            continue
        ver = safe(data, "version") or safe(data, "engine") or f.split("_report")[0]
        gen = safe(data, "generated_at") or safe(data, "date") or ""
        if isinstance(gen, str) and len(gen) >= 8:
            gen = gen[:16]
        # trades metrics - try several shapes
        n = safe(data, "trades", "n") or safe(data, "trades", "count") or safe(data, "n") or safe(data, "production_stats", "n") or safe(data, "tradable_AB", "n") or safe(data, "metrics", "n")
        wr = safe(data, "trades", "wr") or safe(data, "trades", "gross_wr") or safe(data, "wr") or safe(data, "production_stats", "wr") or safe(data, "tradable_AB", "gross_wr") or safe(data, "metrics", "wr") or safe(data, "quality", "qualified_wr")
        avg = safe(data, "trades", "avg_pnl") or safe(data, "avg_pnl") or safe(data, "production_stats", "avg") or safe(data, "tradable_AB", "avg_pnl") or safe(data, "quality", "avg_pnl")
        cum = safe(data, "trades", "cum") or safe(data, "cum") or safe(data, "production_stats", "cum_pnl")
        rr = safe(data, "trades", "avg_rr") or safe(data, "avg_rr") or safe(data, "quality", "avg_realized_r")
        sl = safe(data, "trades", "sl_rate")
        pf = safe(data, "metrics", "pf") or safe(data, "production_stats", "pf") or safe(data, "pf")
        pay = safe(data, "metrics", "payoff") or safe(data, "payoff")
        dec = safe(data, "decision") or safe(data, "gate", "pass") if isinstance(safe(data, "gate"), dict) else safe(data, "gate")
        if dec is True:
            dec = "PASS"
        elif dec is False:
            dec = "FAIL"
        elif dec is None:
            dec = ""
        rows.append({
            "dir": d, "file": f, "ver": str(ver)[:38], "gen": str(gen),
            "n": fmt(n, 0), "wr": fmt(wr), "avg": fmt(avg), "cum": fmt(cum, 1),
            "rr": fmt(rr), "sl": fmt(sl), "pf": fmt(pf), "pay": fmt(pay), "dec": str(dec)[:28],
        })

# dedupe: keep one row per dir (prefer _report.json or version-named)
best = {}
for r in rows:
    d = r["dir"]
    score = 0
    if r["file"].startswith(r["ver"].lower().split("_")[0]) or f.lower().startswith(d.replace("smc_opt_", "")):
        score = 2
    if "report" in r["file"]:
        score += 1
    if "production" in r["file"] or "gate" in r["file"]:
        score += 1
    cur = best.get(d)
    if cur is None or score > cur[0]:
        best[d] = (score, r)

print("version | dir | generated | n | WR% | avg_pnl% | cum% | avg_rr | SL% | PF | payoff | decision")
for d in sorted(best):
    _, r = best[d]
    print(f"{r['ver']} | {r['dir'].replace('smc_opt_','')} | {r['gen']} | {r['n']} | {r['wr']} | {r['avg']} | {r['cum']} | {r['rr']} | {r['sl']} | {r['pf']} | {r['pay']} | {r['dec']}")
print("\nTOTAL dirs parsed:", len(best))
