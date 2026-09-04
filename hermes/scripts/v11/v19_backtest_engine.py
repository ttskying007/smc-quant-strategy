#!/usr/bin/env python3
"""
V19 Backtest Engine — T+1 强制 + 多源结构TP/SL + 详细交易日志
"""
import json, math
from typing import List, Dict, Tuple
from dataclasses import dataclass, field

@dataclass
class TradeV19:
    symbol: str; entry_idx: int; entry_date: str; entry_price: float
    entry_type: str; entry_signal_bar: int
    exit_idx: int; exit_date: str; exit_price: float; exit_method: str
    pnl_pct: float; hold_bars: int
    sl_price: float; sl_source: str
    tp_price: float; tp_source: str
    nearby_signals: List[str] = field(default_factory=list)
    
    def to_dict(self):
        return {k: (round(v,2) if isinstance(v,float) else v) for k,v in self.__dict__.items()}

def _atr(ohlcv, length=14):
    n = min(length, len(ohlcv))
    return sum(max(ohlcv[i]['h']-ohlcv[i]['l'], abs(ohlcv[i]['h']-ohlcv[i-1]['c']), abs(ohlcv[i]['l']-ohlcv[i-1]['c'])) for i in range(len(ohlcv)-n,len(ohlcv)))/n if n>0 else 1

def find_tps(entry_price, signals, swings_dict, ohlcv):
    """
    Multi-source TP: scan ALL resistance points ABOVE entry
    - HH swing highs, OB upper, FVG upper, CHOCH/BOS levels
    - Must be >= entry * 1.015 (at least 1.5% above for meaningful RR)
    """
    candidates = []
    for sh in swings_dict.get('highs', []):
        tp = sh['price']
        if tp >= entry_price * 1.015:
            candidates.append((tp, 'HH_swing', sh['bar_idx']))
    for s in signals:
        if s.type in ('OB_Bear',) and s.upper >= entry_price * 1.015:
            candidates.append((s.upper, 'OB_upper', s.idx))
        if s.type in ('FVG_Bear','FVG_Bull') and s.upper >= entry_price * 1.015:
            candidates.append((s.upper, 'FVG_upper', s.idx))
        if s.type in ('CHOCH_Bull','BOS_Bull') and s.price >= entry_price * 1.015:
            candidates.append((s.price, s.type, s.idx))
    if not candidates:
        return entry_price * 1.04, 'fallback_4pct', -1
    # Return CLOSEST valid TP
    return min(candidates, key=lambda x: x[0])

def find_sls(entry_price, signals, swings_dict, ohlcv):
    """
    Multi-source SL: scan ALL support points BELOW entry
    - LL swing lows, OB lower, FVG lower, CHOCH/BOS levels
    - Must be <= entry * 0.985 (at least 1.5% below for meaningful SL)
    """
    candidates = []
    for sl in swings_dict.get('lows', []):
        sl_price = sl['price']
        if sl_price <= entry_price * 0.985:
            candidates.append((sl_price, 'LL_swing', sl['bar_idx']))
    for s in signals:
        if s.type in ('OB_Bull',) and s.lower <= entry_price * 0.985:
            candidates.append((s.lower, 'OB_lower', s.idx))
        if s.type in ('FVG_Bull',) and s.lower <= entry_price * 0.985:
            candidates.append((s.lower, 'FVG_lower', s.idx))
        if s.type in ('CHOCH_Bear','BOS_Bear') and s.price <= entry_price * 0.985:
            candidates.append((s.price, s.type, s.idx))
    if not candidates:
        return entry_price * 0.96, 'fallback_4pct', -1
    # CLOSEST SL = highest price below entry
    return max(candidates, key=lambda x: x[0])

def backtest_v19(symbol, ohlcv, all_signals, swings_dict, sequences=None):
    """V19 backtest with T+1 enforcement + multi-source TP/SL.
    
    Args:
        sequences: list of sequence dicts from detect_signal_sequences.
                   If provided, ONLY trade entries that are terminal signals of a sequence.
    """
    n = len(ohlcv)
    trades = []
    
    # Build sequence entry filter
    sequence_entry_bars = set()
    if sequences:
        for sq in sequences:
            if sq.get('has_entry'):
                last_sig = sq['signals'][-1]
                sequence_entry_bars.add(last_sig['bar'])
    
    # Entry signals: FVG_Bull and OB_Bull only
    entries = [s for s in all_signals if s.type in ('FVG_Bull', 'OB_Bull')]
    entries.sort(key=lambda s: s.idx)
    
    # Apply sequence filter
    if sequences is not None:
        unfiltered = len(entries)
        entries = [s for s in entries if s.idx in sequence_entry_bars]
        if not entries:
            return trades, {'unfiltered_entries': unfiltered, 'filtered_entries': 0, 'sequences_found': len(sequences)}
    
    used_bars = set()  # T+1: can't enter on same bar as previous exit
    entered_ob_bars = set()  # OB dedup: one entry per OB bar
    
    for sig in entries:
        entry_idx = sig.confirmed_at if sig.confirmed_at > 0 else sig.idx + 1
        if entry_idx >= n - 2: continue
        if entry_idx in used_bars: continue
        if sig.type == 'OB_Bull' and entry_idx in entered_ob_bars:
            continue  # OB dedup
        
        # Use actual market price at entry bar (zone price may be stale)
        entry_price = max(sig.lower, ohlcv[entry_idx]['o'])
        
        tp_price, tp_source, tp_bar = find_tps(entry_price, all_signals, swings_dict, ohlcv)
        sl_price, sl_source, sl_bar = find_sls(entry_price, all_signals, swings_dict, ohlcv)
        
        # MAX_TP cap: TP never exceeds 5% above entry
        max_tp = entry_price * 1.05
        if tp_price > max_tp:
            tp_price = max_tp
            tp_source = 'capped_5pct'
        
        # MIN_PROJECTED_RR: TP distance >= SL distance
        tp_dist = (tp_price - entry_price) / entry_price * 100
        sl_dist = (entry_price - sl_price) / entry_price * 100
        if sl_dist > 0 and tp_dist / sl_dist < 1.0:
            continue
        
        # Walk forward: T+1 enforced
        exit_idx = -1; exit_price = 0; exit_method = 'eod'
        
        for i in range(entry_idx + 1, n):  # T+1: start checking from NEXT bar
            bar = ohlcv[i]
            
            if bar['h'] >= tp_price:
                exit_idx = i; exit_price = tp_price
                exit_method = 'tp_hit'; break
            
            if bar['l'] <= sl_price:
                exit_idx = i; exit_price = sl_price
                exit_method = 'sl_hit'; break
        
        # EOD exit
        if exit_idx < 0:
            exit_idx = n - 1
            exit_price = ohlcv[exit_idx]['c']
            exit_method = 'eod'
        
        # T+1 assertion: exit MUST be strictly after entry
        assert exit_idx > entry_idx, f"T+1 VIOLATION: entry={entry_idx} exit={exit_idx}"
        
        pnl = (exit_price - entry_price) / entry_price * 100
        entry_date = str(ohlcv[entry_idx].get('date', ohlcv[entry_idx].get('t','')))[:10]
        exit_date = str(ohlcv[exit_idx].get('date', ohlcv[exit_idx].get('t','')))[:10]
        
        nearby = [s.type for s in all_signals if abs(s.idx - sig.idx) <= 5][:5]
        
        trades.append(TradeV19(
            symbol=symbol, entry_idx=entry_idx, entry_date=entry_date,
            entry_price=entry_price, entry_type=sig.type, entry_signal_bar=sig.idx,
            exit_idx=exit_idx, exit_date=exit_date, exit_price=exit_price,
            exit_method=exit_method, pnl_pct=pnl,
            hold_bars=exit_idx-entry_idx,
            sl_price=sl_price, sl_source=sl_source,
            tp_price=tp_price, tp_source=tp_source,
            nearby_signals=nearby
        ))
        used_bars.add(exit_idx)
        if sig.type == 'OB_Bull':
            entered_ob_bars.add(entry_idx)
    
    if sequences is not None:
        return trades, {'unfiltered_entries': unfiltered, 'filtered_entries': len(trades), 'sequences_found': len(sequences)}
    return trades

# ════════════════════════════════════════════
# Self-test
# ════════════════════════════════════════════

if __name__ == '__main__':
    import sys
    sys.path.insert(0, '/root/.hermes/scripts')
    from pathlib import Path
    from v11.signals_v19 import detect_all_signals_v19
    
    fpath = Path('/root/.hermes/kline_cache/600519_SH_daily_300.json')
    ohlcv = json.loads(fpath.read_bytes())
    signals, stats, swings, swings_dict = detect_all_signals_v19(ohlcv)
    trades = backtest_v19('600519.SH', ohlcv, signals, swings_dict)
    
    if trades:
        wins = sum(1 for t in trades if t.pnl_pct > 0)
        wr = wins/len(trades)*100
        avg_pnl = sum(t.pnl_pct for t in trades)/len(trades)
        avg_hold = sum(t.hold_bars for t in trades)/len(trades)
        em = {}; [em.update({t.exit_method: em.get(t.exit_method,0)+1}) for t in trades]
        
        print(f"=== V19 Backtest: 600519.SH ===")
        print(f"Trades: {len(trades)} | WR: {wr:.1f}% | P&L: {avg_pnl:+.2f}% | Hold: {avg_hold:.1f}b")
        print(f"Exit: {em}")
        
        print(f"\n=== Trade details (first 10) ===")
        for t in trades[:10]:
            print(f"  {t.entry_date} [{t.entry_type}] in@{t.entry_price:.2f} → {t.exit_date} out@{t.exit_price:.2f} ({t.exit_method})")
            print(f"    P&L: {t.pnl_pct:+.2f}% | Hold: {t.hold_bars}b | SL: {t.sl_price:.2f}[{t.sl_source}] | TP: {t.tp_price:.2f}[{t.tp_source}]")
            print(f"    Signals near entry: {t.nearby_signals}")
        
        # Save
        Path('/root/.hermes/smc_opt_v19').mkdir(exist_ok=True)
        json.dump({
            'symbol': '600519.SH',
            'summary': {'total_trades': len(trades), 'wr': round(wr,1), 'avg_pnl': round(avg_pnl,2), 'avg_hold': round(avg_hold,1), 'exit_methods': {str(k):v for k,v in em.items()}},
            'trades': [t.to_dict() for t in trades],
            'signal_stats': stats['type_counts'],
            'swings': stats['swings'],
        }, open('/root/.hermes/smc_opt_v19/v19_backtest_600519.json','w'), indent=2, ensure_ascii=False)
        print(f"\nSaved to /root/.hermes/smc_opt_v19/v19_backtest_600519.json")
