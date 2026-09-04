# -*- coding: utf-8 -*-
"""Behavior-DNA: track the CURRENT large-money operator, not the stock.
Key insight: a stock may be operated by different majors in different periods
(2024 vs 2025 could be different money). So DNA = rolling behavior signature
at entry time (PIT), and we detect signature shifts (operator change).
Features (entry-60d window, PIT):
  a) trend: 60d return (stage: accumulation/uptrend/distribution)
  b) volatility: 20d ATR/close
  c) volume trend: 20d avg vol / 60d avg vol (accumulation = shrinking, markup = expanding)
  d) swing density: swing points per 60d
Test: signal quality by behavior bucket; operator-change detection (same stock, 2024 vs 2025)."""
import csv, io, json, os, sys
from collections import defaultdict

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
sys.path.insert(0, r"E:\test\smc_project\smc_backtest_report")
from smc_gates import check_economic_gate

KT = r"E:\test\smc_project\hermes\kline_cache_tencent"


def bars(path):
    try:
        raw = json.load(open(path, encoding="utf-8"))
    except Exception:
        return []
    out = []
    for r in raw if isinstance(raw, list) else []:
        t = "".join(c for c in str(r.get("t") or "") if c.isdigit())[:8]
        if t and r.get("o") and r.get("h") and r.get("l") and r.get("c") and r.get("v"):
            out.append({"t": t, "o": float(r["o"]), "h": float(r["h"]), "l": float(r["l"]), "c": float(r["c"]), "v": float(r["v"])})
    out.sort(key=lambda b: b["t"])
    return out


def behavior_at(symbol, entry_date):
    """Return behavior signature dict (PIT, entry-60d window)."""
    code, ex = symbol.split(".")
    fn = f"{code}_{ex}_daily_800.json"
    p = os.path.join(KT, fn)
    if not os.path.exists(p):
        return None
    bs = bars(p)
    dates = [b["t"] for b in bs]
    if entry_date not in dates:
        prev = [d for d in dates if d < entry_date]
        if not prev:
            return None
        i = dates.index(prev[-1])
    else:
        i = dates.index(entry_date)
    if i < 61:
        return None
    w60 = bs[i - 60:i]
    w20 = bs[i - 20:i]
    # a) trend: 60d return
    ret60 = (w60[-1]["c"] / w60[0]["c"] - 1)
    # b) volatility 20d
    vol20 = sum((b["h"] - b["l"]) / b["c"] for b in w20) / len(w20)
    # c) volume trend
    v20 = sum(b["v"] for b in w20) / len(w20)
    v60 = sum(b["v"] for b in w60) / len(w60)
    vol_trend = v20 / v60 if v60 else 1
    # d) stage classification (PIT)
    if ret60 < -0.15 and vol_trend < 0.9:
        stage = "ACCUM"   # 下跌后缩量横盘 = 吸筹
    elif ret60 > 0.20 and vol_trend > 1.1:
        stage = "MARKUP"  # 放量上涨 = 拉升
    elif ret60 > 0.30 and vol_trend > 1.3:
        stage = "DISTRIB"  # 高位放量 = 出货风险
    elif ret60 > 0:
        stage = "UPTREND"
    else:
        stage = "DOWNTREND"
    return {"ret60": ret60, "vol20": vol20, "vol_trend": vol_trend, "stage": stage}


trades = []
with open(r"E:\test\smc_project\wdh\TP2_tencent_trades.csv", encoding="utf-8-sig") as fh:
    for r in csv.DictReader(fh):
        r["net_pnl_pct"] = float(r["net_pnl_pct"])
        r["t1_violation"] = str(r.get("t1_violation", "")).lower() in ("true", "1", "yes")
        trades.append(r)

closes_cache = {}
def r20_of(symbol, entry_date):
    code, ex = symbol.split(".")
    fn = f"{code}_{ex}_daily_800.json"
    if fn not in closes_cache:
        p = os.path.join(KT, fn)
        if not os.path.exists(p):
            closes_cache[fn] = []
            return None
        raw = json.load(open(p, encoding="utf-8"))
        cl = [(("".join(x for x in str(r.get("t") or "") if x.isdigit())[:8]), float(r["c"])) for r in raw if r.get("t") and r.get("c")]
        cl.sort()
        closes_cache[fn] = cl
    cl = closes_cache[fn]
    ds = [c[0] for c in cl]
    if entry_date not in ds:
        prev = [d for d in ds if d < entry_date]
        if not prev:
            return None
        i = ds.index(prev[-1])
    else:
        i = ds.index(entry_date) - 1
    if i < 20:
        return None
    return cl[i][1] / cl[i - 20][1] - 1

tagged = []
for t in trades:
    r20 = r20_of(t["symbol"], str(t["entry_date"]))
    if r20 is None or not (0 <= r20 < 0.15):
        continue
    beh = behavior_at(t["symbol"], str(t["entry_date"]))
    if beh is None:
        continue
    t.update(beh)
    tagged.append(t)
print("tagged:", len(tagged))
from collections import Counter
print("stage 分布:", dict(Counter(t["stage"] for t in tagged)))


def report(label, rs):
    if len(rs) < 50:
        print(f"{label}: n={len(rs)} (过小)"); return
    gate = check_economic_gate(rs)
    o = gate["overall"]
    print(f"{label}: n={o['n']} WR={o['wr']}% avg={o['avg']}% PF={o['pf']} payoff={o['payoff']}")
    for y in ("2024", "2025", "2026"):
        ys = [t for t in rs if str(t["entry_date"]).startswith(y)]
        if ys:
            wy = sum(1 for t in ys if t["net_pnl_pct"] > 0)
            print(f"    {y}: n={len(ys)} WR={100*wy/len(ys):.0f}% avg={sum(t['net_pnl_pct'] for t in ys)/len(ys):+.2f}%")


print("\n=== 行为特征分桶（大资金操作模式）===")
report("基线（全部）", tagged)
report("吸筹（ACCUM）", [t for t in tagged if t["stage"] == "ACCUM"])
report("上升（UPTREND）", [t for t in tagged if t["stage"] == "UPTREND"])
report("拉升（MARKUP）", [t for t in tagged if t["stage"] == "MARKUP"])
report("下跌（DOWNTREND）", [t for t in tagged if t["stage"] == "DOWNTREND"])

# operator change detection: same stock, compare behavior 2024 vs 2025
print("\n=== 换庄检测（同一股票 2024 vs 2025 行为特征）===")
by_sym_year = defaultdict(lambda: defaultdict(list))
for t in tagged:
    y = str(t["entry_date"])[:4]
    by_sym_year[t["symbol"]][y].append(t)
changed = same = 0
examples = []
for sym, years in by_sym_year.items():
    if "2024" in years and "2025" in years and len(years["2024"]) >= 3 and len(years["2025"]) >= 3:
        s24 = Counter(t["stage"] for t in years["2024"]).most_common(1)[0][0]
        s25 = Counter(t["stage"] for t in years["2025"]).most_common(1)[0][0]
        if s24 != s25:
            changed += 1
            if len(examples) < 5:
                examples.append((sym, s24, s25))
        else:
            same += 1
print(f"跨年可比较股票: {changed+same}，其中行为阶段变化(换庄迹象): {changed}，相同: {same}")
for sym, s24, s25 in examples:
    print(f"  {sym}: 2024={s24} -> 2025={s25}")
