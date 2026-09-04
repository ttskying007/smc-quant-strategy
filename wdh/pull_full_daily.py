# -*- coding: utf-8 -*-
"""Pull full-history daily kline (2023-01-01..2026-08-14) from Eastmoney for all
stocks that exist in local kline_cache, into kline_cache_full.
Replaces the 750-bar window limitation -> 2023 full-year coverage for WDH engine.
"""
import concurrent.futures, io, json, os, sys, time, urllib.request, urllib.parse

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
KLINE = r"E:\test\smc_project\hermes\kline_cache"
OUT = r"E:\test\smc_project\hermes\kline_cache_full"
os.makedirs(OUT, exist_ok=True)
UA = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)", "Referer": "https://quote.eastmoney.com/"}
BEG, END = "20230101", "20260814"


def secid(symbol):
    code, ex = symbol.split(".")
    return f"0.{code}" if ex in ("SZ", "BJ") else f"1.{code}"


def fetch(symbol):
    sid = secid(symbol)
    url = ("https://push2his.eastmoney.com/api/qt/stock/kline/get?"
           f"secid={sid}&klt=101&fqt=1&beg={BEG}&end={END}"
           "&fields1=f1,f2,f3,f4,f5,f6&fields2=f51,f52,f53,f54,f55,f56,f57")
    for attempt in range(3):
        try:
            req = urllib.request.Request(url, headers=UA)
            with urllib.request.urlopen(req, timeout=20) as r:
                d = json.loads(r.read())
            kl = (d.get("data") or {}).get("klines") or []
            bars = []
            for line in kl:
                parts = line.split(",")
                if len(parts) >= 6:
                    bars.append({"t": parts[0].replace("-", ""), "o": float(parts[1]), "c": float(parts[2]),
                                 "h": float(parts[3]), "l": float(parts[4]), "v": float(parts[5])})
            if bars:
                fn = symbol.replace(".", "_") + "_daily_full.json"
                with open(os.path.join(OUT, fn), "w", encoding="utf-8") as fh:
                    json.dump(bars, fh)
                return symbol, len(bars), None
            return symbol, 0, "empty"
        except Exception as e:
            if attempt == 2:
                return symbol, 0, str(e)[:80]
            time.sleep(1.0 * (attempt + 1))
    return symbol, 0, "retries"


def main():
    symbols = []
    for p in sorted(os.listdir(KLINE)):
        if p.endswith("_daily_750.json"):
            symbols.append(p.replace("_daily_750.json", "").replace("_", ".", 1))
    print("symbols:", len(symbols))
    done = ok = 0
    t0 = time.time()
    with concurrent.futures.ThreadPoolExecutor(max_workers=6) as ex:
        futs = {ex.submit(fetch, s): s for s in symbols}
        for fut in concurrent.futures.as_completed(futs):
            sym, n, err = fut.result()
            done += 1
            if n:
                ok += 1
            if done % 500 == 0:
                print(f"  {done}/{len(symbols)} ok={ok} {time.time()-t0:.0f}s", flush=True)
    print(f"DONE: {done} symbols, {ok} ok, {time.time()-t0:.0f}s")


if __name__ == "__main__":
    main()
