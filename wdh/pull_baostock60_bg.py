# -*- coding: utf-8 -*-
"""Background: slow-pull baostock 60min data for a small sample (accumulate for future
60min layer). Rate-friendly: 1 stock at a time, long pause. Not blocking research."""
import io, json, os, sys, time

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
import baostock as bs

OUT = r"E:\test\smc_project\hermes\kline_cache_60min_baostock"
os.makedirs(OUT, exist_ok=True)

# small sample of symbols (matching kline_cache daily files)
KLINE = r"E:\test\smc_project\hermes\kline_cache_tencent"
symbols = []
for f in sorted(os.listdir(KLINE))[:20]:
    if f.endswith("_daily_800.json"):
        code, ex = f.split("_")[0], f.split("_")[1]
        symbols.append((code, ex))

lg = bs.login()
print("login:", lg.error_code, flush=True)
if lg.error_code != '0':
    sys.exit(1)

ok = 0
for code, ex in symbols:
    out_p = os.path.join(OUT, f"{code}_{ex}_60m_full.json")
    if os.path.exists(out_p):
        ok += 1
        continue
    sym = ('sh.' if ex == 'SH' else 'sz.') + code
    rs = bs.query_history_k_data_plus(
        sym, "date,time,open,high,low,close,volume,amount,adjustflag",
        start_date='2023-01-01', end_date='2026-08-18', frequency='60', adjustflag='2')
    rows = []
    while rs.error_code == '0' and rs.next():
        rows.append(rs.get_row_data())
    if rows:
        bars = []
        for r in rows:
            if len(r) >= 6 and r[2]:
                bars.append({"t": str(r[1]).replace("-", "")[:12], "d": r[0].replace("-", ""),
                             "o": float(r[2]), "h": float(r[3]), "l": float(r[4]), "c": float(r[5]),
                             "v": float(r[6]) if r[6] else 0})
        with open(out_p, "w", encoding="utf-8") as fh:
            json.dump(bars, fh)
        ok += 1
        print(f"  {code}_{ex}: {len(bars)} 60m bars", flush=True)
    else:
        print(f"  {code}_{ex}: FAIL {rs.error_msg}", flush=True)
    time.sleep(8)  # rate-friendly

bs.logout()
print(f"DONE: {ok}/{len(symbols)} stocks", flush=True)
