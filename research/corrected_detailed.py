# -*- coding: utf-8 -*-
"""逐信号独立 CSV + 年度/月度总报告。复用 already-computed corrected 逐笔。"""
import csv, json, os, sys, time
from collections import defaultdict
try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

RESEARCH = os.path.dirname(os.path.abspath(__file__))
OUTDIR = os.path.join(RESEARCH, "corrected_detail")
os.makedirs(OUTDIR, exist_ok=True)
SRC = os.path.join(RESEARCH, "corrected_trades.csv")
HORIZONS = [("r1",1), ("r5",5), ("r10",10), ("r20",20)]


def load():
    rows = []
    with open(SRC, encoding="utf-8") as f:
        for r in csv.DictReader(f):
            rows.append(r)
    return rows


def _stats(vals):
    if not vals: return None
    n = len(vals)
    mean = sum(vals)/n
    med = sorted(vals)[n//2]
    win = sum(1 for v in vals if v>0)/n*100
    sd = (sum((v-mean)**2 for v in vals)/n)**0.5
    return {"n":n,"mean":round(mean,3),"median":round(med,3),"win_rate":round(win,1),"std":round(sd,3)}


def main():
    rows = load()
    print(f"加载 {len(rows)} 笔", flush=True)
    sigs = sorted(set(r["signal"] for r in rows))
    # 1. 逐信号 CSV
    sig_rows = {s: [] for s in sigs}
    for r in rows:
        sig_rows[r["signal"]].append(r)
    print(f"信号: {sigs}", flush=True)
    for s in sigs:
        sr = sig_rows[s]
        path = os.path.join(OUTDIR, f"signal_{s}.csv")
        with open(path, "w", newline="", encoding="utf-8") as f:
            w = csv.DictWriter(f, fieldnames=["code","signal_date","buy_date","year","month","regime","r1","r5","r10","r20","ewm_exit","ewm_hold","ewm_pnl"])
            w.writeheader()
            for r in sr:
                w.writerow({k:r.get(k,"") for k in w.fieldnames})
        print(f"  {s}: {len(sr)} 笔 -> {path}", flush=True)
    # 2. 年度/月度统计
    def _gather(key, gk_func):
        out = {}
        for s in sigs:
            buckets = {}
            for r in sig_rows[s]:
                gk = gk_func(r)
                if gk not in buckets:
                    buckets[gk] = {hn:[] for hn,_ in HORIZONS}
                    buckets[gk]["ewm"] = []
                for hn,_ in HORIZONS:
                    v = r.get(hn)
                    if v not in (None,""):
                        buckets[gk][hn].append(float(v))
                ev = r.get("ewm_pnl")
                if ev not in (None,""):
                    buckets[gk]["ewm"].append(float(ev))
            out[s] = {k:{hn:_stats(v) for hn,v in d.items()} for k,d in buckets.items()}
        return out
    yearly = _gather("year", lambda r: r["year"])
    monthly = _gather("month", lambda r: r["month"])
    # 3. 报告
    lines = []
    lines.append("# corrected 逐信号独立回测报告\n")
    lines.append(f"- 生成: {time.strftime('%Y-%m-%d %H:%M:%S')}")
    lines.append(f"- 总逐笔: {len(rows)}")
    lines.append(f"- 信号: {sigs}")
    lines.append(f"- 输出: {OUTDIR}\n")
    # 总体
    lines.append("## 一、总体（20日）\n")
    lines.append("| 信号 | n | r20均值 | r20中位 | r20胜率 | ewm均值 |")
    lines.append("|---|---|---|---|---|---|")
    for s in sigs:
        r20 = _stats([float(r["r20"]) for r in sig_rows[s] if r.get("r20") not in (None,"")]) or {}
        e = _stats([float(r["ewm_pnl"]) for r in sig_rows[s] if r.get("ewm_pnl") not in (None,"")]) or {}
        lines.append(f"| {s} | {r20.get('n','-')} | {r20.get('mean','-')} | {r20.get('median','-')} | {r20.get('win_rate','-')} | {e.get('mean','-')} |")
    # 逐年
    lines.append("\n## 二、逐年（20日）\n")
    lines.append("| 年份 | 信号 | n | r20均值 | r20中位 | r20胜率 | ewm均值 |")
    lines.append("|---|---|---|---|---|---|---|")
    for s in sigs:
        for y in sorted(yearly[s].keys()):
            r20 = yearly[s].get(y,{}).get("r20") or {}
            e = yearly[s].get(y,{}).get("ewm") or {}
            lines.append(f"| {y} | {s} | {r20.get('n','-')} | {r20.get('mean','-')} | {r20.get('median','-')} | {r20.get('win_rate','-')} | {e.get('mean','-')} |")
    # 逐月
    lines.append("\n## 三、逐月（20日）\n")
    lines.append("| 月份 | 信号 | n | r20均值 | r20中位 | r20胜率 | 备注 |")
    lines.append("|---|---|---|---|---|---|---|")
    for s in sigs:
        for m in sorted(monthly[s].keys()):
            r20 = monthly[s].get(m,{}).get("r20") or {}
            n = r20.get("n",0)
            flag = " ⚠n<30" if n and n<30 else ""
            lines.append(f"| {m} | {s} | {n} | {r20.get('mean','-')} | {r20.get('median','-')} | {r20.get('win_rate','-')} |{flag}")
    lines.append("\n---\n逐信号 CSV 见 corrected_detail/ 目录。")
    md = os.path.join(RESEARCH, "corrected_detail_report.md")
    with open(md, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))
    print(f"报告: {md}", flush=True)


if __name__ == "__main__":
    main()