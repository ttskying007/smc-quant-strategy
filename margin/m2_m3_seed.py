# -*- coding: utf-8 -*-
"""M2 (short-cover margin confirm) & M3 (first-day financing spike confirm).

Different causal semantics than M1 (which is CLOSED_NO_VARIANTS):
- M2: 融券余额 5 日下降 / 融券偿还量 5 日为正 -> 空头回补 -> 空头压力解除是"聪明钱"接手前兆
- M3: 单日融资买入额 RZMRE 处于该股自身 60 日历史分位 >= 0.80 -> 新资金首日入场（区别于 M1 的 5 日累计"已追高"）

Both keep the SMC main line (fixed, outcome-free). PIT: use D-1 margin data.
"""
import csv, io, json, os, sqlite3, sys

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
HERMES = r"E:\test\smc_project\hermes"
KLINE = os.path.join(HERMES, "kline_cache")
MARGIN_DB = r"E:\test\smc_project\margin\smc_margin.db"
OUT = r"E:\test\smc_project\margin"
PIVOT_L = PIVOT_R = 3
SWEEP_PCT = 0.003
LOOKBACK = 5
MAX_WAIT = 5


def f(x, d=0.0):
    try:
        return float(x) if x not in (None, "") else d
    except Exception:
        return d


def date8(b):
    s = "".join(c for c in str(b.get("t") or b.get("date") or "") if c.isdigit())
    return s[:8] if len(s) >= 8 else ""


def bars_for(path):
    try:
        raw = json.load(open(path, encoding="utf-8"))
    except Exception:
        return []
    out = []
    for r in raw if isinstance(raw, list) else []:
        t = date8(r)
        o, h, l, c = f(r.get("o")), f(r.get("h")), f(r.get("l")), f(r.get("c"))
        if t and o and h and l and c:
            out.append({"t": t, "o": o, "h": h, "l": l, "c": c})
    out.sort(key=lambda b: b["t"])
    return out


def is_swing_low(ks, j):
    if j < PIVOT_L or j + PIVOT_R >= len(ks):
        return False
    lo = ks[j]["l"]
    return lo < min(ks[k]["l"] for k in range(j - PIVOT_L, j)) and lo <= min(ks[k]["l"] for k in range(j + 1, j + PIVOT_R + 1))


def is_swing_high(ks, j):
    if j < PIVOT_L or j + PIVOT_R >= len(ks):
        return False
    hi = ks[j]["h"]
    return hi > max(ks[k]["h"] for k in range(j - PIVOT_L, j)) and hi >= max(ks[k]["h"] for k in range(j + 1, j + PIVOT_R + 1))


def build_smc_seeds(symbol, ks):
    """Same fixed SMC main line as M1 (identical semantic -> comparable)."""
    seeds = []
    swing_lows = [j for j in range(PIVOT_L, len(ks) - PIVOT_R) if is_swing_low(ks, j)]
    for i in range(LOOKBACK, len(ks) - 2):
        b = ks[i]
        swept = None
        for j in reversed(swing_lows):
            if j + PIVOT_R >= i:
                continue
            ssl = ks[j]["l"]
            if b["l"] <= ssl * (1 - SWEEP_PCT) and b["c"] > ssl:
                swept = j
                break
        if swept is None:
            continue
        rsp = i + 1
        if rsp >= len(ks) or not (ks[rsp]["c"] > b["h"]):
            continue
        win = ks[i - LOOKBACK + 1:i + 1]
        if not (win[-1]["h"] > win[0]["h"] and win[-1]["l"] > win[0]["l"]):
            continue
        ob_idx = None
        for k in range(rsp + 1, min(len(ks), rsp + 5)):
            if ks[k]["c"] < ks[k]["o"]:
                ob_idx = k
                break
        if ob_idx is None:
            continue
        ob = ks[ob_idx]
        zl = min(ob["o"], ob["c"], ob["l"])
        zh = min(max(ob["o"], ob["c"]), zl + (ob["h"] - zl) * 0.5)
        lo_i, hi_i = min(swept, i), max(swept, i)
        swing_low = min(ks[k]["l"] for k in range(lo_i, hi_i + 1))
        swing_high = max(ks[k]["h"] for k in range(lo_i, hi_i + 1))
        if zh > swing_low + (swing_high - swing_low) * 0.79:
            continue
        touched = False
        t_idx = None
        entry = None
        for k in range(ob_idx + 1, min(len(ks) - 1, ob_idx + MAX_WAIT + 1)):
            bb = ks[k]
            if bb["l"] <= zl and bb["c"] <= zh:
                if touched:
                    break
                touched, t_idx = True, k
                continue
            if bb["c"] < zl:
                if touched:
                    break
                touched, t_idx = True, k
                continue
            if bb["l"] <= zh and bb["h"] >= zl:
                touched = True
                t_idx = t_idx if t_idx is not None else k
            if touched and k != t_idx and bb["c"] > zh:
                entry_idx = k + 1
                if entry_idx < len(ks):
                    entry = (entry_idx, k)
                break
        if entry is None:
            continue
        entry_idx, reclaim_idx = entry
        tgt = None
        for j in range(entry_idx - PIVOT_R - 1, PIVOT_L - 1, -1):
            if is_swing_high(ks, j) and ks[j]["h"] > max(b["h"], zh):
                tgt = (j, ks[j]["h"])
                break
        if tgt is None:
            continue
        seeds.append({
            "symbol": symbol, "identity": f"{symbol}|{ks[entry_idx]['t']}|{ks[i]['t']}",
            "event_date": ks[i]["t"], "entry_date": ks[entry_idx]["t"], "event_idx": i,
            "entry_idx": entry_idx, "reclaim_idx": reclaim_idx, "sweep_idx": swept,
            "zone_low": round(zl, 6), "zone_high": round(zh, 6),
            "entry_price": round(ks[entry_idx]["o"], 6),
            "target_swing_idx": tgt[0], "target": round(tgt[1], 6),
        })
    return seeds


class MarginLookup:
    """Cached per-stock margin history for M2/M3 confirmation."""
    def __init__(self):
        self.conn = sqlite3.connect(MARGIN_DB)
        self.hist = {}
        self.cur = self.conn.cursor()

    def history(self, scode):
        if scode not in self.hist:
            self.cur.execute("SELECT date,rqye,rqyl,rqchl,rzmre,rzche FROM margin_daily WHERE scode=? ORDER BY date", (scode,))
            self.hist[scode] = self.cur.fetchall()
        return self.hist[scode]

    def confirm(self, scode, entry_date, mode):
        h = self.history(scode)
        # rows before entry_date, take last (D-1)
        prior = [r for r in h if r[0] < entry_date]
        if not prior:
            return None, None
        d, rqye, rqyl, rqchl, rzmre, rzche = prior[-1]
        if mode == "M2":
            # short-cover: short balance (rqye) 5-day fall OR short repay (rqchl) positive on D-1
            fall = False
            if len(prior) >= 6:
                rqye_5ago = prior[-6][1]
                fall = (rqye is not None and rqye_5ago is not None and rqye < rqye_5ago * 0.95)
            repay = (rqchl is not None and rqchl > 0)
            ok = fall or repay
            return ok, {"date": d, "rqye": rqye, "rqye_5ago": (prior[-6][1] if len(prior) >= 6 else None), "rqchl": rqchl}
        if mode == "M3":
            # first-day spike: rzmre percentile vs own 60d history >= 0.80
            win = [r[4] for r in prior[-60:] if r[4] is not None]
            if len(win) < 20 or rzmre is None:
                return None, None
            pct = sum(1 for v in win if v <= rzmre) / len(win)
            ok = pct >= 0.80
            return ok, {"date": d, "rzmre": rzmre, "pctile": round(pct, 4)}
        return None, None


def main():
    ml = MarginLookup()
    out = {}
    for mode in ("M2", "M3"):
        seeds = []
        n_files = 0
        for p in sorted(os.listdir(KLINE)):
            if not p.endswith("_daily_750.json"):
                continue
            n_files += 1
            ks = bars_for(os.path.join(KLINE, p))
            if len(ks) < 200:
                continue
            sym = p.replace("_daily_750.json", "").replace("_", ".", 1)
            scode = sym.split(".")[0]
            for sd in build_smc_seeds(sym, ks):
                ok, info = ml.confirm(scode, sd["entry_date"], mode)
                if ok:
                    seeds.append({**sd, "margin": info})
            if n_files % 1500 == 0:
                print(f"  {mode} {n_files} files, seeds {len(seeds)}", flush=True)
        out[mode] = seeds
        with open(os.path.join(OUT, f"{mode}_seeds.csv"), "w", newline="", encoding="utf-8-sig") as fh:
            w = csv.DictWriter(fh, fieldnames=list(seeds[0].keys()) if seeds else ["symbol"])
            w.writeheader()
            for s in seeds:
                w.writerow(s)
        print(f"{mode}: seeds={len(seeds)} written")
    ml.conn.close()


if __name__ == "__main__":
    main()
