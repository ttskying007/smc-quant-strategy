# -*- coding: utf-8 -*-
"""确认 /kline 交易记录表对 v20c 历史交易的渲染（buildTradeMarkers + renderTradesTable）"""
import io, sys
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
p = r"E:\test\smc_project\hermes\scripts\smc_unified.py"
txt = open(p, encoding="utf-8").read()
# check loadKline sets allTrades from d.trades
i = txt.find("allTrades=d.trades")
print("loadKline allTrades:", "OK" if i > 0 else "MISSING", "|", txt[i:i+40] if i > 0 else "")
# check renderTradesTable renders
i2 = txt.find("function renderTradesTable")
print("renderTradesTable:", "OK" if i2 > 0 else "MISSING")
# check buildTradeMarkers called in renderKline
i3 = txt.find("var tm=buildTradeMarkers(af)")
print("buildTradeMarkers call:", "OK" if i3 > 0 else "MISSING")
