# -*- coding: utf-8 -*-
"""Refresh paper-holding klines from Sina (works! Tencent dead, Eastmoney banned).
Sina gives full 2000-bar daily history quickly. Update kline_cache_tencent files."""
import io, json, os, sys, time, urllib.request

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
OUT = r"E:\test\smc_project\hermes\kline_cache_tencent"
UA = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)", "Referer": "https://finance.sina.com.cn/"}


def fetch_one(symbol):
    code, ex = symbol.split(".")
    sina_sym = ("sh" if ex == "SH" else "sz") + code
    url = f"https://money.finance.sina.com.cn/quotes_service/api/json_v2.php/CN_MarketData.getKLineData?symbol={sina_sym}&scale=240&ma=no&datalen=2000"
    req = urllib.request.Request(url, headers=UA)
    try:
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
            with open(os.path.join(OUT, symbol.replace(".", "_") + "_daily_800.json"), "w", encoding="utf-8") as fh:
                json.dump(bars, fh)
            return symbol, len(bars), bars[-1]["t"]
        return symbol, 0, "empty"
    except Exception as e:
        return symbol, 0, str(e)[:60]


def main():
    ledger = json.load(open(r"E:\test\smc_project\research\paper_ledger.json", encoding="utf-8"))
    codes = sorted({t["code"] for t in ledger})
    symbols = [f"{c}.{'SH' if c.startswith('6') else 'SZ'}" for c in codes]
    print(f"paper holdings: {len(symbols)}", flush=True)
    latest = None
    ok = 0
    for sym in symbols:
        s, n, lt = fetch_one(sym)
        if lt and (latest is None or lt > latest):
            latest = lt
        if n:
            ok += 1
        time.sleep(0.3)
    print(f"DONE: {ok}/{len(symbols)} refreshed, latest: {latest}", flush=True)


if __name__ == "__main__":
    main()
