# -*- coding: utf-8 -*-
"""pytdx 通达信连接测试：K线/实时报价/资金流向/板块"""
import io, sys
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
from pytdx.hq import TdxHq_API
from pytdx.config.hosts import hq_hosts

api = TdxHq_API()
connected = False
for h in hq_hosts[:10]:
    try:
        if api.connect(h[0], h[1], time_out=8):
            connected = True
            print(f"✅ 连接通达信 {h[0]}:{h[1]}")
            break
    except Exception:
        continue

if not connected:
    print("❌ 无法连接通达信服务器")
    sys.exit(1)

# 1. 日 K 线（600519 贵州茅台）
print("\n=== 日 K 线（600519）===")
bars = api.get_security_bars(9, 0, "600519", 0, 5)  # 9=日线
if bars:
    for b in bars:
        print(f"  {b['datetime']} o={b['open']} h={b['high']} l={b['low']} c={b['close']} v={b['vol']}")

# 2. 实时报价（快照）
print("\n=== 实时报价 ===")
snap = api.get_security_quotes([("0", "000001"), ("1", "600519")])
if snap:
    for s in snap:
        print(f"  {s['code']} price={s['price']} last_close={s['last_close']} vol={s['vol']} 买1={s.get('bid1')}")

# 3. 资金流向（财务/资金）
print("\n=== 资金流向（600519 近5日）===")
try:
    ff = api.get_finance_info(1, "600519")
    if ff:
        print(f"  财务: 流通市值={ff.get('ltsz')} 总市值={ff.get('zgb')}")
except Exception as e:
    print(f"  资金流向接口: {e}")

api.disconnect()
print("\n✅ pytdx 通达信接口测试完成")
