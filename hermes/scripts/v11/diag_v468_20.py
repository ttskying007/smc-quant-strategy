#!/usr/bin/env python3
"""Diagnose: test V468 on first 20 stocks"""
import sys
sys.path.insert(0, '/root/.hermes/scripts')
from v11.v468_engine import run_backtest, CACHE_DIR

symbols = sorted([f.stem.replace('_60min_200', '').replace('_', '.')
                 for f in CACHE_DIR.glob('*_60min_200.json')])[:20]
result = run_backtest(symbols, 'V468-20')
