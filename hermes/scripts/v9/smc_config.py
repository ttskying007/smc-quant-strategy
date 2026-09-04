#!/usr/bin/env python3
# SMC V9 — Unified Configuration Module
"""
V9 configuration: YAML-based with env override support.
Replaces all hardcoded values from V84 engine.
"""

import os, json, yaml, logging
from pathlib import Path

HOME = Path.home()

# ─── Default config ────────────────────────────────────────────────

DEFAULT_CONFIG = {
    'hubble': {
        'base': os.environ.get('HUBBLE_BASE', 'http://43.167.234.49:3101'),
        'api_key': os.environ.get('HUBBLE_API_KEY', '123456'),
        'timeout': int(os.environ.get('HUBBLE_TIMEOUT', '15')),
    },
    'paths': {
        'cache_dir': str(HOME / '.hermes' / 'kline_cache'),
        'log_dir': str(HOME / '.hermes' / 'logs'),
        'output_dir': str(HOME / '.hermes' / 'smc_opt_v9'),
        'scripts_dir': str(HOME / '.hermes' / 'scripts'),
    },
    'param_space': {
        'fvg_min_width': {'min': 0.04, 'max': 0.40, 'default': 0.10, 'step': 0.01},
        'fvg_merge_dist': {'min': 1, 'max': 6, 'default': 3, 'step': 1},
        'sweep_lookback': {'min': 3, 'max': 30, 'default': 12, 'step': 1},
        'sweep_wick_ratio': {'min': 1.0, 'max': 5.0, 'default': 2.0, 'step': 0.1},
        'ob_strength_min': {'min': 0.3, 'max': 3.0, 'default': 1.0, 'step': 0.1},
        'confirm_range': {'min': 1, 'max': 6, 'default': 3, 'step': 1},
        'min_sources': {'min': 1, 'max': 5, 'default': 3, 'step': 1},
        'score_min': {'min': 0.5, 'max': 4.0, 'default': 0.5, 'step': 0.1},
        'max_trades': {'min': 2, 'max': 15, 'default': 3, 'step': 1},
        'atr_min_pct': {'min': 0.3, 'max': 5.0, 'default': 1.0, 'step': 0.1},
        'atr_max_pct': {'min': 2.0, 'max': 12.0, 'default': 8.0, 'step': 0.1},
        'sl_pct': {'min': 1.0, 'max': 6.0, 'default': 3.0, 'step': 0.1},
        'tp_pct': {'min': 2.0, 'max': 18.0, 'default': 9.0, 'step': 0.1},
        'vol_adapt_sl': {'min': 0.3, 'max': 1.2, 'default': 0.6, 'step': 0.05},
    },
    'stocks': [
        '600519.SH', '000858.SZ', '300750.SZ', '601318.SH',
        '002415.SZ', '002594.SZ', '600036.SH', '688981.SH',
        '300059.SZ', '600030.SH', '002230.SZ', '000333.SZ',
        '300124.SZ', '600276.SH', '600887.SH',
        '000001.SZ', '002304.SZ', '600809.SH', '300760.SZ',
        '002475.SZ', '000568.SZ', '300015.SZ', '002714.SZ',
        '601012.SH', '300274.SZ', '002352.SZ', '300782.SZ',
        '600585.SH', '601166.SH', '000002.SZ',
        '688111.SH', '600900.SH', '601899.SH', '300498.SZ',
        '002371.SZ', '000725.SZ', '603259.SH', '300308.SZ',
        '600941.SH', '000063.SZ',
    ],
    'logging': {
        'level': os.environ.get('SMC_LOG_LEVEL', 'INFO'),
        'to_stdout': True,
        'to_file': True,
    },
}


def get_config_dir():
    """Get config directory, create if needed."""
    cfg_dir = HOME / '.hermes' / 'config'
    cfg_dir.mkdir(parents=True, exist_ok=True)
    return cfg_dir


def load_config():
    """Load config from YAML, falling back to defaults and env overrides."""
    cfg_path = get_config_dir() / 'v9_config.yaml'

    config = DEFAULT_CONFIG.copy()
    config['param_space'] = dict(DEFAULT_CONFIG['param_space'])

    # Deep-copy list and dict values
    config['stocks'] = list(DEFAULT_CONFIG['stocks'])
    config['hubble'] = dict(DEFAULT_CONFIG['hubble'])
    config['paths'] = dict(DEFAULT_CONFIG['paths'])
    config['logging'] = dict(DEFAULT_CONFIG['logging'])

    # Load YAML if exists
    if cfg_path.exists():
        try:
            with open(cfg_path) as f:
                user_cfg = yaml.safe_load(f) or {}
            # Merge sections
            for section in ('hubble', 'paths', 'logging', 'param_space', 'stocks'):
                if section in user_cfg:
                    if isinstance(user_cfg[section], dict):
                        config[section].update(user_cfg[section])
                    elif isinstance(user_cfg[section], list):
                        config[section] = user_cfg[section]
        except Exception as e:
            logging.warning(f"Config load error: {e}")

    # Apply env overrides on top
    env_map = {
        'HUBBLE_BASE': ('hubble', 'base'),
        'HUBBLE_API_KEY': ('hubble', 'api_key'),
        'HUBBLE_TIMEOUT': ('hubble', 'timeout'),
        'SMC_LOG_LEVEL': ('logging', 'level'),
        'SMC_CACHE_DIR': ('paths', 'cache_dir'),
        'SMC_OUTPUT_DIR': ('paths', 'output_dir'),
    }
    for env_key, (section, key) in env_map.items():
        val = os.environ.get(env_key)
        if val is not None:
            if key == 'timeout':
                val = int(val)
            config[section][key] = val

    # Ensure directories exist
    for dir_key in ('cache_dir', 'log_dir', 'output_dir', 'scripts_dir'):
        Path(config['paths'][dir_key]).mkdir(parents=True, exist_ok=True)

    # Create default YAML if not exists
    if not cfg_path.exists():
        try:
            with open(cfg_path, 'w') as f:
                yaml.dump(config, f, default_flow_style=False, allow_unicode=True)
        except Exception:
            pass

    return config


def save_config(config):
    """Save config to YAML."""
    cfg_path = get_config_dir() / 'v9_config.yaml'
    try:
        with open(cfg_path, 'w') as f:
            yaml.dump(config, f, default_flow_style=False, allow_unicode=True)
        return True
    except Exception as e:
        logging.error(f"Config save error: {e}")
        return False


def get_param_space():
    """Get parameter space from config."""
    cfg = get_config()
    return cfg['param_space']


def get_stocks():
    """Get stock list from config."""
    cfg = get_config()
    return cfg['stocks']


def get_hubble_config():
    """Get Hubble API config."""
    cfg = get_config()
    return cfg['hubble']


# Singleton
_config = None


def get_config():
    """Get cached config (lazy load)."""
    global _config
    if _config is None:
        _config = load_config()
    return _config


def reload_config():
    """Force reload config from disk."""
    global _config
    _config = load_config()
    return _config


def setup_logging():
    """Configure logging based on config."""
    cfg = get_config()
    level = getattr(logging, cfg['logging']['level'].upper(), logging.INFO)
    loggers = [logging.getLogger(name) for name in logging.root.manager.loggerDict]
    root = logging.getLogger()
    root.setLevel(level)

    if cfg['logging']['to_stdout']:
        if not any(isinstance(h, logging.StreamHandler) for h in root.handlers):
            ch = logging.StreamHandler()
            ch.setLevel(level)
            formatter = logging.Formatter('%(asctime)s [%(levelname)s] %(name)s: %(message)s')
            ch.setFormatter(formatter)
            root.addHandler(ch)

    if cfg['logging']['to_file']:
        log_file = Path(cfg['paths']['log_dir']) / 'smc_v9.log'
        if not any(isinstance(h, logging.FileHandler) for h in root.handlers):
            fh = logging.FileHandler(str(log_file))
            fh.setLevel(level)
            formatter = logging.Formatter('%(asctime)s [%(levelname)s] %(name)s: %(message)s')
            fh.setFormatter(formatter)
            root.addHandler(fh)

    return root


# ─── Quick access ──────────────────────────────────────────────────

PARAM_SPACE = DEFAULT_CONFIG['param_space']
TEST_STOCKS = DEFAULT_CONFIG['stocks']

# Initialise on import
setup_logging()