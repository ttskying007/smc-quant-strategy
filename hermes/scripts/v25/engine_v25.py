#!/usr/bin/env python3
"""
V25 Dynamic SL/TP Engine — Smart Money Cost Line + ATR-Adaptive + Trailing + Multi-Tier
Core principle: SL at smart money's cost basis, not at entry price
"""
import json, sys, os
from pathlib import Path
from collections import defaultdict, Counter
from datetime import datetime, timedelta

sys.path.insert(0, '/root/.hermes/scripts')
sys.path.insert(0, '/root/.hermes/scripts/v11')

# ── V25 Configuration ──

class V25Config:
    """Per-stock, per-regime adaptive parameters"""
    
    # Base ATR period
    ATR_PERIOD = 14
    
    # SL multipliers by volatility regime
    SL_VOLATILITY_MAP = {
        'LOW': 0.5,      # ATR% < 1.5%
        'MEDIUM': 1.0,   # ATR% 1.5-4%
        'HIGH': 1.5,     # ATR% 4-8%
        'EXTREME': 2.0,  # ATR% > 8%
    }
    
    # Trailing activation threshold (in R multiples)
    TRAIL_ACTIVATE_R = 1.0   # Activate after 1R profit
    TRAIL_TIGHTEN_R = 2.0    # Tighten trail after 2R profit
    
    # Trailing buffer (ATR multiples)
    TRAIL_BUFFER_NORMAL = 1.0
    TRAIL_BUFFER_TIGHT = 0.5
    
    # TP tier allocation
    TP_TIER_ALLOC = [0.30, 0.30, 0.40]  # TP1: 30%, TP2: 30%, TP3: 40%
    
    # Min hold bars (prevent 1-bar exits)
    MIN_HOLD_BARS = 3
    
    # Max hold bars (time stop)
    MAX_HOLD_BARS = 60
    
    # Regime-based SL adjustment
    REGIME_SL_ADJUST = {
        'TREND_UP': 0.8,     # Tighter SL in trends (less noise)
        'WEAK_UP': 1.0,
        'RANGE': 1.2,        # Wider SL in ranges
        'WEAK_DOWN': 1.0,
        'TREND_DOWN': 0.8,
    }


def classify_volatility(atr_pct):
    """Classify stock volatility from ATR%"""
    if atr_pct < 1.5:
        return 'LOW'
    elif atr_pct < 4.0:
        return 'MEDIUM'
    elif atr_pct < 8.0:
        return 'HIGH'
    else:
        return 'EXTREME'


def compute_atr(klines, period=14, idx=None):
    """Compute ATR from kline data at given index"""
    if idx is None:
        idx = len(klines) - 1
    if idx < period:
        return 0, 0
    
    tr_values = []
    for i in range(max(1, idx - period + 1), idx + 1):
        if i >= len(klines):
            break
        b = klines[i]
        prev = klines[i-1]
        h = float(b.get('h', b.get('high', 0)))
        l = float(b.get('l', b.get('low', 0)))
        c = float(prev.get('c', prev.get('close', 0)))
        tr = max(h - l, abs(h - c), abs(l - c))
        tr_values.append(tr)
    
    if not tr_values:
        return 0, 0
    
    atr = sum(tr_values) / len(tr_values)
    close = float(klines[idx].get('c', klines[idx].get('close', 0)))
    atr_pct = (atr / close * 100) if close > 0 else 0
    
    return atr, atr_pct


def load_kline_cache(symbol):
    """Load daily kline cache"""
    # Symbol format: 000001.SZ -> 000001_SZ_daily_300.json
    parts = symbol.replace('.SH', '_SH').replace('.SZ', '_SZ').replace('.BJ', '_BJ')
    cache_path = Path(f'/root/.hermes/kline_cache/{parts}_daily_300.json')
    if cache_path.exists():
        return json.loads(cache_path.read_text())
    return []


def find_smart_money_cost(pick, klines):
    """
    Identify smart money cost line from zone structure.
    Extracts zone type from detail/sl_source fields.
    """
    # Extract zone_type from detail field (e.g. "FVG_Bull→BOS→PB_BOUNCE [TREND_UP]")
    zone_type = pick.get('zone_type', '') or ''
    if not zone_type:
        detail = pick.get('detail', '')
        if detail and '→' in detail:
            zone_type = detail.split('→')[0].strip()
        else:
            zone_type = pick.get('sl_source', 'FVG_Bull')
    
    zone_bar = pick.get('zone_bar', 0)
    
    dz_low = float(pick.get('dz_low', 0))
    dz_high = float(pick.get('dz_high', 0))
    
    if not dz_low or not dz_high:
        # Fallback: use zone_bar from klines
        if zone_bar < len(klines) and zone_bar >= 0:
            bar = klines[zone_bar]
            dz_low = float(bar.get('l', 0))
            dz_high = float(bar.get('h', 0))
    
    is_bull = 'Bull' in zone_type
    
    if is_bull:
        cost = dz_low + (dz_high - dz_low) * 0.7
        zone_bottom = dz_low
        zone_top = dz_high
    else:
        cost = dz_low + (dz_high - dz_low) * 0.3
        zone_bottom = dz_low
        zone_top = dz_high
    
    return {
        'cost': cost,
        'zone_bottom': zone_bottom,
        'zone_top': zone_top,
        'zone_type': zone_type,
        'zone_bar': zone_bar,
        'is_bull': is_bull,
    }


def compute_dynamic_sltp(pick, klines, atr, atr_pct, entry_idx):
    """
    V25 Dynamic SL/TP computation.
    
    Returns: {
        'sl_price': float,      # Stop loss price
        'sl_pct': float,        # SL as % of entry
        'sl_reason': str,       # Why this SL level
        'tp_tiers': [           # Multi-tier take profits
            {'price': float, 'pct': float, 'type': str, 'alloc': float},
            ...
        ],
        'trail_config': {       # Trailing stop config
            'activate_r': float,
            'tighten_r': float,
            'buffer_normal': float,
            'buffer_tight': float,
        },
        'cost_line': float,     # Smart money cost basis
    }
    """
    entry_price = pick.get('price', 0) or pick.get('entry_price', 0)
    if not entry_price or not klines:
        return None
    
    reg = pick.get('regime', 'WEAK_UP')
    vol_class = classify_volatility(atr_pct)
    
    # ── 1. Smart Money Cost Line ──
    cost_info = find_smart_money_cost(pick, klines)
    if not cost_info:
        cost_info = {'cost': entry_price, 'zone_bottom': entry_price * 0.95, 
                     'zone_top': entry_price * 1.05, 'zone_type': 'unknown', 'zone_bar': 0}
    
    # ── 2. SL: Zone bottom - ATR*buffer (below smart money cost) ──
    sl_k = V25Config.SL_VOLATILITY_MAP.get(vol_class, 1.0)
    sl_k *= V25Config.REGIME_SL_ADJUST.get(reg, 1.0)
    
    if cost_info['is_bull']:
        # Long: SL below zone bottom
        sl_price = cost_info['zone_bottom'] - atr * sl_k
    else:
        # Short: SL above zone top
        sl_price = cost_info['zone_top'] + atr * sl_k
    
    sl_pct = abs(entry_price - sl_price) / entry_price * 100
    
    # ── 3. Multi-tier TP: structural levels ──
    tp_tiers = find_structural_tp_levels(pick, klines, entry_idx, entry_price)
    
    # ── 4. Trailing config ──
    trail_config = {
        'activate_r': V25Config.TRAIL_ACTIVATE_R,
        'tighten_r': V25Config.TRAIL_TIGHTEN_R,
        'buffer_normal': V25Config.TRAIL_BUFFER_NORMAL,
        'buffer_tight': V25Config.TRAIL_BUFFER_TIGHT,
    }
    
    return {
        'sl_price': round(sl_price, 2),
        'sl_pct': round(sl_pct, 2),
        'sl_reason': f"Zone {cost_info['zone_type']} bottom - ATR({atr:.2f})*k({sl_k:.1f})",
        'sl_source': cost_info['zone_type'],
        'tp_tiers': tp_tiers,
        'trail_config': trail_config,
        'cost_line': round(cost_info['cost'], 2),
        'zone_bottom': round(cost_info['zone_bottom'], 2),
        'zone_top': round(cost_info['zone_top'], 2),
        'volatility_class': vol_class,
        'atr': round(atr, 2),
        'atr_pct': round(atr_pct, 2),
    }


def parse_v24_tp_tiers(tp_tiers_str):
    """
    Parse V24 tp_tiers string like "BOS_level:9.4(9.3%)" or 
    "FVG_resist:6.92(1.8%),swing_high:7.43(9.3%)"
    Returns list of {'price': float, 'pct': float, 'type': str}
    """
    import re
    tiers = []
    if not tp_tiers_str or not isinstance(tp_tiers_str, str):
        return tiers
    
    parts = tp_tiers_str.split(',')
    for part in parts:
        m = re.search(r'([^:]+):([\d.]+)\(([\d.]+)%\)', part)
        if m:
            tiers.append({
                'type': m.group(1).strip(),
                'price': float(m.group(2)),
                'pct': float(m.group(3)),
            })
    return tiers


def find_structural_tp_levels(pick, klines, entry_idx, entry_price):
    """
    Multi-tier TP using V24 BOS/swing levels + structural scan.
    TP1: First V24 BOS level (30% position)
    TP2: Next V24 level or extended swing (30%)
    TP3: Runner (trailing only, 40%)
    """
    entry_price = entry_price or pick.get('price', 0)
    if not entry_price:
        return []
    
    # First try V24 TP tiers (BOS levels are reliable structural targets)
    tp_str = pick.get('tp_tiers', '')
    v24_tiers = parse_v24_tp_tiers(tp_str)
    
    tp_tiers = []
    
    if len(v24_tiers) >= 1:
        tp_tiers.append({
            'price': v24_tiers[0]['price'],
            'pct': v24_tiers[0]['pct'],
            'type': f'TP1 {v24_tiers[0]["type"]}',
            'alloc': 0.30,
        })
    if len(v24_tiers) >= 2:
        tp_tiers.append({
            'price': v24_tiers[1]['price'],
            'pct': v24_tiers[1]['pct'],
            'type': f'TP2 {v24_tiers[1]["type"]}',
            'alloc': 0.30,
        })
    
    # If no V24 tiers, fall back to structural scan
    if not tp_tiers:
        detail = pick.get('detail', '')
        zone_type = detail.split('→')[0].strip() if '→' in detail else pick.get('sl_source', '')
        is_bull = 'Bull' in zone_type
        
        if is_bull:
            # Find highs above entry in lookback
            lookback = min(50, entry_idx) if entry_idx else 50
            highs = []
            for i in range(max(0, (entry_idx or len(klines)) - lookback), min(entry_idx or len(klines), len(klines))):
                bar = klines[i]
                h = float(bar.get('h', 0))
                if h > entry_price:
                    highs.append(h)
            if highs:
                tp1 = sorted(set(round(h, 2) for h in highs if h > entry_price * 1.02))
                if tp1:
                    tp_price = tp1[min(1, len(tp1)-1)]
                    tp_tiers.append({
                        'price': tp_price,
                        'pct': round(abs(tp_price-entry_price)/entry_price*100, 1),
                        'type': 'TP1 Swing',
                        'alloc': 0.30,
                    })
            if len(tp_tiers) > 0:
                tp_tiers.append({
                    'price': round(entry_price * (1 + tp_tiers[0]['pct'] * 1.5 / 100), 2),
                    'pct': round(tp_tiers[0]['pct'] * 1.5, 1),
                    'type': 'TP2 Extended',
                    'alloc': 0.30,
                })
            else:
                tp_tiers.append({'price': round(entry_price * 1.05, 2), 'pct': 5.0, 'type': 'TP1 Default', 'alloc': 0.30})
                tp_tiers.append({'price': round(entry_price * 1.10, 2), 'pct': 10.0, 'type': 'TP2 Default', 'alloc': 0.30})
        else:
            tp_tiers.append({'price': round(entry_price * 0.95, 2), 'pct': 5.0, 'type': 'TP1 Default', 'alloc': 0.30})
            tp_tiers.append({'price': round(entry_price * 0.90, 2), 'pct': 10.0, 'type': 'TP2 Default', 'alloc': 0.30})
    
    # TP3: Runner (trailing only)
    tp_tiers.append({
        'price': 0,
        'pct': 0,
        'type': 'TP3 Runner (Trailing)',
        'alloc': 0.40,
    })
    
    return tp_tiers


def compute_trailing_stop(entry_price, current_high, current_low, atr, 
                          pnl_r, trail_config, is_bull, current_trail):
    """
    Update trailing stop based on price action.
    
    Args:
        pnl_r: Current profit in R multiples
        current_trail: Current trail level (None if not activated)
    
    Returns: new_trail_level or None
    """
    if pnl_r < trail_config['activate_r']:
        return None  # Not activated yet
    
    # Choose buffer based on how far in profit
    if pnl_r >= trail_config['tighten_r']:
        buffer = atr * trail_config['buffer_tight']
    else:
        buffer = atr * trail_config['buffer_normal']
    
    if is_bull:
        new_trail = current_low - buffer
    else:
        new_trail = current_high + buffer
    
    # Only move trail in favorable direction
    if current_trail is None:
        return new_trail
    
    if is_bull:
        return max(current_trail, new_trail)
    else:
        return min(current_trail, new_trail)


# ── Engine: Apply V25 to picks ──

def run_v25_engine(picks, output_dir=None):
    """
    Apply V25 dynamic SL/TP to picks and compute backtest results.
    """
    if output_dir is None:
        output_dir = Path('/root/.hermes/smc_opt_v25')
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    
    enhanced_picks = []
    
    for pick in picks:
        sym = pick['symbol']
        klines = load_kline_cache(sym)
        if not klines:
            continue
        
        entry_date = str(pick.get('entry_date', ''))
        
        # Find entry bar index
        entry_idx = None
        for i, bar in enumerate(klines):
            bar_date = str(bar.get('t', bar.get('date', '')))
            if bar_date == entry_date:
                entry_idx = i
                break
        
        if entry_idx is None:
            # Approximate: use zone_bar + zone_age
            zone_bar = pick.get('zone_bar', 0)
            zone_age = pick.get('zone_age', 0)
            entry_idx = zone_bar + zone_age if zone_bar + zone_age < len(klines) else None
        
        if entry_idx is None or entry_idx >= len(klines):
            continue
        
        # Compute ATR at entry
        atr, atr_pct = compute_atr(klines, V25Config.ATR_PERIOD, entry_idx)
        if atr == 0:
            continue
        
        # V25 SL/TP
        sltp = compute_dynamic_sltp(pick, klines, atr, atr_pct, entry_idx)
        if not sltp:
            continue
        
        # Enhance pick with V25 data
        enhanced = dict(pick)
        enhanced.update({
            'v25_sl_price': sltp['sl_price'],
            'v25_sl_pct': sltp['sl_pct'],
            'v25_sl_reason': sltp['sl_reason'],
            'v25_tp_tiers': sltp['tp_tiers'],
            'v25_cost_line': sltp['cost_line'],
            'v25_zone_bottom': sltp['zone_bottom'],
            'v25_zone_top': sltp['zone_top'],
            'v25_atr': sltp['atr'],
            'v25_atr_pct': sltp['atr_pct'],
            'v25_vol_class': sltp['volatility_class'],
        })
        enhanced_picks.append(enhanced)
    
    # Save
    out_path = output_dir / 'v25_picks.json'
    out_path.write_text(json.dumps(enhanced_picks, ensure_ascii=False, indent=2))
    
    print(f"V25: {len(enhanced_picks)} picks enhanced with dynamic SL/TP")
    print(f"Saved to {out_path}")
    
    # Stats
    sl_pcts = [p['v25_sl_pct'] for p in enhanced_picks]
    tp1_pcts = [p['v25_tp_tiers'][0]['pct'] if p['v25_tp_tiers'] else 0 for p in enhanced_picks]
    vol_classes = Counter(p['v25_vol_class'] for p in enhanced_picks)
    
    print(f"\nSL range: {min(sl_pcts):.1f}% - {max(sl_pcts):.1f}% (avg {sum(sl_pcts)/len(sl_pcts):.1f}%)")
    print(f"TP1 range: {min(tp1_pcts):.1f}% - {max(tp1_pcts):.1f}% (avg {sum(tp1_pcts)/len(tp1_pcts):.1f}%)")
    print(f"Vol classes: {dict(vol_classes)}")
    
    return enhanced_picks


if __name__ == '__main__':
    # Load current picks
    picks_path = Path('/root/.hermes/smc_opt_v24/v24_picks.json')
    if not picks_path.exists():
        print("No V24 picks found")
        sys.exit(1)
    
    picks = json.loads(picks_path.read_text())
    print(f"Loaded {len(picks)} V24 picks")
    
    run_v25_engine(picks)
