#!/usr/bin/env python3
"""
SMC Auto Optimizer v1.1 — 入口脚本
用文件方式运行（绕过python3 -c限制）
"""
import sys, os

# Unset proxy for Hubble API
for k in ['http_proxy', 'https_proxy', 'HTTP_PROXY', 'HTTPS_PROXY']:
    os.environ.pop(k, None)

sys.path.insert(0, os.path.expanduser('~/.hermes/skills/trading/smc-engine/scripts'))

from smc_backtest_v2 import (
    fetch_stock_list, fetch_klines, normalize_klines,
    backtest_single, generate_report, compute_sharpe, calc_drawdown
)
from smc_auto_optimizer import SMCOptimizer

import argparse

def main():
    parser = argparse.ArgumentParser(description='SMC Auto Optimizer Launcher')
    parser.add_argument('--mode', default='auto')
    parser.add_argument('--iterations', type=int, default=50)
    parser.add_argument('--stocks', type=int, default=20)
    parser.add_argument('--resume', action='store_true')
    args = parser.parse_args()

    opt = SMCOptimizer(target_stocks=args.stocks, max_iterations=args.iterations)
    opt.run(iterations=args.iterations, mode=args.mode, resume=args.resume)

if __name__ == '__main__':
    main()