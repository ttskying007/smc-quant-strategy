#!/usr/bin/env python3
"""快速测试v44引擎运行"""
import sys
sys.path.insert(0, '/root/.hermes/scripts')
try:
    print("Testing v44_engine...")
    # 测试基础函数
    from v44_engine import load_ohlcv, short_trend, calc_atr, detect_market_phase
    print("  Basic functions OK")

    # 测试OB检测
    from v44_engine import detect_ob_v14
    print("  detect_ob_v14 OK")

    # 测试回踩检测
    from v44_engine import detect_retest_entries
    print("  detect_retest_entries OK")

    print("All functions loaded OK!")
except Exception as e:
    print(f"ERROR: {e}")
    import traceback; traceback.print_exc()