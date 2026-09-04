#!/usr/bin/env python3
"""
SMC扫描脚本 — 用于cronjob定时执行
扫描A股+加密市场，输出信号报告
"""

import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from scripts.smc_market_scan import scan_market, format_scan_report, CN_TOP20, CRYPTO_TOP, US_TOP

# 扫描A股
cn_results = scan_market('cn', CN_TOP20)
print(format_scan_report(cn_results, 'cn', 'daily'))

# 扫描加密
crypto_results = scan_market('crypto', CRYPTO_TOP)
print(format_scan_report(crypto_results, 'crypto', 'daily'))