# -*- coding: utf-8 -*-
"""pytdx 通达信行情测试（K线/实时/分时/资金流向/板块）"""
import io, sys
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
try:
    from pytdx.hq import TdxHq_API
    from pytdx.config.hosts import hq_hosts
    print("pytdx 导入 OK")
    print(f"可用行情服务器: {len(hq_hosts)} 个")
    for h in hq_hosts[:3]:
        print(f"  {h[0]}:{h[1]}")
except Exception as e:
    print(f"pytdx 导入失败: {e}")
