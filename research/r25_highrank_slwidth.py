# -*- coding: utf-8 -*-
"""R25-H4 预注册假设检验（只读分析, 不改任何生产代码）
假设 H4: HIGH_RANK(rank>=4) 的亏损显著集中在 SL 距离过宽的子集。
若成立 -> E2(min-R:R 入场过滤) 可定向修复 HIGH_RANK 亏损悖论。
数据来源: research/results/combo_v20f_trades.csv (1527 EVENT 腿)
输出: research/handover/r25_h4_highrank_slwidth.json
"""
import io, sys, os, json, csv, statistics
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

RESEARCH = os.path.dirname(os.path.abspath(__file__))
CSV = os.path.join(RESEARCH, "combo_v20f_trades.csv")
FORCE_RANK = "rank"; FORCE_RET = "net_pnl_pct"; FORCE_SL = "risk_pct"

def load():
    rows = []
    with open(CSV, encoding="utf-8") as f:
        for r in csv.DictReader(f):
            rows.append(r)
    return rows

def f(x, d=0.0):
    try:
        return float(x)
    except Exception:
        return d

def main():
    rows = load()
    # 识别列名
    cols = list(rows[0].keys())
    print("列:", cols[:20])
    # 推断字段
    k_rank = FORCE_RANK if FORCE_RANK in cols else next((c for c in cols if "rank" in c.lower()), None)
    k_ret = FORCE_RET if FORCE_RET in cols else next((c for c in cols if c.lower() in ("ret_pct", "pnl_pct", "return_pct", "ret", "net_pnl_pct")), None)
    k_sl = FORCE_SL if FORCE_SL in cols else next((c for c in cols if "sl" in c.lower() and ("dist" in c.lower() or "atr" in c.lower())), None)
    k_atr = next((c for c in cols if "atr" in c.lower()), None)
    print(f"rank列={k_rank} ret列={k_ret} sl_dist列={k_sl} atr列={k_atr}")
    if not (k_rank and k_ret):
        print("缺关键列, 退出"); return

    losses = [r for r in rows if f(r.get(k_ret)) < 0]
    print(f"总腿={len(rows)} 亏损腿={len(losses)}")

    def bucket(rs, pred):
        sel = [r for r in rs if pred(r)]
        return len(sel), (statistics.mean(f(r[k_ret]) for r in sel) if sel else None)

    hi = lambda r: f(r[k_rank]) >= 4
    lo = lambda r: f(r[k_rank]) < 4

    res = {"n_rows": len(rows), "n_losses": len(losses),
           "rank_col": k_rank, "ret_col": k_ret}

    # 基础: rank 分层在亏损中的分布
    n_hi, avg_hi = bucket(losses, hi)
    n_lo, avg_lo = bucket(losses, lo)
    res["losses"] = {"rank>=4": {"n": n_hi, "avg_ret": avg_hi},
                     "rank<4": {"n": n_lo, "avg_ret": avg_lo}}
    print(f"亏损腿: rank>=4 n={n_hi} avg={avg_hi and round(avg_hi,2)}%  rank<4 n={n_lo} avg={avg_lo and round(avg_lo,2)}%")

    # H4 核心: rank>=4 亏损中, SL 距离分布 (若有列)
    if k_sl:
        hi_losses = [r for r in losses if hi(r)]
        sls = [f(r[k_sl]) for r in hi_losses]
        if sls:
            sls_sorted = sorted(sls)
            res["h4_slwidth_on_highrank_losses"] = {
                "n": len(sls), "median": sls_sorted[len(sls)//2],
                "mean": statistics.mean(sls),
                "p25": sls_sorted[len(sls)//4], "p75": sls_sorted[3*len(sls)//4],
            }
            print("rank>=4 亏损 SL距离: n=%d median=%.2f mean=%.2f p25=%.2f p75=%.2f" % (
                len(sls), sls_sorted[len(sls)//2], statistics.mean(sls),
                sls_sorted[len(sls)//4], sls_sorted[3*len(sls)//4]))
            # 对比: rank>=4 盈利腿的 SL 距离
            wins_hi = [r for r in rows if hi(r) and f(r[k_ret]) >= 0]
            wsls = [f(r[k_sl]) for r in wins_hi]
            if wsls:
                ws = sorted(wsls)
                res["h4_slwidth_on_highrank_wins"] = {
                    "n": len(wsls), "median": ws[len(ws)//2], "mean": statistics.mean(wsls)}
                print("rank>=4 盈利 SL距离: n=%d median=%.2f mean=%.2f" % (
                    len(wsls), ws[len(ws)//2], statistics.mean(wsls)))
                # H4 判定: 亏损的 SL 是否显著更宽?
                mw = statistics.mean(wsls); ml = statistics.mean(sls)
                res["h4_verdict"] = {
                    "loss_sl_mean": round(ml, 3), "win_sl_mean": round(mw, 3),
                    "diff_pct": round((ml - mw) / mw * 100, 1) if mw else None,
                    "supports_H4": bool(ml > mw * 1.10),
                }
                print(f"H4 判定: 亏损SL均={ml:.3f} vs 盈利SL均={mw:.3f} -> {'支持' if ml > mw*1.10 else '不支持'}")

    out = os.path.join(RESEARCH, "handover", "r25_h4_highrank_slwidth.json")
    json.dump(res, open(out, "w", encoding="utf-8"), ensure_ascii=False, indent=2)
    print("写出:", out)

if __name__ == "__main__":
    main()
