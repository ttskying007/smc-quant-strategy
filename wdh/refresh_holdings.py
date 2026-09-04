# -*- coding: utf-8 -*-
"""Refresh ONLY paper-holdings stocks from Eastmoney (fast, for paper tracking).
Tencent died 8-18; Eastmoney works but full-market refresh is slow/rate-limited.
Paper tracking only needs holding prices to mark-to-market and close."""
import io, json, os, sys, time, urllib.request

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
OUT = r"E:\test\smc_project\hermes\kline_cache_tencent"
UA = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)", "Referer": "https://quote.eastmoney.com/"}
BEG, END = "20230101", "20260820"


def secid(symbol):
    code, ex = symbol.split(".")
    return f"0.{code}" if ex in ("SZ", "BJ") else f"1.{code}"


def refresh_one(symbol):
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
                with open(os.path.join(OUT, symbol.replace(".", "_") + "_daily_800.json"), "w", encoding="utf-8") as fh:
                    json.dump(bars, fh)
                return symbol, len(bars), bars[-1].get("t")
            return symbol, 0, "empty"
        except Exception as e:
            if attempt == 2:
                return symbol, 0, str(e)[:50]
            time.sleep(2.0 * (attempt + 1))
    return symbol, 0, "retries"


def main():
    # paper holdings symbols
    ledger = json.load(open(r"E:\test\smc_project\research\paper_ledger.json", encoding="utf-8"))
    codes = sorted({t["code"] for t in ledger})
    symbols = []
    for c in codes:
        ex = "SH" if c.startswith("6") else "SZ"
        symbols.append(f"{c}.{ex}")
    print(f"paper holdings: {len(symbols)} stocks", flush=True)
    latest = None
    for sym in symbols:
        s, n, lt = refresh_one(sym)
        if lt and (latest is None or lt > latest):
            latest = lt
        time.sleep(0.5)
    print(f"DONE: {len(symbols)} refreshed, latest date: {latest}", flush=True)


if __name__ == "__main__":
    main()
