# SMC V9 — Smart Money Concepts Trading System
# Unified architecture with modular design, config-first, and interactive WebUI
"""
SMC V9 模块化交易系统

Modules:
    smc_config   — YAML config, env overrides, param space, stock list
    smc_hubble   — Hubble API client with retry + cache + error handling
    smc_signals  — All 6 signal detection algorithms (FVG, IFVG, Sweep, OB, BPR, MSB)
    smc_backtest — Trade simulation, parameter evaluation, scoring
    smc_webui    — FastAPI + ECharts interactive dashboard

Usage:
    from v9 import smc_config, smc_hubble, smc_signals, smc_backtest
    
    # Scan signals
    ohlcv, _, _ = smc_hubble.fetch_and_prepare('600519.SH')
    signals = smc_signals.detect_all_signals(ohlcv, smc_config.get_param_space())
    
    # Run backtest
    result = smc_backtest.evaluate_params(default_params, stocks[:20])
    
    # Start WebUI
    python3 -m v9.smc_webui --port 8880
"""

from . import smc_config
from . import smc_hubble
from . import smc_signals
from . import smc_backtest
# smc_webui loaded lazily to avoid circular imports

__version__ = "9.0.0"
__all__ = ['smc_config', 'smc_hubble', 'smc_signals', 'smc_backtest', 'smc_webui']