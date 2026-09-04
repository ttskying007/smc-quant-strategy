# -*- coding: utf-8 -*-
"""调试：龙虎榜代码 vs K 线匹配"""
import io, json, os, sys
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
LHB = r"E:\test\smc_project\hermes\lhb_cache"
KT = r"E:\test\smc_project\hermes\kline_cache_tencent"
code2file = {f.split("_")[0]: os.path.join(KT, f) for f in os.listdir(KT) if f.endswith("_daily_800.json")}
rows = json.load(open(os.path.join(LHB, "20260819.json"), encoding="utf-8"))
matched = 0
net_pos = 0
for r in rows:
    code = str(r.get("SECURITY_CODE", ""))
    net = float(r.get("BILLBOARD_NET_AMT") or 0)
    if net > 0:
        net_pos += 1
    if code in code2file:
        matched += 1
print(f"龙虎榜 {len(rows)} 条 | K线匹配 {matched} | 净买>0 {net_pos}")
# sample unmatched
unmatched = [str(r.get('SECURITY_CODE')) for r in rows if str(r.get('SECURITY_CODE')) not in code2file][:5]
print("未匹配样例:", unmatched)
# sample net>0 with match
for r in rows:
    code = str(r.get("SECURITY_CODE", ""))
    net = float(r.get("BILLBOARD_NET_AMT") or 0)
    if net > 0 and code in code2file:
        print(f"  {code} {r.get('SECURITY_NAME_ABBR')} net={net/1e6:.1f}万")
