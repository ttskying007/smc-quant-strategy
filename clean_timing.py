# -*- coding: utf-8 -*-
import io, sys
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
p = r"E:\test\smc_project\hermes\scripts\smc_unified.py"
txt = open(p, encoding="utf-8").read()
removals = [
    '            print(f"[KLINE-TIME] {symbol} klines-loaded={(_t.time()-_t_start)*1000:.0f}ms n={len(klines)}", flush=True)\n',
    '            print(f"[KLINE-TIME] {symbol} after-signals={(_t.time()-_t_start)*1000:.0f}ms", flush=True)\n',
    '            print(f"[KLINE-TIME] {symbol} pre-trades={(_t.time()-_t_start)*1000:.0f}ms", flush=True)\n',
    '            # TEMP timing\n            import time as _t\n            _t0 = _t.time()\n',
    '            print(f"[KLINE-TIME] {symbol} total={(_t.time()-_t_start)*1000:.0f}ms (build {(_t.time()-_t0)*1000:.0f}ms) signals={len(signals_list)} swings={len(swings_list)} trades={len(trade_list)}", flush=True)\n',
    '        import time as _t\n        _t_start = _t.time()\n',
]
for r in removals:
    if r in txt:
        txt = txt.replace(r, "")
        print("removed:", r.strip()[:60])
    else:
        print("NOT FOUND:", r.strip()[:60])
open(p, "w", encoding="utf-8").write(txt)
print("done")
