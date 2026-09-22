# -*- coding: utf-8 -*-
"""jev_whale_r72.py — R72: 大资金(内部人)窗口分析
q: 入场时点前 90 天 公告窗里增持/回购金额/次数 与 pnl 的相关性"""
import csv, os, sqlite3, sys, io
from collections import defaultdict
from datetime import datetime, timedelta

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
ROOT = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, ROOT)
import config as CFG  # noqa
from core.events import classify_title

LEGS = os.path.join(ROOT, "combo_v22_trades.csv")
OUT = os.path.join(ROOT, "handover", "R72_whale_window.md")

WH = "增持|回购"


def bucket_amt(amt):
    if amt is None:
        return "未披露金额"
    v = float(amt)
    if v < 500:
        return "小于500万"
    if v < 2000:
        return "500-2kw"
    if v < 10000:
        return "2千-1亿"
    return "1亿以上"


def bucket_cnt(n):
    return {"0": "0次", "1": "1次", "2": "2次", "3": "3次+"}.get(min(n, 3).__str__(), "3+")


def main():
    conn = sqlite3.connect(CFG.ANNOUNCE_DB)
    by_code = defaultdict(list)
    for d, c, t in conn.execute("SELECT date, stock_code, title FROM announce"):
        is_ev, kind, pol, amt, pct = classify_title(t)
        if is_ev and pol > 0:
            by_code[c].append((d, kind, amt, pct))
    print(f"公告加载: {len(by_code)} 只标的 / {sum(len(v) for v in by_code.values())} 条积极公告")

    rows = list(csv.DictReader(open(LEGS, encoding="utf-8-sig")))
    legs = []
    for r in rows:
        if r.get("src") != "EVENT":
            continue
        code = r["symbol"].split("_")[0].split(".")[0]
        if code.startswith(("6", "9")):
            pass
        entry = r["entry_date"]  # YYYYMMDD
        d0 = datetime.strptime(entry, "%Y%m%d")
        lo = (d0 - timedelta(days=90)).strftime("%Y-%m-%d")
        hi = d0.strftime("%Y-%m-%d")
        anns = [a for a in by_code.get(code, []) if lo <= a[0] <= hi]
        amt_tot = sum(a[2] or 0 for a in anns if a[2])
        pct_tot = sum(a[3] or 0 for a in anns if a[3])
        legs.append({**r, "n_ev": len(anns), "amt_tot": amt_tot, "pct_tot": pct_tot})

    def st(rs):
        n = len(rs)
        if not n:
            return n, 0, 0, 0
        p = [float(r["net_pnl_pct"] or 0) for r in rs]
        pos = sum(v for v in p if v > 0)
        neg = -sum(v for v in p if v < 0)
        return n, round(sum(p) / n, 2), round(sum(1 for v in p if v > 0) / n * 100, 1), round(pos / neg, 2) if neg else 999

    md = ["# R72 — 大资金(内部人)窗口深挖", f"EVENT 腿 n={len(legs)}\n"]
    for name, keyfn in [("公告次数(前90天)", lambda r: {0: "0次", 1: "1次", 2: "2次"}.get(r["n_ev"], "3+次")),
                        ("增持/回购总金额", lambda r: bucket_amt(r["amt_tot"] if r["amt_tot"] else None)),
                        ("增持占总股本%", lambda r: ("无披露" if not r["pct_tot"] else
                                                       ("<0.5%" if r["pct_tot"] < 0.5 else ("0.5-1%" if r["pct_tot"] < 1 else ">1%"))))]:
        md.append(f"\n## {name}")
        md.append("| 桶 | n | avg% | WR% | PF |")
        md.append("|---|---|---|---|---|")
        g = defaultdict(list)
        for r in legs:
            g[keyfn(r)].append(r)
        for k in sorted(g, key=lambda k: (-st(g[k])[2], k)):
            md.append("| " + " | ".join(str(x) for x in [k, *st(g[k])]) + " |")

    # 组合交叉: 金额×次数 四角
    md.append("\n## 金额×次数 交叉(检查'重诵' vs '一锤')")
    md.append("| 组合 | n | avg% | WR% | PF |")
    md.append("|---|---|---|---|---|")
    g = defaultdict(list)
    for r in legs:
        b_amt = bucket_amt(r["amt_tot"] if r["amt_tot"] else None)
        b_cnt = {0: "0次", 1: "1次", 2: "2次"}.get(r["n_ev"], "3+次")
        g[f"{b_cnt}×{b_amt}"].append(r)
    for k in sorted(g, key=lambda k: -st(g[k])[0]):
        if len(g[k]) >= 15:
            md.append("| " + " | ".join(str(x) for x in [k, *st(g[k])]) + " |")

    open(OUT, "w", encoding="utf-8").write("\n".join(md))
    print(f"R72 → {OUT}; 成功连接 {len(legs)} EVENT 腿")


if __name__ == "__main__":
    main()
