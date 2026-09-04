# -*- coding: utf-8 -*-
"""事件腿入场模式对比：突破入场 vs 回撤限价入场（用户核心问题）
- 突破入场：T+1 开盘直接买入，持有 N 日
- 回撤入场：挂限价单 ≤ 披露日收盘价（PENDING→FILLED），成交后持有 N 日；未成交=放弃
回答：有没有必要等回撤？"""
import io, json, os, sqlite3, sys
from collections import defaultdict

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
sys.path.insert(0, r"E:\test\smc_project\smc_backtest_report")
from smc_gates import check_economic_gate

KT = r"E:\test\smc_project\hermes\kline_cache_tencent"
conn = sqlite3.connect(r"E:\test\smc_project\announce\smc_announce.db")
cur = conn.cursor()

code2file = {f.split("_")[0]: os.path.join(KT, f) for f in os.listdir(KT) if f.endswith("_daily_800.json")}
bar_cache = {}
def bars_of(code):
    if code not in bar_cache:
        p = code2file.get(code)
        if not p:
            bar_cache[code] = []
            return bar_cache[code]
        raw = json.load(open(p, encoding="utf-8"))
        bs = []
        for r in raw:
            t = "".join(x for x in str(r.get("t") or "") if x.isdigit())[:8]
            if t and r.get("o") and r.get("h") and r.get("l") and r.get("c") and r.get("v"):
                bs.append({"t": t, "o": float(r["o"]), "h": float(r["h"]), "l": float(r["l"]), "c": float(r["c"]), "v": float(r["v"])})
        bs.sort(key=lambda b: b["t"])
        bar_cache[code] = bs
    return bar_cache[code]


def is_strong(title):
    t = str(title or "")
    if "回购" in t:
        if "完成" in t or "进度" in t or "进展" in t or "结果" in t or "前十名" in t:
            return False
        return True
    if "增持" in t:
        return True
    return False


def adx14(bs, i):
    if i < 30:
        return None
    plus_dm = minus_dm = tr_sum = 0.0
    for k in range(i - 14, i):
        h, l, pc = bs[k]["h"], bs[k]["l"], bs[k - 1]["c"]
        up = h - bs[k - 1]["h"]
        dn = bs[k - 1]["l"] - l
        plus_dm += up if (up > dn and up > 0) else 0
        minus_dm += dn if (dn > up and dn > 0) else 0
        tr = max(h - l, abs(h - pc), abs(l - pc))
        tr_sum += tr
    if tr_sum <= 0:
        return None
    pdi = 100 * plus_dm / tr_sum
    mdi = 100 * minus_dm / tr_sum
    if pdi + mdi == 0:
        return None
    return 100 * abs(pdi - mdi) / (pdi + mdi)


def stage_at(bs, i):
    if i < 61:
        return None
    w60 = bs[i - 60:i]
    w20 = bs[i - 20:i]
    ret = w60[-1]["c"] / w60[0]["c"] - 1
    v20 = sum(b["v"] for b in w20) / len(w20)
    v60 = sum(b["v"] for b in w60) / len(w60)
    vt = v20 / v60 if v60 else 1
    if ret < -0.15 and vt < 0.9:
        return "ACCUM"
    if ret > 0.30 and vt > 1.3:
        return "DISTRIB"
    if ret > 0.20 and vt > 1.1:
        return "MARKUP"
    if ret > 0:
        return "UPTREND"
    return "DOWNTREND"


# collect events (ACCUM/DOWNTREND + ADX>=20, v18 filter)
cands = []
seen = set()
cur.execute("SELECT date, stock_code, title FROM announce WHERE title LIKE '%增持%' OR title LIKE '%回购%'")
for date, code, title in cur.fetchall():
    if not is_strong(title):
        continue
    d = str(date)[:10].replace("-", "")
    if (code, d) in seen:
        continue
    seen.add((code, d))
    bs = bars_of(code)
    if not bs:
        continue
    dates = [b["t"] for b in bs]
    d8 = d.replace("-", "")
    if d8 not in dates:
        continue
    i = dates.index(d8)
    st = stage_at(bs, i)
    if st not in ("ACCUM", "DOWNTREND"):
        continue
    adx = adx14(bs, i)
    if adx is None or adx < 20:
        continue
    if i + 20 >= len(bs):
        continue
    cands.append({"code": code, "i": i, "close_px": bs[i]["c"], "bs": bs})
conn.close()
print("events:", len(cands))

HOLD = 15
FEE = 0.20

# 1) 突破入场：T+1 开盘直接买
brk = []
# 2) 回撤入场：挂限价 ≤ 披露日收盘，T+1 起 5 日内价格 ≤ 挂单价成交（取第一次触及的收盘价）
retr = []
for c in cands:
    bs = c["bs"]
    i = c["i"]
    ep_brk = bs[i + 1]["o"]  # T+1 open
    if ep_brk <= 0 or i + 1 + HOLD >= len(bs):
        continue
    brk.append({"entry_date": bs[i + 1]["t"],
                "net_pnl_pct": round((bs[i + 1 + HOLD]["c"] / ep_brk - 1) * 100 - FEE, 4)})
    # retrace limit order: fill when low <= limit within 5 days (fill at open next day? use close of touch day)
    limit = c["close_px"]
    filled = None
    for k in range(i + 1, min(i + 6, len(bs))):
        if bs[k]["l"] <= limit:  # touched limit
            fill_px = bs[k]["c"]  # fill at touch day close (conservative) or limit? use close
            filled = (k, fill_px)
            break
    if filled:
        k, fill_px = filled
        if k + HOLD < len(bs):
            retr.append({"entry_date": bs[k]["t"],
                         "net_pnl_pct": round((bs[k + HOLD]["c"] / fill_px - 1) * 100 - FEE, 4)})


def report(label, rs):
    if len(rs) < 200:
        print(f"{label}: n={len(rs)} (过小)"); return
    for t in rs:
        t["t1_violation"] = "False"
        t["year"] = str(t["entry_date"])[:4]
    gate = check_economic_gate(rs)
    o = gate["overall"]
    print(f"{label}: n={o['n']} WR={o['wr']}% avg={o['avg']}% PF={o['pf']} payoff={o['payoff']}")
    for y in ("2024", "2025", "2026"):
        ys = [t for t in rs if t["year"] == y]
        if ys:
            wy = sum(1 for t in ys if t["net_pnl_pct"] > 0)
            print(f"    {y}: n={len(ys)} WR={100*wy/len(ys):.0f}% avg={sum(t['net_pnl_pct'] for t in ys)/len(ys):+.2f}%")


print("\n=== 事件腿：突破入场 vs 回撤限价入场（15日持有）===")
report("突破入场（T+1开盘）", brk)
print(f"\n回撤入场：成交 {len(retr)}/{len(cands)}（挂单价=披露日收盘；5日内价格≤挂单价成交）")
report("回撤限价入场（≤披露收盘）", retr)
