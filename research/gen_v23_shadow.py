# -*- coding: utf-8 -*-
"""gen_v23_shadow.py — R70: v23 影子组合(预注册, 不改生产)
规则(全部 as-weight, 即只降权不删除, 记录全貌):
  s1_choch  : breakout_kind 含 CHoCH    → weight ×0.5      (病灶 P1)
  s4_rank2  : rank == 2                 → weight ×0.5      (病灶 P4)
  s5_r5min  : risk_pct < 5%             → weight ×0.6      (病灶 P5)
  s6_whale  : 入场前90日内 积极公告 1次 → ×0.7, 3+次 → ×1.2 (R72 真金验证)
基线 = v22 冻结 1858 腿; v23 = 同腿 × 权重; 统计对比即可。
纪律: 不修改 v22 任何文件; v23 仅生成 combo_v23_shadow.csv + 统计。
"""
import csv, os, sqlite3, sys
from collections import defaultdict
from datetime import datetime, timedelta

ROOT = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, ROOT)
import config as CFG  # noqa: E402
from core.events import classify_title  # noqa: E402

SRC = os.path.join(ROOT, "combo_v22_trades.csv")
OUT = os.path.join(ROOT, "combo_v23_shadow.csv")

W_CHOCH = 0.5
W_RANK2 = 0.5
W_RISK_LT5 = 0.6
W_WHALE_3PLUS = 1.2   # 3+ 次积极公告 → 加权
W_WHALE_ONCE = 0.7    # 只披露 1 次 → 降权 (R72: 2.03/2.19 PF)


def _whale_counts(legs):
    conn = sqlite3.connect(CFG.ANNOUNCE_DB)
    by_code = defaultdict(list)
    for d, c, t in conn.execute("SELECT date, stock_code, title FROM announce"):
        is_ev, kind, pol, amt, pct = classify_title(t)
        if is_ev and pol > 0:
            by_code[c].append((d, kind))
    m = {}
    for r in legs:
        code = r["symbol"].split("_")[0].split(".")[0]
        d0 = datetime.strptime(r["entry_date"], "%Y%m%d")
        lo, hi = (d0 - timedelta(days=90)).strftime("%Y-%m-%d"), d0.strftime("%Y-%m-%d")
        n = sum(1 for a in by_code.get(code, []) if lo <= a[0] <= hi)
        m[r["symbol"] + "|" + r["entry_date"]] = n
    return m


def st(rows, wkey=None):
    n = len(rows)
    tw = sum(r[wkey] for r in rows) if wkey else n
    if not n or tw == 0:
        return n, round(tw, 1), 0, 0, 0
    if wkey:
        p = [float(r["net_pnl_pct"] or 0) * r[wkey] for r in rows]
    else:
        p = [float(r["net_pnl_pct"] or 0) for r in rows]
    avg = sum(p) / tw
    wr = sum(r[wkey] if wkey else 1 for r, v in zip(rows, p) if v > 0) / tw * 100
    pos = sum(v for v in p if v > 0)
    neg = -sum(v for v in p if v < 0)
    return n, round(tw, 1), round(avg, 2), round(wr, 1), round(pos / neg, 2) if neg else 999


rows = list(csv.DictReader(open(SRC, encoding="utf-8-sig")))
whale = _whale_counts(rows)
for r in rows:
    w = 1.0
    flags = []
    if "CHoCH" in (r.get("breakout_kind") or ""):
        w *= W_CHOCH; flags.append("s1_choch")
    if str(r.get("rank")) == "2":
        w *= W_RANK2; flags.append("s4_rank2")
    try:
        if float(r.get("risk_pct") or 0) < 5:
            w *= W_RISK_LT5; flags.append("s5_risk_lt5")
    except Exception:
        pass
    if r.get("src") == "EVENT":
        n_ev = whale.get(r["symbol"] + "|" + r["entry_date"], 1)
        r["whale_90d_n"] = n_ev
        if n_ev >= 3:
            w *= W_WHALE_3PLUS; flags.append("s6_whale_multi")
        elif n_ev <= 1:
            w *= W_WHALE_ONCE; flags.append("s6_whale_once")
    else:
        r["whale_90d_n"] = None
    r["v23_weight"] = round(w, 3)
    r["v23_flags"] = "|".join(flags) or "none"

cols = list(rows[0].keys())
with open(OUT, "w", encoding="utf-8-sig", newline="") as fh:
    w = csv.DictWriter(fh, fieldnames=cols)
    w.writeheader()
    w.writerows(rows)

print(f"v23 影子 legs: {len(rows)}")
print(f"含规则标记者: {sum(1 for r in rows if r['v23_flags'] != 'none')} 腿({sum(1 for r in rows if r['v23_flags'] != 'none')/len(rows)*100:.0f}%)")
print()
print("| 版本 | n | Σw | avg% | WR% | PF |")
print("|---|---|---|---|---|---|")
print("| v22 基线 |", " | ".join(str(x) for x in st(rows)), "|")
print("| v23 影子(加权) |", " | ".join(str(x) for x in st(rows, "v23_weight")), "|")
print()
print("逐年:")
by_y = defaultdict(list)
for r in rows:
    by_y[r["entry_date"][:4]].append(r)
print("| 年 | v22 avg/PF | v23 avg/PF |")
print("|---|---|---|")
for y in sorted(by_y):
    b = st(by_y[y]); v = st(by_y[y], "v23_weight")
    print(f"| {y} | {b[2]}%/PF {b[4]} | {v[2]}%/PF {v[4]} |")
