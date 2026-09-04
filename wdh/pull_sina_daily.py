# -*- coding: utf-8 -*-
"""Sina full-market daily refresh (Tencent dead, Eastmoney rate-limited, Sina works).
Refreshes all kline_cache_tencent files. Rate-friendly 4 workers + delay."""
import concurrent.futures, io, json, os, sys, time, urllib.request

OUT = r"E:\test\smc_project\hermes\kline_cache_tencent"
UA = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)", "Referer": "https://finance.sina.com.cn/"}
FORCE = os.environ.get("SMC_FORCE_REFRESH", "0") == "1"


def fetch(symbol):
    out_p = os.path.join(OUT, symbol.replace(".", "_") + "_daily_800.json")
    if os.path.exists(out_p) and not FORCE:
        return symbol, "skip", None
    code, ex = symbol.split(".")
    sina_sym = ("sh" if ex == "SH" else "sz") + code
    url = f"https://money.finance.sina.com.cn/quotes_service/api/json_v2.php/CN_MarketData.getKLineData?symbol={sina_sym}&scale=240&ma=no&datalen=800"
    for attempt in range(3):
        try:
            time.sleep(0.2)
            req = urllib.request.Request(url, headers=UA)
            with urllib.request.urlopen(req, timeout=20) as r:
                b = r.read().decode("utf-8", errors="replace")
            d = json.loads(b)
            bars = []
            for x in d:
                t = str(x.get("day", "")).replace("-", "")
                if t and x.get("open"):
                    bars.append({"t": t, "o": float(x["open"]), "c": float(x["close"]),
                                 "h": float(x["high"]), "l": float(x["low"]),
                                 "v": float(x.get("volume") or 0)})
            if bars:
                with open(out_p, "w", encoding="utf-8") as fh:
                    json.dump(bars, fh)
                return symbol, len(bars), None
            return symbol, 0, "empty"
        except Exception as e:
            if attempt == 2:
                return symbol, 0, str(e)[:60]
            time.sleep(1.5 * (attempt + 1))
    return symbol, 0, "retries"


def main():
    symbols = []
    for f in os.listdir(OUT):
        if f.endswith("_daily_800.json"):
            symbols.append(f.replace("_daily_800.json", "").replace("_", ".", 1))
    print(f"symbols: {len(symbols)}", flush=True)
    ok = done = 0
    t0 = time.time()
    # serial (Sina rate-limits concurrency; 58-stock serial test succeeded)
    for sym in symbols:
        s, n, err = fetch(sym)
        done += 1
        if n:
            ok += 1
        if done % 200 == 0:
            print(f"  {done}/{len(symbols)} ok={ok} {time.time()-t0:.0f}s", flush=True)
    print(f"DONE: {done} symbols, {ok} ok, {time.time()-t0:.0f}s", flush=True)


if __name__ == "__main__":
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
    main()
