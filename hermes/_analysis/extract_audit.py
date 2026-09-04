# -*- coding: utf-8 -*-
"""Scan smc_audit/ closure & decision docs, extract version conclusions."""
import json, os, glob, re, csv

ROOT = r"E:\test\smc_project\hermes"
AUDIT = os.path.join(ROOT, "smc_audit")

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

def extract_strings(d, keys, maxlen=400):
    out = []
    if isinstance(d, dict):
        for k in keys:
            v = d.get(k)
            if isinstance(v, str):
                out.append(v)
            elif isinstance(v, dict):
                for kk in keys:
                    if kk in v and isinstance(v[kk], str):
                        out.append(v[kk])
    return " | ".join(out)[:maxlen]

def first_metric(d, keys):
    """Find first numeric value under any of keys, recursive 3 levels."""
    if isinstance(d, dict):
        for k in keys:
            if k in d and num(d[k]) is not None:
                return num(d[k])
        for v in d.values():
            r = first_metric(v, keys)
            if r is not None:
                return r
    elif isinstance(d, list):
        for it in d[:5]:
            r = first_metric(it, keys)
            if r is not None:
                return r
    return None

rows = []
files = sorted(glob.glob(os.path.join(AUDIT, "*.json"))) + sorted(glob.glob(os.path.join(AUDIT, "*.md")))
for f in files:
    bn = os.path.basename(f)
    low = bn.lower()
    if not any(t in low for t in ("closure", "gate", "audit", "report", "decision", "conclusion", "verdict", "replay", "oracle")):
        continue
    # skip massive pure-audit dump files
    if os.path.getsize(f) > 400 * 1024:
        continue
    ver = re.search(r"[vV](\d+[a-z]?)", bn)
    ver = ver.group(1) if ver else "?"
    rec = {"file": bn, "version": ver, "size": os.path.getsize(f), "date": "", "decision": "", "n": "", "wr": "", "avg_pnl": "", "detail": ""}
    if bn.endswith(".json"):
        try:
            with open(f, "r", encoding="utf-8") as fh:
                d = json.load(fh)
        except Exception:
            rec["decision"] = "(parse fail)"
            rows.append(rec)
            continue
        if isinstance(d, dict):
            rec["date"] = d.get("generated_at") or d.get("run_at") or ""
            rec["decision"] = extract_strings(d, ["decision", "headline", "conclusion", "verdict", "gate_reason", "final_verdict", "status", "reason", "promotion_decision", "production_blocker"])
            # headline dict may carry nested decisions
            hd = d.get("headline")
            if isinstance(hd, dict):
                sub = extract_strings(hd, ["decision", "v344_decision", "v345_decision", "gate_passed", "status"])
                if sub:
                    rec["decision"] = sub + " || " + rec["decision"]
            rec["n"] = first_metric(d, ["n", "n_trades", "trade_count", "closed_trade_count", "seed_count", "rows", "trades"])
            rec["wr"] = first_metric(d, ["wr", "net_wr_ge_0_8", "gross_wr", "gross_wr_pct", "win_rate", "net_wr"])
            rec["avg_pnl"] = first_metric(d, ["avg_pnl", "avg", "avg_net_pnl_pct", "avg_net_pnl", "avg_net", "avg_realized_R"])
        elif isinstance(d, list):
            rec["decision"] = "(list)"
    else:
        # markdown
        try:
            with open(f, "r", encoding="utf-8") as fh:
                txt = fh.read()
        except Exception:
            txt = ""
        # extract first heading + decision-like lines
        heads = re.findall(r"^#+\s*(.*)$", txt, re.M)
        if heads:
            rec["decision"] = heads[0][:200]
        for m in re.finditer(r"(?im)^\s*(?:##?\s*)?(?:结论|decision|DECISION|verdict|VERDICT|结论与边界|gate|Gate)\s*[:：]\s*(.+)$", txt):
            rec["decision"] += " || " + m.group(1).strip()[:300]
        # look for 净胜率/avg_net_pnl patterns
        mm = re.search(r"净胜率[:：]\s*([\d.]+)%", txt)
        if mm:
            rec["wr"] = mm.group(1)
        mm = re.search(r"平均净收益[:：]\s*([+\-]?[\d.]+)%", txt)
        if mm:
            rec["avg_pnl"] = mm.group(1)
        mm = re.search(r"平均净收益[^\d]*([+\-]?[\d.]+)%", txt)
        if mm and not rec["avg_pnl"]:
            rec["avg_pnl"] = mm.group(1)
        mm = re.search(r"PF[:：]\s*([\d.]+)", txt)
        if mm:
            rec["detail"] = "PF=" + mm.group(1)
    rows.append(rec)

out_csv = os.path.join(ROOT, "_analysis", "audit_closures.csv")
with open(out_csv, "w", newline="", encoding="utf-8-sig") as fh:
    w = csv.DictWriter(fh, fieldnames=["file", "version", "size", "date", "decision", "n", "wr", "avg_pnl", "detail"])
    w.writeheader()
    for r in rows:
        w.writerow(r)
print("audit docs scanned:", len(rows))
