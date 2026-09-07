# -*- coding: utf-8 -*-
"""TDX 行情源可行性验证 v2: 显式连接已确认可达的行情服务器"""
import io, sys
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
from pytdx.hq import TdxHq_API

# 已验证 TCP 可达的服务器（端口7709）
CANDIDATES = [
    ("119.147.212.81", 7709),
    ("114.80.63.12", 7709),
    ("114.80.67.14", 7709),
    ("202.108.253.130", 7709),
]

api = TdxHq_API(heartbeat=True, auto_retry=True)
connected = False
for ip, port in CANDIDATES:
    try:
        if api.connect(ip, port, time_out=8):
            connected = True
            print(f"✅ 连接 {ip}:{port}")
            break
    except Exception as e:
        print(f"  {ip}:{port} 连接异常: {type(e).__name__}: {e}")

if not connected:
    print("❌ 全部候选失败")
    sys.exit(1)

# 日 K 线
print("\n=== 日 K 线（600519 近5日）===")
try:
    bars = api.get_security_bars(9, 0, "600519", 0, 5)
    if bars:
        for b in bars:
            print(f"  {b['datetime']} o={b['open']} h={b['high']} l={b['low']} c={b['close']} v={b['vol']}")
    else:
        print("  bars 为空")
except Exception as e:
    print(f"  日K线: {type(e).__name__}: {e}")

# 实时报价
print("\n=== 实时报价 ===")
try:
    snap = api.get_security_quotes([("0", "000001"), ("1", "600519")])
    if snap:
        for s in snap:
            print(f"  {s['code']} price={s['price']} last_close={s['last_close']}")
    else:
        print("  quotes 为空")
except Exception as e:
    print(f"  报价: {type(e).__name__}: {e}")

api.disconnect()
print("\n✅ v2 验证完成")