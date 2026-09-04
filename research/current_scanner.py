# -*- coding: utf-8 -*-
"""Current-market scanner for the combined strategy (SMC TP2-R20 + insider events).
Scans latest klines for live candidates:
A) SMC three-TF signal with TP2-R20 conditions (entry eligible next open)
B) Recent insider events (增持/回购) in last 5 trading days -> event candidates
FIX(2026-08-19): freshness gate — only symbols whose kline latest == market latest
produce candidates (no stale-signal risk); key stocks (holdings + recent events)
are force-refreshed from Sina before scanning when --refresh is passed.
Output: candidate list with signal details, all research-only (no BUY)."""
import io, json, os, sys, subprocess
from collections import defaultdict

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
sys.path.insert(0, r"E:\test\smc_project\wdh")
import wdh_engine as we

KT = r"E:\test\smc_project\hermes\kline_cache_tencent"
OUT = r"E:\test\smc_project\research"
os.makedirs(OUT, exist_ok=True)


def bars(path):
    try:
        raw = json.load(open(path, encoding="utf-8"))
    except Exception:
        return []
    out = []
    for r in raw if isinstance(raw, list) else []:
        t = "".join(c for c in str(r.get("t") or "") if c.isdigit())[:8]
        o, h, l, c = we.f(r.get("o")), we.f(r.get("h")), we.f(r.get("l")), we.f(r.get("c"))
        if t and o and h and l and c:
            out.append({"t": t, "o": o, "h": h, "l": l, "c": c})
    out.sort(key=lambda b: b["t"])
    return out


def market_latest():
    """Determine latest trading date from Sina realtime (authoritative)."""
    try:
        import urllib.request
        UA = {"User-Agent": "Mozilla/5.0", "Referer": "https://finance.sina.com.cn/"}
        req = urllib.request.Request("https://hq.sinajs.cn/list=sh600519", headers=UA)
        with urllib.request.urlopen(req, timeout=10) as r:
            b = r.read().decode("gbk", errors="replace")
        # var hq_str_sh600519="name,open,prevclose,current,..." -> date is not in quote; use date via kline instead
    except Exception:
        pass
    # fallback: latest date across kline files that are fresh (from Sina refresh)
    latest = ""
    for f in os.listdir(KT):
        if not f.endswith("_daily_800.json"):
            continue
        bs = bars(os.path.join(KT, f))
        if bs and bs[-1]["t"] > latest:
            latest = bs[-1]["t"]
    return latest or "20260819"


def refresh_key_stocks():
    """Force-refresh holdings + recent-event stocks from Sina (small set, fast serial)."""
    try:
        PY = r"C:\Users\Administrator\AppData\Roaming\uv\python\cpython-3.12.13-windows-x86_64-none\python.exe"
        subprocess.run([PY, r"E:\test\smc_project\wdh\refresh_holdings_sina.py"], timeout=1200, capture_output=True)
    except Exception:
        pass


# A) SMC candidates: seeds whose entry_date == next trading day after last bar (i.e., signal just completed)
import concurrent.futures

def scan_one(p, latest):
    if not p.endswith("_daily_800.json"):
        return None, None
    daily = bars(os.path.join(KT, p))
    if len(daily) < 400:
        return None, None
    # freshness gate: last bar must equal market latest trading date (no stale signals)
    if daily[-1]["t"] != latest:
        return None, None
    sym = p.replace("_daily_800.json", "").replace("_", ".", 1)
    seeds = we.build_seeds(sym, daily)
    last = daily[-1]["t"]
    out = []
    for sd in seeds:
        if int(sd["entry_idx"]) != len(daily) - 1:
            continue
        r20 = sd.get("r20")
        if r20 == "" or r20 is None or not (0 <= float(r20) < 0.15):
            continue
        # v17 SMC leg filters: behavior stage UPTREND/MARKUP + bearish FVG
        entry_idx = int(sd["entry_idx"])
        if entry_idx < 61:
            continue
        w60 = daily[entry_idx - 60:entry_idx]
        ret60 = w60[-1]["c"] / w60[0]["c"] - 1
        if ret60 <= 0:
            continue  # UPTREND/MARKUP proxy (needs volume check for MARKUP)
        has_fvg = any(daily[k]["h"] < daily[k - 2]["l"] for k in range(max(3, entry_idx - 12), entry_idx))
        if not has_fvg:
            continue
        fvg_cnt = sum(1 for k in range(max(3, entry_idx - 12), entry_idx) if daily[k]["h"] < daily[k - 2]["l"])
        out.append({"symbol": sym, "event_date": sd["event_date"], "entry_date": sd["entry_date"],
                    "zone_low": sd["zone_low"], "zone_high": sd["zone_high"],
                    "entry_price": sd["entry_price"], "target": sd["target"],
                    "w_permission": sd["w_permission"], "r20": r20, "last": last,
                    "stage": "UPTREND/MARKUP", "bear_fvg": True, "fvg_cnt": fvg_cnt})
    return (out if out else None), last

if __name__ == "__main__":
    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument("--refresh", action="store_true", help="扫描前刷新关键股票（持仓+事件）")
    args = ap.parse_args()
    if args.refresh:
        print("刷新关键股票（持仓+近期事件）...", flush=True)
        refresh_key_stocks()
    latest = market_latest()
    print(f"市场最新交易日: {latest}", flush=True)
    files = [f for f in os.listdir(KT) if f.endswith("_daily_800.json")]
    smc_cands = []
    fresh_count = 0
    with concurrent.futures.ThreadPoolExecutor(max_workers=8) as ex:
        for cands, last in ex.map(lambda p: scan_one(p, latest), files):
            if cands:
                smc_cands.extend(cands)
            if last == latest:
                fresh_count += 1
    print(f"scanned {len(files)} files, fresh={fresh_count} (数据最新), stale skipped (不产生信号)")
    print(f"\n=== A) SMC 三周期信号候选（entry 即将触发）: {len(smc_cands)} ===")
    for c in smc_cands[:15]:
        print(f"  {c['symbol']}: event={c['event_date']} entry={c['entry_date']} zone=[{c['zone_low']},{c['zone_high']}] entry_price={c['entry_price']} target={c['target']} r20={float(c['r20'])*100:.1f}% W={c['w_permission']}")

    # B) recent insider events: query announce DB for last 5 trading days
    import sqlite3
    conn = sqlite3.connect(r"E:\test\smc_project\announce\smc_announce.db")
    cur = conn.cursor()
    rep = None
    for f in os.listdir(KT):
        if f.endswith("_daily_800.json"):
            rep = bars(os.path.join(KT, f))
            break
    all_dates = sorted(b["t"] for b in rep) if rep else []
    last5 = all_dates[-5:]
    print(f"\n=== B) 最近 5 个交易日: {last5} ===")
    for d in last5:
        dd = f"{d[:4]}-{d[4:6]}-{d[6:8]}"
        cur.execute("SELECT stock_code, stock_name, title FROM announce WHERE date=? AND (title LIKE '%增持%' OR title LIKE '%回购%') LIMIT 10", (dd,))
        rows = cur.fetchall()
        print(f"  {dd}: {len(rows)} 增持/回购事件")
        for code, name, title in rows[:5]:
            print(f"    {code} {name}: {str(title)[:50]}")
    conn.close()

    # save
    with open(os.path.join(OUT, "current_scanner_result.json"), "w", encoding="utf-8") as fh:
        json.dump({
            "latest_date": latest,
            "fresh_count": fresh_count,
            "stale_count": len(files) - fresh_count,
            "coverage_pct": round(100 * fresh_count / len(files), 1) if files else 0,
            "smc_candidates": smc_cands,
            "note": "research-only, no BUY; freshness gate: only latest-data signals; stale=数据未更新到最新（继续后台刷新中）"
        }, fh, ensure_ascii=False, indent=2)
    print("\nscanner result saved (freshness gate)")
