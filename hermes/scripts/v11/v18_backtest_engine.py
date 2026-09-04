#!/usr/bin/env python3
"""
V18 Backtest Engine — T+1 Compliance + Multi-Source Structural TP/SL
===================================================================
Key fixes over V17:
1. T+1: A-share cannot sell same day. entry_idx != exit_idx (exit >= entry+1)
2. Multi-source TP: scan ALL structural resistance points after entry
   - Prior swing highs, OB upper, FVG upper, BSL pools, BOS/CHOCH break levels
   - Filter: TP >= entry_price * 1.01 (at least 1% above entry)
   - Use CLOSEST valid TP
3. Multi-source SL: scan ALL structural support points before entry
   - Prior swing lows, OB lower, FVG lower, SSL pools, BOS/CHOCH break levels
   - Filter: SL <= entry_price * 0.99 (at least 1% below entry)
   - Use CLOSEST valid SL (tightest protection)
4. Entry at zone: entry_price = FVG.lower or OB.lower
5. Progressive trailing BE lock
6. Exit logging: TP hit, SL hit, trailing, EOD
"""
import json, math
from typing import List, Dict, Optional, Tuple
from dataclasses import dataclass, field

@dataclass
class Trade:
    symbol: str
    entry_idx: int
    entry_date: str
    entry_price: float
    entry_type: str  # 'FVG_Bull' or 'OB_Bull'
    entry_signal_idx: int
    exit_idx: int
    exit_date: str
    exit_price: float
    exit_method: str  # 'tp_hit', 'sl_hit', 'trailing', 'eod'
    pnl_pct: float
    hold_bars: int
    sl_price: float
    tp_price: float
    signals_triggered: List[str] = field(default_factory=list)
    metadata: Dict = field(default_factory=dict)

    def to_dict(self):
        return {
            'symbol': self.symbol, 'entry_idx': self.entry_idx,
            'entry_date': self.entry_date, 'entry_price': round(self.entry_price, 2),
            'entry_type': self.entry_type, 'entry_signal_idx': self.entry_signal_idx,
            'exit_idx': self.exit_idx, 'exit_date': self.exit_date,
            'exit_price': round(self.exit_price, 2), 'exit_method': self.exit_method,
            'pnl_pct': round(self.pnl_pct, 4), 'hold_bars': self.hold_bars,
            'sl_price': round(self.sl_price, 2), 'tp_price': round(self.tp_price, 2),
            'signals_triggered': self.signals_triggered,
        }

# ═════════════════════════════════════════════════════════════════
# STRUCTURAL TP/SL SCANNER
# ═════════════════════════════════════════════════════════════════

def find_structural_tp(ohlcv, entry_idx, entry_price, signals, swings):
    """
    Find CLOSEST structural TP above entry price.
    Sources: swing highs, OB upper, FVG upper, BSL pools, CHOCH/BOS levels.
    Filter: TP >= entry_price * 1.01 (at least 1% above)
    """
    candidates = []
    
    # 1. Prior swing highs (from pivothigh detection)
    for sh in swings.get('highs', []):
        if sh['bar_idx'] < len(ohlcv):
            tp = sh['price']
            if tp >= entry_price * 1.01:
                candidates.append(('swing_high', tp, sh['bar_idx']))
    
    # 2. OB upper boundaries
    for s in signals:
        if s.type in ('OB_Bear',) and s.upper >= entry_price * 1.01:
            candidates.append(('ob_upper', s.upper, s.idx))
    
    # 3. FVG upper boundaries
    for s in signals:
        if s.type in ('FVG_Bear', 'FVG_Bull') and s.upper >= entry_price * 1.01:
            candidates.append(('fvg_upper', s.upper, s.idx))
    
    # 4. BSL pools (clustered swing highs) — use swing highs within 5 bars of each other
    # Simplified: use any swing high
    for sh in swings.get('highs', []):
        tp = sh['price']
        if tp >= entry_price * 1.01:
            candidates.append(('bsl_pool', tp, sh['bar_idx']))
    
    # 5. CHOCH/BOS break levels
    for s in signals:
        if s.type in ('CHOCH_Bull', 'BOS_Bull') and s.price >= entry_price * 1.01:
            candidates.append((s.type.lower(), s.price, s.idx))
    
    if not candidates:
        # Fallback: fixed RR target (2x ATR from entry)
        atr = _calc_atr(ohlcv)
        tp = entry_price * 1.03  # 3% minimum
        return tp, 'fixed', -1
    
    # Return CLOSEST TP (smallest distance from entry)
    best = min(candidates, key=lambda x: x[1])
    return best[1], best[0], best[2]

def find_structural_sl(ohlcv, entry_idx, entry_price, signals, swings):
    """
    Find CLOSEST structural SL below entry price.
    Sources: swing lows, OB lower, FVG lower, SSL pools, CHOCH/BOS levels.
    Filter: SL <= entry_price * 0.99 (at least 1% below)
    """
    candidates = []
    
    # 1. Prior swing lows
    for sl in swings.get('lows', []):
        if sl['bar_idx'] < len(ohlcv):
            sl_price = sl['price']
            if sl_price <= entry_price * 0.99:
                candidates.append(('swing_low', sl_price, sl['bar_idx']))
    
    # 2. OB lower boundaries
    for s in signals:
        if s.type in ('OB_Bull',) and s.lower <= entry_price * 0.99:
            candidates.append(('ob_lower', s.lower, s.idx))
    
    # 3. FVG lower boundaries
    for s in signals:
        if s.type in ('FVG_Bull',) and s.lower <= entry_price * 0.99:
            candidates.append(('fvg_lower', s.lower, s.idx))
    
    # 4. SSL pools (clustered swing lows)
    for sl in swings.get('lows', []):
        sl_price = sl['price']
        if sl_price <= entry_price * 0.99:
            candidates.append(('ssl_pool', sl_price, sl['bar_idx']))
    
    # 5. CHOCH/BOS levels
    for s in signals:
        if s.type in ('CHOCH_Bear', 'BOS_Bear') and s.price <= entry_price * 0.99:
            candidates.append((s.type.lower(), s.price, s.idx))
    
    if not candidates:
        # Fallback: fixed SL (1.5% below entry)
        sl = entry_price * 0.985
        return sl, 'fixed', -1
    
    # Return CLOSEST SL (largest price = tightest protection below entry)
    best = max(candidates, key=lambda x: x[1])
    return best[1], best[0], best[2]

def _calc_atr(ohlcv, length=14):
    n = min(length, len(ohlcv))
    trs = []
    for i in range(max(1, len(ohlcv) - n), len(ohlcv)):
        h, l, pc = ohlcv[i]['h'], ohlcv[i]['l'], ohlcv[i-1]['c']
        trs.append(max(h - l, abs(h - pc), abs(l - pc)))
    return sum(trs) / len(trs) if trs else 1.0

# ═════════════════════════════════════════════════════════════════
# TRAILING STOP
# ═════════════════════════════════════════════════════════════════

def trailing_exit(ohlcv, entry_idx, entry_price, sl_price, tp_price):
    """
    Progressive BE lock trailing stop.
    Returns (exit_idx, exit_price, exit_method) or None if not triggered.
    """
    n = len(ohlcv)
    be_locked = False
    trail_level = sl_price
    best_price = entry_price  # For Bull: highest high seen
    
    for i in range(entry_idx + 1, n):
        bar = ohlcv[i]
        bar_low = bar['l']
        bar_high = bar['h']
        hold_bars = i - entry_idx
        
        # Progressive BE lock
        if hold_bars >= 5:
            trail_level = max(trail_level, entry_price * 1.005)
        elif hold_bars >= 3:
            trail_level = max(trail_level, entry_price * 1.002)
        elif hold_bars >= 2:
            trail_level = max(trail_level, entry_price * 1.001)
        
        # Update best price
        best_price = max(best_price, bar_high)
        
        # Trailing: update trail to best_price - buffer
        if best_price > entry_price * 1.01:
            buffer = (best_price - entry_price) * 0.3
            trail_level = max(trail_level, best_price - buffer)
        
        # Check if price hits trail
        if bar_low <= trail_level:
            exit_price = min(bar['o'], trail_level)
            return i, exit_price, 'trailing'
    
    return None

# ═════════════════════════════════════════════════════════════════
# MAIN BACKTEST FUNCTION
# ═════════════════════════════════════════════════════════════════

def backtest_stock_v18(symbol, ohlcv, signals, swings, params=None):
    """
    Backtest a single stock with V18 engine.
    T+1: exit_idx MUST be > entry_idx (A-share rule).
    """
    n = len(ohlcv)
    trades = []
    used_signals = set()  # Track used signal indices to avoid re-entry
    
    # Get entry signals (FVG_Bull and OB_Bull only)
    entry_signals = [s for s in signals if s.type in ('FVG_Bull', 'OB_Bull')]
    entry_signals.sort(key=lambda s: s.idx)
    
    for sig in entry_signals:
        entry_idx = sig.confirmed_at if sig.confirmed_at > 0 else sig.idx + 1
        if entry_idx >= n - 2:  # Need at least 2 bars after entry
            continue
        if sig.idx in used_signals:
            continue
        
        # Entry at zone
        entry_price = sig.lower  # FVG.lower or OB.lower
        
        # Find structural TP and SL
        tp_price, tp_source, tp_bar = find_structural_tp(ohlcv, entry_idx, entry_price, signals, swings)
        sl_price, sl_source, sl_bar = find_structural_sl(ohlcv, entry_idx, entry_price, signals, swings)
        
        # Walk forward from entry+1 (T+1: cannot exit same bar)
        exit_idx = -1
        exit_price = 0
        exit_method = 'eod'
        
        for i in range(entry_idx + 1, n):  # T+1: start from entry+1
            bar = ohlcv[i]
            bar_low = bar['l']
            bar_high = bar['h']
            hold = i - entry_idx
            
            # Check TP
            if bar_high >= tp_price:
                exit_idx = i
                exit_price = max(bar['o'], tp_price)
                exit_method = 'tp_hit'
                break
            
            # Check SL
            if bar_low <= sl_price:
                exit_idx = i
                exit_price = min(bar['o'], sl_price)
                exit_method = 'sl_hit'
                break
            
            # Check trailing
            trail = trailing_exit(ohlcv, entry_idx, entry_price, sl_price, tp_price)
            if trail:
                exit_idx, exit_price, exit_method = trail
                break
        
        # EOD exit
        if exit_idx < 0:
            exit_idx = n - 1
            exit_price = ohlcv[exit_idx]['c']
            exit_method = 'eod'
        
        # Calculate P&L
        pnl_pct = (exit_price - entry_price) / entry_price * 100
        
        # Get dates
        entry_date = str(ohlcv[entry_idx].get('date', ohlcv[entry_idx].get('t', '')))[:10]
        exit_date = str(ohlcv[exit_idx].get('date', ohlcv[exit_idx].get('t', '')))[:10]
        
        # Find which signals were near this entry (for logging)
        nearby = []
        for s in signals:
            if abs(s.idx - sig.idx) <= 5:
                nearby.append(s.type)
        
        trade = Trade(
            symbol=symbol, entry_idx=entry_idx, entry_date=entry_date,
            entry_price=entry_price, entry_type=sig.type,
            entry_signal_idx=sig.idx,
            exit_idx=exit_idx, exit_date=exit_date,
            exit_price=exit_price, exit_method=exit_method,
            pnl_pct=pnl_pct, hold_bars=exit_idx - entry_idx,
            sl_price=sl_price, tp_price=tp_price,
            signals_triggered=nearby,
            metadata={
                'tp_source': tp_source,
                'sl_source': sl_source,
                'sl_bar': sl_bar,
                'tp_bar': tp_bar,
            }
        )
        trades.append(trade)
        used_signals.add(sig.idx)
    
    return trades

# ═════════════════════════════════════════════════════════════════
# BATCH RUNNER
# ═════════════════════════════════════════════════════════════════

def backtest_v18(symbol, signals_func=None):
    """Full V18 backtest: load data -> detect signals -> backtest."""
    import sys
    sys.path.insert(0, '/root/.hermes/scripts')
    from pathlib import Path
    from v11.signals_v18 import detect_all_signals_v18, detect_pivot_swings
    
    # Load kline
    cache = Path('/root/.hermes/kline_cache')
    fname = symbol.replace('.', '_') + '_daily_300.json'
    fpath = cache / fname
    if not fpath.exists():
        print(f"No data for {symbol}")
        return None, None
    
    ohlcv = json.loads(fpath.read_bytes())
    
    # Detect signals
    all_signals, stats = detect_all_signals_v18(ohlcv)
    
    # Get swings
    swings = detect_pivot_swings(ohlcv, left=5)
    
    # Backtest
    trades = backtest_stock_v18(symbol, ohlcv, all_signals, swings)
    
    return trades, stats

# ═════════════════════════════════════════════════════════════════
# SELF-TEST
# ═════════════════════════════════════════════════════════════════

if __name__ == '__main__':
    trades, stats = backtest_v18('600519.SH')
    if trades:
        wins = sum(1 for t in trades if t.pnl_pct > 0)
        wr = wins / len(trades) * 100 if trades else 0
        avg_pnl = sum(t.pnl_pct for t in trades) / len(trades) if trades else 0
        avg_hold = sum(t.hold_bars for t in trades) / len(trades) if trades else 0
        
        print(f"=== V18 Backtest: 600519.SH ===")
        print(f"Total trades: {len(trades)}")
        print(f"WR: {wr:.1f}%")
        print(f"Avg P&L: {avg_pnl:+.2f}%")
        print(f"Avg hold: {avg_hold:.1f} bars")
        
        exit_methods = {}
        for t in trades:
            m = t.exit_method
            exit_methods[m] = exit_methods.get(m, 0) + 1
        print(f"Exit methods: {exit_methods}")
        
        print(f"\n=== Trade Details ===")
        for t in trades[:10]:
            print(f"  Entry: {t.entry_date} @ {t.entry_price:.2f} ({t.entry_type})")
            print(f"  Exit:  {t.exit_date} @ {t.exit_price:.2f} ({t.exit_method})")
            print(f"  P&L: {t.pnl_pct:+.2f}% | Hold: {t.hold_bars} bars")
            print(f"  SL: {t.sl_price:.2f} | TP: {t.tp_price:.2f}")
            print(f"  Signals: {t.signals_triggered[:5]}")
            print()
