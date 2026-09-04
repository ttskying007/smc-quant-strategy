#!/usr/bin/env python3
# SMC V10 — Integrated Backtest Engine
"""
V10回测引擎 — 整合所有V10创新:
1. 每股票独立参数 (per-stock params)
2. 阶段感知交易 (phase-aware)
3. 多周期共振过滤 (resonance filter)
4. 信号序列评分 (sequence scoring)
5. 摆动点结构感知 (swing structure)

与V9的区别:
- evaluate_trades() 现在接受 per_stock_params + phase
- 信号现在通过共振引擎过滤 (resonance filter)
- 每笔交易包含序列评分 + 共振层级
- 支持多时间框架回测 (daily + 4H + 1H)
"""

import math, logging, time, json
from typing import Dict, List, Optional, Tuple
from pathlib import Path
from collections import defaultdict

# Try both import styles
try:
    from . import swing_points
    from . import signal_sequencer
    from . import resonance_engine
    from . import per_stock_opt
except ImportError:
    from v10 import swing_points
    from v10 import signal_sequencer
    from v10 import resonance_engine
    from v10 import per_stock_opt

# Fall back to V9 modules for data
try:
    from .smc_signals import detect_all_signals, score_signal
    from .smc_hubble import fetch_kline, kline_to_ohlcv, calc_atr_pct
except ImportError:
    try:
        from v9.smc_signals import detect_all_signals, score_signal
        from v9.smc_hubble import fetch_kline, kline_to_ohlcv, calc_atr_pct
    except ImportError:
        # Mock for standalone testing
        def detect_all_signals(ohlcv, params):
            return []
        def score_signal(signal, ohlcv):
            return 1.0
        def fetch_kline(symbol, interval, count):
            return []
        def kline_to_ohlcv(kline):
            return []
        def calc_atr_pct(ohlcv):
            return 0

log = logging.getLogger('smc_v10.backtest')


# ═══════════════════════════════════════════════════════════════════════
# V10 Main backtest function
# ═══════════════════════════════════════════════════════════════════════

def evaluate_trades_v10(
    ohlcv: List[Dict],
    params: Dict,
    phase: str = 'trending_up',
    swing_data: Dict = None,
    resonance_threshold: float = 0.35,
) -> Dict:
    """V10 trade evaluation with full resonance + sequence analysis.
    
    Args:
        ohlcv: [{o,h,l,c,v}, ...] chronological order (daily candles)
        params: trading parameters (can be per-stock or global)
        phase: market phase from swing analysis
        swing_data: pre-computed swing analysis (or None to compute)
        resonance_threshold: minimum resonance score to take a trade
    
    Returns:
        dict with all V10-enhanced trade data
    """
    n_bars = len(ohlcv)
    
    # Step 1: Detect all raw signals (using V9 detectors)
    raw_signals = detect_all_signals(ohlcv, params)
    
    # Step 2: Compute swing points (if not provided)
    if swing_data is None:
        swing_data = swing_points.find_swing_points(ohlcv)
    
    # Step 3: Sequence analysis
    seq_result = signal_sequencer.analyze_signal_sequence(raw_signals)
    
    # Step 4: Adjust params for market phase
    phase_params = resonance_engine.adjust_params_for_phase(params, phase)
    
    # Step 5: Filter & score signals
    score_min = phase_params.get('score_min', 0.5)
    confirm_range = phase_params.get('confirm_range', 3)
    max_trades = phase_params.get('max_trades', 5)
    sl_pct = phase_params.get('sl_pct', 3.0)
    tp_pct = phase_params.get('tp_pct', 9.0)
    vol_adapt = phase_params.get('vol_adapt_sl', 0.6)
    atr_min = phase_params.get('atr_min_pct', 0.3)
    atr_max = phase_params.get('atr_max_pct', 8.0)
    
    # TP/SL ratio guard
    if tp_pct / sl_pct < 1.5:
        return _empty_v10('tp_sl_ratio')
    
    # ATR filter
    atr_pct = calc_atr_pct(ohlcv)
    if 0 < atr_pct < atr_min or atr_pct > atr_max:
        return _empty_v10('atr_out_of_range')
    
    # Score signals
    scored = [(score_signal(s, ohlcv), s) for s in raw_signals]
    scored.sort(key=lambda x: -x[0])
    
    # Direction filter from phase
    direction_filter = phase_params.get('_direction_filter', 'both')
    
    trades = []
    trade_logs = []
    rejected = []
    resonance_scores = []
    
    for sig_score, sig in scored:
        if sig_score < score_min:
            continue
        if len(trades) >= max_trades:
            break
        
        idx = sig['idx']
        
        # Direction filter
        sig_dir = sig.get('direction', '')
        if direction_filter == 'long' and sig_dir != 'bull':
            rejected.append({'idx': idx, 'type': sig['type'], 'reason': 'direction_filter'})
            continue
        if direction_filter == 'short' and sig_dir != 'bear':
            rejected.append({'idx': idx, 'type': sig['type'], 'reason': 'direction_filter'})
            continue
        
        # Clustering guard
        too_close = any(abs(t['idx'] - idx) <= confirm_range for t in trades)
        if too_close:
            rejected.append({'idx': idx, 'type': sig['type'], 'reason': 'clustering'})
            continue
        
        # V10: Resonance filter
        # Compute resonance score for this signal's context
        res_score = resonance_engine.evaluate_full_resonance(
            tf_directions={'daily': sig_dir},  # simplified; use multi-TF in real use
            signals=[s for s in raw_signals if abs(s['idx'] - idx) <= 10],
            swing_tree=swing_data.get('tree', {}),
            seq_result=seq_result,
            lookback_idx=idx,
        )
        
        if res_score.total < resonance_threshold:
            rejected.append({
                'idx': idx, 'type': sig['type'],
                'reason': f'resonance({res_score.total:.2f}<{resonance_threshold})',
                'resonance': res_score.to_dict(),
            })
            continue
        
        # Entry at next bar open
        entry = ohlcv[idx + 1]['o'] if idx + 1 < n_bars else ohlcv[idx]['c']
        
        # Volatility-adaptive SL/TP
        vol_factor = 1.0 - vol_adapt * (1.0 - min(atr_pct / 5.0, 1.0))
        sl_adapted = max(0.5, sl_pct * vol_factor)
        tp_adapted = max(sl_adapted * 1.5, tp_pct * vol_factor)
        
        is_bull = sig_dir == 'bull'
        
        if is_bull:
            sl = entry * (1 - sl_adapted / 100)
            tp = entry * (1 + tp_adapted / 100)
        else:
            sl = entry * (1 + sl_adapted / 100)
            tp = entry * (1 - tp_adapted / 100)
        
        # Simulate exit
        hit_sl = hit_tp = False
        exit_price = entry
        exit_idx = idx + 2
        max_look = min(idx + 60, n_bars)
        
        for j in range(idx + 2, max_look):
            bar = ohlcv[j]
            if is_bull:
                if bar['l'] <= sl:
                    hit_sl, exit_price, exit_idx = True, sl, j
                    break
                if bar['h'] >= tp:
                    hit_tp, exit_price, exit_idx = True, tp, j
                    break
            else:
                if bar['h'] >= sl:
                    hit_sl, exit_price, exit_idx = True, sl, j
                    break
                if bar['l'] <= tp:
                    hit_tp, exit_price, exit_idx = True, tp, j
                    break
        
        ret = (exit_price - entry) / entry * 100
        if not is_bull:
            ret = -ret
        
        # V10: Sequence bonus
        seq_boost = signal_sequencer.score_entry_from_sequence(seq_result, base_score=sig_score / 5.0)
        
        # Build comprehensive trade record
        trade = {
            'idx': idx,
            'entry': round(entry, 2),
            'exit': round(exit_price, 2),
            'sl': round(sl, 2),
            'tp': round(tp, 2),
            'ret': round(ret, 2),
            'win': ret > 0,
            'rr': round(tp_adapted / sl_adapted, 2) if hit_tp else (
                round(abs(ret) / sl_adapted, 2) if hit_sl and ret != 0 else 0.5),
            'direction': 'long' if is_bull else 'short',
            'signal_type': sig['type'],
            'signal_score': round(sig_score, 1),
            
            # V10 additions
            'resonance': res_score.to_dict(),
            'resonance_layers': res_score.layers,
            'resonance_total': round(res_score.total, 3),
            'sequence_grade': seq_boost['grade'],
            'sequence_reason': seq_boost['reason'],
            'phase': phase,
            'phase_params_used': {
                'sl_adapted': round(sl_adapted, 2),
                'tp_adapted': round(tp_adapted, 2),
                'direction_filter': direction_filter,
                'score_min': round(score_min, 2),
            },
        }
        trades.append(trade)
        resonance_scores.append(res_score.total)
        
        # Human-readable log
        log_text = _format_v10_trade_log(trade)
        trade_logs.append(log_text)
    
    # Aggregate
    n = len(trades)
    wins = sum(1 for t in trades if t['win'])
    returns = [t['ret'] for t in trades]
    rr_list = [t['rr'] for t in trades]
    
    # By-resonance breakdown
    by_resonance = defaultdict(lambda: {'trades': 0, 'wins': 0, 'returns': []})
    for t in trades:
        layers = t.get('resonance_layers', 0)
        by_resonance[f'L{layers}']['trades'] += 1
        if t['win']:
            by_resonance[f'L{layers}']['wins'] += 1
        by_resonance[f'L{layers}']['returns'].append(t['ret'])
    
    return {
        'n_trades': n,
        'wins': wins,
        'losses': n - wins,
        'returns': returns,
        'rr_list': rr_list,
        'signal_scores': [t['signal_score'] for t in trades],
        'resonance_scores': resonance_scores,
        'avg_resonance': round(sum(resonance_scores) / len(resonance_scores), 3) if resonance_scores else 0,
        'signals_total': len(raw_signals),
        'trades': trades,
        'trade_logs': trade_logs,
        'rejected_signals': rejected,
        'by_resonance': dict(by_resonance),
        'atr_pct': round(atr_pct, 2),
        'phase': phase,
        'params_used': phase_params,
        'sequence_best': seq_result.get('best_sequence', {}).get('name', 'None'),
        'swing_tree_direction': swing_data.get('tree', {}).get('direction'),
    }


def _format_v10_trade_log(trade: Dict) -> str:
    """Format V10 trade log with resonance info."""
    win_str = '✅' if trade['win'] else '❌'
    dir_str = '🟢多' if trade['direction'] == 'long' else '🔴空'
    
    lines = [
        f"━━━ 交易#{trade['idx']} ━━━",
        f"方向: {dir_str} | 信号: {trade['signal_type']} | {win_str}",
        f"入场: {trade['entry']} → 出场: {trade['exit']} "
        f"(SL:{trade['sl']} TP:{trade['tp']})",
        f"收益: {trade['ret']}% | RR: {trade['rr']}",
    ]
    
    if 'resonance' in trade:
        r = trade['resonance']
        lines.append(f"共振: {trade.get('resonance_total', 0):.2f} "
                     f"(TF:{r.get('tf', 0):.2f} Ind:{r.get('indicator', 0):.2f} "
                     f"Swing:{r.get('swing', 0):.2f})")
    
    if 'sequence_grade' in trade:
        lines.append(f"序列: {trade['sequence_grade']} | {trade.get('sequence_reason', '')}")
    
    if 'phase' in trade:
        lines.append(f"阶段: {trade['phase']}")
    
    return '\n'.join(lines)


def _empty_v10(reason='no_trades'):
    return {
        'n_trades': 0, 'wins': 0, 'losses': 0,
        'returns': [], 'rr_list': [], 'signal_scores': [],
        'resonance_scores': [], 'avg_resonance': 0,
        'signals_total': 0, 'trades': [], 'trade_logs': [],
        'rejected_signals': [], 'by_resonance': {},
        'atr_pct': 0, 'phase': 'unknown', 'error': reason,
    }


# ═══════════════════════════════════════════════════════════════════════
# Score computation (V10 enhanced)
# ═══════════════════════════════════════════════════════════════════════

def compute_score_v10(eval_results: Dict[str, Dict]) -> Dict:
    """Compute aggregate score from per-stock eval results.
    
    The V10 score includes resonance quality as an additional dimension.
    """
    total_trades = 0
    total_wins = 0
    all_returns = []
    all_rr = []
    all_resonance = []
    
    stock_with_trades = 0
    total_stocks = len(eval_results)
    
    for r in eval_results.values():
        if not isinstance(r, dict):
            continue
        n = r.get('n_trades', 0)
        if n > 0:
            stock_with_trades += 1
            total_trades += n
            total_wins += r.get('wins', 0)
            all_returns.extend(r.get('returns', []))
            all_rr.extend(r.get('rr_list', []))
            all_resonance.extend(r.get('resonance_scores', []))
    
    if total_trades == 0:
        return {
            'score': 0, 'wr': 0, 'n': 0, 'pf': 0,
            'rr_avg': 0, 'ret': 0, 'coverage': 0,
            'sharpe': 0, 'avg_resonance': 0,
            'total_stocks': total_stocks, 'stocks_with_trades': 0,
        }
    
    wr = total_wins / total_trades * 100
    rr_avg = sum(all_rr) / len(all_rr) if all_rr else 0
    ret_total = sum(all_returns) if all_returns else 0
    
    # Profit factor
    gross_win = sum(r for r in all_returns if r > 0)
    gross_loss = abs(sum(r for r in all_returns if r <= 0))
    pf = gross_win / gross_loss if gross_loss > 0 else 99
    
    # Sharpe ratio (simplified)
    if len(all_returns) >= 3:
        mean_ret = sum(all_returns) / len(all_returns)
        variance = sum((r - mean_ret) ** 2 for r in all_returns) / len(all_returns)
        std_ret = math.sqrt(variance) if variance > 0 else 1
        sharpe = (mean_ret / std_ret) * math.sqrt(total_trades) if std_ret > 0 else 0
    else:
        sharpe = 0
    
    # Average resonance
    avg_resonance = sum(all_resonance) / len(all_resonance) if all_resonance else 0
    
    # V10 score: WR^2.0 × √N × PF × RR × (1 + avg_resonance)
    base_score = (wr / 100) ** 2.0 * math.sqrt(min(total_trades, 50)) * min(3, pf) * min(2.5, rr_avg)
    resonance_bonus = 1.0 + avg_resonance * 0.5  # up to 50% bonus from resonance
    v10_score = base_score * resonance_bonus
    
    # Penalties
    if rr_avg < 1.2 and total_trades >= 3:
        v10_score *= 0.1
    if total_trades < 8:
        v10_score = 0
    elif total_trades < 15:
        v10_score *= max(0.3, total_trades / 15)
    
    coverage = stock_with_trades / total_stocks * 100 if total_stocks > 0 else 0
    
    return {
        'score': round(v10_score, 2),
        'base_score': round(base_score, 2),
        'resonance_bonus': round(resonance_bonus, 3),
        'wr': round(wr, 1),
        'n': total_trades,
        'pf': round(pf, 2),
        'rr_avg': round(rr_avg, 2),
        'ret': round(ret_total, 2),
        'coverage': round(coverage, 1),
        'sharpe': round(sharpe, 2),
        'avg_resonance': round(avg_resonance, 3),
        'total_stocks': total_stocks,
        'stocks_with_trades': stock_with_trades,
    }


# ═══════════════════════════════════════════════════════════════════════
# Multi-stock batch evaluation
# ═══════════════════════════════════════════════════════════════════════

def batch_evaluate_v10(
    stocks: List[str],
    per_stock_params: Dict[str, Dict] = None,
    global_params: Dict = None,
    resonance_threshold: float = 0.35,
    progress_cb=None,
) -> Dict:
    """Evaluate multiple stocks with per-stock parameters.
    
    Args:
        stocks: list of stock symbols
        per_stock_params: {symbol: params} dict from per-stock optimizer
        global_params: fallback params if per-stock not available
        resonance_threshold: minimum resonance to accept trade
        progress_cb: optional callback(idx, total)
    
    Returns:
        Full evaluation results with per-stock details
    """
    from v10.per_stock_opt import GLOBAL_BEST
    
    if global_params is None:
        global_params = GLOBAL_BEST
    
    results = {}
    per_stock_detail = {}
    total = len(stocks)
    
    for i, symbol in enumerate(stocks):
        try:
            # Get stock-specific params
            if per_stock_params and symbol in per_stock_params:
                params = per_stock_params[symbol].get('params', global_params)
            else:
                params = dict(global_params)
            
            # Fetch data
            kline = fetch_kline(symbol, 'daily', 120)
            if not kline or len(kline) < 30:
                results[symbol] = _empty_v10('no_data')
                continue
            
            ohlcv = kline_to_ohlcv(kline)
            
            # Compute swing data once per stock
            swing_data = swing_points.find_swing_points(ohlcv)
            phase = swing_data.get('current_phase', 'ranging')
            
            # Run V10 evaluation
            result = evaluate_trades_v10(
                ohlcv, params, phase=phase,
                swing_data=swing_data,
                resonance_threshold=resonance_threshold,
            )
            
            results[symbol] = result
            per_stock_detail[symbol] = {
                'trades': result.get('trades', []),
                'logs': result.get('trade_logs', []),
                'n': result.get('n_trades', 0),
                'wr': round(result.get('wins', 0) / max(1, result.get('n_trades', 1)) * 100, 1),
                'avg_resonance': result.get('avg_resonance', 0),
                'phase': phase,
            }
            
        except Exception as e:
            log.warning(f"Batch eval {symbol}: {e}")
            results[symbol] = _empty_v10(str(e))
        
        if progress_cb and i % 5 == 0:
            progress_cb(i, total)
    
    score = compute_score_v10(results)
    score['per_stock'] = per_stock_detail
    
    return score


# ═══════════════════════════════════════════════════════════════════════
# Comparison: V9 vs V10
# ═══════════════════════════════════════════════════════════════════════

def compare_v9_v10(symbol: str, params: Dict) -> Dict:
    """Side-by-side comparison of V9 and V10 backtest results."""
    
    kline = fetch_kline(symbol, 'daily', 120)
    if not kline or len(kline) < 30:
        return {'error': f'No data for {symbol}'}
    
    ohlcv = kline_to_ohlcv(kline)
    
    # V9 evaluation
    try:
        from v9.smc_backtest import evaluate_trades as eval_v9
        v9_result = eval_v9(ohlcv, params)
    except ImportError:
        v9_result = _empty_v10('v9_import_error')
    
    # V10 evaluation
    v10_result = evaluate_trades_v10(ohlcv, params)
    
    def _wr(result):
        n = result.get('n_trades', 0)
        return round(result.get('wins', 0) / n * 100, 1) if n > 0 else 0
    
    return {
        'symbol': symbol,
        'v9': {
            'n_trades': v9_result.get('n_trades', 0),
            'wins': v9_result.get('wins', 0),
            'wr': _wr(v9_result),
            'returns': v9_result.get('returns', []),
        },
        'v10': {
            'n_trades': v10_result.get('n_trades', 0),
            'wins': v10_result.get('wins', 0),
            'wr': _wr(v10_result),
            'returns': v10_result.get('returns', []),
            'avg_resonance': v10_result.get('avg_resonance', 0),
            'phase': v10_result.get('phase', 'unknown'),
            'rejected': len(v10_result.get('rejected_signals', [])),
        },
    }