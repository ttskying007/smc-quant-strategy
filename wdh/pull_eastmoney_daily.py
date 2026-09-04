# -*- coding: utf-8 -*-
"""Eastmoney daily kline refresh (Tencent replacement - Tencent API died 8-18).
Force-refresh all kline_cache_tencent files from Eastmoney (has 8-19 data).
Rate-friendly: 6 workers. Uses same output format (t/o/h/l/c/v)."""
import concurrent.futures, io, json, os, sys, time, urllib.request

OUT = r"E:\test\smc_project\hermes\kline_cache_tencent"
os.makedirs(OUT, exist_ok=True)
UA = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)", "Referer": "https://quote.eastmoney.com/"}
BEG, END = "20230101", "20260820"


def secid(symbol):
    code, ex = symbol.split(".")
    return f"0.{code}" if ex in ("SZ", "BJ") else f"1.{code}"


def fetch(symbol):
    sid = secid(symbol)
    url = ("https://push2his.eastmoney.com/api/qt/stock/kline/get?"
           f"secid={sid}&klt=101&fqt=1&beg={BEG}&end={END}"
           "&fields1=f1,f2,f3,f4,f5,f6&fields2=f51,f52,f53,f54,f55,f56,f57")
    for attempt in range(4):
        try:
            time.sleep(0.15)
            req = urllib.request.Request(url, headers=UA)
            with urllib.request.urlopen(req, timeout=25) as r:
                d = json.loads(r.read())
            kl = (d.get("data") or {}).get("klines") or []
            bars = []
            for line in kl:
                parts = line.split(",")
                if len(parts) >= 6:
                    bars.append({"t": parts[0].replace("-", ""), "o": float(parts[1]), "c": float(parts[2]),
                                 "h": float(parts[3]), "l": float(parts[4]), "v": float(parts[5])})
            if bars:
                with open(os.path.join(OUT, symbol.replace(".", "_") + "_daily_800.json"), "w", encoding="utf-8") as fh:
                    json.dump(bars, fh)
                return symbol, len(bars), None
            return symbol, 0, "empty"
        except Exception as e:
            if attempt == 3:
                return symbol, 0, str(e)[:60]
            time.sleep(2.0 * (attempt + 1))
    return symbol, 0, "retries"


def main():
    symbols = []
    for f in os.listdir(OUT):
        if f.endswith("_daily_800.json"):
            symbols.append(f.replace("_daily_800.json", "").replace("_", ".", 1))
    print(f"symbols: {len(symbols)}", flush=True)
    ok = done = 0
    t0 = time.time()
    with concurrent.futures.ThreadPoolExecutor(max_workers=2) as ex:
        futs = {ex.submit(fetch, s): s for s in symbols}
        for fut in concurrent.futures.as_completed(futs):
            sym, n, err = fut.result()
            done += 1
            if n:
                ok += 1
            if done % 200 == 0:
                print(f"  {done}/{len(symbols)} ok={ok} {time.time()-t0:.0f}s", flush=True)
    print(f"DONE: {done} symbols, {ok} ok, {time.time()-t0:.0f}s", flush=True)


if __name__ == "__main__":
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
    main()
