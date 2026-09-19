import csv, os, sys, json, statistics
sys.stdout.reconfigure(encoding="utf-8", errors="replace")
HERE = os.path.dirname(os.path.abspath(__file__))
rows = []
for r in csv.DictReader(open(os.path.join(HERE, "combo_v20f_trades.csv"), encoding="utf-8-sig")):
    if not (r.get("buy_price") or "").strip(): continue
    try:
        r["_pnl"] = float(r["net_pnl_pct"]); r["_mfe"] = float(r["mfe_pct"]) if r.get("mfe_pct") else None
        r["_mae"] = float(r["mae_pct"]) if r.get("mae_pct") else None
    except Exception: continue
    rows.append(r)

def m(rs):
    if not rs: return None
    g = lambda k, fn: fn(x[k] for x in rs if x[k] is not None)
    try:
        return {"n": len(rs), "avg_pnl": round(statistics.mean(r["_pnl"] for r in rs), 2),
                "avg_mfe": round(g("_mfe", statistics.mean), 2), "med_mfe": round(g("_mfe", statistics.median), 2),
                "avg_mae": round(g("_mae", statistics.mean), 2),
                "giveback_pts": round(g("_mfe", statistics.mean) - statistics.mean(r["_pnl"] for r in rs), 2)}
    except Exception as e: return {"err": str(e)}

out = {}
for reason in ("TIME_STOP", "TP2_RUNNER", "BE", "SL_GAP", "SL_HIT"):
    sel = [r for r in rows if r.get("reason") == reason]
    out[reason] = m(sel)
    print(reason, out[reason])

# TIME_STOP 内: MFE>=8% 但最终只兑现一点点的腿 — "回吐大户"
ts = [r for r in rows if r.get("reason") == "TIME_STOP" and r["_mfe"] is not None]
big_gb = [r for r in ts if r["_mfe"] - r["_pnl"] >= 5]
out["time_stop_big_giveback"] = {"n": len(big_gb), "share": round(len(big_gb)/len(ts)*100, 1) if ts else 0,
                                 "avg_mfe": round(statistics.mean(r["_mfe"] for r in big_gb), 1) if big_gb else 0,
                                 "avg_pnl": round(statistics.mean(r["_pnl"] for r in big_gb), 1) if big_gb else 0}
print("TIME_STOP 回吐>=5pp:", out["time_stop_big_giveback"])

# TP2_RUNNER: 退出后假设继续持有到 TIME_STOP 会不会更多? 用 mfe 无法回答(退出即终止 mfe) — 跳过, 记录不可回答
out["note_tp2_unanswerable"] = "TP2_RUNNER 的 mfe 截断在退出点, 无法从CSV估计继续持有收益; 需 bar 级 replay"
json.dump(out, open(os.path.join(HERE, "handover", "r34b_mfe_giveback.json"), "w", encoding="utf-8"),
          ensure_ascii=False, indent=2)
print("写出 handover/r34b_mfe_giveback.json")
