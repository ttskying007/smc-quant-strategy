# -*- coding: utf-8 -*-
"""Paper production tracker for COMBO_SMC_EVENT.
- BUY_VALID generation: event candidates (增持/回购, disclosed within 3 trading days)
  -> paper entry at next trading day open (PIT), hold 10 days.
- Positions tracked daily (mark-to-market from Tencent klines).
- All paper only; no real orders.
Outputs: paper_trades.json (closed), paper_positions.json (open), paper_ledger.json (all)."""
import io, json, os, sqlite3, sys, time, urllib.request

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
ROOT = r"E:\test\smc_project\research"
KT = r"E:\test\smc_project\hermes\kline_cache_tencent"
OUT = ROOT

# ---------- data ----------
code2file = {}
for f in os.listdir(KT):
    if f.endswith("_daily_800.json"):
        code2file[f.split("_")[0]] = os.path.join(KT, f)

bars_cache = {}
def bars_of(code):
    if code not in bars_cache:
        p = code2file.get(code)
        if not p:
            bars_cache[code] = []
            return []
        raw = json.load(open(p, encoding="utf-8"))
        bs = []
        for r in raw:
            t = "".join(x for x in str(r.get("t") or "") if x.isdigit())[:8]
            if t and r.get("o") and r.get("h") and r.get("l") and r.get("c"):
                bs.append({"t": t, "o": float(r["o"]), "h": float(r["h"]), "l": float(r["l"]), "c": float(r["c"])})
        bs.sort(key=lambda b: b["t"])
        bars_cache[code] = bs
    return bars_cache[code]


# ---------- state ----------
def load(name, default):
    p = os.path.join(OUT, name)
    try:
        return json.load(open(p, encoding="utf-8"))
    except Exception:
        return default


def save(name, data):
    with open(os.path.join(OUT, name), "w", encoding="utf-8") as fh:
        json.dump(data, fh, ensure_ascii=False, indent=2)


HOLD = 15


def main():
    # 1. gather event candidates (disclosed in last 3 trading days)
    conn = sqlite3.connect(r"E:\test\smc_project\announce\smc_announce.db")
    cur = conn.cursor()
    # last 3 trading days with data
    cur.execute("SELECT DISTINCT date FROM announce ORDER BY date DESC LIMIT 3")
    recent_days = [r[0] for r in cur.fetchall()]
    events = []
    for dd in recent_days:
        cur.execute("SELECT stock_code, stock_name, title FROM announce WHERE date=? AND (title LIKE '%增持%' OR title LIKE '%回购%')", (dd,))
        for code, name, title in cur.fetchall():
            # v8: strong-signal + behavior-stage (ACCUM/DOWNTREND only for event leg)
            t = str(title or "")
            if "回购" in t and ("完成" in t or "进度" in t or "进展" in t or "结果" in t or "前十名" in t):
                continue  # weak signal
            if "增持" not in t and "回购" not in t:
                continue
            events.append({"disclose_date": dd, "code": code, "name": name, "title": t[:80]})
    conn.close()
    print(f"recent disclosure days: {recent_days}, event candidates (strong): {len(events)}")

    # v8 behavior stage filter for events (ACCUM/DOWNTREND = contrarian accumulation)
    stage_cache = {}
    def stage_of(code, i):
        if code not in stage_cache:
            stage_cache[code] = bars_of(code)
        bs = stage_cache[code]
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

    # v10: deep-accumulation detection (90d deep drop + volume contraction)
    def deep_of(code, i):
        if code not in stage_cache:
            stage_cache[code] = bars_of(code)
        bs = stage_cache[code]
        if i < 91:
            return False
        w90 = bs[i - 90:i]
        w20 = bs[i - 20:i]
        ret90 = w90[-1]["c"] / w90[0]["c"] - 1
        v20 = sum(b["v"] for b in w20) / len(w20)
        v90 = sum(b["v"] for b in w90) / len(w90)
        vt = v20 / v90 if v90 else 1
        return ret90 < -0.20 and vt < 0.75

    # v17: ADX(14) trend strength (events stronger in trend ADX>=20)
    def adx14_of(code, i):
        if code not in stage_cache:
            stage_cache[code] = bars_of(code)
        bs = stage_cache[code]
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

    # v14: 20d volatility (high-vol events stronger)
    def vol20_of(code, i):
        if code not in stage_cache:
            stage_cache[code] = bars_of(code)
        bs = stage_cache[code]
        if i < 20:
            return None
        w20 = bs[i - 20:i]
        if not w20:
            return None
        return sum((b["h"] - b["l"]) / b["c"] for b in w20) / len(w20)

    # 2. determine entry: next trading day open after disclosure (paper)
    ledger = load("paper_ledger.json", [])
    known = {(t["code"], t["disclose_date"]) for t in ledger}
    new_buy_valid = []
    for ev in events:
        key = (ev["code"], ev["disclose_date"])
        if key in known:
            continue
        bs = bars_of(ev["code"])
        if not bs:
            continue
        dates = [b["t"] for b in bs]
        nxt = [d for d in dates if d > ev["disclose_date"].replace("-", "")]
        if not nxt:
            continue
        i = dates.index(nxt[0])
        # v17: event leg only in ACCUM/DOWNTREND (contrarian accumulation)
        st = stage_of(ev["code"], i)
        if st not in ("ACCUM", "DOWNTREND"):
            continue
        # v17: trend confirmation ADX>=20 (insider events stronger in trend)
        adx = adx14_of(ev["code"], i)
        if adx is None or adx < 20:
            continue
        ep = bs[i]["o"]
        if ep <= 0:
            continue
        # v17: depth-dependent hold (DEEP=20d, non-DEEP=15d)
        deep = deep_of(ev["code"], i)
        hold = 20 if deep else 15
        # priority: DEEP + high-vol = crown subset
        vol20 = vol20_of(ev["code"], i)
        priority = "HIGH" if (deep and vol20 is not None and vol20 > 0.041) else "STD"
        t = {"code": ev["code"], "name": ev["name"], "disclose_date": ev["disclose_date"],
             "entry_date": bs[i]["t"], "entry_price": round(ep, 4), "hold": hold,
             "status": "OPEN", "paper": True, "source": "EVENT", "priority": priority}
        ledger.append(t)
        new_buy_valid.append(t)
    print(f"new BUY_VALID (paper): {len(new_buy_valid)}")
    for t in new_buy_valid[:10]:
        print(f"  {t['code']} {t['name']} entry={t['entry_date']} @ {t['entry_price']}")

    # 3. mark-to-market open positions, close at hold expiry
    today = max((b["t"] for b in (bars_of("600519") or [])), default="20260818")
    for t in ledger:
        if t.get("status") != "OPEN":
            continue
        bs = bars_of(t["code"])
        if not bs:
            continue
        dates = [b["t"] for b in bs]
        if dates:
            today = max(today, dates[-1])
        entry_i = dates.index(t["entry_date"]) if t["entry_date"] in dates else None
        if entry_i is None:
            continue
        # current price = last bar close (or at hold expiry)
        expire_i = entry_i + t["hold"]
        if expire_i <= len(bs) - 1 and dates[expire_i] <= today:
            # enough future bars and expiry reached -> close at expire close
            cp = bs[expire_i]["c"]
            t["exit_date"] = dates[expire_i]
            t["exit_price"] = round(cp, 4)
            t["pnl_pct"] = round((cp / t["entry_price"] - 1) * 100 - 0.20, 4)
            t["status"] = "CLOSED"
        else:
            # still open or insufficient data -> mark-to-market, keep OPEN
            cp = bs[-1]["c"]
            t["mark_price"] = round(cp, 4)
            t["mark_pnl_pct"] = round((cp / t["entry_price"] - 1) * 100, 4)

    save("paper_ledger.json", ledger)
    closed = [t for t in ledger if t["status"] == "CLOSED"]
    open_ = [t for t in ledger if t["status"] == "OPEN"]
    print(f"ledger: {len(ledger)} total, {len(open_)} open, {len(closed)} closed")
    if closed:
        wins = [t for t in closed if t["pnl_pct"] > 0]
        avg = sum(t["pnl_pct"] for t in closed) / len(closed)
        print(f"closed: WR={100*len(wins)/len(closed):.1f}% avg_pnl={avg:+.2f}%")

    # dashboard update
    dash = load("combo_dashboard.json", {})
    open_marks = [t.get("mark_pnl_pct") for t in open_ if t.get("mark_pnl_pct") is not None]
    dash["paper_production"] = {
        "status": "PAPER_PRODUCTION_COMBO",
        "buy_valid_count": len(new_buy_valid),
        "open_positions": len(open_),
        "closed_trades": len(closed),
        "closed_avg_pnl": round(sum(t["pnl_pct"] for t in closed) / len(closed), 3) if closed else 0,
        "closed_wr": round(100 * sum(1 for t in closed if t["pnl_pct"] > 0) / len(closed), 1) if closed else 0,
        "open_avg_mark_pnl": round(sum(open_marks) / len(open_marks), 2) if open_marks else 0,
        "open_wr_mark": round(100 * sum(1 for m in open_marks if m > 0) / len(open_marks), 1) if open_marks else 0,
        "today": today,
    }
    save("combo_dashboard.json", dash)
    print("dashboard paper status updated")


if __name__ == "__main__":
    main()
